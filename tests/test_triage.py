import base64
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject

from app import make_handler
from http.server import ThreadingHTTPServer
from triage import KnowledgeBase, Investigations, attachment_text, chunks, evidence_packet, safe_id, terms


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'escalations').mkdir()
        writer = PdfWriter()
        page = writer.add_blank_page(width=500, height=500)
        font = DictionaryObject({NameObject('/Type'):NameObject('/Font'), NameObject('/Subtype'):NameObject('/Type1'), NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 20 400 Td (MedChill DeviceSecure latch investigation) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(self.root / 'escalations' / 'Fixture.pdf')
        writer.close()
        self.repo = self.root / 'source-colortouch' / 'ct-example'
        (self.repo / '.git').mkdir(parents=True)
        (self.repo / 'AMRAccount.cs').write_text('class AMRAccount {\n// Fetch reconciliation account for patient\npublic void GetAMRAccounts() {}\n}\n', encoding='utf-8')
        (self.repo / 'Other.cs').write_text('class Printer { void PrintLabel() {} }', encoding='utf-8')
        (self.repo / 'node_modules').mkdir()
        (self.repo / 'node_modules' / 'secret.ts').write_text('hidden dependency marker')
        self.kb = KnowledgeBase(self.root)
        with patch.object(self.kb, '_git', side_effect=lambda repo, *args: 'develop' if args[0] == 'branch' else 'abc123'):
            self.kb._build()
        self.assertEqual(self.kb.status()['phase'], 'Ready')

    def tearDown(self):
        self.temp.cleanup()

    def test_source_search_has_lines_and_version(self):
        results = self.kb.search('AMR accounts reconciliation')
        self.assertEqual(results[0]['title'], 'AMRAccount.cs')
        self.assertEqual(results[0]['start'], 1)
        self.assertEqual(results[0]['commit_sha'], 'abc123')
        self.assertEqual(results[0]['branch'], 'develop')
        self.assertIn('GetAMRAccounts', results[0]['text'])

    def test_filters_queries_and_empty_results(self):
        self.assertEqual(self.kb.search('accounts', kind='confluence'), [])
        self.assertEqual(self.kb.search('accounts', repo='missing'), [])
        self.assertEqual(self.kb.search('hidden dependency marker'), [])
        self.assertEqual(self.kb.search('the and why'), [])
        self.assertEqual(self.kb.search('zxxyyunknown'), [])
        self.kb.search('"; DROP TABLE evidence; --')
        self.assertTrue(self.kb.search('GetAMRAccounts'))

    def test_pdf_text_has_page_citation(self):
        result = self.kb.search('DeviceSecure latch', kind='confluence')[0]
        self.assertEqual(result['page'], 1)
        self.assertEqual(result['citation'], 'p. 1')
        self.assertIn('MedChill', result['text'])

    def test_index_snapshot_remains_after_source_changes(self):
        (self.repo / 'AMRAccount.cs').write_text('changed working tree', encoding='utf-8')
        self.assertIn('GetAMRAccounts', self.kb.search('GetAMRAccounts')[0]['text'])

    def test_failed_rebuild_retains_previous_index(self):
        with patch.object(self.kb, '_git', side_effect=RuntimeError('Simulated checkout failure')):
            self.kb._build()
        self.assertTrue(self.kb.status()['phase'].startswith('Index failed'))
        self.assertTrue(self.kb.search('GetAMRAccounts'))

    def test_logs_are_isolated_and_preserved(self):
        cases = Investigations(self.root)
        first = cases.save({'title': 'First'})
        second = cases.save({'title': 'Second'})
        added = cases.add_log(first['id'], '../../amr.log', b'11:07 reconcile account empty')
        again = cases.add_log(first['id'], '../../amr.log', b'11:07 reconcile account empty')
        self.assertEqual(added['file'], again['file'])
        self.assertEqual(len(cases.logs(first['id'])), 1)
        self.assertEqual(cases.search_logs(second['id'], 'reconcile'), [])
        self.assertEqual(cases.search_logs(first['id'], 'reconcile')[0]['start'], 1)
        self.assertEqual(cases.get(first['id'])['title'], 'First')

    def test_packet_discloses_no_model_and_version_gap(self):
        result = evidence_packet('why empty', self.kb.search('accounts'), {'version':'29.5'})
        self.assertIn('[E1]', result)
        self.assertIn('No LLM answer', result)
        self.assertIn('not a verified affected release', result)
        self.assertIn('29.5', result)


class InputTests(unittest.TestCase):
    def test_zip_paths_and_binary_rejected(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('../escape.log', 'data')
        with self.assertRaises(ValueError):
            attachment_text('logs.zip', content.getvalue())
        with self.assertRaises(ValueError):
            attachment_text('logs.txt', b'abc\x00def')
        with self.assertRaises(ValueError):
            safe_id('../../example')

    def test_zip_reads_nested_logs_without_extracting(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('nested/log.txt', 'DeviceSecure before latch')
            archive.writestr('ignore.exe', b'no execution')
        self.assertEqual(attachment_text('logs.zip', content.getvalue()), [('nested/log.txt', 'DeviceSecure before latch')])

    def test_chunks_overlap_and_code_tokenization(self):
        result = list(chunks('\n'.join(str(i) for i in range(80))))
        self.assertEqual(result[0][:2], (1,55))
        self.assertEqual(result[1][:2], (46,80))
        self.assertIn('account', terms('PatientAccount'))


class ServerTests(unittest.TestCase):
    def test_local_api_persistence_and_origin_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kb, cases = KnowledgeBase(root), Investigations(root)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(kb, cases))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = 'http://127.0.0.1:' + str(server.server_port)
            try:
                status = json.load(urllib.request.urlopen(base+'/api/status'))
                self.assertFalse(status['model']['connected'])
                javascript = urllib.request.urlopen(base+'/app.js')
                self.assertIn('text/javascript', javascript.headers['Content-Type'])
                javascript.close()
                body = json.dumps({'title':'Saved from API','question':'AMR'}).encode()
                request = urllib.request.Request(base+'/api/investigation', data=body, headers={'Content-Type':'application/json','X-Triage-Request':'1'})
                saved = json.load(urllib.request.urlopen(request))
                loaded = json.load(urllib.request.urlopen(base+'/api/investigation?id='+saved['id']))
                self.assertEqual(loaded['title'],'Saved from API')
                hostile = urllib.request.Request(base+'/api/status', headers={'Host':'evil.example'})
                with self.assertRaises(urllib.error.HTTPError) as context:
                    urllib.request.urlopen(hostile)
                self.assertEqual(context.exception.code,403)
                hostile = urllib.request.Request(base+'/api/index', data=b'{}', headers={'Origin':'https://evil.example','X-Triage-Request':'1'})
                with self.assertRaises(urllib.error.HTTPError) as context:
                    urllib.request.urlopen(hostile)
                self.assertEqual(context.exception.code,403)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
