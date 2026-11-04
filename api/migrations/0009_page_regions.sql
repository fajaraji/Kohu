-- Kohu migration 0009 (up): SAM-marked regions on PDF pages (A7).
-- One row per marked chart or table: the SAM box, the rendered page and
-- mask images (file names under corpus/derived/<source_id>/), and the
-- Muse Spark reading of the cropped region.
CREATE TABLE IF NOT EXISTS page_regions (
  source_id TEXT NOT NULL,
  page INTEGER NOT NULL CONSTRAINT page_regions_page_check CHECK (page >= 1),
  k INTEGER NOT NULL DEFAULT 1,
  phrase TEXT NOT NULL,
  box JSONB,
  page_png TEXT,
  mask_png TEXT,
  reading TEXT,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, page, k)
);
