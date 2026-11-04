-- Kohu migration 0004 (down).
DROP TABLE IF EXISTS video_jobs;
DROP TABLE IF EXISTS guide_steps;
DROP TABLE IF EXISTS transcripts;
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_citation_present_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_citation_present_check CHECK (
  page IS NOT NULL OR cell_range IS NOT NULL OR slide IS NOT NULL);
ALTER TABLE chunks DROP COLUMN IF EXISTS text_origin;
ALTER TABLE chunks DROP COLUMN IF EXISTS t_start;
