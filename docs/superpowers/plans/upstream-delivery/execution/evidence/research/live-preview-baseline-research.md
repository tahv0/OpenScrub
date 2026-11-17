# P05 actual producer / HTTP baseline

Research status: **reproduced on local Linux, 2026-11-17**. The actual pinned `WebCallbacks.scan_frame` and `job_preview` can produce both mixed-image response bytes and a `Content-Length` mismatch through the application's configured Cheroot WSGI path. No product fix was implemented.

The read-before-publication schedule returned a complete newer JPEG with the previous JPEG's length. The read-between-chunks schedule returned an exact old-prefix/new-suffix splice. A separate, explicitly synthetic atomic-replacement control reproduced the consumer's independent stat/open race. Thus an atomic publisher alone does not establish P05's stable-response contract.

## Identity, isolation and scope

Requirements: [live-preview-baseline-brief.md](live-preview-baseline-brief.md), P05 in `docs/superpowers/plans/upstream-delivery/01-core-ux-and-reliability.md`, and the P05 paragraph in [core-history-audit.md](../../preservation/core-history-audit.md). The history paragraph was treated as source-audit context, not passing runtime evidence; donor code was not imported.

- Exact base commit: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
- Exact tree: `795af785b672d397d2e287b5b963c10dcc4dbdf8`.
- Full `git archive` export: `/tmp/openscrub-live-preview-baseline-20261117/export`. Both application and engine imports are asserted to come from this export. The active native worktree was not imported or changed.
- Exported `openscrub_web.py` SHA-256: `9835e1137abee62c0a78e2669ed8bae7059e36bf4bed9f5c7a44f0eb8b40ed3a`.
- Exported `openscrub.py` SHA-256: `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`.
- Exported `zones_ui.py` SHA-256: `a1cdb4e5be90cf2e4282268f7c2499ed2b00879a034f68235d35d56cd74752f7`.
- Existing isolated environment: `/tmp/openscrub-baseline-20261116/env-opencv4.sh`; Python 3.12.16, OpenCV 4.14.0, NumPy 2.5.5, Flask 3.1.3, Werkzeug 3.1.9, Cheroot 11.1.2. Full Python/platform details are in `results.json`.
- Fresh task-local `JOBS_DIR`: `/tmp/openscrub-live-preview-baseline-20261117/synthetic-data/http-live-preview/openscrub_jobs`. Models and other runtime data are redirected beneath this task's `/tmp` root. `OPENSCRUB_NO_AUTOFETCH=1`, the existing isolation helper rejects non-file model fetches, and the probe rejects socket connects outside loopback. No model/dependency downloads or model inference were performed.
- Server: actual `web._serve('127.0.0.1', 0, None)`, actual `cheroot.wsgi.Server`, production `server_name='openscrub'`, 64 worker threads, kernel-assigned ephemeral loopback port. This run used port 52997; reproduction obtains a new port automatically. Only preparation/readiness and lifecycle were observed; the server class, route, application and callback were not substituted. No worker, retention job, browser or full pipeline was started.
- Boundaries: six HTTP requests total: three controls and three distinct schedules. Events control progress; there is no timing sleep, random stress loop, full test suite, build or benchmark. The server was stopped in `finally` and its serving thread joined; the process exited 0. No Git-state changes were made. Writes were restricted to this report/evidence and synthetic task-local `/tmp` paths.

The initial sandboxed attempt could not bind a loopback socket (`EPERM`); that log is retained as `sandbox-binding-denied.log`. The same probe then ran successfully with the loopback permission already authorized by the brief. This is a Linux/WSL2 result, **not Windows coverage**.

## Actual source path and existing limits

Pinned source line numbers below refer to the full export; the relevant application and installed dependency source is preserved with numbered lines in [source-audit.txt](live-preview-baseline-evidence/source-audit.txt).

