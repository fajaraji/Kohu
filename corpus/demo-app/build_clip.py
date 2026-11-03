"""Build the demo clip: synthetic narration + Playwright screen recording.

1. Synthesize each narration line with Kokoro TTS (Apache 2.0 model,
   voice from script.json). The voice is synthetic and labeled as such.
2. Record the demo app with Playwright, pacing each step to its line
   (record.mjs). Ground truth step times and target boxes are written.
3. Mix the lines at their step start times and mux to MP4 (H.264, AAC).

Outputs (committed): refund-process.mp4, clip-truth.json, frames/*.png.
Kokoro model files are not committed; point KOKORO_DIR at a folder with
kokoro-v1.0.int8.onnx and voices-v1.0.bin to rebuild.
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SR = 24000


def synth(lines, voice):
    import soundfile as sf  # noqa: F401  (kokoro returns numpy audio)
    from kokoro_onnx import Kokoro

    kdir = pathlib.Path(os.environ.get("KOKORO_DIR", "/tmp/claude-0/tts"))
    k = Kokoro(str(kdir / "kokoro-v1.0.int8.onnx"),
               str(kdir / "voices-v1.0.bin"))
    out = []
    for line in lines:
        audio, sr = k.create(line, voice=voice, speed=1.0, lang="en-us")
        assert sr == SR
        out.append(np.asarray(audio, dtype=np.float32))
    return out


def main():
    import soundfile as sf

    script = json.loads((HERE / "script.json").read_text())
    clips = synth([s["say"] for s in script["steps"]], script["voice"])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "dur.json").write_text(json.dumps(
            [len(c) / SR for c in clips]))
        subprocess.run(["node", str(HERE / "record.mjs"),
                        str(tmp / "dur.json"), str(tmp / "rec")], check=True)
        truth = json.loads((tmp / "rec" / "truth.json").read_text())
        total = truth["total"] + 0.5
        mix = np.zeros(int(total * SR) + SR, dtype=np.float32)
        for step, clip in zip(truth["steps"], clips):
            i = int(step["start"] * SR)
            mix[i:i + len(clip)] += clip
            step["speech_end"] = round(step["start"] + len(clip) / SR, 2)
        sf.write(tmp / "voice.wav", mix, SR)
        out = HERE / "refund-process.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i",
            str(tmp / "rec" / "raw.webm"), "-i", str(tmp / "voice.wav"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
            "-crf", "28", "-r", "25", "-c:a", "aac", "-b:a", "96k",
            "-shortest", "-movflags", "+faststart", str(out)], check=True)
        frames = HERE / "frames"
        shutil.rmtree(frames, ignore_errors=True)
        frames.mkdir()
        for step in truth["steps"]:
            if step.get("frame"):
                shutil.copy(tmp / "rec" / step["frame"],
                            frames / step["frame"])
            for k in ("start", "end", "action_at"):
                if k in step:
                    step[k] = round(step[k], 2)
    truth["note"] = ("Ground truth from the recording run. start = narration "
                     "start of the step, action_at = when the click or typing "
                     "happened, box = target element in video pixels. Voice "
                     "is synthetic (Kokoro TTS, %s)." % script["voice"])
    (HERE / "clip-truth.json").write_text(json.dumps(truth, indent=1))
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True).stdout.strip()
    print("clip:", out.name, dur, "s", out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
