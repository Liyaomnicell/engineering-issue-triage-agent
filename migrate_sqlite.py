"""Copy the original local SQLite snapshots into PostgreSQL without altering them."""
import json
import sqlite3
import uuid
from pathlib import Path

from psycopg.types.json import Jsonb
from postgres_store import Postgres, copy_records
from triage import ROOT, now


def migrate(root=ROOT, store=None):
    root=Path(root)
    store=store or Postgres()
    if store.metadata('sqlite_import'):
        return {'alreadyImported':True, **store.metadata('sqlite_import')}
    knowledge=root/'.triage'/'knowledge.sqlite'
    investigations=root/'.triage'/'investigations.sqlite'
    if not knowledge.exists() and not investigations.exists():
        raise RuntimeError('No legacy SQLite databases found in .triage')
    generation=uuid.uuid4()
    imported_cases=0
    with store.connection() as db:
        if not db.execute('SELECT pg_try_advisory_xact_lock(87654321) AS locked').fetchone()['locked']:
            raise RuntimeError('Another migration or index build is running')
        if db.execute("SELECT 1 FROM metadata WHERE key='active_generation'").fetchone():
            raise RuntimeError('PostgreSQL already contains an active index. Import into an empty application schema to avoid replacing it.')
        count=0
        if knowledge.exists():
            legacy=sqlite3.connect(knowledge.as_uri()+'?mode=ro',uri=True)
            legacy.row_factory=sqlite3.Row
            try:
                count=copy_records(db,generation,(dict(row) for row in legacy.execute('SELECT * FROM evidence ORDER BY id')))
            finally:
                legacy.close()
            state_path=root/'.triage'/'index-status.json'
            status=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
            status.update(running=False,phase='Ready',ready=True,chunks=count,completed=now(),database='PostgreSQL')
            store.set_metadata(db,'index_status',status)
            store.set_metadata(db,'active_generation',str(generation))
        if investigations.exists():
            legacy=sqlite3.connect(investigations.as_uri()+'?mode=ro',uri=True)
            try:
                for identifier,title,payload,updated in legacy.execute('SELECT id,title,payload,updated FROM investigations'):
                    cursor=db.execute('INSERT INTO investigations(id,title,payload,updated) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',(identifier,title,Jsonb(json.loads(payload)),updated))
                    imported_cases+=cursor.rowcount
            finally:
                legacy.close()
        report={'excerpts':count,'investigations':imported_cases,'completed':now()}
        store.set_metadata(db,'sqlite_import',report)
    return report


if __name__=='__main__':
    print(json.dumps(migrate(),indent=2))
