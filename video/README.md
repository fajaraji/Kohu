# Demo video package

| File | What it is |
|---|---|
| `kohu-demo.mp4` | Rendered demo, about 2 minutes 10 seconds (review before uploading; nothing was submitted) |
| `script.md` | Timed script, what is on screen and the narration |
| `captions.srt` | Captions for the narration |
| `narration.json` | Source of truth for segment timing and narration text |
| `capture.mjs` | Records real product footage from the running app with Playwright |
| `reset_demo.py` | Resets the local demo database (reopens conflicts, removes uploads) before capture |
| `build_video_v3.py` | Builds the current video: one Hyperframes composition in the app's dark style, footage in an app frame with zooms, animated labels and captions, then narration and music mixed with FFmpeg |
| `make_music.py` | Synthesizes the music bed (original, numpy only, no samples) |
| `build_video.py` | Older assembler (v2, section cards between segments), kept for reference |
| `hyperframes/` | Older v2 compositions for the opening, section cards and closing |
| `assets/stock-check.mp4` | Second simulated screen recording, uploaded live in the 2:10 segment |

How it was made, and how to rebuild it:

1. Start the app with the seeded database and a Meta key, then `python video/reset_demo.py`.
2. `node video/capture.mjs /tmp/footage` records six segments of the real app. Besides the video, each segment writes the moments the app waited on Muse Spark and the box on screen that matters from each moment on. Set `KOHU_UPLOAD_CLIP` to a recording that has not been processed before, otherwise the upload comes back from the model cache instantly. Every answer, conflict, decision and video processing run in the footage happened live against the Meta API.
3. `npm install hyperframes@0.8.179 gsap@3.12.5` somewhere, then `python video/build_video_v3.py --footage /tmp/footage --hyperframes <path to .bin/hyperframes> --gsap <path to gsap.min.js>`. It synthesizes the narration, times each segment to it, cuts the footage, renders the composition and mixes voice and music. `--reuse <work dir>` keeps an earlier render and redoes only the audio.

Editing rules: only waiting time is sped up, and each sped-up stretch is labeled with its factor. Zooms only enlarge what the app showed at that moment. The narration voice is labeled synthetic. The narration is generated with Kokoro TTS (Apache 2.0); swap in a recorded human voice if the team prefers. The music is made by `make_music.py` for this video and ducks under the voice.
