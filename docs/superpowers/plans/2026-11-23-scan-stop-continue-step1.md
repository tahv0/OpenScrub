# Stop and continue a scan (step 1: detector-only scans) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A running detector-only scan can be stopped (progress saved, GPU freed) and continued later, also after a Docker restart or crash, producing exactly the report an uninterrupted scan would.

**Architecture:** The scan loop's carried state is snapshotted at a frame boundary (top of the `while True` loop in `_run_scan_impl`) into one gzip-JSON progress file in the job folder: on Stop, and as an autosave every 300 s. Tracking, smoothing, grouping, letter masks and manual tracks already run once after the loop over the whole `raw` list, so a continued run restores `raw` plus a few counters, rebuilds two recent-frame values by re-reading the frames they came from, seeks to the stop frame and runs the normal loop and tail. The web app adds a `stopped` phase, a `continue` action and lifecycle rules for the file.

**Tech Stack:** Python 3.10+, OpenCV, Flask (openscrub_web), pytest; headless Chrome via playwright-core for the UI check (as used earlier on this branch).

**Spec:** `docs/superpowers/specs/2026-11-23-scan-stop-continue-design.md`

## Global Constraints

- Report JSON is a compatibility surface: extend, never break. The progress file is private; Review and render never read it.
- Fail closed: a missing, corrupt, other-version or identity-mismatched progress file refuses Continue; never guess.
- A scan that is never stopped must produce a byte-identical report and the same decode pattern as before (fast-skip and gap seeks keep working: the new stop check must NOT set `monitor_stop`).
- Equality means exact: every report field except timing/log fields (list them in one helper in the test file, with a reason per field).
- One progress file per job: `<job dir>/scan-progress.json.gz`; each save is stage + fsync + `os.replace`; no history, never written outside the job folder; logs show counts and frame numbers only, never detection text.
- Deleted on: scan completion (after the report is published), Cancel, job delete, Retry (fresh scan). Kept while a continued scan runs until the next save replaces it.
- Autosave interval 300 s wall time; SIGTERM waits at most 20 s for a Stop save.
- Step 1 support (`stop_supported`): no text category in `--categories` or any window (text = anything outside `{face, plate, person, qrcode, screen, anytext, none}`), and `checkpoint_review` off. Unsupported scans: no Stop button, unchanged behaviour.
- Identity includes engine `VERSION`, a new `SCAN_PROGRESS_VERSION = 1`, content SHA-256 of the original input and of the scan copy (when normalization made one), every resolved scan setting except an explicit exclusion list of paths and render/output options, and SHA-256 of every model file the detectors loaded. Execution backend (provider, DNN target, CPU fallback) is excluded and logged.
- Web rules in CLAUDE.md hold: nothing ends the worker loop, no `sys.exit` reachable from a job, request paths follow the containment rule, mobile fit (no horizontal scroll).
- No real data; tests use synthetic video and fake detectors (monkeypatched classes as in `tests/test_assisted_letters.py::scan_assisted`). Set `OPENSCRUB_NO_AUTOFETCH=1`; no test may download a model.
- Never commit anything under `openscrub_jobs/` or `tmp/`. Commit on `feat/scan-stop-continue` only; do not push.

## Review Focus

1. Stop pressed while the loop is in a fast-skip gap between windows, or after the last window (fast-stop) — Continue must give the same report, including `scene_cuts` entries at the post-jump frame.
2. The video replaced at the same path (or a model file swapped, or OpenScrub updated) between Stop and Continue — Continue refused with a message naming what changed; the progress file kept until the owner cancels.
3. A crash in the middle of an autosave write (stage file present, replace not done) — the previous progress file is intact, the stage file is removed at the next save or rehydrate.
4. After a Docker restart the job's source video is not mounted — the stopped job still appears in the list as stopped (today's rehydrate silently skips report jobs whose input is missing; that must not happen to stopped jobs), and Continue fails with "source video not found at <path>".
5. Continue pressed twice, or while another job runs — queued exactly once, runs after the current job.

---

### Task 1: Progress file format, atomic save/load, identity

**Files:**
- Create: `openscrub_internal/scan_progress.py`
- Test: `tests/test_scan_progress_file.py`
- Modify: `pyproject.toml` / wheel include lists only if `openscrub_internal` files are listed individually (check how `plate_letters.py` ships; follow the same).

