# Demo video package

| File | What it is |
|---|---|
| `kohu-demo.mp4` | Rendered 3 minute demo (review before uploading; nothing was submitted) |
| `script.md` | Timed script, what is on screen and the narration |
| `captions.srt` | Captions for the narration |
| `narration.json` | Source of truth for segment timing and narration text |
| `capture.mjs` | Records real product footage from the running app with Playwright |
| `reset_demo.py` | Resets the local demo database (reopens conflicts, removes uploads) before capture |
| `build_video.py` | Assembles footage, cards, narration and captions with FFmpeg |
| `hyperframes/` | Hyperframes compositions for the opening, section cards and closing |
| `assets/stock-check.mp4` | Second simulated screen recording, uploaded live in the 2:10 segment |

How it was made, and how to rebuild it:

1. Start the app with the seeded database and a Meta key, then `python video/reset_demo.py`.
2. `node video/capture.mjs /tmp/footage` records six segments of the real app. Every answer, conflict, decision and video processing run in the footage happened live against the Meta API.
3. In each of `hyperframes/opening`, `hyperframes/closing` and `hyperframes/card`, copy `gsap.min.js` (from `npm install gsap@3.12.5`) next to `index.html` and run `npx hyperframes@0.8.179 render`. The section cards use `--variables '{"kicker": "...", "title": "..."}'` with the six titles listed in `script.md`.
4. `python video/build_video.py --footage /tmp/footage --cards <rendered cards dir>`.

Editing rules applied by `build_video.py`: only waiting time is sped up, each sped-up stretch is labeled with its factor, and the narration voice is labeled synthetic. The narration is generated with Kokoro TTS (Apache 2.0); swap in a recorded human voice if the team prefers.
