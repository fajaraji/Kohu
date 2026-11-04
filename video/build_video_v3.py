"""Demo video v3: one Hyperframes timeline in the Kohu UI style.

  python video/build_video_v3.py --footage DIR --out video/kohu-demo.mp4

What it does
  1. Synthesizes the narration (Kokoro TTS, labeled synthetic) and times
     each segment to its narration, so there are no long gaps.
  2. Cuts each footage recording (video/capture.mjs) to fit: normal parts
     play at real speed, only the waiting on Muse Spark is sped up, and
     every sped-up stretch gets an on-screen label with its factor. If the
     normal parts are still too long, the whole segment is sped up and
     labeled.
  3. Writes a Hyperframes composition: animated opening, footage inside an
     app frame that zooms to what matters (from the capture's focus
     events), animated segment labels, captions, short transitions, an
     animated closing with the eval numbers.
  4. Renders it with Hyperframes and mixes narration over the original
     music bed (video/make_music.py), ducking the music under speech.
"""

import argparse
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
W, H, FPS = 1280, 720, 30
FRAME = 0.84                       # app frame size relative to the canvas
FW, FH = round(W * FRAME), round(H * FRAME)
TRIM = 1.0                         # page load at the start of each capture
SR = 24000
FONT = "Inter, 'DejaVu Sans', sans-serif"
LABELS = {
    "s2-process": ("New hire", "How do I process a customer refund?"),
    "s3-licensed": ("Licensed data", "Data the company already paid for"),
    "s4-seats": ("Seat-limited data", "Only the role with a seat sees the cells"),
    "s5-conflict": ("Two sources disagree", "A person decides, the answer changes"),
    "s6-upload": ("New recording", "A screen recording becomes reviewed steps"),
    "s7-licenses": ("License usage", "Who actually used the paid data"),
}
STATS = [("96 / 100", "answers passed: 20 frozen questions, five live runs"),
         ("0 / 74", "access checks leaked a source the role cannot see"),
         ("2 / 3", "planted conflicts caught, 0 of 3 control pairs flagged"),
         ("4 / 5", "steps found and marked on a recording made after tuning")]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def dur(path):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "csv=p=0", str(path)], capture_output=True, text=True,
        check=True).stdout.strip())


# --------------------------------------------------------------- narration

def synth(segments, voice):
    from kokoro_onnx import Kokoro
    kdir = pathlib.Path(os.environ.get("KOKORO_DIR", "/tmp/claude-0/tts"))
    k = Kokoro(str(kdir / "kokoro-v1.0.int8.onnx"), str(kdir / "voices-v1.0.bin"))
    out = {}
    for s in segments:
        text = re.sub(r"\[pause [0-9.]+\]\s*", "", s["say"])
        sents = [x.strip() for x in re.split(r"(?<=[.?!])\s+", text) if x.strip()]
        parts, cues, t = [], [], 0.0
        for sent in sents:
            a, sr = k.create(sent, voice=voice, speed=1.06, lang="en-us")
            a = np.asarray(a, dtype=np.float32)
            for c0, c1, txt in phrase_cues(a, sent):
                cues.append((t + c0, t + c1, txt))
            parts += [a, np.zeros(int(0.18 * SR), dtype=np.float32)]
            t += len(a) / SR + 0.18
        out[s["id"]] = (np.concatenate(parts), cues, t)
    return out


MAX_CHARS = 42      # one short caption line


