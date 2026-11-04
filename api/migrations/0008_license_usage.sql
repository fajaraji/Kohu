-- Kohu migration 0008 (up): who used licensed data.
-- One row each time an answer cites a licensed source. sample = true marks
-- the seeded baseline rows, which the app labels as sample data.
CREATE TABLE IF NOT EXISTS source_access_log (
  id BIGSERIAL PRIMARY KEY,
  source_id TEXT NOT NULL,
  persona TEXT NOT NULL,
  user_id TEXT NOT NULL,
  run_id TEXT,
  pointer TEXT,
  sample BOOLEAN NOT NULL DEFAULT false,
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS source_access_log_source_at_idx
  ON source_access_log (source_id, at);
