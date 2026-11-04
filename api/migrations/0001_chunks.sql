-- Kohu migration 0001 (up): chunks table for cited, license-filtered RAG.
--
-- Contract (PRD.md FR2, PLAN.md section 3, corpus/manifest.json):
--   chunk = text + source id + license class + citation pointer
--   (page for PDFs, cell range for sheets, slide for decks).
-- License class is set at ingest and is immutable at query time (enforced
-- by never UPDATEing it; see T22). Canonical values:
--   'open-internal', 'licensed', 'manager-restricted'.
--
-- Safety: additive-only initial migration. All statements are
-- IF NOT EXISTS so a retried run is a no-op once applied. The runner
-- (api/migrate.py) additionally records each applied version in
-- schema_migrations inside the same transaction, so partial failure
-- leaves no half-applied version marked done.
-- Rollback: api/migrations/0001_chunks.down.sql.
-- Requires: Postgres >= 13 (gen_random_uuid is built-in).
-- History: the first version created a pgvector embedding column that was
-- never filled. It was removed (search is Postgres full text, see 0005);
-- databases that already applied the old version drop it in 0005.

CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id TEXT NOT NULL,
  license_class TEXT NOT NULL
    CONSTRAINT chunks_license_class_check
    CHECK (license_class IN ('open-internal', 'licensed', 'manager-restricted')),
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL
    CONSTRAINT chunks_text_nonempty_check CHECK (char_length(text) > 0),
  -- Citation pointer: exactly the anchor kind the source uses.
  -- PDF page (>= 1), e.g. handbook p.4.
  page INTEGER
    CONSTRAINT chunks_page_check CHECK (page IS NULL OR page >= 1),
  -- Sheet range with sheet name, e.g. 'Q3-Growth!A1:F200'.
  cell_range TEXT,
  -- Deck slide number (>= 1), e.g. sales-deck slide 7.
  slide INTEGER
    CONSTRAINT chunks_slide_check CHECK (slide IS NULL OR slide >= 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chunks_source_chunk_unique UNIQUE (source_id, chunk_index),
  -- Every chunk must carry at least one citation anchor (FR4/AC7).
  CONSTRAINT chunks_citation_present_check CHECK (
    page IS NOT NULL OR cell_range IS NOT NULL OR slide IS NOT NULL
  )
);

CREATE INDEX IF NOT EXISTS chunks_source_id_idx ON chunks (source_id);
CREATE INDEX IF NOT EXISTS chunks_license_class_idx ON chunks (license_class);
