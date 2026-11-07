# Inline review performance implementation plan

**Goal:** Edit a plate in its finding card without repeated video decoding or overlapping status polls.
**Architecture:** One lossless, source-keyed preview crop shared by thumbnail, inline editor and training sample. Bounded FFmpeg accurate seeking with timestamp validation replaces prefix replay. Lazy browser requests, single-flight polling, visible retry and cancellation.
**Tech stack:** Existing Flask, embedded JavaScript, NumPy/OpenCV and FFmpeg; no new runtime dependency.
**Spec:** User-approved direction in this conversation: remove modal, reuse finding image, fix resource exhaustion, preserve exact masks.

## Constraints and review focus
- Python >=3.9; package and Docker app layout unchanged.
- Never accept an unverified frame in indexed review; seek failure must be visible, not silently produce the wrong frame.
- Timeouts, corrupt video, concurrent preview requests and closed/replaced cards must terminate safely.
- Cache is private, source-keyed, atomically replaced and contained inside the existing job/vault directory.
- Save/cancel, track propagation, rotation, existing Blur/Keep decisions and mobile scaling stay correct.

## Tasks
- [x] Add failing tests for repeated decoding, frame identity and bounded decoder work.
- [x] Replace prefix decoder with timed, single-threaded, timestamp-checked FFmpeg seek; add bounded frame reuse.
- [x] Share cached original crop and geometry between thumbnail/editor/save; reject stale preview tokens.
- [x] Reuse the finding image in an inline editor; local-only pointer edits, cancel and saved state.
- [x] Lazy-load one visible preview at a time; prevent stale work, catch errors and provide explicit retry.
- [x] Make polling single-flight with timeout/backoff and job-switch guards.
- [x] Run regression tests and a full Flask/Chromium flow at desktop/mobile with actual video (no image/API mocks for the main flow).
- [ ] Review diff, publish fix PR against integration/all-prs; do not merge or change main.