**Interfaces:**
- Produces:
  - `SCAN_PROGRESS_VERSION = 1`, `PROGRESS_NAME = "scan-progress.json.gz"`
  - `class ProgressError(ValueError)` — unreadable/corrupt/other version.
  - `class ProgressMismatch(ProgressError)` with `.what: str` (human text, e.g. "the video file changed", "the plate model changed", "OpenScrub was updated", "scan settings changed: plate_threshold").
  - `encode_detection(d) -> dict` / `decode_detection(obj) -> Detection` — exact round trip for `Detection` and `NarrowPlateDetection` including tuple types (`cbox`, `aoff`, `poly` nested tuples), `manual_plate_quad`, `narrow_plate`, and the `_plate_policy_evidence` `MappingProxyType` attribute (encoded as a tagged dict, restored as `MappingProxyType`). Unknown extra instance attributes raise `ProgressError` at encode time (fail closed: a new attribute must be handled explicitly).
  - `save(path, state: dict) -> None` — gzip JSON (`allow_nan=False`), stage `path + ".stage"` in the same dir, fsync file, `os.replace`, fsync dir (posix). Removes a leftover stage first.
  - `load(path) -> dict` — raises `ProgressError` on any parse/version problem.
  - `file_sha256(path) -> str`
  - `settings_identity(args) -> dict` — JSON-safe snapshot of `vars(args)` minus `EXCLUDED_SETTINGS` (a module-level frozenset: `video, output, report, config, batch, from_report, original_video` path keys, render/output-only keys `mode, mode_map, coverage, face_shape, out_quality, out_format, encoder, hdr_output, preview, pad, draw_scores, audio_*` render options — the implementer lists every one present in `build_parser()` with a one-word reason comment; anything not listed is IN). Path-valued model/file args are replaced by their content hash.
  - `compare_identity(saved: dict, current: dict) -> None` — raises `ProgressMismatch` naming the first differing key.

- [ ] **Step 1: Write failing tests**
  - `test_detection_round_trip_is_exact`: build a plain dense `Detection`, one with `poly=((( .1,.2),(.3,.4)),)`, a `NarrowPlateDetection` via `openscrub._record_narrow_plate(...)`, and one carrying `_plate_policy_evidence=MappingProxyType({"origin":"detection","frame":7,"geometry_valid":True})`; assert `type(out) is type(d)`, `vars(out) == vars(d)`, `type(out.cbox) is tuple`, `isinstance(out._plate_policy_evidence, MappingProxyType)`.
  - `test_unknown_detection_attribute_is_refused`: `d.surprise = 1` → `encode_detection` raises `ProgressError`.
  - `test_save_replaces_and_leaves_one_file`: two saves, dir listing is exactly `[PROGRESS_NAME]`, `load` returns the second state.
  - `test_leftover_stage_is_removed_and_old_file_kept`: write garbage to `path + ".stage"` with a valid prior file present; `load(path)` returns the prior state; next `save` leaves no stage file.
  - `test_corrupt_or_other_version_is_refused`: truncated gzip, and `version: 99` → `ProgressError`.
  - `test_identity_names_what_changed`: two identities differing in `plate_threshold` → `ProgressMismatch` whose `.what` contains `plate_threshold`; differing input hash → `.what == "the video file changed"`.
  - `test_render_only_settings_are_not_identity`: changing `mode` from blur to inpaint leaves `settings_identity` equal.
- [ ] **Step 2:** Run `OPENSCRUB_NO_AUTOFETCH=1 python -m pytest -q tests/test_scan_progress_file.py` — expect FAIL (module missing).
- [ ] **Step 3:** Implement `openscrub_internal/scan_progress.py` (signatures above). JSON floats round-trip exactly via `repr`; restore tuples explicitly.
- [ ] **Step 4:** Re-run the tests — expect PASS.
- [ ] **Step 5:** Commit `feat(scan): progress file format for stop and continue`.

### Task 2: Engine stop, autosave and continue (the equivalence test)

**Files:**
- Modify: `openscrub.py` (`run_scan`, `_run_scan_impl`, new `ScanStopped`, `stop_supported`)
- Test: `tests/test_scan_stop_continue.py`

