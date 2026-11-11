# ColorTouch Diagnostics

An Angular engineering investigation workspace backed by a Python JSON API
and PostgreSQL 18. Search local Confluence PDF exports, source checkouts, and
case-specific logs; inspect citations and save investigation context.

## Current stack

- Angular 22, TypeScript 6, standalone components, signals, Forms and HttpClient.
- Python 3.12 API using the existing single-user HTTP server.
- PostgreSQL via Psycopg 3: JSONB investigations and metadata, full-text
  tsvectors, a GIN search index, and ts_rank_cd ranking.
- pypdf for offline PDF text extraction.
- Docker Compose deployment layout and GitHub Actions build/test workflow.

LLM answers, live Confluence/TFS collection, embeddings, and multi-user
authentication are still deferred. Source and PDF images are not OCR'd.
Affected versions are context, not an automatic historical-release filter.

## Recommended deployment: Docker Compose

GitHub stores application code and runs CI. A company server or cloud machine
runs these containers; GitHub Pages cannot execute the Python/PostgreSQL app.

1. Install Docker with Compose on the deployment machine.
2. Copy .env.example to .env and replace POSTGRES_PASSWORD with a strong secret.
   Do not commit .env. Compose passes PostgreSQL connection values separately,
   so passwords containing URL-reserved characters do not break its connection.
3. Provide the escalations/ and source-colortouch/ knowledge folders.
4. Run:

    docker compose up -d --build

Open http://127.0.0.1:8765. The default is local access only. A team deployment
needs company sign-in and an HTTPS reverse proxy; configure the expected host
in TRIAGE_ALLOWED_HOSTS. This repository does not provision those services.
Do not expose the app publicly as an authenticated team service yet.

PostgreSQL data persists in a named Docker volume. Logs and offline knowledge
are bind-mounted from the project; source-colortouch is read only. The runtime
user (UID 10001) needs write permission to .triage and escalations. Docker build
context explicitly excludes evidence, logs, source checkouts, local databases,
and credentials.

Docker containers have not been run on the current Windows machine because
Docker is not installed. The PostgreSQL engine, API and Angular build are
validated locally.

## Local development

Install Python 3.11+, Node 24, pnpm 11 and PostgreSQL 18, then:

    python -m venv .venv
    .venv/Scripts/python -m pip install -r requirements.txt
    pnpm --dir frontend install --frozen-lockfile
    pnpm --dir frontend build

Set DATABASE_URL in an ignored .env using .env.example as a template. For a
company server, use its required TLS connection options. The backend also
accepts standard PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE variables.

Start the API and built Angular UI:

    ./start.ps1

Open http://127.0.0.1:8765. Stop a foreground instance with Ctrl+C. A background
instance's PID is in .triage/server.pid. Avoid starting two instances on the
same port.

For Angular development, start the API and then:

    pnpm --dir frontend start

The Angular development server proxies /api to http://127.0.0.1:8765.
The production Python server serves frontend/dist/frontend/browser.

### Optional project-local PostgreSQL on Windows

This workspace has official PostgreSQL binaries under ignored
.tools/postgresql/pgsql. setup_local_postgres.py initializes a cluster in
.triage/pgdata and generates credentials in ignored .env. It does not install
a Windows service and does not print the password:

    .venv/Scripts/python setup_local_postgres.py

It listens only on 127.0.0.1:54329. Run the same helper after reboot to restart
the cluster. Fresh clones do not contain these binaries; use Docker Compose
or install PostgreSQL separately. The helper refuses to overwrite an existing
.env when creating a new cluster.

## Migrating the previous SQLite version

With PostgreSQL configured, run:

    .venv/Scripts/python migrate_sqlite.py

For Compose, with the old .triage folder mounted:

    docker compose exec app python migrate_sqlite.py

The migration:
- Opens legacy SQLite databases read only and leaves them unchanged.
- Copies excerpt IDs, citations, code versions and saved case histories.
- Rebuilds PostgreSQL search vectors from original excerpt text.
- Publishes the new active index and the import marker in one transaction.
- Does not replace an existing active PostgreSQL index.
- Is idempotent after a successful import and preserves subsequent edits.

Original log files remain under escalations/<investigation-id>/logs; they are
not duplicated into the database. The migration was run successfully for the
existing local corpus and saved investigation.

The old triage.py SQLite classes and recover_index.py/repair_index.py remain
for legacy recovery and migration regression tests. The running API uses
postgres_store.py and does not fall back to SQLite.

## Search and evidence

Use questions, keywords, or code symbols. Filters support repository and source
type. Citations contain file lines or PDF pages plus branch/commit metadata.
Results are evidence leads, not confidence scores or generated conclusions.

Uploaded text, CSV, JSON, XML and ZIP logs stay scoped to their investigation.
Archives are inspected without extracting or executing files. Upload size is
20 MB/file; ZIP expansion limits are enforced.

Refresh knowledge index after updating source checkouts or PDF exports.
PostgreSQL builds a new generation and publishes it only after success. The
previous generation stays available on failure. Prior generations are retained
for rollback and require a future retention policy for frequent large rebuilds.

Code indexing excludes dependency/build directories, minified/generated files,
symlinks and files over 512 KB. Excerpts are capped at 10,000 characters, with
truncation labeled. Extraction gaps are visible in the Knowledge base panel.

## Tests and CI

    .venv/Scripts/python -m unittest discover -s tests -v

PostgreSQL integration tests require TEST_DATABASE_URL. They create and remove
isolated test schemas, never application tables. For a local test database, set
TEST_DATABASE_URL to that database's connection string.

GitHub Actions provisions PostgreSQL 18, builds Angular and runs the complete
test suite. It does not deploy the app or upload knowledge sources.

## Repository exclusions

.gitignore excludes escalations/, source-colortouch/, .triage/, .tools/,
.env credentials, Python virtual environments, node_modules and Angular builds.
Commit application code, schema migrations, frontend sources and its pnpm
lockfile. Keep company source code and diagnostic evidence out of this repo.
