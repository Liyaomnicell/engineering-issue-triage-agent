"""Integration tests against real PostgreSQL (local or GitHub Actions service)."""
import os
import json
import hashlib
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from psycopg import sql
from psycopg.types.json import Jsonb
from postgres_store import Postgres, KnowledgeBase, Investigations, copy_records


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'),'Set TEST_DATABASE_URL to run PostgreSQL integration tests')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema='test_'+uuid.uuid4().hex
        self.store=Postgres(os.environ['TEST_DATABASE_URL'],self.schema)
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.generation=uuid.uuid4()
        records=[{'id':1,'kind':'code','title':'AMRAccountProcessor.cs','path':'source-colortouch/ct-example/AMRAccountProcessor.cs','start':10,'end':20,'page':0,'repo':'ct-example','branch':'develop','commit_sha':'abc123','url':'','text':'GetAMRAccounts retrieves pending reconciliation accounts'}, {'id':2,'kind':'confluence','title':'MedChill latch investigation','path':'escalations/medchill.pdf','start':1,'end':10,'page':3,'repo':'','branch':'','commit_sha':'','url':'','text':'DeviceSecure triggered before solenoid latch'}]
        with self.store.connection() as db:
            copy_records(db,self.generation,records)
            self.store.set_metadata(db,'active_generation',str(self.generation))
            self.store.set_metadata(db,'index_status',{'running':False,'phase':'Ready','chunks':2,'files':2,'errors':[],'skipped':0})
        self.kb=KnowledgeBase(self.root,self.store)
        self.cases=Investigations(self.root,self.store)

    def tearDown(self):
        with self.store.connection() as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.temp.cleanup()

    def test_ranked_retrieval_preserves_citations_and_filters(self):
        result=self.kb.search('AMR accounts reconciliation',kind='code',repo='ct-example')[0]
        self.assertEqual(result['title'],'AMRAccountProcessor.cs')
        self.assertEqual(result['citation'],'lines 10-20')
        self.assertEqual(result['commit_sha'],'abc123')
        self.assertEqual(self.kb.search('accounts',repo='missing'),[])
        self.assertEqual(self.kb.search('the and why'),[])
        pdf=self.kb.search('DeviceSecure latch',kind='confluence')[0]
        self.assertEqual(pdf['citation'],'p. 3')

    def test_investigations_and_logs_are_isolated(self):
        first=self.cases.save({'title':'Case one'})
        second=self.cases.save({'title':'Case two'})
        self.cases.add_log(first['id'],'amr.log',b'reconciliation account empty')
        self.assertEqual(len(self.cases.search_logs(first['id'],'account')),1)
        self.assertEqual(self.cases.search_logs(second['id'],'account'),[])
        self.assertEqual(self.cases.get(first['id'])['title'],'Case one')
        self.assertEqual(len(self.cases.list()),2)

    def test_failed_transaction_does_not_replace_active_generation(self):
        try:
            with self.store.connection() as db:
                self.store.set_metadata(db,'active_generation',str(uuid.uuid4()))
                raise RuntimeError('Interrupted build')
        except RuntimeError:
            pass
        self.assertEqual(self.store.metadata('active_generation'),str(self.generation))
        self.assertTrue(self.kb.search('accounts'))

    def test_queries_are_parameterized(self):
        self.kb.search("'; DROP TABLE evidence; --")
        self.assertTrue(self.kb.search('accounts'))
        with self.assertRaises(ValueError):
            Postgres(os.environ['TEST_DATABASE_URL'],'unsafe;drop schema public')

    def test_sqlite_import_is_read_only_and_idempotent(self):
        from migrate_sqlite import migrate
        with self.store.connection() as db:
            db.execute("DELETE FROM metadata WHERE key='active_generation'")
        folder=self.root/'.triage'
        folder.mkdir()
        path=folder/'investigations.sqlite'
        with sqlite3.connect(path) as legacy:
            legacy.execute('CREATE TABLE investigations(id TEXT,title TEXT,payload TEXT,updated TEXT)')
            case={'id':'imported','title':'Original','question':'AMR','description':'','sourceUrl':'','version':'','history':[]}
            legacy.execute('INSERT INTO investigations VALUES(?,?,?,?)',('imported','Original',json.dumps(case),'2026-11-10T00:00:00+00:00'))
        legacy.close()
        original=hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(migrate(self.root,self.store)['investigations'],1)
        case=self.cases.get('imported')
        case['title']='Changed after import'
        self.cases.save(case)
        self.assertTrue(migrate(self.root,self.store)['alreadyImported'])
        self.assertEqual(self.cases.get('imported')['title'],'Changed after import')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),original)


if __name__=='__main__':
    unittest.main()
