"""PostgreSQL persistence and full-text retrieval for the diagnostic platform."""
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from triage import ROOT, EXCLUDED, TEXT_EXTENSIONS, KnowledgeBase as LegacyKnowledgeBase, Investigations as LegacyInvestigations, chunks, decode_text, filesystem_path, now, read_csv, safe_id, terms, words


def load_environment(root=ROOT):
    path = Path(root) / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if re.fullmatch(r'[A-Z][A-Z0-9_]*', key.strip()):
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Postgres:
    def __init__(self, dsn=None, schema=None):
        load_environment()
        self.dsn = dsn or os.getenv('DATABASE_URL', '')
        self.schema = schema or os.getenv('TRIAGE_DB_SCHEMA', 'triage')
        if not self.dsn and not os.getenv('PGHOST'):
            raise RuntimeError('DATABASE_URL is required. Configure PostgreSQL in .env; see README.md.')
        if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', self.schema):
            raise ValueError('Invalid PostgreSQL schema name')
        with self.connection() as db:
            db.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
            db.execute((ROOT / 'migrations' / '001_postgresql.sql').read_text(encoding='utf-8'))

    @contextmanager
    def connection(self):
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=8, options=f'-c search_path={self.schema},public') as db:
            yield db

    def metadata(self, key, default=None):
        with self.connection() as db:
            row = db.execute('SELECT value FROM metadata WHERE key=%s', (key,)).fetchone()
        return row['value'] if row else default

    @staticmethod
    def set_metadata(db, key, value):
        db.execute('INSERT INTO metadata(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value', (key, Jsonb(value)))


def collect_evidence(root, repositories, update, error):
    """Yield source snapshots; independent of the storage engine."""
    from pypdf import PdfReader
    root = Path(root)
    sources = {row['File']: row.get('SourceUrl', '') for row in read_csv(root / 'escalations' / 'index.csv')}
    update(phase='Reading Confluence PDFs')
    def records(kind, title, path, text, repo='', branch='', commit='', url='', page=0):
        for start, end, excerpt in chunks(text):
            yield {'kind':kind,'title':title,'path':str(path.relative_to(root)),'start':start,'end':end,'page':page,'repo':repo,'branch':branch,'commit_sha':commit,'url':url,'text':excerpt}
    for pdf in sorted((root / 'escalations').glob('*.pdf')):
        try:
            count = 0
            for page_no, page in enumerate(PdfReader(pdf).pages, 1):
                text = page.extract_text() or ''
                if text.strip():
                    yield from records('confluence',pdf.stem,pdf,text,url=sources.get(pdf.name,''),page=page_no)
                    count += 1
            if not count:
                error(pdf.name,'No extractable text; OCR is not enabled')
        except Exception as exc:
            error(pdf.name,str(exc))
    source_root = root / 'source-colortouch'
    for repo in sorted(source_root.iterdir()) if source_root.exists() else []:
        if not repo.is_dir() or repo.is_symlink() or not (repo / '.git').exists():
            continue
        branch, commit = LegacyKnowledgeBase._git(repo,'branch','--show-current'), LegacyKnowledgeBase._git(repo,'rev-parse','HEAD')
        if not commit:
            error(repo.name,'Could not read Git commit')
            continue
        repositories.append({'name':repo.name,'branch':branch,'commit':commit})
        update(phase='Indexing ' + repo.name)
        walk_root = filesystem_path(repo)
        for directory, dirs, filenames in os.walk(walk_root, followlinks=False):
            dirs[:] = [d for d in dirs if d.lower() not in EXCLUDED and not (Path(directory)/d).is_symlink()]
            for name in filenames:
                path = repo / Path(directory).relative_to(walk_root) / name
                if path.suffix.lower() not in TEXT_EXTENSIONS or name.endswith(('.min.js','.map','.g.cs','.designer.cs')) or name in {'package-lock.json','yarn.lock'}:
                    continue
                try:
                    readable = filesystem_path(path)
                    if readable.is_symlink() or readable.stat().st_size > 512*1024:
                        update(skipped_increment=1)
                        continue
                    text = decode_text(readable.read_bytes())
                    relative = path.relative_to(repo).as_posix()
                    yield from records('code',relative,path,text,repo.name,branch,commit,f'https://bitbucket.org/omnicell/{repo.name}/src/{commit}/{relative}')
                except Exception as exc:
                    error(str(path.relative_to(root)),str(exc))
        if commit != LegacyKnowledgeBase._git(repo,'rev-parse','HEAD'):
            raise RuntimeError(f'{repo.name} changed during indexing; rebuild required')


COPY_SQL = 'COPY evidence(generation,id,kind,title,path,start_line,end_line,page,repo,branch,commit_sha,url,text,title_terms,body_terms) FROM STDIN'


def copy_records(db, generation, records):
    count = 0
    with db.cursor().copy(COPY_SQL) as copy:
        for count, item in enumerate(records, 1):
            copy.write_row((generation,item.get('id',count),item['kind'],item['title'],item['path'],item['start'],item['end'],item['page'],item['repo'],item['branch'],item['commit_sha'],item['url'],item['text'],' '.join(words(item['title'])),' '.join(words(item['text']))))
    return count


