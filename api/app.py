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
import subprocess
import sys
from contextlib import asynccontextmanager

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fastapi import (Depends, FastAPI, File, Form, HTTPException,  # noqa: E402
                     Request, UploadFile)
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import auth  # noqa: E402
import corpus  # noqa: E402
import db  # noqa: E402
import demo  # noqa: E402
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
    if demo.public() and len(os.environ.get("KOHU_SESSION_SECRET", "")) < 16:
        raise RuntimeError("KOHU_PUBLIC_DEMO=1 needs KOHU_SESSION_SECRET of "
                           "at least 16 characters")
    migrate.ensure_up_once(database_url())
    yield


app = FastAPI(title="Kohu", lifespan=_lifespan)

SECURITY_HEADERS = {
    # Media URLs carry ?token=, so never send them on as a Referer.
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self'; "
        "style-src 'self'; script-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"),
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


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
    visitor: str | None = Field(default=None, description="browser id, 8-32 "
                                "hex; groups personas of one visitor")


@app.post("/login")
def login(req: LoginRequest):
    visitor = req.visitor if re.fullmatch(r"[a-f0-9]{8,32}",
                                          req.visitor or "") else None
    user = req.user
    if demo.public():
        # Each visitor counts as their own user in license usage.
        visitor = visitor or auth.new_visitor()
        user = "%s-%s" % (req.persona, visitor[:8])
    try:
        token = auth.issue(req.persona, user, visitor=visitor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    s = auth.verify(token)
    return {"token": token, "persona": s["persona"], "user": s["user"],
            "visitor": s["visitor"],
            "label": policy.PERSONA_LABELS[s["persona"]]}


@app.get("/config")
def config():
    """What the UI should offer (public demo hides shared-state editing)."""
    return {"public_demo": demo.public(),
            "uploads": not demo.public(),
            "step_editing": not demo.public()}


@app.post("/demo/reset")
def demo_reset(s=Depends(session)):
    """Forget this visitor's Steward decisions (public demo only)."""
    import conflict
    if not demo.public():
        raise HTTPException(status_code=404, detail="only in public demo")
    return {"cleared": conflict.reset_visitor(s["visitor"], database_url())}


def client_ip(request: Request):
    # Only trust Cloudflare's header when the app is known to sit behind
    # Cloudflare; otherwise any client could rotate it to dodge limits.
    if os.environ.get("KOHU_BEHIND_CLOUDFLARE") == "1":
        ip = request.headers.get("cf-connecting-ip")
        if ip:
            return ip
    # Vercel sets x-real-ip itself and overwrites what the client sent.
    if os.environ.get("KOHU_BEHIND_VERCEL") == "1":
        ip = request.headers.get("x-real-ip")
        if ip:
            return ip
    return request.client.host if request.client else "unknown"


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


@app.get("/cells/{source_id}")
def cells(source_id: str, range: str, s=Depends(session)):  # noqa: A002
    """Rows around a cited cell or window, for the citation panel."""
    import retrieval
    _visible_entry(source_id, s["persona"])
    out = retrieval.read_grid(source_id, range, s["persona"], CORPUS_DIR)
    if out is None:
        raise HTTPException(status_code=404, detail="no such range")
    return out


@app.get("/files/{source_id}/slide/{n}.png")
def slide_image(source_id: str, n: int, s=Depends(session)):
    """A deck slide rendered at build time (corpus/build_slides.py)."""
    e = _visible_entry(source_id, s["persona"])
    path = DERIVED_DIR / source_id / ("slide-%02d.png" % n)
    if e.get("kind") != "deck" or n < 1 or not path.is_file():
        raise HTTPException(status_code=404, detail="no such slide")
    return FileResponse(path, media_type="image/png")


@app.get("/files/{source_id}/page/{page}.png")
def page_image(source_id: str, page: int, hl: str = "", s=Depends(session)):
    """A PDF page rendered as PNG, with optional highlighted text."""
    import pymupdf
    from fastapi.responses import Response

    e = _visible_entry(source_id, s["persona"])
    if e.get("kind") != "pdf":
        raise HTTPException(status_code=404, detail="not a PDF source")
    doc = pymupdf.open(str(corpus.source_path(e, CORPUS_DIR)))
    if not 1 <= page <= doc.page_count:
        raise HTTPException(status_code=404, detail="no such page")
    pg = doc[page - 1]
    for needle in [h.strip() for h in hl.split("||") if h.strip()][:4]:
        for rect in pg.search_for(needle[:200]):
            annot = pg.add_highlight_annot(rect)
            annot.update()
    png = pg.get_pixmap(dpi=110).tobytes("png")
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300"})


@app.get("/regions/{source_id}/{page}")
def page_regions(source_id: str, page: int, s=Depends(session)):
    """SAM-marked chart or table regions on a PDF page (A7)."""
    import regions
    _visible_entry(source_id, s["persona"])
    return {"source_id": source_id, "page": page,
            "regions": regions.regions(source_id, page, database_url())}


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
    run_id: str | None = Field(default=None, description="optional client "
                               "chosen run id (32 hex) to poll progress")


@app.post("/ask")
def ask(req: AskRequest, request: Request, s=Depends(session)):
    """Agent answer for the token's persona (never a persona in the body)."""
    import psycopg
    import agent

    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=422,
                            detail="query must be a non-empty string")
    if len(query) > 500:
        raise HTTPException(status_code=422, detail="query is too long")
    limited = demo.check_ask(s["visitor"], client_ip(request))
    if limited:
        raise HTTPException(status_code=429, detail=limited)
    if req.run_id is not None and not agent.valid_run_id(req.run_id):
        raise HTTPException(status_code=422, detail="run_id must be 32 hex")
    if req.run_id and agent.run_steps(req.run_id, s["persona"],
                                      database_url(), CORPUS_DIR):
        raise HTTPException(status_code=409, detail="run_id already used")
    try:
        with demo.visitor_scope(s["visitor"]):
            return agent.run(query, s["persona"], s["user"], database_url(),
                             CORPUS_DIR, run_id=req.run_id)
    except psycopg.OperationalError:
        raise HTTPException(status_code=503,
                            detail="database unavailable; try again shortly")


