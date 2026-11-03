# U1 spike: Meta API checks

Run on 2026-11-03 with `python api/spike.py` against the live Meta Model API (`https://api.meta.ai/v1`, key attached by the environment's egress proxy, never printed). Raw numbers are in `docs/spike-results.json`; raw responses are saved as `tests/fixtures/meta/live_*.json`. Spend for the whole spike was about $0.11.

Inputs were built for this repo: the demo clip `corpus/demo-app/refund-process.mp4` (68 s, Playwright recording of the simulated back office app with a synthetic Kokoro voice), its frames, and pages of `corpus/licensed/asean-outlook-report.pdf`. Ground truth step times and element boxes come from the recording run (`corpus/demo-app/clip-truth.json`).

## Results

| Check | Result |
|---|---|
| `GET /v1/models` | 9 models, including `muse-spark-1.3`, `muse-voice-transcribe-1.0`, `sam-3.1` |
| Transcription, `POST /v1/asr/transcribe` (WAV 16 kHz mono, `mode: ENDPOINTING`) | Worked in 15.9 s for 68 s of audio. Response keys `sessionId`, `transcript`, `audioDurationMs`, `turns[{turnId, startMs, endMs, transcript}]`. Turn starts were within about 0.2 s of the true narration starts. The transcript repeats a few words ("for for", "Next,Next,") at turn edges |
| Video, `POST /v1/files` then Spark 1.3 with `input_video` + transcript, `text.format` JSON schema, `background: true` | Upload 3.0 s, processing 23.9 s with polling. 18,955 input and 2,255 output tokens. 9 steps returned for 9 real actions. Step start error to the nearest true step start: median 0.19 s, max 0.47 s. Spoken reasons came back for the four steps that state one, and `reason` was null where nothing was said, except the supervisor code step, where the model treated "Any refund above $500 needs a supervisor code" as the reason |
| SAM 3.1, noun phrase prompt, 5 app screenshots (1280x720) | Weak on UI. 3 of 5 returned no match (Orders menu item, Check stock button, refund reason dropdown). Search box matched (IoU 0.97). Order number field matched the whole dialog (IoU 0.11) |
| SAM 3.1, box prompt from the true element box | 5 of 5 matched, IoU 0.88 to 0.995 |
| Spark gives a box (JSON schema), then SAM box prompt | Spark box IoU 0.85 to 0.97; SAM refined it to IoU 0.88 to 0.994 on 5 of 5 |
| SAM 3.1, noun phrase on PDF pages (rendered at 100 dpi) | `bar chart` on the chart page found the chart (1 record). `table` found the table on page 3 (1 record) and both tables on page 6 (2 records) |
| Python mask parser | Meta publishes `meta-sam-parser` 0.1.0 on PyPI (SAM License) with `decode_mask_to_raster`. It is listed in `api/requirements.txt` and used by `api/sam_parse.py` when installed. Installing it in this build sandbox was blocked by the sandbox's permission check, so mask decoding was not run here. Box parsing (our own regex over the documented grammar) was run on all live outputs above |

## Decisions

1. Video timing does not drift (median 0.19 s), so step times come from Spark. They are still validated: inside the video duration, ascending, and each start is snapped to the nearest transcript turn start when one is within 1.5 s. Transcript turns are the fallback when validation fails.
2. SAM phrases fail on UI elements, so video frames use: Spark proposes a box (with the step instruction as context); a SAM phrase match is kept only if it is small and agrees with that box (`mark_status = phrase`); otherwise SAM refines Spark's box with a box prompt (`box`); if SAM returns nothing, Spark's box is drawn (`spark_box`). SAM did not "still fail" on UI once given a box, so A7 is not mandatory. It stays in the plan and is done if time remains.
3. Masks are drawn from the SAM mask when `meta-sam-parser` is installed (Docker image installs it) and from the SAM box otherwise. Which one was drawn is stored per step.
4. The ASR fixture used in unit tests was corrected to the live shape (`transcript` per turn, not `text`).

## Follow-up on the full pipeline (A3, A4)

`python api/video.py process refund-process-video` on the same clip: ASR, upload, Spark in background mode (28.7 s), 9 steps, all within 0.43 s of the true narration start. First marking rule (phrase first, unguided Spark box): 6 of 9 marks had IoU of at least 0.5 with the true element. After giving Spark the step instruction and checking phrase matches against Spark's box: 9 of 9, IoU 0.78 to 0.96. The rule was tuned on this clip, so this is not a held-out result.
