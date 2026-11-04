-- Kohu migration 0005 (down). The pg_trgm extension is left in place.
DROP INDEX IF EXISTS chunks_text_trgm_idx;
DROP INDEX IF EXISTS chunks_tsv_idx;
ALTER TABLE chunks DROP COLUMN IF EXISTS tsv;