**Interfaces:**
- Consumes: Task 1 module.
- Produces:
  - `openscrub.stop_supported(args) -> bool` (rule in Global Constraints; reads `args.categories` and `args.windows_data`, `args.custom_regex` ids that are selected, `phrase`, `mrn`).
  - `class ScanStopped(Exception)` with `.frame: int`, `.total: int`.
  - `class ScanProgressControl` (in `openscrub_internal/scan_progress.py`): `__init__(self, path, *, stop_requested: Callable[[], bool], resume: bool, autosave_seconds: float = 300, clock=time.monotonic)`; attributes the engine fills: `.saved_frame`, `.total`.
  - `run_scan(args, cb=None, *, stop_requested=None, _checkpoint_stream=None, progress=None)` — `progress` is mutually exclusive with `stop_requested`/`_checkpoint_stream` (ValueError) and with `not stop_supported(args)` (ValueError: "stop and continue does not support text categories yet").

**Behaviour to implement:**
- At `run_scan` entry (before `normalize_vfr` mutates args) take `settings_identity(args)`. Start a daemon thread hashing the original input; hash the scan copy after `normalize_vfr` when `args.video` changed; hash model files after detectors load (record the actual file each loaded detector uses). The first save waits for the hashes (log "hashing the video for stop/continue: N s" once).
- Top of loop, before the existing stop/cancel checks: if `progress` and (`progress.stop_requested()` or autosave due) → snapshot. Invariant asserted at snapshot: `len(cum) == len(bands) == idx`. Snapshot keys: `version, identity, next_frame=idx, total, raw (encoded), cum, bands, scene_cuts, cut_idx, letter_stats, n_scans, last_scan_idx, scan_cx, scan_cy, prev_fcx, prev_fcy, zone_dropped, win_inactive, n_recalled, recall_counts`. Refuse to snapshot (raise `ProgressError`, scan continues without autosave — log once) if any found-derived structure is non-empty (`face_tracks, bt_deep, prev_keys, zdrop_raw, scans`, `memory` not None): those are step 2.
- On stop: after the save, release the capture and detectors (drop references; `cb.log` "stopped at frame b of N — progress saved"), raise `ScanStopped(idx, total)`. A stop at `idx == 0` raises `PipelineCancelled` without saving.
- Resume (`progress.resume`): run setup unchanged; `compare_identity(saved, current)` once hashes are ready (before the first frame is processed); restore the snapshot; skip the start-of-scan fast-skip block; rebuild `cut_sig` from frame `cut_idx` (if `assisted` and `cut_idx >= 0`) and `scan_small` from frame `last_scan_idx` (if `bt_on` and `last_scan_idx >= 0`) using `_grab_frame`; then `_seek_cap(cap, next_frame, fps)` (failure → `ProgressError("cannot seek to the saved frame")`). Then the normal loop and tail.
- After a successful tail the engine does NOT delete the file (the web does, after publish).

- [ ] **Step 1: Write the failing equivalence tests.** Helper `straight(tmp_path, monkeypatch, argv)` runs `run_scan` once; `stopped(tmp_path, monkeypatch, argv, stop_at=[...])` runs with a `ScanProgressControl` whose `stop_requested` returns True when the engine's next frame equals the next value in `stop_at`, catches `ScanStopped`, then continues with `resume=True` until done. Fake detectors (monkeypatched like `scan_assisted`) return boxes derived from frame content (a square that moves 3 px per frame, and disappears for frames 14–16) so tracks cross the stop point. `report_equal(a, b)` writes both states with `openscrub.write_report` and compares JSON after removing the timing/log fields.
  - `test_stop_continue_equals_straight_scan[plate-full]`, `[plate-assisted]` (with a scene cut at frame 20), `[face]`, `[person]`, `[qrcode]` (real cv2 detector, a synthetic QR drawn with `cv2.QRCodeEncoder` if available, else skip), each with `stop_at` in `([1], [13], [20], [N-1], [5, 13, 30])`.
  - `test_stop_in_fast_skip_gap_equals_straight_scan`: `--detect-windows-frac 0-0.2,0.8-1.0`, stop inside and right after the gap.
  - `test_autosave_then_crash_continues_equal`: injectable clock makes an autosave due at frame 25; the fake detector raises `KeyboardInterrupt`-like `RuntimeError("crash")` at frame 31; continue from the file → equal report.
  - `test_changed_video_refuses_continue`: rewrite the video with one different frame → `ProgressMismatch`, `.what == "the video file changed"`.
  - `test_text_scan_is_not_supported`: `stop_supported` false for `name`, for `plate` + a window with `email`, for a selected custom regex; `run_scan(..., progress=...)` raises ValueError.
  - `test_unstopped_scan_unchanged`: same argv with and without a `ScanProgressControl` that never stops (autosave disabled by clock) → equal reports and identical `cv2.VideoCapture.set` call list (monkeypatch spy) — fast-skip still used.
  - `test_stop_before_first_frame_saves_nothing`: stop at frame 0 → `PipelineCancelled`, no file.
