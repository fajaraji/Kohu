"""Kohu access policy: who may see which source, and what was licensed.

Access is decided per source from corpus/manifest.json "visible_to"
(merged with manifest.local.json for uploaded videos). Every read path
(search, read_section, read_cells, file download, run trace, conflict
view) filters through visible_sources() before it touches content.

License coverage is the point of the demo: the company paid for the
ASEAN report under a company-wide license, so every employee may read
and cite it, while the full dataset is seat-limited to Analyst and
Steward. Vendor, terms and seats are simulated and labeled.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus  # noqa: E402

PERSONAS = ("employee", "analyst", "manager", "steward")
PERSONA_LABELS = {"employee": "Employee (new hire)",
                  "analyst": "Analyst (dataset seat)",
                  "manager": "Manager",
                  "steward": "Steward (data admin)"}
STEWARD = "steward"
VIDEO_EDITORS = ("manager", "steward")

# Simulated license terms. Shown in the app with a "simulated" label.
LICENSE_REGISTRY = {
    "asean-outlook-report": {
        "vendor": "Meridian Market Data (simulated vendor)",
        "product": "ASEAN Economic Indicators Report 2019 to 2024",
        "coverage": "Company-wide: every employee may read and cite it",
        "seats": None,
        "term": "2026-01-01 to 2026-12-31",
        "annual_cost_usd": 18000,
        "simulated": True},
    "asean-indicators-dataset": {
        "vendor": "Meridian Market Data (simulated vendor)",
        "product": "ASEAN indicators dataset, full values",
        "coverage": "Seat-limited: Analyst and Steward roles only",
        "seats": 5,
        "term": "2026-01-01 to 2026-12-31",
        "annual_cost_usd": 24000,
        "simulated": True},
}


def check_persona(persona):
    if persona not in PERSONAS:
        raise ValueError("unknown persona %r (want one of %s)"
                         % (persona, ", ".join(PERSONAS)))
    return persona


def visible_sources(persona, corpus_dir=corpus.DEFAULT_CORPUS):
    """Sorted source ids the persona may see. Raises on unknown persona."""
    check_persona(persona)
    return sorted(e["id"] for e in corpus.load_manifest(corpus_dir)["entries"]
                  if persona in e.get("visible_to", []))


def can_see(persona, source_id, corpus_dir=corpus.DEFAULT_CORPUS):
    return source_id in set(visible_sources(persona, corpus_dir))


def license_info(source_id):
    """License card for a licensed source, else None."""
    info = LICENSE_REGISTRY.get(source_id)
    return dict(info, source_id=source_id) if info else None


def is_licensed(source_id):
    return source_id in LICENSE_REGISTRY


# Backwards-compatible names used by older modules.
def allowed_sources(persona, manifest=None):
    return visible_sources(persona)


def enforce(candidates, persona, run_id=None, database_url=None,
            corpus_dir=corpus.DEFAULT_CORPUS):
    """Drop any candidate from a source the persona may not see.

    Defense in depth for the extractive path: search already filters by
    source, and this re-check drops anything smuggled in. Licensed
    sources the persona may see carry their license card.
    """
    visible = set(visible_sources(persona, corpus_dir))
    allowed = []
    for c in candidates:
        if c["source_id"] not in visible:
            continue
        row = dict(c)
        lic = license_info(c["source_id"])
        if lic:
            row["license"] = lic
        allowed.append(row)
    return {"allowed": allowed, "stubs": []}
