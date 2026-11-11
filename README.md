# ColorTouch Diagnostics

A single-user diagnostic workspace that searches local Confluence PDF exports,
ColorTouch source checkouts, and investigation-specific text logs. It runs on
this Windows computer and does not send evidence to an external service.

## Run

From this project folder in PowerShell:

```powershell
.\start.ps1
```

Open **http://127.0.0.1:8765** and choose **Build knowledge index** the first time.
The launcher uses the bundled Codex Python runtime when present. Otherwise,
install Python 3.11+ and run `python -m pip install -r requirements.txt`.
The only nonstandard Python dependency is `pypdf`.

To build the index before starting the server:

```powershell
.\start.ps1 --index
.\start.ps1
```

Use `--port 8766` to select another port. The server binds only to `127.0.0.1`.
Stop it with Ctrl+C. The runtime is not installed as a Windows service.
If a background instance is already running, reuse its local URL rather than
starting a second instance on the same port. The initial background launch PID
is recorded in `.triage/server.pid`.

## Working features

- Questions and keyword/code-symbol searches using SQLite FTS5 and BM25
  keyword ranking, English stemming, identifier splitting, and a small explicit
  vocabulary expansion. This version does **not** use semantic embeddings.
- Confluence PDF text with document/page citations and source-page links from
  `escalations/index.csv`. The PDFs are offline exports, not live Confluence.
- Source excerpts with file/line citations, repository, branch, and Git commit.
  Code is read from `source-colortouch/`; originals are not modified.
- Filter by source type and repository; inspect a complete retrieved excerpt.
- Save investigations, descriptions, affected versions, reference URLs, and a
  history of questions. A saved question can be rerun against the current index.
- Upload text/CSV/JSON/XML logs and ZIP archives. ZIP contents are read without
  extracting or executing files; size and path limits apply. Case logs are only
  searched inside their own investigation.
- Download a Markdown evidence packet containing the question, context,
  citations, retrieved text, and known evidence limitations.
- Background index rebuilds retain the previous index until the replacement is
  ready. Refresh after updating PDF exports or repository checkouts.

## Current boundaries

As requested, this first implementation prioritizes local search. **No LLM is
connected and no generated answer or root cause conclusion is produced.**
Choosing OpenAI, company Azure OpenAI, or another approved provider is a later
integration; no credentials are required for the current features.

Escalation URLs are stored as references. Automatic TFS intake, attachment
downloads, recursive linked-page collection, and live Confluence sync are not
implemented in the app yet. The chat workflow in `AGENTS.md` remains available
for those collection tasks. Paste a description or upload logs to investigate
them in this version. Code search uses indexed working checkouts, not every
branch/tag. An affected-version entry is context, **not** a release filter.
Use the displayed branch and commit to verify applicability. Commit links are
valid for clean tracked files; local edits/untracked files may differ from HEAD.

PDF extraction does not include images, scanned pages, or OCR. Code indexing
excludes dependency/build directories, minified/generated files, symbolic links,
and text files larger than 512 KB. Excerpts are capped at 10,000 characters;
truncation is labeled. Index errors and skipped oversized files are shown in
the Knowledge base panel. Search results are leads, not confidence scores.

## Local data

- `.triage/knowledge.sqlite`: searchable excerpt snapshots (Git ignored).
- `.triage/investigations.sqlite`: saved investigation context/history.
- `.triage/index-status.json`: index status, coverage, and extraction errors.
- `escalations/<investigation-id>/logs/`: original uploads (Git ignored), named
  with a content hash to avoid overwrites. IDs are local investigation IDs.
- Browser downloads: exported Markdown evidence packets.

There is no multi-user authentication. This is a loopback-only local tool,
not a team server. The application does not post to TFS or modify source code.

## Checks

```powershell
python -m unittest discover -s tests -v
```

Tests cover retrieval metadata/filtering, safe query handling, snapshot behavior,
index failure recovery, persistent investigations, log isolation, ZIP handling,
and local HTTP origin restrictions.

## Implementation

`app.py` serves the UI and JSON API; `triage.py` handles retrieval and local
persistence; `web/` contains the browser interface. No npm or JavaScript build
step is required.
