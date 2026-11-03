-- Kohu migration 0007 (up): detected conflicts and Steward decisions.
--
-- A conflict is two sources stating different things about the same fact.
-- Sides are stable keys (source_id, pointer), so re-ingest keeps them.
-- conflict_id is a hash of the two sides. Every Spark judgment is kept
-- in conflict_judgments (conflict or not) for the eval. A resolved
-- conflict marks the losing side stale: search ranks it lower and the
-- answer step labels it superseded. Replaces the fixed seeded pair in
-- steward_tasks, which is dropped.

CREATE TABLE IF NOT EXISTS conflict_judgments (
  pair_id TEXT PRIMARY KEY,
  a_source TEXT NOT NULL, a_pointer TEXT NOT NULL,
  b_source TEXT NOT NULL, b_pointer TEXT NOT NULL,
  is_conflict BOOLEAN NOT NULL,
  result JSONB NOT NULL DEFAULT '{}',
  judge TEXT NOT NULL DEFAULT 'spark',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conflicts (
  conflict_id TEXT PRIMARY KEY,
  a_source TEXT NOT NULL, a_pointer TEXT NOT NULL, a_text TEXT NOT NULL,
  b_source TEXT NOT NULL, b_pointer TEXT NOT NULL, b_text TEXT NOT NULL,
  summary TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'medium'
    CONSTRAINT conflicts_severity_check CHECK (severity IN
      ('low', 'medium', 'high')),
  evidence_a TEXT, evidence_b TEXT,
  judge TEXT NOT NULL DEFAULT 'spark',
  status TEXT NOT NULL DEFAULT 'open'
    CONSTRAINT conflicts_status_check CHECK (status IN
      ('open', 'resolved', 'dismissed')),
  winner TEXT CONSTRAINT conflicts_winner_check CHECK (winner IS NULL
    OR winner IN ('a', 'b')),
  note TEXT,
  resolved_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ,
  CONSTRAINT conflicts_resolution_check CHECK (
    (status = 'resolved' AND winner IS NOT NULL) OR
    (status <> 'resolved' AND winner IS NULL))
);

CREATE INDEX IF NOT EXISTS conflicts_a_idx ON conflicts (a_source, a_pointer);
CREATE INDEX IF NOT EXISTS conflicts_b_idx ON conflicts (b_source, b_pointer);

DROP TABLE IF EXISTS steward_tasks;
