## Task 5: publish and serve one complete live-preview JPEG generation

### Global constraints

Preserve Austin upstream defaults, Python>=3.9, preview scale/quality/cadence, ordinary routes and entry points. No custom training/workbench, new dependencies/version, global storage framework or root helper files. Tests belong under `tests/`. Use synthetic input and existing isolated tools only. No original-checkout/user-data changes, publication or subagents.

### What, why and when

Actual callback/Cheroot schedules return a complete newer JPEG with an older Content-Length or a splice of two JPEGs. Atomic replacement alone leaves an independent path-stat/open race. Fix both producer publication and consumer snapshot identity in a separate P05 PR after its completed baseline. This branch is independent of report/lifecycle PRs; C01 later combines their ownership boundaries.

The supervisor will create `pr/live-preview-snapshots` in `/home/tahv0/.codex/worktrees/c832/OpenScrub` from exact Austin-plus-test-only base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` before dispatch. Read `live-preview-baseline-research.md` and the retained bounded actual-server probe, not the whole delivery plan. Preserve the baseline's exact measured distinctions; do not repeat unrelated research or infer Windows support.

### Implementation contract

1. Keep `WebCallbacks.scan_frame`'s existing throttle behavior:0.4seconds, including consuming the interval on an attempted publication; width720 including upscaling, integer aspect-derived height and JPEGquality70. The callback accepts the same frame/time/found inputs. No browser polling, inference scheduling or image-content change.
2. Add a small local `_publish_preview_jpeg(path, image, quality) -> bool`. Encode before touching the served destination; reject failed/empty encoding. Write the full encoding to a same-directory temporary file, close it, then replace the served path. Clean the temporary file on each failure. Expected encode/filesystem failures returnFalse and retain the previous complete preview (or no preview if none existed), allowing scan work to continue. Do not catch cancellation/process-termination exceptions or hide unrelated programmer errors. A preview snapshot is disposable; do not impose report durability or a general file-publisher abstraction without a demonstrated requirement.
3. `job_preview` must derive body and Content-Length from the same immutable generation. Use one opened-file snapshot and `send_file` with `BytesIO` or another equally small verified construction; path-stat followed by separate open is insufficient. Keep JPEG mime type, inline preview filename, no-cache/max_age0 behavior and ordinary conditional/Range behavior where supported. If Last-Modified is retained, derive it from the same opened generation, and ensure ETag validation cannot identify different bytes as unchanged. Document any deliberately changed response field. Missing preview still404; failures must not serve partial bytes.
4. Do not retain an unbounded generation cache or add a permanent per-job image copy. State memory honestly as transient encoded publication/response snapshots; width720 alone does not bound height or bytes for arbitrary aspect ratios. Atomic replacement plus immutable response snapshots must cover both established races.

### Evidence and delivery

Add real production callback/route regressions in `tests/test_live_preview.py`. Controlled events must bound waits and preserve real file/socket behavior; do not rely only on tolerant JPEG decoding or source inspection.

- RED→GREEN: publication between response metadata and read, between ordinary read chunks, and path-stat/open replacement or its equivalent same-generation invariant. Through actual configured Cheroot HTTP, assert body equals one whole expected JPEG byte sequence and declared length equals received length. Include no-preview404 and unchanged-preview conditional/Range controls, with exact response headers retained.
- Test failed/empty encoding, temporary-write/replace failure, temporary cleanup, prior-preview byte preservation and successful retry/HTTP read. Confirm throttle/scale/quality defaults unchanged using real image encoding. Keep callbacks nonfatal only for the selected expected failures.
- Run focused cases, then full suite at stabilized source, sdist→wheel/source/test inclusion, actual installed CLI/web startup and Python3.9 focused cases with active imports. Use existing compatible environments and task-local `/tmp/openscrub-task5`; no tool/model installation. Record Linux/WSL2 limits; Windows replacement/read behavior remains untested unless actually executed.
- Make only necessary branch-local discovery/documentation packaging updates. Self-review, commit and write `task-5-report.md` / `task-5-pr.md` under this SDD workspace with exact base/head, contract, RED/GREEN commands/results, complete-generation byte evidence and memory/platform limits. No throughput claim or external publication.

The compatible environments are `/tmp/openscrub-baseline-20261116/env-opencv4.sh` and `/tmp/openscrub-python39-20261117/env.sh`. Override source paths and assert actual imports. Native worktree/Git writes may require already-authorized `require_escalated`. No nested agents or changes to other branches.
