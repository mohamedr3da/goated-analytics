CREATE TABLE IF NOT EXISTS tracked_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  x_user_id TEXT NOT NULL UNIQUE,
  username TEXT NOT NULL,
  display_name TEXT NOT NULL,
  profile_image_url TEXT,
  account_created_at TEXT,
  verified INTEGER NOT NULL DEFAULT 0,
  verified_type TEXT,
  protected INTEGER NOT NULL DEFAULT 0,
  tracking_started_at TEXT NOT NULL,
  is_tracking_enabled INTEGER NOT NULL DEFAULT 1,
  last_successful_refresh_at TEXT,
  last_refresh_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_tracked_accounts_username ON tracked_accounts (username);
CREATE INDEX IF NOT EXISTS ix_tracked_accounts_x_user_id ON tracked_accounts (x_user_id);

CREATE TABLE IF NOT EXISTS account_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES tracked_accounts(id),
  captured_at TEXT NOT NULL,
  followers_count INTEGER,
  following_count INTEGER,
  post_count INTEGER,
  listed_count INTEGER,
  raw_metrics TEXT,
  UNIQUE(account_id, captured_at)
);

CREATE INDEX IF NOT EXISTS ix_account_snapshots_account_captured
  ON account_snapshots (account_id, captured_at);

CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  x_post_id TEXT NOT NULL UNIQUE,
  account_id INTEGER NOT NULL REFERENCES tracked_accounts(id),
  created_at TEXT NOT NULL,
  text_preview TEXT NOT NULL,
  url TEXT NOT NULL,
  post_type TEXT NOT NULL DEFAULT 'post',
  referenced_post_id TEXT,
  conversation_id TEXT,
  lang TEXT,
  possibly_sensitive INTEGER,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  raw_data TEXT
);

CREATE INDEX IF NOT EXISTS ix_posts_account_created ON posts (account_id, created_at);
CREATE INDEX IF NOT EXISTS ix_posts_account_first_seen ON posts (account_id, first_seen_at);
CREATE INDEX IF NOT EXISTS ix_posts_x_post_id ON posts (x_post_id);

CREATE TABLE IF NOT EXISTS post_metric_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL REFERENCES posts(id),
  captured_at TEXT NOT NULL,
  impression_count INTEGER,
  like_count INTEGER,
  reply_count INTEGER,
  repost_count INTEGER,
  quote_count INTEGER,
  bookmark_count INTEGER,
  video_view_count INTEGER,
  raw_metrics TEXT,
  UNIQUE(post_id, captured_at)
);

CREATE INDEX IF NOT EXISTS ix_post_metric_snapshots_post_captured
  ON post_metric_snapshots (post_id, captured_at);

CREATE TABLE IF NOT EXISTS collection_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  successes INTEGER NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  error TEXT
);

CREATE INDEX IF NOT EXISTS ix_collection_runs_started ON collection_runs (started_at);

