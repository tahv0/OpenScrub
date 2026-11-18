# fix(web): publish and serve complete preview generations

Candidate: `pr/live-preview-cache-regressions` at `ac0f5e4661701e954e04dbc95eb00d9317c04cc6`.

Branch: `pr/live-preview-cache-regressions`
Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`
Head: `ac0f5e4661701e954e04dbc95eb00d9317c04cc6`

A scan publication could overwrite a preview while Cheroot was serving it, returning a newer JPEG with the previous Content-Length or an old-prefix/new-suffix splice. A separate path-stat/open race survived an atomic-publisher-only control.

Encode each preview before touching its served path, write and close a same-directory temporary file, then atomically replace. Expected encoding/filesystem failures preserve the previous complete preview and remain nonfatal; cleanup is attempted on every path. The existing 0.4-second attempt throttle, width720/upscaling, integer aspect height and JPEG quality70 remain unchanged.

Serve one opened-generation BytesIO snapshot so body, length and SHA-256 ETag identify the same JPEG. Keep image/jpeg, inline preview.jpg, max_age0/no-cache and ETag conditional/Range behavior. Deliberately omit Last-Modified because second-resolution dates cannot identify rapidly changing frames. Missing preview remains404; snapshot read errors fail before a partial JPEG200 can be sent.

Changed files: `openscrub_web.py`, `tests/test_live_preview.py`, `pyproject.toml` (sdist tests), and README/CONTRIBUTING test-discovery commands. No dependency/version, browser, report/lifecycle or entry-point change.

Validation at the original runtime implementation `b70d420` (the reviewed header-test follow-up is recorded below):

- RED: 20 failed / 2 preserved controls, plus 4 additional failing failure/helper cases, before production edits. Actual configured Cheroot reproduced the retained complete-B/stale-length and exact-splice hashes.
- GREEN: 26 focused cases passed; bounded real HTTP schedules assert exact complete JPEG bytes and matching full-response length. Separate controls cover304/206/416, equal-size/equal-mtime changed ETags,404, failures/cleanup/retry, throttle/resize/quality, and acquisition failure before response.
- Stabilized full suite: 160 passed, no failures/skips.
- Active-source CPython3.9.25/OpenCV4.14.0 focused run: 26 passed, including real Cheroot schedules.
- Offline sdist → wheel from sdist succeeded; exact source/test inclusion, unchanged Python>=3.9 and packaged Python3.9 grammar verified.
- Fresh offline installed target: generated CLI/web help, actual web main/idle-worker/Cheroot startup, exact JPEG/length,304/206/404 and SIGINT exit0 passed.
- Diff checks and committed-byte/artifact provenance passed; worktree clean.

Memory consists of transient encoding and whole response snapshots, with per-concurrent-request cost; there is no retained generation cache or permanent per-job image copy. Width720 does not bound height or bytes for arbitrary aspect ratios. Verified on Linux/WSL2; Windows replacement/read behavior remains untested. Disposable previews have no fsync/durability guarantee; cleanup is best effort if the filesystem refuses unlink. No throughput claim.

Detailed commands, exact headers/byte identities, artifact hashes and limits: [retained delivery report](../evidence/delivery/task-5-report.md); original execution: `/tmp/openscrub-task5/`. Local commit only; no external publication. Independent task review approved the runtime change; the header-coverage suggestion is closed by the reviewed follow-up below.

Readiness descendant: `pr/live-preview-cache-regressions` at `ac0f5e4661701e954e04dbc95eb00d9317c04cc6`, based on retained original `b70d42011168192cdf7a9ef93a5e9419a92a1cdb`. Two added real Cheroot regressions pin Last-Modified absence and valid old/future If-Modified-Since requests returning complete status-200 responses and the same ETag. All 28 native owning tests and the two new Python 3.9 cases pass; production bytes/recipe are unchanged. [Follow-up report](../evidence/delivery/task-51-report.md) and [independent approval](../evidence/delivery/task-51-review.md). This is an update to the same focused contribution, with no external publication.
