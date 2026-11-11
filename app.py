"""Single-user loopback server for the local diagnostic workspace."""
import argparse
import base64
import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from triage import ROOT, KnowledgeBase, Investigations, evidence_packet


def make_handler(kb, investigations):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'ColorTouchLocal/1.0'

        def log_message(self, fmt, *args):
            # Do not log questions, paths, or source evidence.
            pass

        def send(self, data, code=200, content_type='application/json; charset=utf-8'):
            body = json.dumps(data).encode() if content_type.startswith('application/json') else data.encode() if isinstance(data, str) else data
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            host = self.headers.get('Host', '')
            origin = self.headers.get('Origin')
            return host == expected and (not origin or origin == 'http://' + expected)

        def do_GET(self):
            if not self.allowed():
                return self.send({'error': 'Local origin required'}, 403)
            route = urlparse(self.path)
            query = parse_qs(route.query)
            try:
                if route.path == '/api/status':
                    return self.send({'index': kb.status(), 'model': {'connected': False, 'message': 'Model provider not configured. Search and evidence export work locally.'}, 'liveConnectors': False})
                if route.path == '/api/investigations':
                    return self.send(investigations.list())
                if route.path == '/api/investigation':
                    case = investigations.get(query.get('id', [''])[0])
                    return self.send({**case, 'logs': investigations.logs(case['id'])})
                if route.path == '/api/evidence':
                    return self.send(kb.evidence(query.get('id', [''])[0]))
                assets = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/adjustments.css': 'adjustments.css'}
                if route.path in assets:
                    path = ROOT / 'web' / assets[route.path]
                    types = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css'}
                    return self.send(path.read_bytes(), content_type=types[path.suffix] + '; charset=utf-8')
                self.send({'error': 'Not found'}, 404)
            except (ValueError, OSError) as error:
                self.send({'error': str(error)}, 400)

        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Triage-Request') != '1':
                return self.send({'error': 'Local application request required'}, 403)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 29 * 1024 * 1024:
                    return self.send({'error': 'Request must be smaller than 29 MB'}, 413)
                payload = json.loads(self.rfile.read(size))
                route = urlparse(self.path).path
                if route == '/api/index':
                    return self.send({'started': kb.start_index(), 'index': kb.status()})
                if route == '/api/investigation':
                    return self.send(investigations.save(payload))
                if route == '/api/log':
                    data = base64.b64decode(payload['data'], validate=True)
                    return self.send(investigations.add_log(payload['id'], payload['name'], data))
                if route in {'/api/search', '/api/packet'}:
                    question = payload.get('question', '').strip()
                    if not question or len(question) > 8000:
                        raise ValueError('Enter a question between 1 and 8,000 characters')
                    case = investigations.get(payload['caseId']) if payload.get('caseId') else {}
                    kind, repo = payload.get('kind', 'all'), payload.get('repo', '')
                    if kind == 'all':
                        results = kb.search(question, 'confluence', repo, limit=6) + kb.search(question, 'code', repo, limit=12)
                        results.sort(key=lambda source: source['rank'])
                    else:
                        results = [] if kind == 'log' else kb.search(question, kind, repo)
                    if case and payload.get('kind', 'all') in {'all', 'log'}:
                        results = investigations.search_logs(case['id'], question) + ([] if payload.get('kind') == 'log' else results)
                    if payload.get('kind') == 'log' and not case:
                        results = []
                    return self.send({'results': results, 'packet': evidence_packet(question, results, case), 'index': kb.status(), 'generated': False})
                self.send({'error': 'Not found'}, 404)
            except (ValueError, KeyError, TypeError) as error:
                self.send({'error': str(error)}, 400)
            except Exception:
                self.send({'error': 'Operation failed. Check local file access and index status.'}, 500)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--index', action='store_true', help='Build index and exit')
    args = parser.parse_args()
    kb = KnowledgeBase()
    if args.index:
        kb.start_index()
        while kb.status()['running']:
            threading.Event().wait(1)
        print(json.dumps(kb.status(), indent=2))
        raise SystemExit(0 if kb.status()['phase'] == 'Ready' else 1)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(kb, Investigations()))
    print(f'ColorTouch Diagnostics: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
