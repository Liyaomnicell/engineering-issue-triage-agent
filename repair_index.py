"""Retry only unreadable source files after fixing Windows long-path handling."""
import gc
import json
import os
import shutil

from triage import BuildLock, KnowledgeBase, ROOT, chunks, database, decode_text, filesystem_path, now, words


def repair():
    kb = KnowledgeBase()
    lock = BuildLock(kb.data / 'index.lock')
    staging = kb.data / 'knowledge-repair.sqlite'
    try:
        shutil.copyfile(kb.db, staging)
        errors, added = [], 0
        with database(staging) as db:
            db.execute('PRAGMA synchronous=OFF')
            for issue in kb.state['errors']:
                path = ROOT / issue['path']
                if not issue['path'].startswith('source-colortouch'):
                    errors.append(issue)
                    continue
                try:
                    text = decode_text(filesystem_path(path).read_bytes())
                    repo_name = path.relative_to(ROOT / 'source-colortouch').parts[0]
                    repo = ROOT / 'source-colortouch' / repo_name
                    metadata = next(r for r in kb.state['repositories'] if r['name'] == repo_name)
                    if kb._git(repo, 'rev-parse', 'HEAD') != metadata['commit']:
                        raise RuntimeError('Repository changed since indexing; rebuild required')
                    if db.execute('SELECT 1 FROM evidence WHERE path=? LIMIT 1', (issue['path'],)).fetchone():
                        continue
                    relative = path.relative_to(repo).as_posix()
                    url = f"https://bitbucket.org/omnicell/{repo_name}/src/{metadata['commit']}/{relative}"
                    for start, end, excerpt in chunks(text):
                        cursor = db.execute('INSERT INTO evidence(kind,title,path,start,end,page,repo,branch,commit_sha,url,text) VALUES(?,?,?,?,?,?,?,?,?,?,?)', ('code', relative, issue['path'], start, end, 0, repo_name, metadata['branch'], metadata['commit'], url, excerpt))
                        db.execute('INSERT INTO search(rowid,title,body) VALUES(?,?,?)', (cursor.lastrowid, ' '.join(words(relative)), ' '.join(words(excerpt))))
                    added += 1
                except Exception as error:
                    errors.append({'path':issue['path'], 'error':str(error)[:300]})
            total = db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]
            # Explicitly release the last cursor before publishing on Windows.
            if 'cursor' in locals():
                cursor.close()
        gc.collect()
        os.replace(staging, kb.db)
        kb.state.update(completed=now(), errors=errors, chunks=total, files=kb.state['files']+added)
        kb.state_file.write_text(json.dumps(kb.status(), indent=2), encoding='utf-8')
        print(json.dumps({'recoveredFiles':added, 'remainingErrors':len(errors), 'excerpts':total}))
    finally:
        lock.close()


if __name__ == '__main__':
    repair()