@app.get("/runs/{run_id}/steps")
def run_steps(run_id: str, s=Depends(session)):
    import agent

    if not agent.valid_run_id(run_id):
        raise HTTPException(status_code=404, detail="no such run")
    out = agent.run_steps(run_id, s["persona"], database_url(), CORPUS_DIR)
    # A trace holds the asker's question, so only the asker may read it
    # (a Steward may read any trace outside the public demo).
    owner_ok = out is not None and (
        out.get("user") == s["user"]
        or (s["persona"] == policy.STEWARD and not demo.public()))
    if not owner_ok:
        raise HTTPException(status_code=404, detail="no such run")
    out.pop("user", None)
    return out


# ---------------------------------------------------------------- video

def video_editor(s=Depends(session)):
    if demo.public():
        raise HTTPException(status_code=403, detail="Uploading and editing "
                            "videos is turned off in the public demo. The "
                            "processed example shows the result.")
    if s["persona"] not in policy.VIDEO_EDITORS:
        raise HTTPException(status_code=403, detail="only a Manager or the "
                            "Steward can upload or review videos")
    return s


def _video_entry(source_id, persona):
    e = _visible_entry(source_id, persona)
    if e.get("kind") != "video":
        raise HTTPException(status_code=404, detail="not a video source")
    return e


@app.post("/videos")
async def upload_video(file: UploadFile = File(...),
                       title: str = Form(default=""),
                       s=Depends(video_editor)):
    """Upload an MP4 (max 10 min, 200 MB) and start processing it."""
    import uuid
    import video

    if not (file.filename or "").lower().endswith(".mp4"):
        raise HTTPException(status_code=422, detail="MP4 files only")
    sid = "video-" + uuid.uuid4().hex[:10]
    rel = pathlib.Path("uploads") / (sid + ".mp4")
    dest = CORPUS_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with dest.open("wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > 200 * 1024 * 1024:
                f.close()
                dest.unlink()
                raise HTTPException(status_code=413, detail="file too large")
            f.write(chunk)
    import video
    try:
        info = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0",
             str(dest)], capture_output=True, text=True, timeout=30)
        ok = info.returncode == 0 and "video" in info.stdout
        ok = ok and 0 < video.duration(dest) <= video.MAX_SECONDS
    except (subprocess.SubprocessError, ValueError, OSError):
        ok = False
    if not ok:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="not a readable MP4 "
                            "video of at most 10 minutes")
    corpus.add_local_entry({
        "id": sid, "filename": str(rel), "kind": "video",
        "title": (title or file.filename)[:120], "origin": "uploaded",
        "license_class": "open-internal",
        "visible_to": list(policy.PERSONAS),
        "notice": "Uploaded by %s" % s["user"],
        "citation_anchors": {"type": "timestamp", "format": "t=<seconds>s"}},
        CORPUS_DIR)
    import psycopg
    with psycopg.connect(database_url()) as conn:
        video.set_status(conn, sid, "queued")
    video.process_async(sid, database_url(), CORPUS_DIR)
    return {"source_id": sid, "status": "queued"}


