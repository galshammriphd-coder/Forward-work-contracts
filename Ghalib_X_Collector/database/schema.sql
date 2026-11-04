-- Ghalib X Data Collector — SQLite schema
-- Raw values collected from X are kept untouched (posts.raw_text / posts.raw_json,
-- accounts.raw_json, post_sources). Processing writes to separate columns
-- (clean_text, detected_language, ...) and never overwrites the originals.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS search_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    search_type      TEXT    NOT NULL,              -- hashtag | user | keyword | advanced | import
    query_text       TEXT    NOT NULL,              -- human readable search phrase
    queries_json     TEXT    NOT NULL DEFAULT '[]', -- list of X search queries actually executed
    params_json      TEXT    NOT NULL DEFAULT '{}', -- full search form (re-run / resume)
    start_date       TEXT,
    end_date         TEXT,
    sort_mode        TEXT    NOT NULL DEFAULT 'live', -- live (latest) | top
    max_posts        INTEGER NOT NULL DEFAULT 300,
    status           TEXT    NOT NULL DEFAULT 'new',  -- new | running | completed | stopped | failed
    received_count   INTEGER NOT NULL DEFAULT 0,
    new_count        INTEGER NOT NULL DEFAULT 0,
    duplicate_count  INTEGER NOT NULL DEFAULT 0,
    processed_count  INTEGER NOT NULL DEFAULT 0,
    error_count      INTEGER NOT NULL DEFAULT 0,
    last_error       TEXT,
    progress_json    TEXT    NOT NULL DEFAULT '{}', -- per-query progress (resume support)
    parent_job_id    INTEGER REFERENCES search_jobs(id) ON DELETE SET NULL,
    created_by       TEXT,
    created_at       TEXT    NOT NULL,
    started_at       TEXT,
    finished_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON search_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON search_jobs(created_at);

CREATE TABLE IF NOT EXISTS accounts (
    username          TEXT PRIMARY KEY,               -- lower-case screen name
    user_id           TEXT,
    screen_name       TEXT,                           -- original casing
    display_name      TEXT,
    profile_url       TEXT,
    description       TEXT,
    location          TEXT,
    followers_count   INTEGER,
    following_count   INTEGER,
    statuses_count    INTEGER,
    account_created_at TEXT,
    verified          INTEGER,
    profile_image_url TEXT,
    first_seen_at     TEXT NOT NULL,
    last_updated_at   TEXT NOT NULL,
    raw_json          TEXT
);

CREATE TABLE IF NOT EXISTS posts (
    post_id            TEXT PRIMARY KEY,
    raw_text           TEXT,                          -- text exactly as received
    clean_text         TEXT,                          -- processing output
    username           TEXT,
    display_name       TEXT,
    profile_url        TEXT,
    post_url           TEXT,
    published_at       TEXT,                          -- ISO-8601 UTC
    published_date     TEXT,                          -- local date (settings timezone)
    published_time     TEXT,                          -- local time
    language           TEXT,                          -- language reported by X
    detected_language  TEXT,                          -- processing output
    post_type          TEXT,                          -- original | reply | quote | repost
    hashtags_json      TEXT NOT NULL DEFAULT '[]',
    mentions_json      TEXT NOT NULL DEFAULT '[]',
    urls_json          TEXT NOT NULL DEFAULT '[]',
    media_json         TEXT NOT NULL DEFAULT '[]',
    replies_count      INTEGER,
    reposts_count      INTEGER,
    likes_count        INTEGER,
    quotes_count       INTEGER,
    bookmarks_count    INTEGER,
    views_count        INTEGER,
    conversation_id    TEXT,
    in_reply_to_post_id TEXT,
    in_reply_to_user   TEXT,
    quoted_post_id     TEXT,
    search_keyword     TEXT,                          -- query that first found the post
    first_job_id       INTEGER REFERENCES search_jobs(id) ON DELETE SET NULL,
    source             TEXT,                          -- graphql | dom | import
    first_collected_at TEXT NOT NULL,
    last_collected_at  TEXT NOT NULL,
    is_processed       INTEGER NOT NULL DEFAULT 0,
    processed_at       TEXT,
    is_valid           INTEGER NOT NULL DEFAULT 1,
    validation_notes   TEXT,
    raw_json           TEXT,
    FOREIGN KEY (username) REFERENCES accounts(username) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_username  ON posts(username);
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at);
CREATE INDEX IF NOT EXISTS idx_posts_date      ON posts(published_date);
CREATE INDEX IF NOT EXISTS idx_posts_lang      ON posts(detected_language);
CREATE INDEX IF NOT EXISTS idx_posts_job       ON posts(first_job_id);
CREATE INDEX IF NOT EXISTS idx_posts_collected ON posts(first_collected_at);

