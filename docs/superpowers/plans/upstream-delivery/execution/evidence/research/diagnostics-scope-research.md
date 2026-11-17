# P12: a small opt-in persistent lifecycle record

Recommend P12 as a new private module, not a donor logger transplant. The concrete gap is losing the last known worker action/stage/progress and failure classification when the service exits. Keep bounded **in-memory UI logs and their cursor API in a separate PR**. P12 is independent of ETA and P03 polling.

## Evidence and limits

Research used full `git archive` exports of baseline `12919c96c6f7558136b50d7b4d85e5e6b62f1971`, donor `b7bc41727590e970e622c6ce9b46511e5e4f0295`, and donor `50e3816f361b0c0de673f4be90638c5d73149535` under `/tmp/openscrub-diagnostics-scope-20261117`. Git object reads only; no active native worktree reads, checkout/index/ref changes, product edits, donor execution, installation, network requests, model downloads, builds, suite runs or benchmarks. The two donor logger files have identical SHA-256 hashes. Planning reads were limited to P12 and the corresponding preservation diagnostics/lifecycle paragraphs.

`diagnostics-scope-evidence/results.json` records three tiny full-module synthetic cases: actual baseline worker failure followed by a fresh-process recovery; actual `main()` with an inert `_serve` raising an exception; and actual `main()` with inert `_serve` triggering SIGTERM. The `_serve` replacement never opened a listener. These establish startup/shutdown boundary behavior, **not configured WSGI/TLS-server behavior**. The worker used the actual missing-input failure path, not a replacement engine. Synthetic jobs/config/cache directories were temporary, joined worker threads released all file owners, all child processes exited, and the task-owned runtime directory was removed after capture. Existing `env-opencv4.sh` supplied the interpreter; imports asserted the pinned export.

Observed:

- The real worker caught a path-bearing scan error, left the worker alive, and retained its error in `job['error']` and `job['log']`. The UI also accepted inert OCR/query/provider sentinels through `WebCallbacks.log`. No app-owned persistent log appeared; only `input.mp4` and `options.json` remained in the job directory.
- A separate process rehydrated that job with generic “scan had not completed” text. The original error, callback messages and progress were gone. Recovery establishes incompletion, not its cause.
- The worker log retained 1,208 entries while `job_public` exposed only the last 30. `/log?from=1200` returned absolute list indices (`from=1200`, `len=1208`, eight lines). Stopping and checking a real worker restarted it; file-owner count after stop was zero.
- The injected serve-boundary exception produced a Python traceback containing the exception sentinel on stderr and exit 1; SIGTERM produced the existing stdout message and exit 0. Neither created a diagnostic file/marker. The existing startup banner includes the access token on stdout. Capturing console output is therefore not a privacy-safe implementation of P12.

Source-only inventory:

| Current owner/path | Behavior and diagnostic implication |
| --- | --- |
| `openscrub_web.py:490,538,903,955` | Plain per-job list; callbacks append arbitrary strings. `_run_job` catches `BaseException`, handles cancellation/SystemExit, publishes UI error state and clears ETA. Ordinary caught job errors need not reach stdout/stderr. Outer worker escape and watchdog paths print messages. Preserve queue generations, operation validity, release/finally logic and watchdog survival. |
| `openscrub_web.py:4438` | Rehydration infers error/review/done from uploads/reports/output. It does not recover the former diagnostic history. Successful report recovery likewise creates a fresh generic log. |
| `openscrub.py:3435` | CLI default callbacks print; web callbacks replace this with in-memory append. Console/container logging may survive externally, but application ownership/retention is unspecified. Dockerfiles set `PYTHONUNBUFFERED=1`; this fixes buffering, not persistence. |
| `openscrub.py:3398,4145` | Encoder stderr is captured to temporary files; failure construction embeds its tail in exceptions/UI logs. Other subprocesses use captured output or DEVNULL. These are inherited controls, not safe structured records. |
| `openscrub_web.py:3944,4580` | Existing vault atexit hook refuses unsafe locking while files/transitions are active. SIGTERM explicitly invokes it then `os._exit`; a second SIGTERM exits immediately. Diagnostics must fit these paths without adding joins on job/file locks or changing exit/lock behavior. |
| `openscrub_web.py:4702`; `openscrub.py:120,4791` | Cheroot suppresses known TLS handshake/browser noise; Paddle logger levels and temporary OpenCV DNN silence are existing controls. Do not capture root/library warnings or replace this filtering. |
| Config/packaging | No persistent-diagnostics flag in baseline `main`. Existing data-root logic distinguishes checkout versus installed/frozen per-user storage. Wheel/sdist include `openscrub_internal`; all Dockerfiles already copy that directory. PyInstaller analyzes static imports. |

## Donor audit: mechanisms versus payloads

