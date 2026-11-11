CREATE TABLE IF NOT EXISTS metadata (
    key text PRIMARY KEY,
    value jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS investigations (
    id text PRIMARY KEY,
    title text NOT NULL,
    payload jsonb NOT NULL,
    updated timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    generation uuid NOT NULL,
    id bigint NOT NULL,
    kind text NOT NULL CHECK (kind IN ('code', 'confluence')),
    title text NOT NULL,
    path text NOT NULL,
    start_line integer NOT NULL,
    end_line integer NOT NULL,
    page integer NOT NULL DEFAULT 0,
    repo text NOT NULL DEFAULT '',
    branch text NOT NULL DEFAULT '',
    commit_sha text NOT NULL DEFAULT '',
    url text NOT NULL DEFAULT '',
    text text NOT NULL,
    title_terms text NOT NULL,
    body_terms text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
      setweight(to_tsvector('english'::regconfig, title_terms), 'A') ||
      setweight(to_tsvector('english'::regconfig, body_terms), 'B')
    ) STORED,
    PRIMARY KEY (generation, id)
);
CREATE INDEX IF NOT EXISTS evidence_search_idx ON evidence USING gin(search_vector);
CREATE INDEX IF NOT EXISTS evidence_filter_idx ON evidence(generation, kind, repo);
