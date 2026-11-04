"""Citation pointers: parse and resolve page, slide, cell and time pointers.

Pointer forms: p.3, slide 4, Data!A2:J11 or Data!I11, t=42.5s.
resolve_citation() finds the chunk a pointer names (a single cell
resolves to the row window that contains it). The answer checks that
used to live here (one shared word) were replaced by api/answer.py,
which checks markers and numbers against the cited chunk.
"""

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import retrieval  # noqa: E402

REPO = HERE.parent
DEFAULT_CORPUS = REPO / "corpus"
DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres@localhost:5432/kohu")


TIME_RE = re.compile(r"t=(\d+(?:\.\d+)?)s")


def _parse_pointer(citation):
    """(page, cell_range, slide, t_start) from a citation dict, or None."""
    ptr = (citation or {}).get("pointer")
    if ptr is None:
        return None
    ptr = str(ptr).strip()
    m = re.fullmatch(r"p\.(\d+)", ptr)
    if m:
        return (int(m.group(1)), None, None, None)
    m = re.fullmatch(r"slide (\d+)", ptr)
    if m:
        return (None, None, int(m.group(1)), None)
    m = TIME_RE.fullmatch(ptr)
    if m:
        return (None, None, None, float(m.group(1)))
    if "!" not in ptr:
        return None
    return (None, ptr, None, None)


def _cell_in_range(cell_range, cell_pointer):
    """True when a window pointer contains a single-cell pointer.

    Both are ``Sheet!...`` pointers, e.g. window ``Q3-Growth!A2:F21``
    contains cell ``Q3-Growth!E12``.
    """
    win = re.fullmatch(r"(.+)!([A-Z]+)(\d+):([A-Z]+)(\d+)",
                       cell_range or "")
    cel = re.fullmatch(r"(.+)!([A-Z]+)(\d+)", cell_pointer or "")
    if not win or not cel or win.group(1) != cel.group(1):
        return False
    _, c1, r1, c2, r2 = win.groups()
    _, col, row = cel.groups()
    return c1 <= col <= c2 and int(r1) <= int(row) <= int(r2)


def resolve_citation(citation, source_id, conn):
    """Fetch the cited chunk row, or None when unresolvable.

    A single-cell pointer (``Sheet!E12``) resolves to the chunk whose
    window contains that cell; a window pointer must match exactly.
    """
    if not citation or not source_id:
        return None
    triple = _parse_pointer(citation)
    if triple is None:
        return None
    page, cell_range, slide, t_start = triple
    if t_start is not None:
        return conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide, t_start "
            "FROM chunks WHERE source_id = %s AND abs(t_start - %s) < 0.05",
            (source_id, t_start)).fetchone()
    if page is not None:
        return conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide "
            "FROM chunks WHERE source_id = %s AND page = %s",
            (source_id, page)).fetchone()
    if slide is not None:
        return conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide "
            "FROM chunks WHERE source_id = %s AND slide = %s",
            (source_id, slide)).fetchone()
    row = conn.execute(
        "SELECT id, source_id, text, page, cell_range, slide "
        "FROM chunks WHERE source_id = %s AND cell_range = %s",
        (source_id, cell_range)).fetchone()
    if row is not None:
        return row
    if re.fullmatch(r".+![A-Z]+\d+", cell_range or ""):
        rows = conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide "
            "FROM chunks WHERE source_id = %s AND cell_range IS NOT NULL",
            (source_id,)).fetchall()
        for candidate in rows:
            if _cell_in_range(candidate[4], cell_range):
                return candidate
    return None


if __name__ == "__main__":
    raise SystemExit("library module; see api/answer.py for answer checks")