Both donors' `openscrub_logging.py` are identical. Useful ideas are non-throwing emission, rotation, monotonic activity sampling, explicit start/finish, and a previous-run marker. Their defaults/ownership are unsuitable: logging starts unconditionally, rotation is 10 MiB plus five backups, monitor interval is 30 seconds, and `faults.log` rotates only at startup rather than by size.

| Donor source | Keep only a sanitized derivative | Exclude |
| --- | --- | --- |
| `JobLog.append:119–134`, web callbacks | None of the message bridge | Every arbitrary UI message. Actual engine callers include recalled OCR strings (`openscrub.py` baseline 8422), paths, custom labels and raw error/tool strings. |
| `event`, `exception`, formatter, global/root hooks | Fixed error codes, bounded numeric errno/exit code | Message/exception strings, traceback/source paths, arbitrary class/thread names, root/library records, Python warnings and native fault dumps. Credential substitution/regexes do not sanitize arbitrary data. |
| `start_job`, `finish_job`, `progress`, `heartbeat_once` | Ordinary scan/render start, known stage, numeric current/total and inactivity duration, terminal outcome | Learning context/stages; copied job dictionaries; raw resource-file strings; repeated separate stall warnings. No memory-pressure diagnosis. |
| HTTP request hooks, web `938–967` | None in this small scope | Request IDs/tracing, arbitrary JSON response `error` reason, exception info. Donor route templates omit query/body data, but that does not make response/exception content safe. No direct plate-query persistence was found in these hooks; it remains excluded by schema. |
| `_review_process:1545–1560` | A future separately justified known tool status/return code | Raw command/path/stderr; crop/frame/box metadata and images. No explicit crop payload emission was found in these logger calls, but errors can contain paths. |
| Settings/model/download/update/waveform hooks | Defer | Arbitrary exceptions, URLs, model/user identifiers and subprocess output. Only TOKEN is explicitly registered as a secret; no provider-secret allowlist exists. No direct provider credential source was found in inspected logger callers; generic exceptions/library records are still an unrestricted ingestion path. |
| `learning_session.py:591–599,640–682` and learning web hooks | None | Preflight stderr, training logfile path, child output, progress, model/refinement/workbench hooks. Source inspected only, never executed. |
| `running.json` handling | Bounded fixed control record | Echoing arbitrary parsed previous marker contents; arbitrary active-job snapshots. |

## Exact small contract for the P12 card

Add `openscrub_internal/diagnostics.py`, narrow hooks in `openscrub_web.py`, `tests/test_runtime_logging.py` and `docs/LOGGING.md`. Use only stdlib dependencies. One `--diagnostics` flag enables it; default false, no settings framework or UI. Importing or calling the disabled API must not create directories/files, install hooks, start threads or alter console output.

Use an event-specific allowlist, not arbitrary `str(value)` or JSON `default=str`. Reject/drop unknown kinds/fields and invalid types without persisting their values. No exception objects, `exc_info`, free-form messages, nested mappings, argv, paths, URLs, usernames, headers, tokens, OCR/phrase/plate queries, crop metadata, detections or job options are accepted. Strings are finite enums except internally generated versions/session references. Validate finite bounded numbers and cap encoded event size at 1 KiB. Keep existing UI errors unchanged.

Every line is JSON with `schema=1`, UTC timestamp, internally generated session reference and fixed `kind`; job actions use a session-scoped action reference generated inside the module. If retaining the proposed `event(..., job_id=...)` call shape, treat the job ID as an in-memory lookup key and **serialize only the generated action reference**, never the source job ID. Do not keep job objects alive. This intentionally gives action/stage diagnosis without a durable link to a deleted job.

| Event | Additional permitted fields |
| --- | --- |
| `service_started` | build version, transport enum `http/https` |
| `job_started` | action enum `scan/render`, stage `prepare` |
| `job_stage` | stage enum `scan/post/render`; one record on actual transition |
| `job_heartbeat` | known stage, nonnegative bounded integer current/total, monotonic `idle_seconds` (finite, bounded); no separate “stalled” diagnosis |
| `job_finished` | action, outcome enum `review/done/cancelled/error/superseded`; fixed error code `system_exit/os_error/value_error/runtime_error/other`, optional bounded integer errno/exit code; no arbitrary exception class name |
| `worker_restarted` / `worker_loop_error` | boolean active-action-lost; fixed error classification only |
| `service_stop` | reason enum `normal/sigterm/interrupt/startup_failure/serve_failure`, bounded active-action count, vault result enum `not_enabled/already_locked/locked/busy/failed` |
| `previous_run_unclean` | boolean previous active action; previous allowlisted stage only if valid; no echoed old JSON or OOM claim |

Hook placement: configure after CLI parsing and before startup work; start an action only after worker admission and `_operation_valid` checks in `_run_job`; sample counters from `WebCallbacks.progress` without file I/O per callback; emit stage transitions there; finish/unregister in the existing operation's finally block without reading a newer operation's phase as its outcome. Add fixed worker escape/watchdog events at existing catch/restart sites. No replacement worker implementation. Record stop/vault outcomes in the existing shutdown owner, preserving lock order and busy refusal. Existing atexit vault work must precede diagnostic close; SIGTERM explicitly closes before existing `os._exit`. `_serve` remains unchanged apart from outer service outcome handling: keep TLS suppression and existing stderr behavior. Unhandled startup/serve failures may retain the marker; no global root/exception hooks.

