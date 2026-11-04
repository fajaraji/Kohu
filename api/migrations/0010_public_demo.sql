-- Kohu migration 0010 (up): public demo safety.
--
-- visitor_decisions: in public demo mode (KOHU_PUBLIC_DEMO=1) a Steward
-- decision is stored per visitor, so one visitor cannot change what the
-- next visitor or a judge sees. The shared conflicts table stays open.
-- meta_usage: Meta API usage per call, so the spend stop survives a
-- container restart (the JSONL log in logs/ does not).
CREATE TABLE IF NOT EXISTS visitor_decisions (
  visitor TEXT NOT NULL,
  conflict_id TEXT NOT NULL,
  status TEXT NOT NULL CONSTRAINT visitor_decisions_status_check
    CHECK (status IN ('resolved', 'dismissed')),
  winner TEXT CONSTRAINT visitor_decisions_winner_check
    CHECK (winner IS NULL OR winner IN ('a', 'b')),
  note TEXT,
  decided_by TEXT,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (visitor, conflict_id)
);

CREATE TABLE IF NOT EXISTS meta_usage (
  id BIGSERIAL PRIMARY KEY,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind TEXT NOT NULL,
  model TEXT,
  label TEXT,
  input_tokens BIGINT NOT NULL DEFAULT 0,
  output_tokens BIGINT NOT NULL DEFAULT 0,
  audio_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
  images INTEGER NOT NULL DEFAULT 0,
  usd DOUBLE PRECISION NOT NULL DEFAULT 0
);