- [ ] **Step 2:** Run `OPENSCRUB_NO_AUTOFETCH=1 python -m pytest -q tests/test_scan_stop_continue.py` — expect FAIL.
- [ ] **Step 3:** Implement per "Behaviour to implement". If a rebuilt value cannot be made exact, save it instead and note why in a comment.
- [ ] **Step 4:** Re-run — expect PASS. Also run `tests/test_assisted_letters.py tests/test_scan_stop_boundary.py tests/test_combined_plate_options.py tests/test_optional_plate_scan.py` — unchanged results.
- [ ] **Step 5:** Measure: autosave time for 100 000 synthetic raw rows (encode + gzip + write); log it in the report file of this task. If > 3 s, lower gzip level before anything else.
- [ ] **Step 6:** Commit `feat(scan): stop a detector-only scan and continue it exactly`.

### Task 3: Web job lifecycle (stopped phase, Stop, Continue, Cancel, rehydrate, watchdog, SIGTERM)

**Files:**
- Modify: `openscrub_web.py`
- Test: `tests/test_web_scan_stop_continue.py`

**Interfaces:**
- Consumes: `openscrub.stop_supported`, `ScanStopped`, `ScanProgressControl`, `ProgressError`, `ProgressMismatch`, `PROGRESS_NAME`.
- Produces (used by Task 4):
  - Phase `"stopped"` (not in `_ACTIVE_PHASES`); job fields `stopped_frame`, `stopped_total`.
  - `job_public` adds `stop_supported: bool`, `stopped_frame`, `stopped_total`, `stopping: bool`.
  - `POST /api/jobs/<jid>/stop_scan` → 200 when the job is scanning with progress control, sets the owner's stop event; 409 otherwise.
  - `POST /api/jobs/<jid>/continue` → 200 and `enqueue(job, "continue")` when phase is `stopped`; 409 otherwise (including when already queued).
  - Cancel route accepts phase `stopped`: deletes the progress file, phase `cancelled`.

**Behaviour:**
- `_run_job` for action `scan` of a supported job, and for `continue`: build args as Retry does (from `options.json`), create `ScanProgressControl(os.path.join(job["dir"], PROGRESS_NAME), stop_requested=owner.progress_stop.is_set, resume=(action == "continue"))`, call `run_scan(args, cb, progress=control)`, then the existing write_report/publish path; after a successful publish delete the progress file.
- `ScanStopped` → phase `stopped`, `stopped_frame/total`, `progress` = frame/total × the scan share of the bar, `eta None`, log line.
- `ProgressMismatch`/`ProgressError` on continue → phase stays `stopped`, `error` = "Can't continue: <what>. Cancel the scan and start it again." File kept.
- Any other exception during a supported scan when a progress file exists → phase `stopped` with `error` = "The scan stopped because of an error at N% (<msg>). Continue scan carries on from the last save." (keeps the disk-full hint from `_with_disk_full_hint`).
- Retry (fresh scan) deletes a leftover progress file first.
- `_rehydrate_jobs`: a dir with `PROGRESS_NAME` (or its `.osvault` form) and no completed report registers as `stopped` with frame/total from the file, **even when the source video is missing** (set `error` "source video not found at <path>" then). A dir with both a completed report and a progress file: delete the progress file, register normally. A leftover `.stage` file is deleted.
- `check_worker`: an orphaned scanning job with a progress file becomes `stopped`, not `error`.
- SIGTERM handler: before locking, if the running job is a supported scan, set its stop event and wait up to 20 s for its phase to leave `scanning`; then lock as today.
- Retention treats `stopped` like any finished job.

