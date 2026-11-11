"""Initialize the optional project-local PostgreSQL test/runtime cluster."""
import os
import secrets
import subprocess
from pathlib import Path

import psycopg
from triage import ROOT


def setup():
    binary=ROOT/'.tools'/'postgresql'/'pgsql'/'bin'
    if not (binary/'initdb.exe').exists():
        raise SystemExit('Extract the official PostgreSQL Windows binaries into .tools/postgresql first, or use Docker Compose.')
    data=ROOT/'.triage'/'pgdata'
    data.parent.mkdir(exist_ok=True)
    envfile=ROOT/'.env'
    if not data.exists():
        if envfile.exists():
            raise SystemExit('.env already exists; refusing to overwrite database settings. Use the existing database or move the settings yourself.')
        password=secrets.token_urlsafe(32)
        pwfile=ROOT/'.triage'/'postgres-bootstrap-password'
        pwfile.write_text(password,encoding='utf-8')
        subprocess.run([str(binary/'initdb.exe'),'-D',str(data),'-U','triage','--pwfile',str(pwfile),'--auth','scram-sha-256','--encoding','UTF8','--locale','C'],check=True,stdout=subprocess.DEVNULL)
        envfile.write_text(f'DATABASE_URL=postgresql://triage:{password}@127.0.0.1:54329/triage\nPOSTGRES_USER=triage\nPOSTGRES_DB=triage\nPOSTGRES_PASSWORD={password}\n',encoding='utf-8')
    from postgres_store import load_environment
    load_environment()
    status=subprocess.run([str(binary/'pg_ctl.exe'),'-D',str(data),'status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if status.returncode:
        subprocess.run([str(binary/'pg_ctl.exe'),'-D',str(data),'-l',str(ROOT/'.triage'/'postgres.log'),'-o','-h 127.0.0.1 -p 54329','-w','start'],check=True,stdout=subprocess.DEVNULL)
    dsn=os.environ['DATABASE_URL']
    from psycopg.conninfo import make_conninfo
    with psycopg.connect(make_conninfo(dsn,dbname='postgres'),autocommit=True) as db:
        if not db.execute("SELECT 1 FROM pg_database WHERE datname='triage'").fetchone():
            db.execute('CREATE DATABASE triage')
    print('Project-local PostgreSQL is ready on 127.0.0.1:54329. Credentials are in ignored .env; they were not printed.')


if __name__=='__main__':
    setup()
