-- Kohu migration 0005 (up): Postgres full text and trigram search.
--
-- Search is ts_rank over an English tsvector plus pg_trgm word
-- similarity, always filtered by source_id = ANY(visible sources).
-- The unused pgvector embedding column (never filled) is dropped, with
-- its index, on databases that still have it.
-- Rollback: 0005_search.down.sql.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP INDEX IF EXISTS chunks_embedding_idx;
ALTER TABLE chunks DROP COLUMN IF EXISTS embedding;

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_text_trgm_idx
  ON chunks USING gin (text gin_trgm_ops);
