# Recorded fixtures

Files named `live_*` are real responses saved by `api/spike.py` on 2026-11-03. The other files were first shaped from the Meta Model API documentation (Responses
API, Files API, ASR transcribe, SAM 3.1 output grammar) because the real API
could not be reached from the build environment. They are test inputs, not
real model output, and are never used by the running app. See
`docs/run-report.md` for which paths were verified against the live API.
The SAM line in `sam_two_records.txt` is the documented example from the
`meta-sam-parser` package README.
