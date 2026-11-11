# Reliable progress and video sections implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans task by task; verify behavior with tests before claiming completion.

**Goal:** Recover stalled progress/log views, expose inexpensive learning progress,
and preserve/export reviewed sections while rescanning selected intervals.

**Architecture:** Extend the existing Flask worker/UI. Attached section jobs keep
candidate revisions isolated; the parent report and immutable snapshots retain
approved work. Pure report helpers merge only the selected absolute frame range.

**Tech Stack:** Python, Flask, OpenCV, FFmpeg, embedded browser JavaScript, pytest,
Playwright; no new shipped dependencies.

**Spec:** `docs/superpowers/specs/2026-11-11-progress-sections-design.md`

## Global constraints

- Work on `integration/all-prs`; preserve existing human corrections and reports.
- Additional status work must be throttled and must not run additional inference.
- Source hashes, verified frame bounds, and transactional publication protect data.
- Use standard Python 3.9+ syntax and package new modules in all distributions.

## Review focus

- Suspended or abort-insensitive requests cannot block a fresh active job view.
- Log reset/catch-up cannot retain an invalid cursor or unbounded DOM history.
- A failed or stale candidate cannot replace an approved interval.
- Detection and audio boundaries must not leak outside an exported interval.
- Source lifetime and approval metadata must survive restart and rendering.

## Tasks

### 1. Polling and logs

Files: `openscrub_web.py` polling/lifecycle and log endpoint;
`test_job_polling_browser.py`, `test_job_polling_node.py`.

- [x] Reproduce stale flights, visibility recovery, job switching and cursor reset.
- [x] Implement bounded cancellable polling with lifecycle wake and stale guards.
- [ ] Verify regression tests and existing browser review behavior.

### 2. Learning telemetry

Files: `learning_session.py`, `scripts/train_plate_seg.py`, telemetry tests.
Interface: `update_learning(job, stage=None, message=None, **progress_fields)`.

- [x] Test actual telemetry parsing and stage/counter timestamps.
- [x] Emit throttled trainer callbacks; connect existing refinement progress.
- [x] Show stage counts/age and existing rescan previews in the web job view.

### 3. Section report operations

Files: `video_sections.py`, `test_video_sections.py`.
Interfaces: `bounds`, `covered`, `slice_report`, `replace_range`.

- [x] Test frame boundaries, source mismatch, scroll offsets and crossing tracks.
- [x] Implement pure clipping/merging with rejected/manual/audio data retained.
- [x] Verify outside-range results remain identical and provenance is explicit.

### 4. Section workflow and exports

Files: `openscrub_web.py`, `openscrub.py`, `video_learning.py`, packaging files,
section route/browser/render tests, user documentation.

- [x] Test create/approve/candidate/export lifecycle and failure preservation.
- [x] Add section controls, attached jobs, source lifetime checks and recovery.
- [x] Bound refinement to section context and render exact approved intervals.
- [x] Document section review/export, source lifetime and progress limitations.
- [ ] Verify existing suite, actual synthetic rendering, browser flows and build.
- [x] Review diff independently and resolve actionable findings.
- [ ] Commit and publish to the authorized branch.

## Local verification checkpoint

The completed telemetry items were checked with a real small subprocess and
injected trainer callbacks; the scoped learning suite passed **212 tests**.
The section renderer/refiner suite passed **21 tests**, using actual CPU FFmpeg
output for exact source-frame selection, SDR/HDR boundaries, audio offset and
redaction, delayed audio, and short-decoder cleanup. A related compatibility
subset passed **67 tests** for existing audio, clipping, HDR, report and
Stop & Review behavior. The edited renderer/refiner files also passed Python
AST parsing and `git diff --check`.

Independent review added behavioral regressions for manual/audio-only drafts,
candidate tracking at approval, navigation during saves, precise input defaults,
model-list refresh, export retry, source retention and preview invalidation.
The final scoped PAGE run passed **32 tests**. Real Chromium cases are included
for inactive-tab recovery and desktop/mobile section approval/export; this
workspace cannot launch Chromium because its sandbox denies a required socket,
so those cases run in the branch's CI gate.

The final integrated local gate passed **615 tests in 243.46 seconds**, excluding
the browser-containing test files that require Chromium. The final renderer suite
also includes three real VFR/HDR parent-to-section exports that verify reuse of
the prepared source without full-video normalization in the child job.
The **1.0.89** source distribution and wheel built successfully; an isolated
installation imported all new runtime modules and registered the section routes.
Changed Python files, both evaluated PAGE script blocks and the staged diff
passed syntax/whitespace checks.

The user guide is `docs/VIDEO_SECTIONS.md`, linked from the README. The browser CI
gate runs on publication to `integration/all-prs`; its result is recorded against
the published commit. No production NVIDIA training or throughput benchmark was
performed for the telemetry or section changes.