1. `openscrub.py:8047–8060` draws current detections onto a copied frame and calls `cb.scan_frame(...)` when `wants_frames` is true. The research invokes the actual callback directly with synthetic display frames, avoiding unrelated scan/model work.
2. `openscrub_web.py:361–367`: `WebCallbacks.wants_frames=True`; each callback initializes `_last_frame=0.0`.
3. `openscrub_web.py:414–423`: `scan_frame` obtains `time.time()`, skips calls with `now - _last_frame < 0.4`, and updates `_last_frame` **before** resizing/writing. This is a wall-clock per-callback publication throttle of nominally 2.5 writes/second. A fresh callback was used for each scheduled publication so the real gate passes without sleeps or a fake clock. A separate consecutive-call control confirmed the immediate second call preserves the prior JPEG and leaves `_last_frame` unchanged.
4. The same callback sets `scale=720/w` and resizes to `(720, int(h*scale))`, then calls `cv2.imwrite(served_preview_path, small, [cv2.IMWRITE_JPEG_QUALITY, 70])`. This normalizes to width 720, including upscaling narrow inputs; it is not a downscale-only rule. Aspect-derived height uses integer truncation. Rate, resize and JPEG quality all live in this one method. The generated frames here are 720×240 and retain that output shape.
5. **Failed-encode/publication handling is absent here.** The Boolean result of `cv2.imwrite` is ignored, and there is no local encode check, nonempty-buffer validation, temporary file, replacement, cleanup, exception recovery, or guarantee to retain the previous complete JPEG. A failed write attempt has already consumed the callback's throttle interval. The pipeline callback invocation has no surrounding local preview-error catch. `_run_job`'s generic `BaseException` handler at `openscrub_web.py:778–791` can mark the whole job as error if an exception escapes; that does not detect a `False` return or restore a JPEG. Failure injection was not run in this baseline; absence of handling is a source finding, not a measured claim about every OpenCV failure mode.
6. `openscrub_web.py:1074–1080`: `job_preview` resolves the job, checks `os.path.exists`, and returns `send_file(path, mimetype='image/jpeg', max_age=0)`. There is no stable snapshot, preview-specific lock or publication coordination.
7. Installed Werkzeug's `send_file` obtains `size`/`mtime` from `os.stat(path)`, then separately calls `open(path, 'rb')`, constructs a file wrapper and assigns the earlier `size` to `Content-Length`. Cheroot supplies no `wsgi.file_wrapper` in this environment, so the real Werkzeug `FileWrapper` performs ordinary `read(8192)` calls. Actual Cheroot `Gateway.respond` consumes that iterable and writes chunks. The probe's stack evidence shows this path.
8. The browser's existing detail refresh uses `setInterval(refresh,900)` at line 2118. During `scanning`, lines 2174–2177 update the preview image URL with a timestamp query. That polling cadence is separate from the callback's 0.4-second disk-write throttle and does not synchronize I/O. No browser changes are required to expose the server-side race.

`max_age=0` generates `Cache-Control: no-cache, max-age=0`; it does not freeze file bytes or reconcile path metadata and the opened file.

## Real generated JPEG identities

The actual callback generated all expected JPEGs with its real resize and `cv2.imwrite` path. A uses deterministic random pixels; B is solid red; C combines green with a different deterministic random texture. They are distinguishable by encoded bytes and decoded pixels. Expected files are retained.

| JPEG | Bytes | SHA-256 |
|---|---:|---|
| A, noise | 96,380 | `3a39eb931613d2a538eaf3415816e6459aa0ba9bd3d94d4c8f0ca968467f5d43` |
| B, red | 3,329 | `ac757845e84629b627e18faea306583ec7dfabd22925e05b481a066d5f0e0771` |
| C, green/texture | 58,060 | `dd64fc72a11615f82f8e1319b7cfbea89e00923ec41d4fa207163a1a49387e27` |

Each of the three unscheduled HTTP controls returned 200 with an exact expected hash, matching length, SOI/EOI markers and a decoded 240×720×3 image. These controls establish that the harness normally serves the actual JPEG unchanged.

## Controlled interleavings and HTTP results

