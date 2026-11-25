# Stop and continue a scan: design

Status: draft for the owner's approval, 2026-11-23.

## Why

The owner runs long scans, often plate scans in the slow "letters only, no box
fallback" mode, on the same PC they use for games. They want to pause a scan to
free the GPU for a game and carry on later the same evening or the next day.
Today the only way to stop is Cancel, which throws the scan's progress away;
Retry starts again from frame 0. The owner lost a review earlier the same day
through a misunderstood rescan, so losing work is a known pain.

## Goals

1. **Stop**: a running scan can be stopped. The scan finishes the frame in
   hand, saves its progress into the job folder and ends. Every model is
   unloaded, so the GPU is fully free.
2. **Continue scan**: a stopped job continues from the saved frame. The finished
   job equals one from a scan that never stopped: one job, one review, one gap
   list, plate/face/person tracks that cross the stop point are one track and
   one card.
3. **Survives a Docker restart or a crash.** While a scan runs, progress is also
   autosaved at a fixed interval (my call: every 5 minutes of wall time). After a
   restart or crash the job appears as stopped at the last save, never vanishes
   and never restarts from frame 0 on its own.
4. **Every scan type**, built in two steps inside this project:
   - Step 1: detector-only scans (face, plate in every cover mode, person,
     qrcode, screen, anytext, manual track boxes). This is the owner's current
     need and is usable on its own.
   - Step 2: scans with text categories (OCR, the text memory, scroll tracking,
     backtracking), using the same mechanism. Owner's decision: "whatever we need
     to make this stop & continue possible", including saving the text memory.
     Until step 2 lands, a text scan shows no Stop button and Cancel warns.
5. **Cancel asks first** on a scan that has made progress: "Cancel throws away
   N minutes of scanning. Use Stop to continue later." Cancel itself keeps its
   meaning (progress is discarded).

## Non-goals

- Changing settings between Stop and Continue. The rest of the scan uses the
  saved settings.
- Reviewing a partial scan. The existing experimental "Stop & Review"
  (`checkpoint_review`, `docs/CHECKPOINT_CONTRACT.md`) does that for a narrow
  case and is not changed. The two features stay separate in the UI; Stop &
  Review keeps its own button when that option is on.
- Surviving a change of the video file, a model swap or a code change that
  alters scanning. Continue is refused in those cases (below).
- Choosing the cover style at render time (noted separately, not this project).

## Anti-goals (a failure even if it works)

- A continued scan whose report differs from an uninterrupted scan of the same
  input and settings, apart from timing/log fields. Under-blur from a lost piece
  of state is the worst outcome, because nothing would look wrong.
- A stopped job that disappears from the list or loses its progress silently.
- Old copies of the saved progress piling up, or saved progress outliving its
  use.
- Continue stitching together results from a different video, settings or
  model.
- Any change to scans that are never stopped.

## Behaviour

### Stop

- A **Stop** button beside Cancel on a running scan (scanning phase, including
  "letters only"). Pressing it sets the job's stop signal. The scan loop checks
  it between frames (the loop already has a `stop_requested` hook and a clean
  "stop_requested" exit used by Stop & Review).
- The scan writes the progress file, then the job enters a new phase
  **`stopped`** with "Stopped at 42% (frame b of N)" and two actions:
  **Continue scan** and Cancel (discard). Retry is not offered for a stopped job.
- A Stop pressed before the first frame is done behaves like Cancel without the
  question (nothing to keep).
- Stop is only offered when the job's scan type is supported (step 1:
  detector-only; after step 2: all).

### Autosave

- During a supported scan, the same progress file is written at a frame
  boundary at most every 5 minutes. Autosave must not slow the scan noticeably
  (measure; the raw sample list for a long 4K plate scan is the size driver).
- On server start, rehydration registers a job that has a progress file and no
  finished report as `stopped` at the saved frame, including after a crash in
  the middle of a scan. It never restarts such a job automatically.

### Continue

- Queued like any scan (single worker). The run re-opens the video, verifies the
  identity (below), restores the saved state, seeks to frame b using the
  existing verified seek (`_seek_cap`, which checks the decoded frame's own
  timestamp) and runs the normal loop to the end, then the normal end-of-scan
  processing once over all frames.
- State that is a function of recent frames (the backtrack buffer of ~2.5 s of
  small frames, the previous frame signature for scene cuts, the last OCR frame)
  may be rebuilt by re-reading frames just before b instead of being saved.
  Either way the result must match an uninterrupted scan.
- A continued scan can itself be stopped and continued again, any number of
  times.

### What is saved, and when it is deleted

The progress file holds exactly the scan loop's carried state at frame b and
nothing else: the raw per-frame detections collected so far (before track
assignment and smoothing, which already run once at the end of a scan), the
counters and per-frame arrays the end-of-scan processing needs (for example
scroll offsets and safety bands, scene cuts), and in step 2 the text memory
(the PII strings found so far, their category and sighting counts). No frames,
no images, no OCR text that was not classified as PII.

- One progress file per job, in the job folder. Each save replaces the previous
  one atomically (stage + replace, like report publishing); no history.
- Deleted when the scan completes (after the report is published), when the
  job is cancelled, when the job is deleted, and when the owner discards it
  after a refused Continue.
- While a continued scan runs, the previous file stays until the first new save
  replaces it, so a crash right after Continue loses nothing.
- It is in the job folder, so the vault encrypts it with the rest of the job
  and retention (`--retain-days`) treats the job like any other.
- It is never written outside the job folder (no temp dirs, no logs). Logs
  show counts and frame numbers only.

### Identity check on Continue

