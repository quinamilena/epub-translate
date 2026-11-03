CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    source_path     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'queued',
    progress        INTEGER NOT NULL DEFAULT 0,
    message         TEXT,
    provider        TEXT,
    model           TEXT,
    base_url        TEXT,
    glossary        TEXT,
    has_api_key     INTEGER NOT NULL DEFAULT 0,
    parser_version  INTEGER NOT NULL DEFAULT 1,
    source_title    TEXT,
    total_chapters  INTEGER NOT NULL DEFAULT 0,
    done_chapters   INTEGER NOT NULL DEFAULT 0,
    total_blocks    INTEGER NOT NULL DEFAULT 0,
    done_blocks     INTEGER NOT NULL DEFAULT 0,
    output_path     TEXT,
    validation_json TEXT,
    errors_json     TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    file_name    TEXT NOT NULL,
    item_id      TEXT,
    order_index  INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    UNIQUE(job_id, file_name)
);

CREATE TABLE IF NOT EXISTS blocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,
    chapter_id      INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    block_index     INTEGER NOT NULL,
    source_text     TEXT NOT NULL,
    translated_text TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    UNIQUE(chapter_id, block_index)
);

CREATE INDEX IF NOT EXISTS idx_blocks_pending ON blocks(job_id, status);
CREATE INDEX IF NOT EXISTS idx_chapters_pending ON chapters(job_id, status);
