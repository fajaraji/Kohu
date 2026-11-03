-- Kohu migration 0001 (down): rollback for 0001_chunks.sql.
--
-- Drops the chunks table. Dropping data is destructive; the runner only runs
-- this on an explicit `migrate.py down` request, never implicitly.

DROP TABLE IF EXISTS chunks;
