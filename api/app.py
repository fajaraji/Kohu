"""Kohu API.

Run:  uvicorn api.app:app --port 8000   (UI served at /)

Every route that touches content reads the persona from a signed token
(api/auth.py): `Authorization: Bearer <token>`, or `?token=` for media
elements that cannot send headers. Source files are served only through
GET /files/{source_id}, which checks the persona may see that source.
There is no static mount of the corpus folder.
"""

import os
import pathlib
import re
import sys
from contextlib import asynccontextmanager

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import auth  # noqa: E402
import corpus  # noqa: E402
import db  # noqa: E402
import migrate  # noqa: E402
import policy  # noqa: E402

REPO = HERE.parent
CORPUS_DIR = pathlib.Path(os.environ.get("KOHU_CORPUS", REPO / "corpus"))
DERIVED_DIR = CORPUS_DIR / "derived"
MEDIA_TYPES = {".pdf": "application/pdf", ".mp4": "video/mp4",
               ".png": "image/png", ".pptx": "application/vnd.openxmlformats-"
               "officedocument.presentationml.presentation",
               ".xlsx": "application/vnd.openxmlformats-officedocument."
               "spreadsheetml.sheet"}


def database_url():
    return db.database_url()


@asynccontextmanager
async def _lifespan(app):
    migrate.ensure_up_once(database_url())
    yield


app = FastAPI(title="Kohu", lifespan=_lifespan)


# ------------------------------------------------------------------ auth

def session(request: Request):
    """Verified {"persona", "user"} from the bearer header or ?token=."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else None
    token = token or request.query_params.get("token")
    try:
        return auth.verify(token)
    except auth.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None


def steward_only(s=Depends(session)):
    if s["persona"] != policy.STEWARD:
        raise HTTPException(status_code=403,
                            detail="this action is for the Steward only")
    return s


class LoginRequest(BaseModel):
    persona: str = Field(description="employee, analyst, manager or steward")
    user: str | None = Field(default=None, description="optional user name")


@app.post("/login")
def login(req: LoginRequest):
    try:
        token = auth.issue(req.persona, req.user)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    s = auth.verify(token)
    return {"token": token, "persona": s["persona"], "user": s["user"],
            "label": policy.PERSONA_LABELS[s["persona"]]}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/me")
def me(s=Depends(session)):
    return {**s, "label": policy.PERSONA_LABELS[s["persona"]]}


# ----------------------------------------------------------------- files

def _visible_entry(source_id, persona):
    """Manifest entry when visible; 404 for unknown, 403 for denied."""
    e = corpus.entry(source_id, CORPUS_DIR)
    if e is None:
        raise HTTPException(status_code=404, detail="no such source")
    if not policy.can_see(persona, source_id, CORPUS_DIR):
        raise HTTPException(status_code=403,
                            detail="your role does not cover this source")
    return e


@app.get("/files/{source_id}")
def get_file(source_id: str, s=Depends(session)):
    e = _visible_entry(source_id, s["persona"])
    path = corpus.source_path(e, CORPUS_DIR).resolve()
    if not path.is_file() or CORPUS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(path, media_type=MEDIA_TYPES.get(
        path.suffix.lower(), "application/octet-stream"),
        filename=path.name, content_disposition_type="inline")


@app.get("/files/{source_id}/assets/{name}")
def get_asset(source_id: str, name: str, s=Depends(session)):
    """Derived images (video frames, SAM marks, page renders)."""
    _visible_entry(source_id, s["persona"])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.png", name):
        raise HTTPException(status_code=404, detail="no such asset")
    path = DERIVED_DIR / source_id / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such asset")
    return FileResponse(path, media_type="image/png")


@app.get("/sources")
def sources(s=Depends(session)):
    out = []
    for e in corpus.load_manifest(CORPUS_DIR)["entries"]:
        if s["persona"] not in e.get("visible_to", []):
            continue
        out.append({"source_id": e["id"], "title": e.get("title"),
                    "kind": e.get("kind"), "origin": e.get("origin"),
                    "license": policy.license_info(e["id"])})
    return {"persona": s["persona"], "sources": out}


# ------------------------------------------------------------------- ask

class AskRequest(BaseModel):
    query: str = Field(description="non-empty question")


@app.post("/ask")
def ask(req: AskRequest, s=Depends(session)):
    """Agent answer for the token's persona (never a persona in the body)."""
    import psycopg
    import agent

    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=422,
                            detail="query must be a non-empty string")
    if len(query) > 500:
        raise HTTPException(status_code=422, detail="query is too long")
    try:
        return agent.run(query, s["persona"], s["user"], database_url(),
                         CORPUS_DIR)
    except psycopg.OperationalError:
        raise HTTPException(status_code=503,
                            detail="database unavailable; try again shortly")


@app.get("/runs/{run_id}/steps")
def run_steps(run_id: str, s=Depends(session)):
    import agent

    if not agent.valid_run_id(run_id):
        raise HTTPException(status_code=404, detail="no such run")
    out = agent.run_steps(run_id, s["persona"], database_url(), CORPUS_DIR)
    if out is None:
        raise HTTPException(status_code=404, detail="no such run")
    return out


@app.get("/steward/queue")
def steward_queue(s=Depends(steward_only)):
    import conflict
    return {"persona": s["persona"],
            "conflicts": conflict.list_conflicts(s["persona"], database_url(),
                                                 CORPUS_DIR, status="open")}


UI_DIR = REPO / "ui"
if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