A single monitor may sample active action snapshots at most once per 60 monotonic seconds **per active job**, including under repeated progress/poll calls. Remove finished actions promptly; idle service emits no heartbeats. Inactivity is evidence of no reported progress, not proof of a hang. Do not add `/proc`, cgroup or platform resource probes to this first scope.

## Ownership, failure, retention and packaging

These are private **service-level**, sanitized records in `_data_root()/logs`, outside `JOBS_DIR` and outside vault encryption. No job-owned log/crop/cache is added. Job delete, retention sweep and vault lock must neither hold nor close logger files, and the logger must never reserve a job-file lease or recreate a deleted job. Service diagnostics can therefore survive a job deletion or locked vault until rotation/manual removal; document that explicitly. Per-session action references minimize persistent linkage. If actual stable job IDs or job-specific content later become required, revisit job/vault-owned storage in a separate proposal rather than slipping them into this schema.

Use `runtime.jsonl` with 5 MiB maximum and exactly two backups: at most 15 MiB of event files. Pre-encode/cap records and rotate before a write that would exceed the limit; do not assume stock rotation bounds an oversized record. Bound the single atomic running marker and its temporary file to 1 KiB each; no separate faults file. Directory permissions 0700 and files 0600 where supported; Windows relies on the user's profile ACL and needs native validation. An exclusive service-writer lock is needed to avoid two processes rotating the same file or mistaking one another's marker for a crash; a second live writer must disable its diagnostics, not overwrite the owner. No cross-process coordination framework.

Marker means “this diagnostics session has no observed orderly close.” Acquire exclusive writer ownership before reading it. Validate a bounded prior record, emit only approved derived fields, then atomically replace it. Remove it only after observed orderly shutdown and successful final record/flush; interrupted writes, failed cleanup, abrupt termination or storage failure may leave uncertainty. Report missing/unreadable state as unknown. SIGKILL, power loss, native crash and lost storage cannot guarantee a final event; an unclean marker **never identifies OOM**. An orderly service stop with active jobs does not prove those jobs finished or that vault encryption succeeded.

On unwritable directory, full disk, rollover/permission/closed-stream/marker failure: disable that sink, emit at most one fixed diagnostic-unavailable console message per minute without path/exception content, and let scan/render/save/cleanup continue. No recursive logging, busy retries, unbounded queue or diagnostics exception may escape. Keep startup/stop sync writes small; monitor failure cannot kill/restart the job worker. Persisted bytes are best effort, not a transaction or fsync durability promise.

Source/package work stays inside P12: static import of the private module; verify source CLI/web and installed entry points resolve it; inspect wheel/sdist contents and all Docker COPY/install paths (directory inclusion already exists); confirm PyInstaller static-import collection, using explicit hidden import only if evidence requires it. Never write into site-packages/Program Files. Installed/frozen startup/stop/error plus Windows rotation/reopen/permissions checks remain delivery validation, **not performed by this research**. Donor standalone `openscrub_logging.py` packaging changes are unnecessary for the private-package design.

## Separate retention PR and focused verification

A tail is not retention. P03 fixes client polling: the prepared client consumes authoritative returned `from/lines/len` and handles shrink/reset. It does not cap the producer list. Future server retention must preserve compatible absolute cursor semantics: monotonically increasing next sequence, retained base sequence, and explicit reset/clamp behavior for requests before base or beyond current end. Silently trimming/reindexing a list can stall or duplicate the client. Review retry/restart, concurrent append, `/jobs` tail/length and `/log` together. Choose count/byte caps and maximum line length in that separate API/privacy proposal; P12 must not change the list or polling contract.

P12 focused tests should cover default-off no side effects; exact event schema/type/size rejection with inert sensitive sentinels (including unknown fields and hostile exception/`__str__` values); 5 MiB/two-backup hard bounds; repeated callbacks and fake-clock heartbeat limits; genuine finish/cancel/failure and stale-operation ownership; worker survival/watchdog preservation; unwritable/open/rollover/flush/marker failures; validated prior-marker versus clean close, double close, SIGTERM and deliberate abrupt exit; absence of root/library/TLS/request capture; no job content/reference after delete; vault busy/failure and file-owner release; second writer refusal; package inclusion and writable installed/frozen roots. Use small synthetic processes and existing fixtures. No new training telemetry, model-library events, remote telemetry, request tracing, full settings subsystem or arbitrary exception capture.

Evidence: `diagnostics-scope-evidence/` contains commands/probe, compact source excerpts, export identities/source hashes, stdout/stderr/exit results and the checked JSON summary. These support the narrowed P12 justification, not implementation completion or platform certification.