-- Which job found which post (a post can be found by several jobs).
CREATE TABLE IF NOT EXISTS job_posts (
    job_id        INTEGER NOT NULL REFERENCES search_jobs(id) ON DELETE CASCADE,
    post_id       TEXT    NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    query         TEXT,
    is_new        INTEGER NOT NULL DEFAULT 1,
    collected_at  TEXT    NOT NULL,
    PRIMARY KEY (job_id, post_id)
);
CREATE INDEX IF NOT EXISTS idx_job_posts_post ON job_posts(post_id);

-- Untouched source record for every capture (provenance).
CREATE TABLE IF NOT EXISTS post_sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id       TEXT    NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    job_id        INTEGER REFERENCES search_jobs(id) ON DELETE CASCADE,
    source        TEXT    NOT NULL,
    source_url    TEXT,
    captured_at   TEXT    NOT NULL,
    raw_json      TEXT
);
CREATE INDEX IF NOT EXISTS idx_sources_post ON post_sources(post_id);

CREATE TABLE IF NOT EXISTS hashtags (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tag           TEXT NOT NULL UNIQUE,              -- normalised (lower case, no #)
    display_tag   TEXT NOT NULL,
    occurrences   INTEGER NOT NULL DEFAULT 0,
    post_count    INTEGER NOT NULL DEFAULT 0,
    first_seen    TEXT,
    last_seen     TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS post_hashtags (
    post_id     TEXT    NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    hashtag_id  INTEGER NOT NULL REFERENCES hashtags(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, hashtag_id)
);
CREATE INDEX IF NOT EXISTS idx_post_hashtags_tag ON post_hashtags(hashtag_id);

-- One row per capture: lets the user see engagement evolve between collections.
CREATE TABLE IF NOT EXISTS post_metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id       TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    job_id        INTEGER REFERENCES search_jobs(id) ON DELETE SET NULL,
    captured_at   TEXT NOT NULL,
    replies_count INTEGER,
    reposts_count INTEGER,
    likes_count   INTEGER,
    quotes_count  INTEGER,
    bookmarks_count INTEGER,
    views_count   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_metrics_post ON post_metrics(post_id);

CREATE TABLE IF NOT EXISTS collection_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER REFERENCES search_jobs(id) ON DELETE CASCADE,
    ts         TEXT NOT NULL,
    level      TEXT NOT NULL,
    event      TEXT NOT NULL,
    message    TEXT,
    details    TEXT
);
CREATE INDEX IF NOT EXISTS idx_clogs_job ON collection_logs(job_id);

CREATE TABLE IF NOT EXISTS processing_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL,
    job_id           INTEGER REFERENCES search_jobs(id) ON DELETE SET NULL,
    step             TEXT NOT NULL,
    ts               TEXT NOT NULL,
    records_in       INTEGER,
    records_affected INTEGER,
    message          TEXT
);
CREATE INDEX IF NOT EXISTS idx_plogs_run ON processing_logs(run_id);

CREATE TABLE IF NOT EXISTS sentiment_results (
    post_id     TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    model       TEXT NOT NULL,
    label       TEXT NOT NULL,                       -- positive | negative | neutral | mixed
    score       REAL,
    scores_json TEXT,
    analyzed_at TEXT NOT NULL,
    PRIMARY KEY (post_id, model)
);
CREATE INDEX IF NOT EXISTS idx_sentiment_label ON sentiment_results(label);

CREATE TABLE IF NOT EXISTS topic_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    post_id        TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    topic_id       INTEGER NOT NULL,
    topic_label    TEXT,
    topic_keywords TEXT,
    weight         REAL,
    model          TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_run  ON topic_results(run_id);
CREATE INDEX IF NOT EXISTS idx_topics_post ON topic_results(post_id);

CREATE TABLE IF NOT EXISTS entity_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    entity      TEXT NOT NULL,
    entity_type TEXT NOT NULL,                       -- person | organization | government | location | product | event | misc
    model       TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_post ON entity_results(post_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entity_results(entity_type);

CREATE TABLE IF NOT EXISTS exports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER REFERENCES search_jobs(id) ON DELETE SET NULL,
    export_type   TEXT NOT NULL,                     -- data | report
    format        TEXT NOT NULL,
    path          TEXT NOT NULL,
    record_count  INTEGER,
    filters_json  TEXT,
    created_by    TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    search_type TEXT NOT NULL,
    params_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'viewer',     -- admin | analyst | viewer
    created_at    TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    actor     TEXT,
    action    TEXT NOT NULL,
    target    TEXT,
    details   TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