Continue is refused with a clear message, offering "Discard saved progress and
scan again", when any of these differ from what the progress file recorded:
the scan video's content (hash), the resolved scan settings and windows/zones,
the selected model files' content (hash), and a scan-format version constant
bumped whenever the scan loop's carried state changes. The existing checkpoint
identity code (`openscrub_internal/checkpoints.py`) may be reused where it fits;
this feature does not need its review/merge machinery. Hashing a long video
takes time; that cost is accepted on Stop/Continue (my call), not per autosave.

### Cancel

Unchanged meaning, plus the confirmation question above when the scan has made
progress (running or stopped). Cancelling a stopped job deletes its progress
file.

## Constraints

- Report JSON is a compatibility surface: extend, never break. The progress file
  is a separate, private file, never read by Review or rendering.
- Fail closed: if the progress file is missing, corrupt, from another version
  or fails the identity check, Continue is refused; it never guesses.
- No real data in tests; synthetic video only.
- Web job rules in CLAUDE.md hold: nothing may end the worker loop, no
  `sys.exit` path reachable from a job, request paths follow the containment
  rule.
- Builds on `fix/plate-lettering` (the letters mode adds scene cuts and letter
  state to the scan); a new branch from it (my call: `feat/scan-stop-continue`).

## Validation

- **The equivalence test (the core guarantee):** a synthetic scan run straight
  through, and the same scan stopped at several frames (including the first and
  last frames, a frame inside a plate/face track, and right at a scene cut) and
  continued, must produce reports equal after removing timing/log fields.
  Covers detector-only scans in step 1 (plates in full, strict and letters
  modes; faces; person with a stub/synthetic model where needed) and text scans
  in step 2 (with text memory recall across the stop point, scrolling and
  backtracking). Stopping more than once in one scan is included.
- Crash test: a scan killed after an autosave rehydrates as stopped and
  continues to an equal report.
- Identity tests: changed video, settings, model file or format version each
  refuse Continue.
- Retention tests: one file only, deleted on completion, cancel, delete and
  discard; never written outside the job folder.
- Web: Stop/Continue/Cancel flow, phases, rehydration, the Cancel question; UI
  checked in a headless browser at phone and desktop width.
- The owner's real test: stop a long letters-mode scan, play, continue, and
  compare with what they expect.

## Settled after the builder check (my calls)

- **Equality means exact.** Detections, boxes, polygons, scores, track/person
  ids, scene cuts, bands and every other report field must be equal, after
  removing timing/log fields only. Any state that cannot be rebuilt exactly
  from frames before b is saved instead. The test runs on CPU with synthetic
  video; on a real GPU, float noise between runs is accepted as it is today.
- **Identity fields.** In: the original input's content hash, the scan copy's
  content hash when one is used (normalization, tonemapping), every resolved
  setting that changes what is detected (categories, windows and zones by
  content, ignore regions, thresholds, scan speed and strides, tiling, plate
  coverage, track boxes, custom regex/phrase/allowlist contents), selected model
  file hashes and the scan-format version. Out: the execution backend
  (onnxruntime provider, OpenCV DNN target, CPU fallback), encoder and output
  or render options. A Continue on a different backend is allowed and logged
  loudly.
- **Hashing.** The original input is hashed once, after the models are
  unloaded on Stop (so the GPU is freed first) and again on Continue before the
  models load. The scan copy is hashed the same way. Autosaves record the
  hashes computed at the first Stop or, for a crash, the hashes are computed on
  Continue against the values recorded at scan start (my call: the scan
  records the hashes once at its start only when Stop is supported for it; this
  costs one read of the video at scan start, measured and logged).
- **Supported scan type.** Step 1 supports a job when no category in the job or
  in any window is a text category (built-in text categories, custom regex,
  phrase, mrn, anytext is visual and counts as supported). Manual track boxes
  run at the end of the scan from saved settings, as today, and are in the
  equivalence test.
- **Stop & Review.** The new Stop uses the same loop hook with its own exit
  reason; the Stop & Review exit path (audio deferral, prefix candidate) runs
  only for `checkpoint_review` jobs. A `checkpoint_review` job shows only Stop &
  Review. Unstopped scans must stay byte-identical (the hook is a cheap flag
  check).
- **Worker and phases.** A stopped job does not hold the worker. Continue
  queues like any scan behind other jobs. A crash during an autosave leaves the
  previous progress file (atomic replace). A job with a progress file and no
  finished report rehydrates as `stopped`; Stop & Review jobs keep their own
  rehydration path.
- **Vault and shutdown.** Scans only run while the job store is unlocked, as
  today, so autosave writes into an unlocked folder. On SIGTERM (`docker stop`)
  the server first asks a running supported scan to Stop and waits up to 20 s
  for its save, then locks as today. A save that does not finish in time leaves
  the last autosave.
- **Step 2** gets its own implementation plan after step 1 is in use; this
  document covers both.
- **Cancel with no progress** (queued, or before the first frame) cancels at
  once without the question.

## Left to the builder

The progress file's format (JSON vs a compressed format; the raw sample list can
be large), the exact autosave interval within "at most every 5 minutes", which
recent-frame state is saved vs rebuilt, how the scan loop's state is collected
(a state object is preferable to tracking 30 loose locals by hand), labels and
layout within the existing job view and mobile-fit rules.

## Calls I made (for the owner to check)

1. Stop is a new button; Cancel keeps discarding progress but asks first.
2. Autosave every 5 minutes; a crashed scan comes back as stopped, never
   restarts on its own.
3. Step 1 is detector-only scans; text scans follow in step 2 of this project.
4. Settings cannot change between Stop and Continue.
5. Hashing the video happens on Stop and Continue, not on every autosave.
6. Stop & Review stays as it is, separate.
7. New branch `feat/scan-stop-continue` from `fix/plate-lettering`.
