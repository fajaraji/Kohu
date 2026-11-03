"""Assemble the 3 minute demo video from real footage and Hyperframes cards.

Inputs
  video/narration.json         segments, timing, narration text (source of truth)
  <footage>/<segment>.webm     real product recordings from video/capture.mjs
  <footage>/<segment>.events.json  when the app was waiting on Muse Spark
  <cards>/opening.mp4, closing.mp4, card1..6.mp4  rendered with Hyperframes
                               from video/hyperframes/

Rules applied
  * Only waiting time is sped up, and every sped-up stretch is labeled on
    screen with its factor. If the remaining footage is still too long
    for its slot, the whole segment is sped up and labeled too.
  * Narration is a synthetic Kokoro voice and is labeled as such.
  * Captions are written to video/captions.srt and burned in.

Usage
  python video/build_video.py --footage DIR --cards DIR --out video/renders/kohu-demo.mp4
"""

import argparse
import json
import os
import pathlib
import subprocess
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SR = 24000
W, H, FPS = 1280, 720, 30
CARD = 2.5
TRIM_START = 1.2
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(cmd):
    subprocess.run(cmd, check=True)


def dur(path):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "csv=p=0", str(path)], capture_output=True, text=True,
        check=True).stdout.strip())


def synth(segments, voice):
    from kokoro_onnx import Kokoro
    kdir = pathlib.Path(os.environ.get("KOKORO_DIR", "/tmp/claude-0/tts"))
    k = Kokoro(str(kdir / "kokoro-v1.0.int8.onnx"),
               str(kdir / "voices-v1.0.bin"))
    out = {}
    for s in segments:
        import re
        sents = []
        for chunk in re.split(r"(\[pause [0-9.]+\])", s["say"]):
            if chunk.startswith("[pause"):
                sents.append(chunk)
                continue
            sents += [x.strip() + "." for x in chunk.split(". ") if x.strip()]
        sents = [x[:-1] if x.endswith("..") else x for x in sents]
        parts, cues, t = [], [], 0.0
        for sent in sents:
            m = re.fullmatch(r"\[pause ([0-9.]+)\]", sent)
            if m:
                parts.append(np.zeros(int(float(m.group(1)) * SR),
                                      dtype=np.float32))
                t += float(m.group(1))
                continue
            audio, sr = k.create(sent, voice=voice, speed=1.05, lang="en-us")
            a = np.asarray(audio, dtype=np.float32)
            cues.append((t, t + len(a) / SR, sent))
            parts += [a, np.zeros(int(0.25 * SR), dtype=np.float32)]
            t += len(a) / SR + 0.25
        out[s["id"]] = (np.concatenate(parts), cues)
    return out


def pieces(events, total):
    """[(start, end, is_wait)] after trimming the page load."""
    waits = sorted((e["start"], e["end"]) for e in events
                   if e.get("type") == "wait")
    out, t = [], TRIM_START
    for a, b in waits:
        if a > t:
            out.append((t, a, False))
        out.append((max(a, t), b, True))
        t = b
    if total > t:
        out.append((t, total, False))
    return [p for p in out if p[1] - p[0] > 0.05]


def fx(f):
    return ("%.1f" % f).rstrip("0").rstrip(".") if f < 10 else "%d" % round(f)


def label(text):
    return ("drawbox=x=0:y=0:w=iw:h=44:color=black@0.55:t=fill,"
            "drawtext=fontfile=%s:text='%s':x=20:y=12:fontsize=22:"
            "fontcolor=#ffd166" % (FONT, text.replace("'", "")))