The probe wraps **only** `builtins.open` for the exact response JPEG opened in `rb` mode, delegating to the original `BufferedReader`. Its `read` method leaves arguments, offsets, return values, buffering, descriptors, exceptions and close behavior unchanged; it waits immediately before one selected real read. All other opens delegate normally. The caller remains the real Werkzeug file wrapper. No synthetic response bytes or altered read sizes are inserted. A separate stat wrapper delegates the actual stat and pauses before returning that exact captured result in the third schedule. Both wait/release points have bounded event deadlines.

An observer delegates Cheroot's actual `start_response` and records the real headers before iteration. `response.socket_headers_already_sent` in the event log is the value captured **at start_response time**, not a fresh measurement at the later read pause. For the second-read schedule, Cheroot has consumed/written the first yielded chunk before requesting the second read.

| Case | Causal schedule | HTTP Content-Length | Received bytes | Exact received identity |
|---|---|---:|---:|---|
| `read-1` | Stat A; open A; capture A headers; pause before real first read; actual callback overwrites same pathname with B; resume | 96,380 | 3,329 | Complete B, hash `ac757845…e0771` |
| `read-2` | Stat/open A; capture A headers; read/yield first normal 8,192 bytes of A; pause before real second read; actual callback overwrites with C; resume at offset 8,192 | 96,380 | 58,060 | Exactly `A[:8192] + C[8192:]`, hash `adae3b9f26140d45138151d04415d4be92f1d36d07f4f04db55270cf84a796d7` |
| `stat-open-atomic` | Actual `send_file` stats A; pause before returning A's stat; actual callback generates B in a separate synthetic staging job; harness `os.replace`s B over served path; return captured A stat, then real route opens B | 96,380 | 3,329 | Complete B, hash `ac757845…e0771` |

All three actual responses were `HTTP/1.1 200 OK`, `Content-Type: image/jpeg`, `Content-Disposition: inline; filename=preview.jpg`, `Cache-Control: no-cache, max-age=0`, `Accept-Ranges: bytes`, `Connection: close`, and `Server: openscrub`. Their stale-size-based ETags and full Date/Last-Modified/Expires values are preserved in each raw `.http` file and `results.json`. A raw loopback socket reads until the requested connection closes, recording all header/body bytes rather than hiding a short body behind an HTTP client framing exception.

For both in-place schedules the served inode remained 101521 while the callback changed size and contents. In the atomic control it changed from 101521 to 101572. The numeric identities are run-specific; the unchanged/changed relationships identify the different mechanisms.

The first-read response is a complete, decodable B image with the wrong advertised length. A content decoder alone would pass it; HTTP framing does not. Its content is newer than the metadata captured by the response.

The second-read response has SOI and EOI markers and OpenCV's tolerant decoder returns a 240×720 image, **but emits `Corrupt JPEG data: premature end of data segment`**. The body matches neither A nor C and exactly matches the recorded byte splice. Its decoded pixel mean is BGR `[178.007, 86.238, 181.450]`, compared with A `[127.365, 127.457, 127.326]` and C `[84.280, 167.757, 83.975]`; decoded mean absolute differences from A and C are 68.331 and 103.180. It is corrupted mixed-image data, not either complete image. Therefore merely checking `imdecode(...) is not None` would be an insufficient regression assertion.

The third schedule is **a diagnostic control, not current producer behavior or an implemented fix**. It uses the actual callback to generate the replacement and the actual unchanged route to consume it; the harness supplies only the atomic path replacement. It isolates the consumer stat/open gap even when the published file itself is complete. The earlier two schedules establish the current in-place producer problem independently.

## Smallest fix boundary and required regression

Keep the implementation local to `openscrub_web.py`: one preview publication helper called by `scan_frame`, and stable response construction in `job_preview`. Existing `_last_frame`, width/aspect rule and quality 70 should remain explicit and unchanged unless separately justified. P06A's report helper does not need to become a generic storage framework simply to share an atomic-write name; no donor journal or Findings code is needed.

There are two distinct obligations:

