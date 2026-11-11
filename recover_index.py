"""Recover a completed staging index after Windows prevents its final rename."""
import json
import os
import sqlite3
from triage import KnowledgeBase, ROOT, database, now


def recover():
    kb = KnowledgeBase()
    staging = kb.data / 'knowledge-building.sqlite'
    if not staging.exists():
        raise RuntimeError('No staging index to recover')
    with database(staging) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('Staging index failed integrity check; rebuild required')
        rows = db.execute("SELECT DISTINCT repo,branch,commit_sha FROM evidence WHERE kind='code'").fetchall()
        counts = db.execute('SELECT COUNT(*),COUNT(DISTINCT path) FROM evidence').fetchone()
    repositories = []
    expected = {repo: commit for repo, branch, commit in rows}
    for repo in sorted((ROOT / 'source-colortouch').iterdir()):
        if not repo.is_dir() or not (repo / '.git').exists():
            continue
        commit = kb._git(repo, 'rev-parse', 'HEAD')
        if repo.name in expected and expected[repo.name] != commit:
            raise RuntimeError(f'{repo.name} changed since indexing; rebuild required')
        repositories.append({'name':repo.name, 'branch':kb._git(repo, 'branch', '--show-current'), 'commit':commit})
    os.replace(staging, kb.db)
    kb.state.update(running=False, phase='Ready', completed=now(), repositories=repositories, chunks=counts[0])
    kb.state['errors'] = [error for error in kb.state['errors'] if error['path'] != 'index']
    kb.state_file.write_text(json.dumps(kb.status(), indent=2), encoding='utf-8')
    print(json.dumps({'excerpts':counts[0], 'files':counts[1], 'repositories':len(repositories), 'unreadable':len(kb.state['errors'])}))


if __name__ == '__main__':
    recover()
