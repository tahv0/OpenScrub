# Task 621 / P06B.1: job file lifetimes

> The initial-submission evidence below records head4479b57. **Fix round1**, appended at the end, supersedes its source-selection and unchanged-JavaScript scope claims. The amended clean head is **c697d5a686d4dccbdf4f474567628d5d24e75a03**; use the fix-round evidence for that source. The284-test full run belongs to4479b57, not the amended head.

Background tracking, thumbnail decoding, report saves and streamed responses could still be using a job after its public phase became terminal. Vault lock and deletion checked phases alone: a real save stage could be removed by encryption, or a live stream's directory deleted. This change reserves file ownership before admission and keeps it through actual publication, decoder cleanup, queue handoff and WSGI close. Encryption/removal now refuses those owners at the same guarded boundary that admits work.

## Exact source and scope

- Reviewed base: `3795d49f6293baf7b8c35534862a4881447e1b16` (Task620's combined P06A/P06D/P07a).
- Local implementation head: `4479b57612f4e5c463d31900f76277a5fcebb8a9`.
- Branch/worktree: `pr/job-file-lifetimes`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`; clean after the single local commit. No remote publication or subagents.
- Eight changed files: `openscrub.py`, `openscrub_web.py`, `openscrub_internal/lifetimes.py`, `test_openscrub.py`, `tests/test_job_lifecycle.py`, `tests/test_job_response_lifetime.py`, `tests/test_large_report_io.py`, `tests/test_review_save_failures.py`.
- Original checkout remains `main` at `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`, with its existing untracked `docs/`. No original product files, original Git refs, individual reviewed branches, or user runtime data were changed. Only these requested SDD report/PR files were written there.

This is **in-process web ownership**, not filesystem or inter-process locking. CLI/GUI tools and other processes targeting the same live job directory are not coordinated. No report transactions, final engine publication callback, operation-generation cancellation boundary, replay IDs, report cache, custom training, models, dependency changes or version changes were added. Version remains 1.0.96. P06A's atomic helper and P06D's report document behavior are unchanged; evaluated `APP_JS` equals the exact base.

## Implementation and ownership boundaries

`openscrub_internal/lifetimes.py` is a 95-line private helper: initialized per-job state, store/per-job counters, idempotent leases, optional operation-local source leases, and a streaming iterable that closes its underlying iterator before releasing ownership. It has no repository/service abstraction or dependency imports. New jobs and both reportful/reportless recovery constructors initialize the same `_files` state; reports, options and `job_public()` never serialize it.

Admission and tree transitions use `VAULT_LOCK`. Brief registry checks take `JOBS_LOCK` only in **VAULT_LOCK → JOBS_LOCK** order. JSON publication, inference, decoding, ordinary file work, FFmpeg, response transfer and retry sleeps run outside both locks. No worker join occurs under either mutex, and already-guarded admissions reserve a queue ticket before calling the non-recursive `enqueue()` submission path after releasing the guard.

The relevant web boundaries are `_validate_files_locked` (identity/readiness/deleting), `_reserve_files_locked` and `_own_files`, the request hooks, `_reserve_queue_locked`/worker pickup, `_delete_job`, `_vault_lock_locked`/`_vault_lock_now`, setup/unlock, and retention. Live identity checks reject old captured dictionaries after removal. Internal `VAULT.closed`/`VAULT.error` flags distinguish readiness from a merely non-None key; public vault status adds a safe nullable recovery error without paths/keys.

- **Intake:** a store lease begins before multipart/form parsing and options writes. Each newly registered destination also gets a work lease through the entire intake response. Cancelled uploads cannot reopen retry/render while the upload still owns resources. Intake's source-job lease transfers without a gap to the queued ticket.
- **Queue/worker:** tickets include an idempotent lease as the fourth tuple element. Existing two/three-element entries remain accepted. State change and reservation happen together; pickup and cancellation decide the same ticket under the guard. A genuinely queued cancellation releases that ticket synchronously, permitting the existing immediate retry interface. An already picked-up worker releases only after its own final cleanup. Old skipped tickets cannot execute or release a later retry's lease. Existing `qgen` remains queue invalidation, not Task622's final-publication generation.
- **Tracking/thumbnails:** background leases are reserved before thread creation and released on failed start or worker finally. Single-tracker admission checks the actual reserved lease as well as public status, so `done` before cleanup does not admit a second tracker. The tracker callback exposes the existing job Event. Retry/render, or a new tracker needing a fresh Event, cannot clear cancellation while prior work still owns files. A new tracker gets a cleared Event only after old work releases it. Thumbnail normalization/registration precedes the thumbnail reservation; its decoder uses that admitted source snapshot and closes in finally.
- **Ordinary requests:** job input/media/frame/thumbnail operations own the primary job and any containing source job. Detached JSON/JPEG ownership ends after building independent bytes; report/download/video/cache `send_file` responses retain ownership through their WSGI iterator's close, exhaustion or exception. No whole-video buffering or transfer-time mutex was added. Content-Length, Range, download names and bytes are retained. Web decoder exception exits close their capture before releasing ownership.
- **Deletion/retention:** deletion atomically closes job admissions and refuses phase-active or owned jobs with 409. The existing reap/marker/retry policy remains. Actual reap/marker work owns the store; background retry sleeps hold no mutex or ownership, and each later attempt must reacquire readiness before touching the tree. Locked attempts defer to later retry/unlock/startup/retention. Retention shares the same deletion boundary, skips active old jobs and preserves age/marker policy.
- **Vault:** manual lock returns 409 for queued phases or any active owner; auto-lock's exact transition decision defers under the same definition. Setup, encryption, decryption and registration close admissions under the transition guard; waiting requests recheck readiness afterward. Failed transitions stay closed until explicit successful setup/unlock recovery. Unlock publishes readiness/key only after decryption and registration complete.
- **Shutdown:** a nonblocking registry probe is released before the normal lock-order path, and both transition acquisition and registry inspection are nonblocking for shutdown. A signal interrupting either non-reentrant mutex returns an honest NOT-locking diagnostic; it does not wait/join or encrypt busy files after a timeout. Idle encryption retains its existing tree-duration limitation.

### Approved source-path and decoder follow-through

The pinned inventory omitted `/api/server_video` and `/api/waveform`, whose server path can point into `JOBS_DIR`, including via a symlink. Supervisor-approved follow-through applies ownership to the validated canonical target before stat/read/stream access, preserving the existing inline confinement rules. Missing/deleting containing jobs are rejected; unrelated allowed external paths keep their existing behavior, including when the vault is locked.

A destination job B may reference job A's file as server input. Operation-local secondary leases identify the **physical canonical source** directly, without recursively following unrelated job metadata or introducing a global registry. Queued/worker/tracker/media operations retain A while reading it; active B therefore prevents deleting/retaining A. Requests, queue/worker args and background decoders use admitted source snapshots. A change to normalized input reserves a new containing owner before following it. Self/alias dependencies are deduplicated. Metadata/status/log/report-only requests do not pin input unnecessarily. **Idle references are not permanent retention pins**: A can be deleted once active owners leave, while B's status/log/delete remain usable and its missing input route fails honestly.

The supervisor also approved a release-only `track_manual_region` finally: the newly wired existing cancellation polling could raise before its old explicit release. Real synthetic VideoCapture diagnostics reproduced zero explicit releases on cancellation and failed open. The function now releases on every exit. Matching, thresholds, outputs, fallback polling and `_hold_rest` polling were not changed. An AST audit confirms this is the sole engine change after mechanically removing the old release statements; the nested docstring value is preserved exactly. Baseline/head NCC fallback output is exactly equal for all 26 samples on the same synthetic video.

## RED → GREEN evidence

All logs/scripts/data are under `/tmp/openscrub-task621` unless stated otherwise. The first RED cases ran before production implementation; later REDs cover refinements/bugs exposed while integrating the same ownership contract. Logs remain available rather than being overwritten by passing runs.

| RED evidence | Observed failure / purpose |
| --- | --- |
| `red.log`, `red-shutdown.log` | Four actual-route failures: real report stage removed by successful lock (then save FileNotFoundError); active tracking accepted as idle by lock; live Range download deleted; failed partial encryption admitted mutation. Separate held-VAULT_LOCK shutdown schedule self-deadlocked. |
| `red2.log`, `red3.log` | Intake allowed deletion before save completed. Sharpening the queue schedule from submission to pre-reservation showed cancel+retry executing the obsolete render instead of the retry scan (`[True]` versus `[False]`). The first too-late queue schedule had passed and was corrected, not counted as a behavioral RED. |
| `red4.log` | Four decoder error routes left captures explicitly unclosed; real tracking callback reported cancellation False after cancel. |
| `red5.log` | Early implementation's legacy queue path recursively reacquired JOBS_LOCK. Bounded strict-mutex test caught it before the compatibility branch was moved out of that lock. |
| `red6.log`, `red7.log` | Real synthetic tracker cancellation/failed open had zero explicit releases; terminal track status admitted another tracker before actual cleanup. |
| `red8.log` | Tracking could enter while cancelled worker ownership remained; a later tracker inherited the old set Event (`[True, True]` instead of `[True, False]`). |
| `red9.log`, `red10.log` | Six direct/symlink preview/waveform/dependent-intake routes bypassed source ownership. Initial over-broad dependent-input admission then hid an otherwise live job's status after its idle source was deleted; narrowed to actual input consumers. |
| `red11.log`, `red12.log` | Cancelled intake returned missing-input410 instead of busy409 before intake finished; work reservation fixed admission. The RED test's interrupted post-assert queue drain also triggered its leak assertion, so draining moved into finally. A signal interrupting JOBS_LOCK self-deadlocked; the new nonblocking probe/inspection fixed it without inversion. |

GREEN: final Python3.12 full discovery includes all **48 lifecycle/socket cases**, **6 new evaluated-JS consumer checks**, and the complete **230-test base**, totaling **284 passed**. Focused runs include `focused-final2.log` (48 passed); the exact committed tree is established by `full-final3.log` and the packaged source checks. Tests use actual Flask routes, real report staging/publication and representative real encrypt/decrypt, bounded Events, explicit thread joins and zero-owner cleanup assertions. Expensive inference is stubbed at its computational boundary. No sleep-only interleaving proof or miniature route implementation is used.

### Full-run fixture corrections, disclosed

`full1.log`: 235 passed / 2 failed (the run preceded nine later focused additions, so 230+7=237). Exact failures were `test_openscrub.py::test_job_retry_reuses_upload_without_a_new_job`, which manually switched a still-owned queued ticket through scanning/error before expecting missing-video410, and `tests/test_vault_cleanup.py::test_successful_report_publication_does_not_abort_vault_lock`, which saw owners leaked by old root fixtures discarding queue tuples and an unconsumed video response. Root fixtures now cancel actual queued work before the410 assertion, explicitly release discarded tickets, explicitly close the streamed response, and assert zero owners. All original behavior assertions remain.

`full2.log`: 265 passed (230+35 at that point). `full-final.log`: 275 passed / 8 failed after the later path/consumer additions. Two `tests/test_large_report_io.py::test_background_tracking_publication[False/True]` fixtures lacked a job cancel Event; six new `test_lifecycle_rejections_keep_current_review_and_drafts` variants incorrectly expected two audio spans although setup creates one. Added the synthetic Event/corrected the test expectation; no product workaround. `fixture-corrections.log`: all81 affected existing/new checks pass. `full-final2.log`: 283 passed before the extra JOBS_LOCK-held shutdown case. Final `full-final3.log`: **284 passed**.

## Actual Cheroot / socket evidence

`tests/test_job_response_lifetime.py` calls the shipped `_serve()` and its actual Cheroot configuration (`numthreads=64`), binding loopback sockets. Nine combinations exercise download/report/video × full completion/iterator error/client disconnect. The underlying file iterator pauses after its first yielded chunk, after Flask handler teardown. While genuinely active, actual HTTP DELETE and vault lock return409 and the owner remains live. Each close path releases exactly once; subsequent real HTTP vault lock succeeds.

Every response is a206 Range of **1,048,576 bytes** (`bytes 3-1048578`), with exact Content-Length and Content-Range. Complete responses equal the exact source slice; attachment names remain `synthetic_redacted.mp4` / `synthetic_audit.json`. Error reads produce an incomplete transfer; disconnect closes the actual client socket. Whole videos are never buffered by the product. Generated byte files/a padded synthetic JSON report are used, not user media.

`socket-fixed.log`: 9 passed; final full/floor runs include the same nine schedules. Initial harness-only errors are preserved in `socket.log` and `focused3.log`: replacing Cheroot's module Server broke its internal super lookup, and HTTPConnection had transferred a Connection:close socket before the test tried to shut it down. Observation now patches prepare only, and retains the socket before getresponse. These are harness corrections, not claimed product REDs.

The existing delete/retry/vault-lock browser consumers were inspected and exercised with the evaluated shipped JS:409/423 rejection returns before clearing/reopening the current job or deleting REVIEW_DRAFTS; rejected vault lock displays failure, never Locked. Six cases pass with no JS/UI/polling changes. This is a Node VM consumer check, not a new full browser/visual QA claim.

## Final verification commands and artifacts

Python3.12 environment: `. /tmp/openscrub-baseline-20261116/env-opencv4.sh`, then `PYTHONPATH=/tmp/openscrub-task621:$PYTHONPATH` and `PYTEST_PLUGINS=task621_isolation`. The task-local plugin reuses the supplied no-fetch policy with web data at `/tmp/openscrub-task621/runtime`; earlier checks used the supplied synthetic harness data only. Existing compatible model fixtures were reused, with no new models/dependencies. Runtime: Python3.12.16, opencv-python4.14.0.94, NumPy2.5.5, pytest9.2.0, Cheroot11.1.2, build1.6.1.

| Command | Result / artifact |
| --- | --- |
| `python -m pytest -q --basetemp /tmp/openscrub-task621/full-final3-tmp -o cache_dir=/tmp/openscrub-task621/pytest-cache` | Exit0; **284 passed in91.93s**, no failures/skips; `full-final3.log`. |
| `PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PIP_CACHE_DIR=/tmp/openscrub-task621/pip-cache python -m build --outdir /tmp/openscrub-task621/dist` | Exit0; isolated Hatchling1.33.0 sdist, then wheel **from that sdist**; `build-final2.log`. No network/dependency/version change. |
| `PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:$PYTHONPATH python /tmp/openscrub-task621/check_packaging.py` | Exit0 on final committed head; `packaging-final-head.log`, `packaging.json`. Exact source/test bytes in sdist/wheel, all packaged Python parses with3.9 grammar, unchanged project/build metadata and APP_JS, Node parse, tracker-only AST scope, and real source-updater inclusion. |
| `python /tmp/openscrub-task621/check_tracker.py` | Baseline/head NCC sample sequence exactly equal,26 samples; `tracker-output.log`, `tracker-output-equality.json`. No tracker model used. |
| Local no-deps wheel install using bootstrap pip `--python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python --target /tmp/openscrub-task621/installed/site-packages` | Exit0, `install-final2.log`; installed engine/web/private helper bytes equal final committed tree. No environment dependency install/change. |
| `python /tmp/openscrub-task621/check_installed.py` | Exit0; actual installed CLI `--help`, actual installed web console entrypoint/configured Cheroot, homepage/jobs API, real vault setup/lock/unlock and idle SIGTERM exit0; `installed-startup-final3.log`, `installed-startup.json`, `installed-web.log`. Fresh task-local synthetic profile per run, no HOME changes or model fetches. |
| `git diff --check` and clean worktree status | Exit0; committed head4479b57612f4e5c463d31900f76277a5fcebb8a9. |

The first installed attempt used the compatible venv's absent pip; bootstrap pip's `--python` managed the pipless target without installing pip/dependencies there. An installed recheck initially reused the prior synthetic keystore (correctly locked at shutdown); the harness now creates a fresh task-local profile per run. Initial logs remain. No success was inferred from those failed harness invocations.

### Fresh Python3.9 floor runtime check

The supervisor provided `. /tmp/openscrub-python39-20261117/env.sh` after implementation stabilized. `python39-imports.log` asserts engine/web/lifetimes import from this exact active worktree, **not** the floor environment's installed base. Python3.9.25, OpenCV4.14.0.94, NumPy2.0.2, Cheroot11.1.2 were used with the supplied outward-network/model-fetch/write audit. `task621_python39` directs runtime data into `/tmp/openscrub-python39-20261117/task621/runtime`; fixtures/cache are task-specific under that task621 directory.

Exact focused command: `python -m pytest -q tests/test_job_lifecycle.py tests/test_job_response_lifetime.py tests/test_review_save_failures.py::test_lifecycle_rejections_keep_current_review_and_drafts --basetemp /tmp/openscrub-python39-20261117/task621/pytest-tmp -o cache_dir=/tmp/openscrub-python39-20261117/task621/pytest-cache`.

Exit0: **54 passed in8.60s**, `python39-focused.log`. This exercises all new lifetime/decoder/actual-Cheroot/API-consumer regressions at the floor; no runtime incompatibility was found and the package floor was not raised. The full230-test baseline was not repeated on3.9; final3.12 full/build evidence is separate.

## Packaging and remaining limits

The sole added runtime wheel file is `openscrub_internal/lifetimes.py`; wheel/sdist include the private package already. All three Dockerfiles copy the whole package. PyInstaller's web entrypoint statically imports the new module, so existing analysis follows it; no hidden dynamic import was introduced. The actual source updater installed and byte-verified the helper from the locally built hash-verified sdist. README/CONTRIBUTING and pytest default discovery already include `tests/` and remain consistent. No unrelated packaging refactor was needed.

Linux verification does **not** establish Windows file-sharing/close behavior, macOS behavior, actual frozen-executable behavior or TLS/proxy disconnect behavior. Docker CLI exists but the daemon socket returned permission denied (`docker-availability.log`), so no container build/run is claimed; container/frozen inclusion is a static source check. No new model inference/download, training, performance or large-corpus privacy claim is made.

Cancellation promptly sets the existing Event and preserves ownership until cleanup. It is **not** a promise that already-running cancelled work cannot publish before it exits. NCC fallback's main loop and `_hold_rest` still lack cancellation polling; existing Vit polling and `_track_person_dense` polling are unchanged. The latter has its existing finally restoring detector state and releasing capture; this task did not exercise actual detector models. Future P10/O02 should audit backend cancellation latency/resource behavior under real inference. The new release-only finally closes manual-track captures even on the existing Vit PipelineCancelled branch and failed open.

An indefinitely running/blocked owner can keep delete/manual lock busy; auto-lock defers and shutdown reports that plaintext may remain. Idle encryption still needs sufficient shutdown grace for the actual tree; there is no new deadline guarantee or forced encryption after timeout. Existing marker retries are bounded attempts with30-second sleeps and may require unlock/startup/retention to complete.

External filesystem changes, hard-link aliases outside the canonical job tree and other processes are outside the guard. Canonical symlink aliases into the tree are covered; idle cross-job references do not pin retention. Existing thumbnail-cache invalidation and rehydration's output.mp4 assumption remain separate limitations.

Latest-document lost updates, per-job report transactions, final cancellation/publication ordering and P07b replay/idempotence remain the named next tasks. Fresh independent review is still required; no merge/publication was performed.


## Fix round1: selected render originals and the shared allowlist

**Reviewed fix base:** `4479b57612f4e5c463d31900f76277a5fcebb8a9`.
**Amended head:** `c697d5a686d4dccbdf4f474567628d5d24e75a03`, commit `Own selected render sources and shared allowlist access`.
Branch remains `pr/job-file-lifetimes` in the same native worktree and is clean. No remote publication, subagents, original-checkout product/Git changes, user data, dependencies, models or version changes. The original reviewed Task621 base remains3795d49.

The independent review's two Important findings were verified, not inferred from the diff: a normalized job B could render from job A's `provenance.original_input` while owning only B, and `/api/allowlist` could recreate plaintext inside an already locked store. Both supplied actual-route reproductions now pass on the amended source. The fix changes five files: engine, web, existing private lifetime helper, evaluated-JS tests and new scoped `tests/test_job_source_allowlist_lifecycle.py`.

### Render source contract and interfaces

Render admission reads provenance under the already admitted primary/current-input request lifetime, **outside VAULT_LOCK**. `_select_render_input(job, owner)` resolves the canonical candidate, reserves a live containing job before its first source existence check, and transfers the exact selected canonical input into the queue lifetime before releasing admission ownership. `_reserve_queue_locked(..., render_owner=...)` reserves that selected source rather than assuming `job.video` is what rendering reads. Self/symlink aliases are deduplicated by containing-job state. The source stays owned from accepted queueing through worker/normalizer/hash/decode/report/cleanup completion; a public cancelled phase does not release it.

The same preparation occurs in `enqueue(job, "render")` for skip-review's automatic scan→render handoff. A computationally stubbed scan changes its real args to a normalized B path; real report publication and `_update_job_source` then record B/current plus A/original, and the internally queued render retains A after the scan worker releases it. Legacy queue entries resolve their source during owned pickup. An unowned direct private `_run_job` invocation now acquires an ordinary lifetime before entering its existing body.

Worker args carry a private `_report_input` path. `run_pipeline` honors it before normalization and does not re-follow a later report's original-input field into another unowned source. The normal CLI/GUI branch, when this private pin is absent, is structurally unchanged and explicitly tested for original/alias/missing behavior. Its public signature is unchanged. `_settings_dict` explicitly excludes the pin; a real web render checks that it never appears in persisted options, report settings/document or public job JSON. The private lease gains only a consistently initialized `report_input` flag; no transaction/generation/caching/publication callback is added.

Selection deliberately distinguishes missing originals from stale owners:

- A missing original in a live ready source job is statted while that job is reserved, then its unnecessary provisional lease is released and rendering falls back to the admitted current input.
- An absent original under an unregistered containing job also falls back. Only an absence/existence metadata check is made under the guarded store admission; the unregistered path is never opened/decoded. If that path exists, admission returns404 rather than reading an orphan/condemned file.
- A registered deleting source is refused409 before its file is opened; ordinary live identity/vault-readiness checks remain in force.
- Self aliases need no secondary owner. Existing external originals retain default selection and external missing originals retain fallback; external mutation remains outside coordination.
- Missing/malformed reports preserve the existing asynchronous render acceptance/error behavior. They are not silently repaired, cached or published by admission.

The selected **input**, not the document, is pinned. The engine still loads its render document independently; this is not latest-document serialization or report transaction safety. Normalization's derived outputs remain inside the already owned destination job. Idle references still do not permanently pin source retention, and stronger cancel/publication ordering remains Task622.

### Shared allowlist and demonstrated consumer follow-through

The existing request hooks now acquire a **store-wide** lifetime for both GET and POST `/api/allowlist` before any existence check/open. Existing read handles explicitly close within that lifetime. Ready API behavior remains unchanged: words/count/path shape, whitespace stripping, deduplication, remove and clear. Closed/partial transitions return423, and a running write causes manual vault lock409. An Event-controlled write pauses after the real file opens but before writing; lock refuses, the write finishes, then real encryption/unlock restore the exact committed bytes. Reverse-order GET/POST waiters prove a request waiting behind encryption rechecks and cannot recreate plaintext. A real partial-encryption failure keeps both methods closed until recovery.

Inspection found a concrete consumer issue caused by these required refusals: `loadPersist` unconditionally parsed a423 HTML body and rejected without handling; `rmPersist`/`clearPersist` ignored POST status and started an unawaited reload. The supervisor authorized a demonstrated narrow correction after evaluated-shipped-JS RED. Only four JS functions change: new `persistFailure` plus `loadPersist`, `clearPersist`, `rmPersist`. Reads/mutations preserve displayed data on failure, show locked/recovery/network failure through the existing `persistnote`, and refused mutations do not reload or claim success. Successful acknowledged mutations still reload normally. No new UI mode, controls, polling, draft behavior or unrelated JS changed.

### RED → GREEN, including corrected selection of tests

Artifacts are under `/tmp/openscrub-task621/fix1`.

- `red.log`: **7 failed,11 deselected** before fixes. Failures cover allowlist locked GET/POST, queued render originals direct/symlink, extant unregistered/deleting owners and late provenance switching. Both supplied reviewer findings are represented by actual routes/worker/real run_pipeline, pausing only at normalization computation.
- `js-red.log`: **9 failed,71 deselected** before consumer changes. Evaluated emitted-JS checks expose escaping/silent locked/recovery/network refusals and unwanted reloads.
- `allowlist-green.log` is an intermediate mixed result: the `-k allowlist` expression also matched the *filename* of the new source/allowlist file, so six not-yet-fixed render controls were selected as well (**6 failed,26 passed,66 deselected**). This was not claimed as an allowlist or render success; the subsequent explicit file/node matrix resolves them.
- `green1.log`: **30 passed in2.40s**, all initial18 new route controls plus12 new consumer cases after both fixes. Later skip-review, ordinary-engine-source and asynchronous invalid/missing-report controls bring the new route file to24 cases.
- `targeted.log`: **188 passed in41.15s**, clean output, using the matrix below. This includes all old lifecycle/stream schedules, the24 new route controls,12 new consumer cases, real report roundtrip/failure tests and selected real HDR/audio/worker regressions.
- `review-repros.log`: **10 passed in0.21s** for the two verbatim reviewer reproductions plus8 existing vault-cleanup cases. Reproduction output is explicit: allowlist `route_status:423, vault_locked:true, plaintext_created:false`; render uses A's actual input, real DELETE A returns409, `source_exists:true`, B is rendering. Workers join and fixtures assert zero ownership.
- `python39.log`: **36 passed in2.63s** for all24 new route cases and12 new evaluated-JS cases. `python39-imports.log` verifies engine/web/helper come from the active worktree, not the floor environment's installed4479/3795 source. Python3.9.25 uses the supplied network/model/write isolation and task-specific fixture/cache paths.

No full-suite repeat was needed for this focused correction. The earlier284-test full3.12 result is retained as evidence for FIX_BASE4479, **not claimed for c697d5a**. The amended source is covered by the scoped188-case matrix, separate10-case reproduction/vault check and36-case floor check.

### Exact verification and packaging

For3.12, source `/tmp/openscrub-baseline-20261116/env-opencv4.sh`, then set `PYTHONPATH=/tmp/openscrub-task621:$PYTHONPATH`, `PYTEST_PLUGINS=task621_isolation`. The actual targeted command was:

```sh
python -m pytest -q \
  tests/test_job_lifecycle.py tests/test_job_response_lifetime.py \
  tests/test_job_source_allowlist_lifecycle.py tests/test_large_report_io.py \
  tests/test_report_roundtrip.py tests/test_review_save_failures.py \
  test_openscrub.py::test_from_report_respects_edits \
  test_openscrub.py::test_report_roundtrip_preserves_tracks \
  test_openscrub.py::test_hdr_probe_and_tonemap \
  test_openscrub.py::test_hdr_output_preserved \
  test_openscrub.py::test_hdr_output_sdr_toggle \
  test_openscrub.py::test_audio_redaction_mute_and_report_roundtrip \
  test_openscrub.py::test_render_strips_source_metadata \
  test_openscrub.py::test_render_survives_iphone_spatial_audio_track \
  test_openscrub.py::test_web_worker_survives_a_dying_job_and_cancel_clears_the_queue \
  test_openscrub.py::test_job_retry_reuses_upload_without_a_new_job \
  --basetemp /tmp/openscrub-task621/fix1/targeted-tmp \
  -o cache_dir=/tmp/openscrub-task621/fix1/cache
```

Verbatim reviewer/vault check uses `PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub/tests:/tmp/openscrub-task621:$PYTHONPATH` and:

```sh
python -m pytest -q -s /tmp/openscrub-task621-review/test_uncovered_owners.py \
  tests/test_vault_cleanup.py \
  --basetemp /tmp/openscrub-task621/fix1/review-repros-tmp \
  -o cache_dir=/tmp/openscrub-task621/fix1/cache
```

For3.9, source `/tmp/openscrub-python39-20261117/env.sh`; prepend active source and `/tmp/openscrub-task621/py39-harness` to PYTHONPATH and use `PYTEST_PLUGINS=task621_python39`:

```sh
python -m pytest -q tests/test_job_source_allowlist_lifecycle.py \
  tests/test_review_save_failures.py::test_allowlist_refusal_preserves_display_and_reports_error \
  tests/test_review_save_failures.py::test_allowlist_ready_success_updates_display_after_acknowledgement \
  --basetemp /tmp/openscrub-python39-20261117/task621/fix1-pytest-tmp \
  -o cache_dir=/tmp/openscrub-python39-20261117/task621/fix1-pytest-cache
```

| Build/check | Exact evidence |
| --- | --- |
| `PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PIP_CACHE_DIR=/tmp/openscrub-task621/pip-cache python -m build --outdir /tmp/openscrub-task621/fix1/dist` | Exit0; `build.log`; isolated Hatchling1.33.0 builds sdist then wheel **from that sdist**. No new dependency/version or network access. |
| `PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:$PYTHONPATH python /tmp/openscrub-task621/fix1/check_packaging.py` | Exit0 on final committed head; `packaging-final-head.log`, `packaging.json`. All source/tests exact in artifacts; all packaged Python parses with3.9 grammar; Node syntax passes. Engine AST differs from FIX_BASE only by the private selection branch/settings exclusion; default selection else branch is exact. JS differs only in the four named functions; other JS and outside-scope web Python are exact. Project/build metadata unchanged. |
| Source updater / release inclusion | Same checker executes actual hash-verified source updater with the local sdist and byte-compares amended runtime sources; existing full-package wheel/sdist/container copy and frozen static imports still include the helper. No new runtime module or packaging refactor. New scoped tests are included in the sdist/default test discovery. |
| Bootstrap pip `--python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python install --no-index --no-deps --target /tmp/openscrub-task621/fix1/installed/site-packages .../dist/openscrub-1.0.96-py3-none-any.whl` | Exit0, `install.log`; project only, no environment dependency changes. |
| `python /tmp/openscrub-task621/fix1/check_installed.py` | Exit0; `installed-startup.log`, `installed-startup.json`, `installed-web.log`. Actual installed CLI help and web console entrypoint/configured Cheroot, ready allowlist add/read, real vault setup/lock, GET+POST423 while locked, unlock preserving words, idle SIGTERM exit0. Fresh task-local profile; no HOME/model changes. |
| Installed bytes and local Git | `installed-source-equality.log`: final engine/web/helper bytes equal c697d5a. `git diff --check 4479b57612f4e5c463d31900f76277a5fcebb8a9..HEAD` exits0; worktree clean. |

The existing nine real Cheroot Range completion/error/disconnect schedules run in the188-case matrix and pass; this fix did not change the iterable/stream close mechanism. No Windows/macOS/container/frozen/TLS execution was added. The previous Docker daemon permission limitation remains; static inclusion is not a container execution claim.

### Remaining limits / re-review scope

Both Important blockers are addressed and ready for scoped re-review; independent approval is not claimed. Coordination is still in-process. Other processes, external filesystem mutation/hard links, idle source references and external inputs retain the earlier documented limits. Missing-source fallback uses metadata to distinguish absence from an extant orphan; it never opens an unregistered source. Store allowlist ownership coordinates lifetime, not simultaneous allowlist-update serialization or atomic-write durability. Report-document lost updates, latest-document transactions, cancellation/publication ordering and P07b replay remain deferred. Source pinning does not claim those guarantees or change backend cancellation latency.