def chunks(sent):
    """Split a sentence into short caption phrases: clauses first (after
    commas), then long clauses into balanced pieces, then tiny pieces
    merged with a neighbour."""
    keep = {"Viet Nam": "Viet_Nam", "Muse Spark": "Muse_Spark", "SAM 3.1": "SAM_3.1"}
    for k, v in keep.items():
        sent = sent.replace(k, v)
    clauses, cur = [], []
    for w in sent.split():
        cur.append(w)
        if w.endswith(","):
            clauses.append(cur)
            cur = []
    if cur:
        clauses.append(cur)
    pieces = []
    for c in clauses:
        n = -(-len(" ".join(c)) // (MAX_CHARS + 4))
        target = len(" ".join(c)) / n
        part = []
        for w in c:
            if part and len(pieces) < 99 and len(" ".join(part)) >= target - 4 and n > 1:
                pieces.append(part)
                part, n = [], n - 1
            part.append(w)
        pieces.append(part)
    out = []
    for p in pieces:
        if out and (len(" ".join(p)) < 14 or len(" ".join(out[-1])) < 14) \
                and len(" ".join(out[-1] + p)) <= MAX_CHARS + 6:
            out[-1] = out[-1] + p
        else:
            out.append(p)
    return [" ".join(c).replace("_", " ") for c in out]


def phrase_cues(audio, sent):
    """(start, end, text) per phrase within one sentence's audio.

    Kokoro gives no word times, so each phrase boundary is first placed in
    proportion to its characters, then moved to the nearest pause in the
    audio within 0.35 s. Speech is found with a 10 ms energy envelope.
    """
    parts = chunks(sent)
    dur = len(audio) / SR
    hop = SR // 100
    env = np.array([np.sqrt(np.mean(audio[i:i + hop] ** 2))
                    for i in range(0, max(1, len(audio) - hop), hop)])
    loud = env > 0.08 * (env.max() if len(env) else 1)
    voiced = np.nonzero(loud)[0]
    s0 = voiced[0] / 100 if len(voiced) else 0.0
    s1 = (voiced[-1] + 1) / 100 if len(voiced) else dur
    pauses = []   # centres of quiet runs of at least 50 ms inside speech
    run = 0
    for i, v in enumerate(loud):
        if not v:
            run += 1
        else:
            if run >= 5 and i / 100 > s0 + 0.2:
                pauses.append((i - run / 2) / 100)
            run = 0
    total = sum(len(p) for p in parts)
    bounds, acc = [s0], 0
    for p in parts[:-1]:
        acc += len(p)
        guess = s0 + (s1 - s0) * acc / total
        near = [q for q in pauses if abs(q - guess) <= 0.35 and q > bounds[-1] + 0.3]
        bounds.append(min(near, key=lambda q: abs(q - guess)) if near else guess)
    bounds.append(s1)
    lead = 0.1   # show each phrase just before it is spoken
    return [(max(0.0, bounds[i] - lead), bounds[i + 1] - (lead if i + 1 < len(parts) else 0.0), parts[i])
            for i in range(len(parts))]


# ----------------------------------------------------------------- footage

def plan_footage(ev, slot):
    """[(a, b, factor, is_wait)] in source time so output length == slot."""
    waits = sorted((e["start"], e["end"]) for e in ev["events"] if e["type"] == "wait")
    pieces, t = [], TRIM
    for a, b in waits:
        if a > t:
            pieces.append((t, a, False))
        pieces.append((max(a, t), b, True))
        t = b
    if ev["total"] - 0.6 > t:
        pieces.append((t, ev["total"] - 0.6, False))
    pieces = [p for p in pieces if p[1] - p[0] > 0.05]
    normal = sum(b - a for a, b, w in pieces if not w)
    wait = sum(b - a for a, b, w in pieces if w)
    min_wait = 1.2 * sum(1 for p in pieces if p[2])
    if normal + min_wait <= slot:
        f = wait / max(slot - normal, 0.1) if wait else 1.0
        return [(a, b, max(f, 1.0) if w else 1.0, w) for a, b, w in pieces], 1.0
    g = normal / max(slot - min_wait, 0.1)
    return [(a, b, (b - a) / 1.2 if w else g, w) for a, b, w in pieces], g


def cut_footage(src, ev, slot, out, tmp):
    plan, g = plan_footage(ev, slot)
    parts, spans, t_out = [], [], 0.0
    for i, (a, b, f, w) in enumerate(plan):
        p = tmp / ("%s-%02d.mp4" % (out.stem, i))
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % a, "-to", "%.3f" % b,
             "-i", str(src), "-an", "-vf", "setpts=(PTS-STARTPTS)/%.5f,fps=%d,scale=%d:%d"
             % (f, FPS, W, H), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-pix_fmt", "yuv420p", str(p)])
        d = (b - a) / f
        spans.append({"a": a, "b": b, "f": f, "wait": w, "out0": t_out, "out1": t_out + d})
        t_out += d
        parts.append(p)
    lst = tmp / (out.stem + ".txt")
    lst.write_text("".join("file '%s'\n" % p for p in parts))
    joined = tmp / (out.stem + "-joined.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(joined)])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-vf",
         "tpad=stop_mode=clone:stop_duration=3", "-t", "%.3f" % slot, "-an", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "18", "-g", str(FPS), "-keyint_min", str(FPS), "-pix_fmt", "yuv420p", str(out)])

    def to_out(t):
        for s in spans:
            if s["a"] <= t <= s["b"]:
                return s["out0"] + (t - s["a"]) / s["f"]
        return 0.0 if t < TRIM else min(slot, spans[-1]["out1"])
    labels = [(s["out0"], s["out1"], "Waiting for Muse Spark, sped up %s×" % fx(s["f"]))
              for s in spans if s["wait"] and s["f"] > 1.05]
    if g > 1.05:
        labels = [(0, slot, "Sped up %s×" % fx(g))]
    zooms = []
    for e in ev["events"]:
        if e["type"] == "focus":
            zooms.append((to_out(e["t"]), e["rect"]))
        elif e["type"] == "clear":
            zooms.append((to_out(e["t"]), None))
    return labels, zooms