class KnowledgeBase:
    def __init__(self, root=ROOT, store=None):
        self.root, self.store = Path(root), store or Postgres()
        self.lock = threading.Lock()
        self.state = None

    def status(self):
        with self.lock:
            state = dict(self.state) if self.state else self.store.metadata('index_status', {'running':False,'phase':'Not indexed','files':0,'chunks':0,'errors':[],'skipped':0})
        state['ready'] = bool(self.store.metadata('active_generation'))
        state['database'] = 'PostgreSQL'
        return state

    def update(self, **values):
        with self.lock:
            if 'skipped_increment' in values:
                self.state['skipped'] += values.pop('skipped_increment')
            self.state.update(values)

    def _error(self, path, error):
        with self.lock:
            if len(self.state['errors']) < 100:
                self.state['errors'].append({'path':path,'error':error[:300]})

    def start_index(self):
        with self.lock:
            if self.state and self.state.get('running'):
                return False
            self.state={'running':True,'phase':'Starting PostgreSQL index','files':0,'chunks':0,'errors':[],'skipped':0,'started':now()}
        threading.Thread(target=self._build,daemon=True).start()
        return True

    def _build(self):
        repositories, seen = [], set()
        generation = uuid.uuid4()
        try:
            with self.store.connection() as db:
                # Session lock spans COPY and atomic metadata publication.
                if not db.execute('SELECT pg_try_advisory_xact_lock(87654321) AS locked').fetchone()['locked']:
                    raise RuntimeError('Another PostgreSQL index build is running')
                def records():
                    for record in collect_evidence(self.root,repositories,self.update,self._error):
                        seen.add(record['path'])
                        with self.lock:
                            self.state['files']=len(seen)
                            self.state['chunks']+=1
                        yield record
                copy_records(db,generation,records())
                self.update(running=False,phase='Ready',completed=now(),repositories=repositories)
                self.store.set_metadata(db,'active_generation',str(generation))
                self.store.set_metadata(db,'index_status',self.state)
                # Prior generations remain available for rollback; never delete source evidence.
        except Exception as exc:
            self._error('index',str(exc))
            self.update(running=False,phase='Index failed; previous PostgreSQL generation retained')
        finally:
            with self.lock:
                self.state['running']=False

    def search(self, query, kind='all', repo='', limit=16):
        tokens=terms(query)
        generation=self.store.metadata('active_generation')
        if not tokens or not generation:
            return []
        query_text=' OR '.join('"'+token+'"' for token in tokens)
        filters, params=['generation=%s','search_vector @@ q.query'],[generation]
        if kind in {'code','confluence'}:
            filters.append('kind=%s');params.append(kind)
        if repo:
            filters.append('repo=%s');params.append(repo)
        with self.store.connection() as db:
            rows=db.execute("WITH q AS (SELECT websearch_to_tsquery('english',%s) AS query) SELECT id,kind,title,path,start_line AS start,end_line AS end,page,repo,branch,commit_sha,url,text,(-ts_rank_cd(search_vector,q.query,34) - CASE WHEN strpos(lower(title),lower(%s))>0 THEN 1.0::real ELSE 0.0::real END) AS rank FROM evidence CROSS JOIN q WHERE "+' AND '.join(filters)+' ORDER BY rank,id LIMIT 160',[query_text,query.strip(),*params]).fetchall()
        seen, results={},[]
        for row in rows:
            key=(row['path'],row['page'])
            if seen.get(key,0)>=2:
                continue
            seen[key]=seen.get(key,0)+1
            row['citation']=f"p. {row['page']}" if row['kind']=='confluence' else f"lines {row['start']}-{row['end']}"
            results.append(row)
            if len(results)>=limit:
                break
        return results

    def evidence(self, identifier):
        generation=self.store.metadata('active_generation')
        with self.store.connection() as db:
            row=db.execute('SELECT id,kind,title,path,start_line AS start,end_line AS end,page,repo,branch,commit_sha,url,text FROM evidence WHERE generation=%s AND id=%s',(generation,int(identifier))).fetchone()
        if not row:
            raise ValueError('Evidence not found in the current index')
        return row


class Investigations(LegacyInvestigations):
    def __init__(self, root=ROOT, store=None):
        self.root, self.store=Path(root),store or Postgres()

    def list(self):
        with self.store.connection() as db:
            rows=db.execute('SELECT id,title,updated FROM investigations ORDER BY updated DESC').fetchall()
        return [{**row,'updated':row['updated'].isoformat()} for row in rows]

    def get(self, identifier):
        with self.store.connection() as db:
            row=db.execute('SELECT payload FROM investigations WHERE id=%s',(safe_id(identifier),)).fetchone()
        if not row:
            raise ValueError('Investigation not found')
        return row['payload']

    def save(self, payload):
        identifier=safe_id(payload.get('id') or uuid.uuid4().hex)
        item={key:payload.get(key,default) for key,default in {'title':'Untitled investigation','question':'','description':'','sourceUrl':'','version':'','history':[]}.items()}
        if any(not isinstance(item[key],str) for key in ('title','question','description','sourceUrl','version')):
            raise ValueError('Investigation fields must be text')
        if not isinstance(item['history'],list) or len(item['history'])>100:
            raise ValueError('Invalid investigation history')
        item.update(id=identifier,updated=now())
        with self.store.connection() as db:
            db.execute('INSERT INTO investigations(id,title,payload,updated) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET title=EXCLUDED.title,payload=EXCLUDED.payload,updated=EXCLUDED.updated',(identifier,item['title'][:160],Jsonb(item),item['updated']))
        return item