def footage_clip(seg, footage, tmp):
    src = footage / (seg["id"] + ".webm")
    ev = json.loads((footage / (seg["id"] + ".events.json")).read_text())
    avail = seg["length"] - CARD
    ps = pieces(ev["events"], ev["total"])
    normal = sum(b - a for a, b, w in ps if not w)
    wait = sum(b - a for a, b, w in ps if w)
    plan = []
    if seg.get("trim_to"):
        plan = [(ps[0][0], ps[0][0] + avail, 1.0, None)]
    elif normal <= avail - 1.0 or wait == 0:
        f = max(1.0, wait / max(0.5, avail - normal)) if wait else 1.0
        for a, b, w in ps:
            plan.append((a, b, f if w else 1.0,
                         "Waiting for Muse Spark, sped up %sx" % fx(f)
                         if w and f > 1.05 else None))
    else:
        g = normal / (avail - 1.0 - 0.6 * sum(1 for p in ps if p[2]))
        for a, b, w in ps:
            if w:
                f = (b - a) / 0.6
                plan.append((a, b, f, "Waiting for Muse Spark, sped up %sx"
                             % fx(f)))
            else:
                plan.append((a, b, g, "Sped up %sx" % fx(g)
                             if g > 1.05 else None))
    parts = []
    for i, (a, b, f, lab) in enumerate(plan):
        out = tmp / ("%s-%02d.mp4" % (seg["id"], i))
        vf = "setpts=(PTS-STARTPTS)/%.4f,fps=%d,scale=%d:%d" % (f, FPS, W, H)
        if lab:
            vf += "," + label(lab)
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % a, "-to",
             "%.3f" % b, "-i", str(src), "-an", "-vf", vf, "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             str(out)])
        parts.append(out)
    joined = tmp / (seg["id"] + "-joined.mp4")
    concat(parts, joined)
    # Pad or cut to the slot exactly.
    fixed = tmp / (seg["id"] + "-fixed.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-vf",
         "tpad=stop_mode=clone:stop_duration=%.2f" % avail, "-t",
         "%.3f" % avail, "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-pix_fmt", "yuv420p", str(fixed)])
    return fixed


def concat(parts, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join("file '%s'\n" % p for p in parts))
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(out)])


def norm(src, out, length):
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf",
         "fps=%d,scale=%d:%d,tpad=stop_mode=clone:stop_duration=2" % (FPS, W, H),
         "-t", "%.3f" % length, "-an", "-c:v", "libx264", "-preset",
         "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])


def srt_time(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60,
                                    ms // 1000 % 60, ms % 1000)


def main():
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("--footage", required=True)
    ap.add_argument("--cards", required=True)
    ap.add_argument("--out", default=str(HERE / "renders" / "kohu-demo.mp4"))
    args = ap.parse_args()
    footage, cards = pathlib.Path(args.footage), pathlib.Path(args.cards)
    spec = json.loads((HERE / "narration.json").read_text())
    segs = spec["segments"]
    voice = synth(segs, spec["voice"])
    total = segs[-1]["start"] + segs[-1]["length"]
    mix = np.zeros(int((total + 1) * SR), dtype=np.float32)
    cues = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        parts = []
        for s in segs:
            audio, scues = voice[s["id"]]
            if s["kind"] == "hyperframes":
                clip = tmp / (s["id"] + ".mp4")
                norm(cards / s["file"], clip, s["length"])
                parts.append(clip)
                t0 = s["start"] + 0.5
            else:
                card = tmp / ("card%d.mp4" % s["card"])
                norm(cards / ("card%d.mp4" % s["card"]), card, CARD)
                parts += [card, footage_clip(s, footage, tmp)]
                t0 = s["start"] + 0.3
            room = s["length"] - (t0 - s["start"]) - 0.2
            if len(audio) / SR > room:
                print("warning: narration for %s is %.1fs, slot room %.1fs"
                      % (s["id"], len(audio) / SR, room))
            i = int(t0 * SR)
            mix[i:i + len(audio)] += audio[:len(mix) - i]
            cues += [(t0 + a, t0 + b, txt) for a, b, txt in scues]
        video = tmp / "video.mp4"
        concat(parts, video)
        sf.write(tmp / "voice.wav", mix, SR)
        srt = "".join("%d\n%s --> %s\n%s\n\n" % (
            n + 1, srt_time(a), srt_time(b), txt)
            for n, (a, b, txt) in enumerate(cues))
        (HERE / "captions.srt").write_text(srt)
        (tmp / "captions.srt").write_text(srt)
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        style = ("FontName=DejaVu Sans,FontSize=17,PrimaryColour=&H00FFFFFF,"
                 "BackColour=&H99000000,BorderStyle=4,Outline=0,Shadow=0,"
                 "MarginV=18")
        vf = ("subtitles=%s:force_style='%s',drawtext=fontfile=%s:"
              "text='Synthetic narration voice':x=w-tw-14:y=h-28:fontsize=14:"
              "fontcolor=white@0.6" % (tmp / "captions.srt", style,
                                      FONT.replace("-Bold", "")))
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i",
             str(tmp / "voice.wav"), "-vf", vf, "-c:v", "libx264", "-preset",
             "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-b:a", "128k", "-shortest", "-movflags", "+faststart",
             str(out)])
    print("wrote", out, "%.1f s" % dur(out), out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