1. **Producer completeness:** encode before touching the served pathname; reject false/empty encoding; write a complete same-directory temporary file and atomically replace the destination only after success, with cleanup and prior-preview retention on failure. This protects an already-open reader's old inode on Linux. Test the real helper for failed encoding and failed temporary write/replace, verifying the old JPEG remains byte-identical and no incomplete snapshot is published.
2. **Consumer snapshot:** determine headers and response content from the same stable generation. A small preview-specific bytes snapshot read after atomic publication, served as immutable bytes/`BytesIO`, closes the demonstrated path-stat/open gap and avoids a later streaming mutation. Opening first and deriving metadata from that same stable descriptor is another possible design, but must establish its header/body invariant explicitly. `send_file(path)` with a new atomic producer still has the reproduced stat/open gap. Reading bytes without fixing in-place publication would still permit a torn read. Decide consciously how to preserve current cache/conditional/range behavior when constructing the snapshot.

The future regression should run through the configured real Cheroot WSGI path, retaining the event schedules from this probe. Assert response body equals **one complete expected generation**, decode succeeds, and declared length equals actual body bytes. Include both the pause after metadata/header capture and a pause between normal read chunks to reject a mixed response; add a stat/open replacement schedule or equivalent deterministic proof that metadata and bytes cannot diverge. Under a bytes-snapshot consumer, the read wrapper may move to snapshot acquisition and the test must still hold the publication/response schedule at the correct boundary. Include a no-preview/404 control and failed publication followed by a valid HTTP read of the prior generation. These are test requirements, not claims that a fix already passes.

The existing width normalization bounds width, **not absolute JPEG bytes or height for arbitrary aspect ratios**. A snapshot design should describe memory as the encoded current preview plus transient encoding/response snapshots, with no retained unbounded generation cache. Establish an explicit byte ceiling if a hard bound is required; do not claim a universal fixed bound solely from width 720. This bounded research did not establish Windows replacement/open-file behavior, browser error rendering, production failure frequency, or deletion/vault lifetime semantics. Those remain separate gates; P05's local-Linux reproduction gate is satisfied.

## Reproduction and retained evidence

From the source repository, using the existing environment and loopback permission:

```bash
task_root=/tmp/openscrub-live-preview-baseline-20261117
evidence=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/live-preview-baseline-evidence
mkdir -p "$task_root/export"
git -C /home/tahv0/src/OpenScrub archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 | tar -x -C "$task_root/export"
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
cd "$task_root/export"
timeout 90 python "$evidence/probe.py" "$evidence" > "$evidence/run.log" 2>&1
```

The source export command reads Git; it does not check out, branch, stage, commit or change product files. Rerunning overwrites this task's evidence and synthetic preview files. The successful run exited 0; the assertions intentionally confirm the observed baseline failures as well as exact control behavior, not repaired product behavior.

- [probe.py](live-preview-baseline-evidence/probe.py): complete reproducible script, six requests, bounded events, actual server lifecycle and baseline assertions.
- [results.json](live-preview-baseline-evidence/results.json): source/environment/server identity, full HTTP headers, expected/received lengths and hashes, image checks, exact interleaving events, read sizes/offsets/stacks, inode relationships, shutdown and throttle observations.
- [run.log](live-preview-baseline-evidence/run.log): successful exit's printed observations and actual decoder corruption warning.
- [source-audit.txt](live-preview-baseline-evidence/source-audit.txt): exact numbered producer/route/call-site/server and installed dependency source.
- [artifact-verification.json](live-preview-baseline-evidence/artifact-verification.json): independent reparse of all six retained raw HTTP responses; expected/body hash and length checks, exact-splice confirmation, source-hash comparison and probe syntax validation. All checks passed, confirming three controls and three baseline failures.
- `expected-*.jpg`, `control-*.http`, `control-*.body.jpg`, `read-1.http`, `read-1.body.jpg`, `read-2.http`, `read-2.body.jpg`, `stat-open-atomic.http`, and `stat-open-atomic.body.jpg`: actual generated images and raw received bytes. In total the evidence folder is under 1 MiB.
- `sandbox-binding-denied.log`: the initial environment limitation before the successful authorized loopback run.