def fx(f):
    return ("%.1f" % f).rstrip("0").rstrip(".") if f < 10 else "%d" % round(f)


def zoom_target(rect):
    """(scale, x, y) for the zoom wrapper so rect fills the frame nicely."""
    s = FW / W
    x1, y1, x2, y2 = rect
    z = min(W / max(x2 - x1, 1), H / max(y2 - y1, 1)) * 0.92
    z = max(1.0, min(z, 1.9))
    cx, cy = (x1 + x2) / 2 * s, (y1 + y2) / 2 * s
    tx = FW / 2 - z * cx
    ty = FH / 2 - z * cy
    tx = min(0, max(FW - z * FW, tx))
    ty = min(0, max(FH - z * FH, ty))
    return round(z, 3), round(tx, 1), round(ty, 1)


# ------------------------------------------------------------- composition

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: %(W)dpx; height: %(H)dpx; overflow: hidden; background: #0a0a0b; }
#root { position: relative; width: 100%%; height: 100%%; font-family: %(FONT)s; color: #f4f4f5; overflow: hidden; }
.bg { position: absolute; inset: 0; background: #0a0a0b; }
.glow { position: absolute; inset: -160px -80px auto -80px; height: 820px; filter: blur(70px);
  background: radial-gradient(40%% 55%% at 22%% 30%%, rgba(196,64,30,.55), transparent 70%%),
              radial-gradient(35%% 50%% at 62%% 18%%, rgba(214,146,52,.38), transparent 70%%),
              radial-gradient(30%% 45%% at 85%% 55%%, rgba(120,40,24,.35), transparent 70%%); }
.clip { position: absolute; }
.bg, .center { inset: 0; }
.center { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 0 120px; }
.line { font-size: 54px; font-weight: 700; letter-spacing: -0.03em; line-height: 1.12; }
.grad { background: linear-gradient(90deg, #ffcf8a, #f0603c); -webkit-background-clip: text; background-clip: text; color: transparent; }
.big { font-size: 170px; font-weight: 800; letter-spacing: -0.05em; line-height: 1; }
.small { margin-top: 18px; font-size: 20px; color: #a1a1aa; }
.badge { display: inline-flex; align-items: center; gap: 8px; font-size: 15px; color: #f6c39b; border: 1px solid rgba(240,140,90,.35);
  background: rgba(240,96,60,.10); border-radius: 999px; padding: 6px 14px; }
.badge i { width: 7px; height: 7px; border-radius: 50%%; background: #f0603c; display: inline-block; }
.headline { font-size: 60px; font-weight: 700; letter-spacing: -0.035em; line-height: 1.05; margin: 20px 0 26px; }
.cmd { width: 660px; background: rgba(24,24,27,.8); border: 1px solid rgba(255,255,255,.14); border-radius: 14px;
  box-shadow: 0 24px 60px rgba(0,0,0,.5); text-align: left; overflow: hidden; }
.cmd .in { display: flex; align-items: center; gap: 12px; padding: 16px 18px; font-size: 21px; border-bottom: 1px solid rgba(255,255,255,.08); }
.cmd .in .q { flex: 1; color: #f4f4f5; white-space: nowrap; overflow: hidden; }
.cmd .caret { display: inline-block; width: 2px; height: 22px; background: #f0603c; vertical-align: middle; margin-left: 2px; }
.cmd .key { font-size: 13px; color: #a1a1aa; border: 1px solid rgba(255,255,255,.14); border-radius: 7px; padding: 5px 9px; }
.cmd .row { display: flex; gap: 12px; align-items: center; padding: 11px 18px; font-size: 16px; color: #d4d4d8; }
.cmd .row.sel { background: linear-gradient(90deg, rgba(240,96,60,.16), rgba(240,96,60,.03)); color: #fff; }
.cmd .row .ic { width: 24px; height: 24px; border-radius: 7px; border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.05); }
.cmd .row.sel .ic { border-color: rgba(240,96,60,.45); background: rgba(240,96,60,.14); }
.cmd .row .h { margin-left: auto; font: 12px 'DejaVu Sans Mono', monospace; color: #71717a; }
.logo { display: flex; align-items: center; gap: 14px; font-size: 64px; font-weight: 800; letter-spacing: -0.03em; }
.diamond { width: 40px; height: 40px; transform: rotate(45deg); border-radius: 6px; background: linear-gradient(135deg, #ffcf8a, #f0603c); }
.frame { opacity: 0; position: absolute; left: %(FL)dpx; top: %(FT)dpx; width: %(FW)dpx; height: %(FH)dpx; border-radius: 14px; overflow: hidden;
  border: 1px solid rgba(255,255,255,.14); box-shadow: 0 30px 80px rgba(0,0,0,.6), 0 0 0 1px rgba(0,0,0,.4); background: #0a0a0b; }
.zoom { position: absolute; left: 0; top: 0; width: %(FW)dpx; height: %(FH)dpx; transform-origin: 0 0; }
.zoom video { width: 100%%; height: 100%%; display: block; object-fit: cover; }
.pill { position: absolute; display: flex; align-items: center; gap: 10px; background: rgba(16,16,18,.82); border: 1px solid rgba(255,255,255,.12);
  border-radius: 999px; padding: 8px 16px 8px 12px; font-size: 16px; box-shadow: 0 10px 30px rgba(0,0,0,.45); }
.pill .k { font-size: 12.5px; color: #ffb48d; border: 1px solid rgba(240,96,60,.4); background: rgba(240,96,60,.12); border-radius: 999px; padding: 3px 9px; }
.lab { opacity: 0; left: %(FL)dpx; top: 14px; }
.sped { right: %(FL)dpx; top: 14px; font-size: 13.5px; color: #fbbf24; border-color: rgba(251,191,36,.35); padding: 6px 12px; }
.cap { position: absolute; left: 0; right: 0; bottom: 18px; display: flex; justify-content: center; }
.cap span { max-width: 960px; text-align: center; font-size: 22px; line-height: 1.35; padding: 7px 16px; border-radius: 10px;
  background: rgba(10,10,11,.78); border: 1px solid rgba(255,255,255,.08); }
.prog { position: absolute; left: 0; right: 0; top: 0; height: 3px; background: rgba(255,255,255,.06); }
.prog i { display: block; height: 100%%; background: linear-gradient(90deg, #ffcf8a, #f0603c); transform-origin: 0 50%%; }
.voice { position: absolute; right: 16px; bottom: 6px; font-size: 11px; color: rgba(255,255,255,.4); }
.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 26px 70px; width: 980px; margin-top: 28px; text-align: left; }
.stat .n { font-size: 66px; font-weight: 800; letter-spacing: -0.03em; }
.stat .l { font-size: 19px; color: #a1a1aa; margin-top: 2px; }
.kick { font-size: 18px; color: #ffb48d; }
.note { margin-top: 26px; font-size: 16px; color: #71717a; }
.url { margin-top: 18px; font-size: 22px; color: #ffad7a; }
"""


def el_id(prefix, i):
    return "%s%d" % (prefix, i)


def build_html(segs, total, voice_cues):
    css = CSS % {"W": W, "H": H, "FONT": FONT, "FW": FW, "FH": FH,
                 "FL": (W - FW) // 2, "FT": (H - FH) // 2 + 10}
    body, js = [], []
    body.append('<div class="bg clip" id="bg" data-start="0" data-duration="%.3f"></div>' % total)
    body.append('<div class="glow clip" id="glow" data-start="0" data-duration="%.3f"></div>' % total)
    js.append('tl.fromTo("#glow", {x: -40, opacity: .7}, {x: 40, opacity: 1, duration: %.2f, ease: "sine.inOut"}, 0);' % total)
    for s in segs:
        a, d = s["start"], s["len"]
        if s["id"] == "opening":
            body.append(opening_html(a, d))
            js.append(opening_js(a, d))
        elif s["id"] == "closing":
            body.append(closing_html(a, d))
            js.append(closing_js(a, d))
        else:
            i = s["idx"]
            k, t = LABELS[s["id"]]
            body.append(
                '<div class="frame" id="f%d">'
                '<div class="zoom" id="z%d"><video id="v%d" src="clips/%s.mp4" muted data-start="%.3f" '
                'data-duration="%.3f"></video></div></div>' % (i, i, i, s["id"], a, d))
            body.append('<div class="pill lab clip" id="l%d" data-start="%.3f" data-duration="%.3f">'
                        '<span class="k">%s</span>%s</div>' % (i, a, d, html.escape(k), html.escape(t)))
            js.append('tl.fromTo("#f%d", {opacity: 0, scale: .965, y: 18}, {opacity: 1, scale: 1, y: 0, duration: .45, ease: "power3.out"}, %.3f);' % (i, a))
            js.append('tl.to("#f%d", {opacity: 0, scale: .985, duration: .3, ease: "power2.in"}, %.3f);' % (i, a + d - 0.3))
            js.append('tl.fromTo("#l%d", {opacity: 0, x: -16}, {opacity: 1, x: 0, duration: .45, ease: "power3.out"}, %.3f);' % (i, a + 0.15))
            js.append('tl.to("#l%d", {opacity: 0, duration: .25}, %.3f);' % (i, a + d - 0.3))
            for j, (s0, s1, text) in enumerate(s["labels"]):
                ln = max(0.4, s1 - s0)
                body.append('<div class="pill sped clip" id="sp%d_%d" data-start="%.3f" data-duration="%.3f">%s</div>'
                            % (i, j, a + s0, ln, html.escape(text)))
                js.append('tl.fromTo("#sp%d_%d", {opacity: 0, y: -8}, {opacity: 1, y: 0, duration: .25}, %.3f);' % (i, j, a + s0))
            for (tz, rect) in s["zooms"]:
                t0 = a + max(0.05, min(d - 0.9, tz))
                if rect is None:
                    js.append('tl.to("#z%d", {scale: 1, x: 0, y: 0, duration: .8, ease: "power2.inOut"}, %.3f);' % (i, t0))
                else:
                    z, x, y = zoom_target(rect)
                    js.append('tl.to("#z%d", {scale: %s, x: %s, y: %s, duration: .9, ease: "power2.inOut"}, %.3f);' % (i, z, x, y, t0))
    for n, (c0, c1, text) in enumerate(voice_cues):
        body.append('<div class="cap clip" id="c%d" data-start="%.3f" data-duration="%.3f"><span>%s</span></div>'
                    % (n, c0, max(0.3, c1 - c0), html.escape(text)))

    body.append('<div class="prog clip" id="prog" data-start="0" data-duration="%.3f"><i id="progbar"></i></div>' % total)
    js.append('tl.fromTo("#progbar", {scaleX: 0}, {scaleX: 1, duration: %.3f, ease: "none"}, 0);' % total)
    body.append('<div class="voice clip" id="voicenote" data-start="0" data-duration="%.3f">Synthetic narration voice. Original music.</div>' % total)
    return ("<!doctype html><html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=%d, height=%d'>"
            "<script src='gsap.min.js'></script><style>%s</style></head><body>"
            "<div id='root' data-composition-id='kohu' data-start='0' data-duration='%.3f' data-width='%d' data-height='%d'>%s</div>"
            "<script>window.__timelines = window.__timelines || {}; const tl = gsap.timeline({paused: true});\n%s\n"
            "window.__timelines['kohu'] = tl; tl.seek(0);</script></body></html>"
            % (W, H, css, total, W, H, "\n".join(body), "\n".join(js)))


def opening_html(a, d):
    q = "How do I process a customer refund?"
    rows = [("How do I process a customer refund?", "process + video", True),
            ("What was Viet Nam's GDP growth in 2023?", "licensed report", False),
            ("Which country grew fastest in 2024?", "chart page", False)]
    rows_html = "".join('<div class="row%s"><span class="ic"></span>%s<span class="h">%s</span></div>'
                        % (" sel" if sel else "", html.escape(t), h) for t, h, sel in rows)
    return """
<div class="clip center" id="o1" data-start="%(a).3f" data-duration="3.4"><div class="line">Know-how sits on a few laptops<br>and in a few heads.</div></div>
<div class="clip center" id="o2" data-start="%(b).3f" data-duration="3.2"><div class="line">Data the company paid for<br><span class="grad">goes unopened.</span></div></div>
<div class="clip center" id="o3" data-start="%(c).3f" data-duration="4.2"><div class="big grad" id="pct">0%%</div>
  <div class="line" style="font-size:34px;margin-top:8px">of a team's time goes to searching for answers.</div>
  <div class="small">Atlassian, State of Teams 2025, about 12,000 knowledge workers</div></div>
<div class="clip center" id="o4" data-start="%(e).3f" data-duration="%(f).3f">
  <div class="badge"><i></i>Muse Spark 1.3 &middot; Muse Voice Transcribe 1.0 &middot; SAM 3.1</div>
  <div class="headline">Everything your company knows,<br><span class="grad">one question</span> away.</div>
  <div class="cmd"><div class="in"><span class="q"><span id="typed"></span><span class="caret"></span></span><span class="key">Ask &#8629;</span></div>%(rows)s</div>
</div>""" % {"a": a, "b": a + 3.4, "c": a + 6.6, "e": a + 10.8, "f": d - 10.8, "rows": rows_html}


def opening_js(a, d):
    q = "How do I process a customer refund?"
    return """
tl.fromTo("#o1 .line", {opacity: 0, y: 28, filter: "blur(6px)"}, {opacity: 1, y: 0, filter: "blur(0px)", duration: .8, ease: "power3.out"}, %(a).3f);
tl.to("#o1", {opacity: 0, y: -20, duration: .4}, %(a1).3f);
tl.fromTo("#o2 .line", {opacity: 0, y: 28, filter: "blur(6px)"}, {opacity: 1, y: 0, filter: "blur(0px)", duration: .8, ease: "power3.out"}, %(b).3f);
tl.to("#o2", {opacity: 0, y: -20, duration: .4}, %(b1).3f);
tl.fromTo("#o3", {opacity: 0, scale: .94}, {opacity: 1, scale: 1, duration: .7, ease: "power3.out"}, %(c).3f);
const pct = {v: 0};
tl.to(pct, {v: 25, duration: 1.4, ease: "power2.out", onUpdate: () => { document.getElementById("pct").textContent = Math.round(pct.v) + "%%"; }}, %(c).3f);
tl.to("#o3", {opacity: 0, y: -20, duration: .4}, %(c1).3f);
tl.fromTo("#o4 .badge", {opacity: 0, y: 12}, {opacity: 1, y: 0, duration: .5}, %(e).3f);
tl.fromTo("#o4 .headline", {opacity: 0, y: 22}, {opacity: 1, y: 0, duration: .7, ease: "power3.out"}, %(e1).3f);
tl.fromTo("#o4 .cmd", {opacity: 0, y: 30, scale: .97}, {opacity: 1, y: 0, scale: 1, duration: .7, ease: "power3.out"}, %(e2).3f);
const typed = {n: 0}; const Q = %(q)s;
tl.to(typed, {n: Q.length, duration: 1.8, ease: "none", onUpdate: () => { document.getElementById("typed").textContent = Q.slice(0, Math.round(typed.n)); }}, %(e3).3f);
tl.fromTo("#o4 .row", {opacity: 0, x: -10}, {opacity: 1, x: 0, duration: .35, stagger: .12}, %(e3).3f);
tl.to("#o4", {opacity: 0, scale: .98, duration: .35}, %(end).3f);
""" % {"a": a, "a1": a + 3.0, "b": a + 3.4, "b1": a + 6.2, "c": a + 6.6, "c1": a + 10.4,
       "e": a + 10.8, "e1": a + 11.0, "e2": a + 11.4, "e3": a + 12.0, "end": a + d - 0.35,
       "q": json.dumps(q)}


def closing_html(a, d):
    stats = "".join('<div class="stat"><div class="n">%s</div><div class="l">%s</div></div>'
                    % (html.escape(n), html.escape(l)) for n, l in STATS)
    return """
<div class="clip center" id="e1" data-start="%(a).3f" data-duration="%(d1).3f">
  <div class="kick">Measured, failures included</div>
  <div class="stats">%(stats)s</div>
  <div class="note">Small demo corpus. Only the second recording is held out. Every number and failure is in docs/eval-result.md.</div></div>
<div class="clip center" id="e2" data-start="%(b).3f" data-duration="%(d2).3f">
  <div class="logo"><span class="diamond"></span>Kohu</div>
  <div class="headline" style="font-size:38px;margin:18px 0 0">Ask what your company knows<br>and what it has <span class="grad">paid for</span>.</div>
  <div class="url">github.com/fajaraji/Kohu</div></div>""" % {
        "a": a, "d1": d - 4.2, "b": a + d - 4.2, "d2": 4.2, "stats": stats}


def closing_js(a, d):
    return """
tl.fromTo("#e1 .kick", {opacity: 0, y: 10}, {opacity: 1, y: 0, duration: .4}, %(a).3f);
tl.fromTo("#e1 .stat", {opacity: 0, y: 24}, {opacity: 1, y: 0, duration: .55, stagger: .45, ease: "power3.out"}, %(a1).3f);
tl.fromTo("#e1 .note", {opacity: 0}, {opacity: 1, duration: .5}, %(a2).3f);
tl.to("#e1", {opacity: 0, duration: .4}, %(b0).3f);
tl.fromTo("#e2 .logo", {opacity: 0, scale: .9}, {opacity: 1, scale: 1, duration: .6, ease: "back.out(1.6)"}, %(b).3f);
tl.fromTo("#e2 .headline", {opacity: 0, y: 14}, {opacity: 1, y: 0, duration: .6}, %(b1).3f);
tl.fromTo("#e2 .url", {opacity: 0}, {opacity: 1, duration: .5}, %(b2).3f);
""" % {"a": a, "a1": a + 0.3, "a2": a + 2.4, "b0": a + d - 4.6, "b": a + d - 4.2,
       "b1": a + d - 3.8, "b2": a + d - 3.3}


# ------------------------------------------------------------------- main

def main():
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("--footage", required=True)
    ap.add_argument("--out", default=str(HERE / "kohu-demo.mp4"))
    ap.add_argument("--hyperframes", default="/tmp/claude-0/hf/node_modules/.bin/hyperframes")
    ap.add_argument("--gsap", default="/tmp/claude-0/hf/node_modules/gsap/dist/gsap.min.js")
    ap.add_argument("--reuse", help="work dir of an earlier run; keeps its render and only redoes the audio")
    args = ap.parse_args()
    footage = pathlib.Path(args.footage)
    spec = json.loads((HERE / "narration.json").read_text())
    voice = synth(spec["segments"], spec["voice"])
    segs, t, idx = [], 0.0, 0
    for s in spec["segments"]:
        audio, cues, speech = voice[s["id"]]
        lead = 0.5 if s["id"] == "opening" else 0.45
        length = speech + lead + 0.45
        if s["id"] == "opening":
            length = max(length, 15.0)
        if s["id"] == "closing":
            length = max(length, 13.0)
        idx += 1
        segs.append({"id": s["id"], "start": t, "len": length, "idx": idx,
                     "lead": lead, "audio": audio, "cues": cues})
        t += length
    total = t
    print("total %.1f s" % total, [(s["id"], round(s["len"], 1)) for s in segs])
    work = pathlib.Path(args.reuse) if args.reuse else pathlib.Path(tempfile.mkdtemp(prefix="kohu-v3-"))
    proj = work / "project"
    (proj / "clips").mkdir(parents=True, exist_ok=True)
    for s in segs:
        if s["id"] in LABELS:
            ev = json.loads((footage / (s["id"] + ".events.json")).read_text())
            s["labels"], s["zooms"] = cut_footage(footage / (s["id"] + ".webm"), ev, s["len"],
                                                  proj / "clips" / (s["id"] + ".mp4"), work)
    cues = [(s["start"] + s["lead"] + a, s["start"] + s["lead"] + b, txt)
            for s in segs for a, b, txt in s["cues"]]
    silent = work / "silent.mp4"
    if not silent.exists():
        render(args, segs, total, cues, proj, silent)
    finish(args, segs, total, cues, work, silent)


def render(args, segs, total, cues, proj, silent):
    (proj / "index.html").write_text(build_html(segs, total, cues))
    shutil.copy(args.gsap, proj / "gsap.min.js")
    for f in ("hyperframes.json", "package.json"):
        src = HERE / "hyperframes" / "opening" / f
        if src.exists():
            shutil.copy(src, proj / f)
    (proj / "meta.json").write_text('{"id":"kohu-demo-v3","name":"Kohu demo v3"}')
    env = dict(os.environ, HYPERFRAMES_SKIP_SKILLS="1")
    run([args.hyperframes, "render", "-q", "standard", "-f", str(FPS), "-o", str(silent)],
        cwd=proj, env=env, stdin=subprocess.DEVNULL)


def finish(args, segs, total, cues, work, silent):
    import soundfile as sf
    # Narration track.
    mix = np.zeros(int((total + 1) * SR), dtype=np.float32)
    for s in segs:
        i = int((s["start"] + s["lead"]) * SR)
        a = s["audio"][:max(0, len(mix) - i)]
        mix[i:i + len(a)] += a
    sf.write(work / "voice.wav", mix, SR)
    music = work / "music.wav"
    run(["python3", str(HERE / "make_music.py"), str(music), "%.2f" % (total + 1)])
    (HERE / "captions.srt").write_text("".join(
        "%d\n%s --> %s\n%s\n\n" % (n + 1, srt(a), srt(b), txt) for n, (a, b, txt) in enumerate(cues)))
    out = pathlib.Path(args.out)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(work / "voice.wav"),
         "-i", str(music), "-filter_complex",
         "[1:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=1.0[v];"
         "[2:a]aresample=48000,volume=0.55[m];"
         "[v]asplit=2[v1][v2];"
         "[m][v1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
         "[md][v2]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", str(out)])
    print("wrote", out, "%.1f s" % dur(out), out.stat().st_size // 1024, "KB; work dir", work)


def srt(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


if __name__ == "__main__":
    main()
