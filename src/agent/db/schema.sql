CREATE TABLE IF NOT EXISTS drafts (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    post_type       TEXT NOT NULL,
    source_ref      TEXT,
    caption         TEXT NOT NULL,
    hashtags        TEXT NOT NULL,
    image_url       TEXT,
    image_credit    TEXT,
    status          TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    approved_at     TEXT,
    posted_at       TEXT,
    buffer_post_id  TEXT,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS rotation_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_day        TEXT,
    project_index   INTEGER DEFAULT 0,
    skill_index     INTEGER DEFAULT 0,
    exp_index       INTEGER DEFAULT 0
);

INSERT OR IGNORE INTO rotation_state (id, last_day, project_index, skill_index, exp_index)
    VALUES (1, NULL, 0, 0, 0);

CREATE TABLE IF NOT EXISTS post_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id        TEXT REFERENCES drafts(id),
    post_type       TEXT,
    source_ref      TEXT,
    posted_at       TEXT,
    linkedin_url    TEXT
);