@app.get("/videos")
def list_videos(s=Depends(session)):
    import video
    out = []
    for e in corpus.load_manifest(CORPUS_DIR)["entries"]:
        if e.get("kind") == "video" and s["persona"] in e["visible_to"]:
            st = video.status(e["id"], database_url())
            out.append({"source_id": e["id"], "title": e.get("title"),
                        "status": st["status"] if st else "not processed"})
    return {"videos": out}


@app.get("/videos/{source_id}/status")
def video_status(source_id: str, s=Depends(session)):
    import video
    _video_entry(source_id, s["persona"])
    st = video.status(source_id, database_url())
    if st is None:
        raise HTTPException(status_code=404, detail="not processed yet")
    return st


@app.get("/videos/{source_id}/steps")
def video_steps(source_id: str, s=Depends(session)):
    import video
    e = _video_entry(source_id, s["persona"])
    rows = video.steps(source_id, database_url())
    if s["persona"] not in policy.VIDEO_EDITORS or demo.public():
        rows = [r for r in rows if r["approved"]]
    return {"source_id": source_id, "title": e.get("title"),
            "can_review": (s["persona"] in policy.VIDEO_EDITORS
                           and not demo.public()),
            "steps": rows}


class StepEdit(BaseModel):
    instruction: str | None = None
    reason: str | None = None
    clear_reason: bool = False
    shift_s: float | None = None


@app.patch("/videos/{source_id}/steps/{n}")
def edit_video_step(source_id: str, n: int, req: StepEdit,
                    s=Depends(video_editor)):
    import video
    _video_entry(source_id, s["persona"])
    if req.instruction is not None and not req.instruction.strip():
        raise HTTPException(status_code=422, detail="instruction is empty")
    ok = video.edit_step(source_id, n, req.instruction, req.reason,
                         req.shift_s, req.clear_reason, database_url())
    if not ok:
        raise HTTPException(status_code=404, detail="no such step")
    return {"ok": True}


class Approve(BaseModel):
    steps: list[int] | None = None


@app.post("/videos/{source_id}/approve")
def approve_video(source_id: str, req: Approve, s=Depends(video_editor)):
    import video
    _video_entry(source_id, s["persona"])
    return video.approve(source_id, req.steps, database_url(), CORPUS_DIR)


# -------------------------------------------------------------- licenses

@app.get("/licenses")
def licenses_route(s=Depends(session)):
    import licenses
    return {"persona": s["persona"],
            "cards": licenses.cards(s["persona"], database_url(), CORPUS_DIR)}


# ------------------------------------------------------------ conflicts

@app.get("/conflicts")
def conflicts(status: str | None = None, s=Depends(session)):
    """Conflicts whose two sides this persona may both see."""
    import conflict
    if status not in (None, "open", "resolved", "dismissed"):
        raise HTTPException(status_code=422, detail="bad status filter")
    with demo.visitor_scope(s["visitor"]):
        return {"persona": s["persona"],
                "can_decide": s["persona"] == policy.STEWARD,
                "decisions_are_private": demo.public(),
                "conflicts": conflict.list_conflicts(
                    s["persona"], database_url(), CORPUS_DIR, status)}


class Resolve(BaseModel):
    winner: str | None = Field(default=None, description="a or b")
    dismiss: bool = False
    note: str = ""


@app.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, req: Resolve,
                     s=Depends(steward_only)):
    import conflict
    if req.dismiss == (req.winner is not None):
        raise HTTPException(status_code=422,
                            detail="send either winner (a or b) or dismiss")
    if req.winner not in (None, "a", "b"):
        raise HTTPException(status_code=422, detail="winner must be a or b")
    with demo.visitor_scope(s["visitor"]):
        out = conflict.resolve(conflict_id, "dismiss" if req.dismiss
                               else req.winner, req.note, s["user"],
                               database_url())
    if out is None:
        raise HTTPException(status_code=404, detail="no such conflict")
    return out


@app.post("/conflicts/{conflict_id}/reopen")
def reopen_conflict(conflict_id: str, s=Depends(steward_only)):
    import conflict
    with demo.visitor_scope(s["visitor"]):
        if conflict.get(conflict_id, database_url()) is None:
            raise HTTPException(status_code=404, detail="no such conflict")
        conflict.reopen(conflict_id, database_url())
        return conflict.get(conflict_id, database_url())


@app.get("/steward/queue")
def steward_queue(s=Depends(steward_only)):
    import conflict
    with demo.visitor_scope(s["visitor"]):
        return {"persona": s["persona"],
                "conflicts": conflict.list_conflicts(
                    s["persona"], database_url(), CORPUS_DIR, status="open")}


UI_DIR = REPO / "ui"
if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
