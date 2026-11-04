-- Kohu migration 0004 (up): video citations, transcripts, guide steps,
-- and the origin of each chunk's text.
--
-- chunks.t_start: seconds into a video for chunks built from approved
--   guide steps; citation pointer form "t=42.5s".
-- chunks.text_origin: where the text came from (text-layer, spark-vision,
--   sidecar-fallback, video-step).
-- transcripts: one row per video, Muse Voice Transcribe turns as JSON.
-- guide_steps: steps Spark proposed from a video, with SAM marks; a
--   person reviews, edits and approves them before they become chunks.
-- Additive only. Rollback: 0004_video.down.sql.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS t_start DOUBLE PRECISION
  CONSTRAINT chunks_t_start_check CHECK (t_start IS NULL OR t_start >= 0);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_origin TEXT NOT NULL
  DEFAULT 'text-layer';

ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_citation_present_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_citation_present_check CHECK (
  page IS NOT NULL OR cell_range IS NOT NULL OR slide IS NOT NULL
  OR t_start IS NOT NULL);

CREATE TABLE IF NOT EXISTS transcripts (
  source_id TEXT PRIMARY KEY,
  turns JSONB NOT NULL DEFAULT '[]',
  text TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS guide_steps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id TEXT NOT NULL,
  n INTEGER NOT NULL CONSTRAINT guide_steps_n_check CHECK (n >= 1),
  t_start DOUBLE PRECISION NOT NULL
    CONSTRAINT guide_steps_t_start_check CHECK (t_start >= 0),
  t_end DOUBLE PRECISION NOT NULL,
  instruction TEXT NOT NULL,
  reason TEXT,
  target_phrase TEXT,
  box JSONB,
  mask_path TEXT,
  frame_path TEXT,
  mark_status TEXT NOT NULL DEFAULT 'pending'
    CONSTRAINT guide_steps_mark_status_check CHECK (mark_status IN
      ('pending', 'phrase', 'box', 'spark_box', 'failed')),
  approved BOOLEAN NOT NULL DEFAULT false,
  origin TEXT NOT NULL DEFAULT 'spark',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT guide_steps_source_n_unique UNIQUE (source_id, n),
  CONSTRAINT guide_steps_time_order_check CHECK (t_end >= t_start)
);

CREATE INDEX IF NOT EXISTS guide_steps_source_idx ON guide_steps (source_id);

-- Video processing jobs (status for GET /videos/{id}/status).
CREATE TABLE IF NOT EXISTS video_jobs (
  source_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'queued',
  detail JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