- [ ] **Step 1: Write failing tests** (fake detectors + synthetic video through the real worker, like `tests/test_render_failure_retry.py` drives `worker()`):
  - `test_stop_then_continue_reaches_review_and_deletes_progress`
  - `test_stop_scan_is_refused_for_text_jobs` (409, `stop_supported` false)
  - `test_cancel_stopped_job_deletes_progress`
  - `test_continue_twice_is_queued_once`
  - `test_changed_video_keeps_job_stopped_with_reason`
  - `test_error_after_autosave_becomes_stopped`
  - `test_rehydrate_registers_stopped_job_even_without_source`
  - `test_rehydrate_cleans_progress_of_completed_job_and_stage_files`
  - `test_watchdog_orphan_with_progress_becomes_stopped`
  - `test_sigterm_stops_running_scan_before_lock` (call the handler's stop-and-wait helper directly; do not send a real signal)
  - `test_retry_deletes_stale_progress`
- [ ] **Step 2:** Run them — expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run them plus `tests/test_render_failure_retry.py tests/test_assisted_letters_web.py` — expect PASS.
- [ ] **Step 5:** Commit `feat(web): stopped scans can be continued after a stop, crash or restart`.

### Task 4: UI (Stop, stopped view, Continue, Cancel question)

**Files:**
- Modify: `openscrub_web.py` (APP_JS / APP_CSS in `PAGE`)
- Test: `tests/test_web_scan_stop_continue.py` (page-string assertions)

**Interfaces:**
- Consumes: Task 3 routes and `job_public` fields.

**Behaviour and copy:**
- Running supported scan: a `Stop` button beside Cancel, title "Stop the scan and free the GPU. Continue later from this point." Pressed → disabled "Stopping…".
- Stopped job detail: heading "Stopped at 42% (frame b of N)", text "Progress is saved in the job folder. Continue scan carries on from here; the result is the same as an uninterrupted scan.", buttons **Continue scan** and **Cancel scan** (secondary). If `error` is set, show it above the buttons.
- Jobs list: stopped jobs show "stopped 42%" and a ▶ icon titled "Continue scan".
- Cancel on a scanning job with progress > 0, or on a stopped job: `confirm("Cancel throws away the scanning done so far. Use Stop to continue later.")` (stopped: "Cancel throws away the saved progress of this scan."). No question when nothing has been scanned.
- PAGE is a normal Python string: escape `\n`/`\t` in JS as `\\n`/`\\t`.

- [ ] **Step 1: Write failing tests:** `test_page_has_stop_continue_controls` asserting the strings above, `api/jobs/'+...+'/stop_scan`, `/continue`, and that `cancelJob` contains `confirm(`.
- [ ] **Step 2:** Run — FAIL. **Step 3:** Implement. **Step 4:** Run — PASS.
- [ ] **Step 5:** JS check from the evaluated page (CLAUDE.md verification command) and `node --check`.
- [ ] **Step 6:** Headless-browser check at 390 px and 1280 px with a synthetic stopped job and a running job (fake detectors): buttons visible, no horizontal scroll, Continue moves the job to queued/scanning. Screenshots only of synthetic content.
- [ ] **Step 7:** Commit `feat(web): Stop and Continue scan buttons`.

### Task 5: Docs and full verification

**Files:**
- Modify: `CLAUDE.md` (new bullet "SCAN STOP AND CONTINUE" in the web section: file name, lifecycle rules, step 1 scope, equivalence test name), `README.md` (short user section: Stop vs Cancel, what survives a restart).

- [ ] **Step 1:** Write the docs.
- [ ] **Step 2:** Run `python -c "import ast; ast.parse(open('openscrub.py').read())"` and the same for `openscrub_web.py`, the JS check, `OPENSCRUB_NO_AUTOFETCH=1 python -m pytest -q` (compare failing ids against the branch baseline with `grep -vxFf`; zero new failures), and `python -m build`.
- [ ] **Step 3:** Commit `docs: stop and continue a scan`.
