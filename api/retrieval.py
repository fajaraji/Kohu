"""Kohu retrieval: full text search, section reads and cell reads.

Every function takes the persona and filters by the sources that persona
may see BEFORE reading any row (source_id = ANY(visible)), so content
from a denied source never enters ranking, tool output or logs.

Search scoring (B3): Postgres ts_rank_cd over an English tsvector, pg_trgm
word_similarity, and term coverage (share of the query's content terms
found in the chunk). Chunks a Steward marked stale (a losing side of a
resolved conflict) are ranked lower.

  score = 0.6 * coverage + 0.3 * rank/(rank+1) + 0.1 * similarity
  (x 0.5 when stale)

MIN_RELEVANCE_SCORE = 0.4 was calibrated on this corpus (tests/test_b3_search.py):
gibberish scores nothing, the off-topic "What is the capital of France?"
peaks at 0.38, while on-topic queries put the right page first at 0.66
to 0.89.
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus  # noqa: E402
import db  # noqa: E402
import migrate  # noqa: E402
import policy  # noqa: E402

DEFAULT_CORPUS = corpus.DEFAULT_CORPUS
PERSONAS = policy.PERSONAS
MIN_RELEVANCE_SCORE = 0.4
STALE_FACTOR = 0.5

STOPWORDS = frozenset(
    "what was for and the a an of to in is it that with how why who which "
    "are were has have had this these those then than be been or on at by "
    "from do does did can could should would will i we you our my me us "
    "about tell much many any there their they them its when where".split())

KIND_OF_ANCHOR = {"page": "pdf", "slide": "deck", "cell-range": "sheet",
                  "timestamp": "video"}


def query_terms(text):
    terms = [t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
             if t not in STOPWORDS and len(t) >= 2]
    return sorted(set(terms))


def format_time(t):
    """Video pointer for a time in seconds, e.g. 42.5 -> 't=42.5s'."""
    return "t=%.1fs" % float(t)


def citation_for(row):
    """row: (id, source_id, text, page, cell_range, slide[, t_start])."""
    _, source_id, _, page, cell_range, slide = row[:6]
    t_start = row[6] if len(row) > 6 else None
    if t_start is not None:
        return {"source_id": source_id, "pointer": format_time(t_start)}
    if page is not None:
        return {"source_id": source_id, "pointer": "p.%d" % page}
    if slide is not None:
        return {"source_id": source_id, "pointer": "slide %d" % slide}
    return {"source_id": source_id, "pointer": cell_range}


def visible_ids(persona, kinds=None, corpus_dir=DEFAULT_CORPUS):
    ids = policy.visible_sources(persona, corpus_dir)
    if not kinds:
        return ids
    kinds = {k.strip().lower() for k in kinds}
    by_id = {e["id"]: e for e in corpus.load_manifest(corpus_dir)["entries"]}
    return [i for i in ids if KIND_OF_ANCHOR.get(
        by_id[i]["citation_anchors"]["type"]) in kinds]


def _coverage(text, terms):
    if not terms:
        return 0.0
    low = text.lower()
    words = set(re.findall(r"[a-z0-9]+", low))
    hit = 0
    for t in terms:
        if t in words or (len(t) >= 5 and t[:5] in low):
            hit += 1
    return hit / len(terms)


def _stale_keys(conn):
    import conflict
    return conflict.stale_keys(conn)


ROW_COLS = "c.id, c.source_id, c.text, c.page, c.cell_range, c.slide, c.t_start"


def _hit(row, score, stale, titles):
    return {"chunk_id": str(row[0]), "source_id": row[1],
            "title": titles.get(row[1], row[1]), "text": row[2],
            "citation": citation_for(row), "score": round(score, 4),
            "stale": stale}


def search(query, persona, database_url=None, kinds=None, limit=8,
           corpus_dir=DEFAULT_CORPUS, min_score=MIN_RELEVANCE_SCORE):
    """Ranked hits from sources the persona may see, best first."""
    import psycopg

    database_url = db.database_url(database_url)
    terms = query_terms(query)
    visible = visible_ids(persona, kinds, corpus_dir)
    if not terms or not visible:
        return []
    tsq = " | ".join(terms)
    raw = " ".join(terms)
    titles = corpus.titles(corpus_dir)
    migrate.ensure_up_once(database_url)
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT %s, ts_rank_cd(c.tsv, q, 32), word_similarity(%%s, c.text) "
            "FROM chunks c, to_tsquery('english', %%s) q "
            "WHERE c.source_id = ANY(%%s) AND (c.tsv @@ q "
            "OR word_similarity(%%s, c.text) > 0.5)" % ROW_COLS,
            (raw, tsq, visible, raw)).fetchall()
        stale = _stale_keys(conn)
    hits = []
    for r in rows:
        cov = _coverage(r[2], terms)
        score = 0.6 * cov + 0.3 * float(r[7]) + 0.1 * float(r[8])
        is_stale = (r[1], citation_for(r)["pointer"]) in stale
        if is_stale:
            score *= STALE_FACTOR
        if score >= min_score:
            hits.append(_hit(r, score, is_stale, titles))
    hits.sort(key=lambda h: (-h["score"], h["source_id"], h["chunk_id"]))
    return hits[:limit]


def read_section(chunk_id, persona, neighbors=0, database_url=None,
                 corpus_dir=DEFAULT_CORPUS):
    """The chunk and up to `neighbors` chunks either side, same source.

    Returns [] for an unknown chunk and for a chunk the persona may not
    see, with no difference between the two.
    """
    import psycopg

    database_url = db.database_url(database_url)
    visible = policy.visible_sources(persona, corpus_dir)
    neighbors = max(0, min(int(neighbors or 0), 2))
    titles = corpus.titles(corpus_dir)
    try:
        import uuid
        uuid.UUID(str(chunk_id))
    except ValueError:
        return []
    with psycopg.connect(database_url) as conn:
        base = conn.execute(
            "SELECT c.source_id, c.chunk_index FROM chunks c "
            "WHERE c.id = %s AND c.source_id = ANY(%s)",
            (chunk_id, visible)).fetchone()
        if base is None:
            return []
        rows = conn.execute(
            "SELECT %s FROM chunks c WHERE c.source_id = %%s AND "
            "c.chunk_index BETWEEN %%s AND %%s ORDER BY c.chunk_index"
            % ROW_COLS, (base[0], base[1] - neighbors,
                         base[1] + neighbors)).fetchall()
        stale = _stale_keys(conn)
    return [_hit(r, 1.0, (r[1], citation_for(r)["pointer"]) in stale, titles)
            for r in rows]


CELL_RE = re.compile(r"^(?:(?P<sheet>[^!]+)!)?(?P<c1>[A-Z]{1,2})(?P<r1>\d+)"
                     r"(?::(?P<c2>[A-Z]{1,2})(?P<r2>\d+))?$")


def _col_num(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def read_cells(source_id, cell_range, persona, corpus_dir=DEFAULT_CORPUS,
               max_cells=120):
    """Exact cell values from a sheet the persona may see.

    Returns {"source_id", "pointer", "text", "cells": {ref: value}} or None
    for an unknown or denied source (same answer for both).
    """
    from openpyxl import load_workbook

    if source_id not in set(policy.visible_sources(persona, corpus_dir)):
        return None
    e = corpus.entry(source_id, corpus_dir)
    if e is None or e["citation_anchors"]["type"] != "cell-range":
        return None
    m = CELL_RE.match((cell_range or "").strip().replace("$", ""))
    if not m:
        return None
    sheet = m.group("sheet") or e["citation_anchors"]["sheet"]
    c1, r1 = _col_num(m.group("c1")), int(m.group("r1"))
    c2 = _col_num(m.group("c2")) if m.group("c2") else c1
    r2 = int(m.group("r2")) if m.group("r2") else r1
    c1, c2 = sorted((c1, c2))
    r1, r2 = sorted((r1, r2))
    if (c2 - c1 + 1) * (r2 - r1 + 1) > max_cells:
        r2 = r1 + max(0, max_cells // (c2 - c1 + 1) - 1)
    wb = load_workbook(str(corpus.source_path(e, corpus_dir)),
                       read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        return None
    ws = wb[sheet]
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    cells, lines = {}, []
    import ingest
    for r_no, row in enumerate(ws.iter_rows(min_row=r1, max_row=r2,
                                            min_col=c1, max_col=c2,
                                            values_only=True), start=r1):
        parts = []
        for c_off, v in enumerate(row):
            ref = "%s%d" % (ingest.col_letter(c1 + c_off), r_no)
            cells[ref] = v
            col_name = header[c1 + c_off - 1] if c1 + c_off - 1 < len(
                header) else ""
            parts.append("%s (%s) = %s" % (ref, col_name, ingest.fmt_cell(v)))
        lines.append("; ".join(parts))
    wb.close()
    start = "%s%d" % (ingest.col_letter(c1), r1)
    end = "%s%d" % (ingest.col_letter(c2), r2)
    pointer = "%s!%s" % (sheet, start if start == end else start + ":" + end)
    return {"source_id": source_id, "pointer": pointer,
            "title": corpus.titles(corpus_dir).get(source_id, source_id),
            "text": "\n".join(lines), "cells": cells}


def read_grid(source_id, pointer, persona, corpus_dir=DEFAULT_CORPUS,
              pad_rows=2):
    """Header + rows around a cited cell or window, for the citation panel.

    Returns {"sheet", "header": [...], "rows": [{"row": n, "cells": [...]}],
    "highlight": {"rows": [r1, r2], "cols": [c1, c2]}} or None when the
    source is unknown or denied.
    """
    from openpyxl import load_workbook
    import ingest

    if source_id not in set(policy.visible_sources(persona, corpus_dir)):
        return None
    e = corpus.entry(source_id, corpus_dir)
    if e is None or e["citation_anchors"]["type"] != "cell-range":
        return None
    m = CELL_RE.match((pointer or "").strip())
    if not m:
        return None
    sheet = m.group("sheet") or e["citation_anchors"]["sheet"]
    c1, r1 = _col_num(m.group("c1")), int(m.group("r1"))
    c2 = _col_num(m.group("c2")) if m.group("c2") else c1
    r2 = int(m.group("r2")) if m.group("r2") else r1
    window = (c1 == 1 and r2 - r1 >= 1)
    lo = r1 if window else max(2, r1 - pad_rows)
    hi = r2 if window else r2 + pad_rows
    hi = min(hi, lo + 60)  # the panel shows a window, never a whole sheet
    wb = load_workbook(str(corpus.source_path(e, corpus_dir)),
                       read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        return None
    ws = wb[sheet]
    header = [ingest.fmt_cell(v) for v in next(
        ws.iter_rows(min_row=1, max_row=1, values_only=True))]
    rows = [{"row": n, "cells": [ingest.fmt_cell(v) for v in r]}
            for n, r in enumerate(ws.iter_rows(min_row=lo, max_row=hi,
                                               values_only=True), start=lo)]
    wb.close()
    return {"sheet": sheet, "header": header,
            "letters": [ingest.col_letter(i + 1) for i in range(len(header))],
            "rows": rows, "highlight": {"rows": [r1, r2], "cols": [c1, c2]},
            "window": window}


# ------------------------------------------------- legacy compatibility

def meets_relevance(score):
    return (score or 0) >= MIN_RELEVANCE_SCORE


def load_manifest(corpus_dir=DEFAULT_CORPUS):
    return corpus.load_manifest(corpus_dir)


def allowed_sources(persona, manifest=None):
    return policy.visible_sources(persona)


def retrieve(query, persona, run_id=None, database_url=None,
             corpus_dir=DEFAULT_CORPUS, limit=50):
    """Candidates for the legacy extractive path (no planner needed)."""
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    return search(query, persona, database_url, limit=limit,
                  corpus_dir=corpus_dir, min_score=0.0)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Kohu search")
    ap.add_argument("--persona", required=True, choices=PERSONAS)
    ap.add_argument("query")
    args = ap.parse_args(argv)
    for h in search(args.query, args.persona, limit=10):
        print("%.3f %s %s%s  %.70s" % (
            h["score"], h["source_id"], h["citation"]["pointer"],
            " (stale)" if h["stale"] else "",
            h["text"].replace("\n", " ")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
