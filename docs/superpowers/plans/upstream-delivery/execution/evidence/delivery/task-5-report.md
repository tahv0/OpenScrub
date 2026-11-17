# Task 5 / P05 delivery report

Status: DONE. Local implementation, tests, self-review and commit completed on 2026-11-17. Independent review remains the supervisor's next step. No external publication.

## Identity and scope

- Brief: `task-5-brief.md` in this directory.
- Worktree: `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
- Branch: `pr/live-preview-snapshots`.
- Exact parent/base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
- Exact head: `b70d42011168192cdf7a9ef93a5e9419a92a1cdb` (`fix(web): publish and serve complete preview generations`).
- Branch was clean at dispatch and after commit; parent was verified again after commit. No branch switching, report/lifecycle implementation copying, nested agents, original-checkout product/data edits, dependency/tool installation, model download, version bump or publication occurred.
- Evidence: `/tmp/openscrub-task5/`; hashes and committed-file identities: `evidence-manifest.json`. Only these two designated SDD delivery documents were written in the original checkout.

Read the completed `live-preview-baseline-research.md` and retained `live-preview-baseline-evidence/probe.py`. Their actual producer/Cheroot findings were used as evidence, not treated as a product fix. The baseline's synthetic atomic-replacement control remains distinguished from the old in-place publisher.

Five changed files:

| File | Purpose |
|---|---|
| `openscrub_web.py` | Local complete-JPEG publisher and immutable preview response snapshot |
| `tests/test_live_preview.py` | 26 callback/route/helper cases, including actual configured Cheroot HTTP |
| `pyproject.toml` | Include `tests/` in sdist; existing wheel include policy unchanged |
| `README.md` | Discover both root and `tests/` suite with `python -m pytest` |
| `CONTRIBUTING.md` | Same necessary discovered-suite command update |

## Final contract

`WebCallbacks.scan_frame(frame, t, found)` keeps the existing wall-clock 0.4-second throttle, with `_last_frame` updated before an attempted publication. Failed attempts consume the interval. The callback still resizes to width 720, including upscaling, with integer aspect-derived height, and encodes JPEG quality 70. No image-content, browser-polling, inference-scheduling, other-route or entry-point change was made.

`_publish_preview_jpeg(path, image, quality) -> bool` calls real `cv2.imencode` before touching the served destination. False, absent or empty output returns False. Successful encoding is written into a same-directory temporary file, closed, and then atomically replaced over the served path. It returns True only after replacement. Expected `cv2.error` and `OSError` failures return False and retain the previous published bytes, or leave no preview if none existed. A `finally` block attempts temporary unlink on success and every exceptional path; unlink errors are suppressed so a filesystem cleanup refusal does not make preview publication fatal. There is no fsync/durability promise for this disposable image. `ValueError`, `KeyboardInterrupt`, `SystemExit` and other unrelated errors are not caught. Termination during replacement is tested to propagate while cleaning its temporary file and preserving prior bytes.

`job_preview` opens the served preview once, reads that generation before constructing the response, closes the descriptor, and passes a BytesIO snapshot to Flask `send_file`. Thus response length comes from the same immutable bytes as the body. Combined with the publisher's replacement rule, acquisition can span a publication without changing the opened generation. A missing job/file still returns 404; disappearance before open also returns 404. Other snapshot read failures produce an ordinary HTML500 before JPEG headers/body are sent. They cannot leave a partial JPEG200.

Preserved response behavior: `Content-Type: image/jpeg`, `Content-Disposition: inline; filename=preview.jpg`, `Cache-Control: no-cache, max-age=0`, expiry at max_age0, ETag conditional responses, byte Range/ETag If-Range handling, and `Accept-Ranges: bytes` in the tested stack. Intentionally changed fields:

- ETag is now the quoted SHA-256 digest of the response JPEG bytes, instead of path/mtime/size metadata. Equal-size distinct JPEGs with restored identical mtime do not validate as unchanged.
- Last-Modified is omitted. A second-resolution date is unsuitable for rapid preview generations; no date-based freshness validator is offered. ETag validation remains supported.

Memory is transient publication encoding and whole response snapshots, potentially including a BytesIO copy, in addition to existing decoded/resized frame memory. Each concurrent response may retain its own complete encoded snapshot while serving. No permanent per-job image copy or unbounded generation cache is introduced. Width 720 alone does not bound height or encoded bytes for arbitrary aspect ratios; no universal fixed-memory/byte ceiling or throughput claim is made.

## Focused RED → GREEN evidence

Environment: existing `/tmp/openscrub-baseline-20261116/env-opencv4.sh`, CPython3.12.16, OpenCV4.14.0, NumPy2.5.5. Task-local `env.sh`, `task5_isolation.py` and `sitecustomize.py` isolate data/models/cache/config/tmp, refuse non-file model fetching and outward socket connects, and prohibit Python writes outside this task root. The isolated tests reuse a task-local copy of an already available model for the existing full suite; no model download is performed. New preview tests use only synthetic frames and do not perform inference.

From the native worktree:

```sh
. /tmp/openscrub-task5/env.sh
python -m pytest tests/test_live_preview.py -q -s --basetemp=/tmp/openscrub-task5/red-tmp
python -m pytest tests/test_live_preview.py -q -s -k 'helper_returns or termination_during or acquisition_failure' --basetemp=/tmp/openscrub-task5/red-extra-tmp
# After the minimal production patch:
python -m pytest tests/test_live_preview.py -q -s --basetemp=/tmp/openscrub-task5/green-tmp
```

Before any production edits, the initial 22 cases yielded **20 failed, 2 passed in 8.49s** (`red.log`). The four additional helper/acquisition/termination cases then yielded **4 failed, 22 deselected in 1.14s** (`red-extra.log`), still before production edits. Those include missing helper status support, absent termination behavior, disappearance returning500, and snapshot-read failure returning200. After implementation, all **26 passed in 9.63s** (`green.log`). The two initially passing cases are the preserved real-encoding resize/quality/throttle controls.

All three race regressions run production `web._serve('127.0.0.1', 0, None)`, actual configured Cheroot with its 64-thread pool and `Server: openscrub`, real file I/O and real loopback sockets. Events and socket/readiness/join deadlines bound the schedules; there is no stress loop or timing sleep. The read observers delegate Werkzeug's real FileWrapper with its ordinary 8192-byte chunks. The HTTP client reads until connection close so it records short bodies rather than hiding them behind client framing errors. Every full200 JPEG assertion compares exact bytes against an independent real OpenCV encoding and verifies declared length equals received body length.

| Controlled schedule | Baseline RED result | GREEN result |
|---|---|---|
| Pause before first response read after headers; actual callback publishes B | Length 96,380; body complete B, 3,329 bytes | Length/body 96,380; exact complete A |
| Pause before second ordinary response chunk; actual callback publishes C | Length 96,380; body 58,060, exact recorded splice hash | Length/body 96,380; exact complete A |
| Pause before actual path open; harness replaces with complete callback-generated staged B | Length 96,380; body complete B, 3,329 bytes | Length/body 3,329; exact complete B |

The third row is an explicit atomic-replacement consumer control, not a claim that the old producer already replaced files. It deterministically covers the old path-stat/open gap and the new same-generation invariant. A separate real descriptor test reads the first 8192 bytes of A, invokes the real callback publishing C, then reads the remaining bytes from that same descriptor; GREEN is whole A while the served path contains whole C. This protects snapshot acquisition as well as later HTTP iteration.

Measured JPEG SHA-256 identities match the retained baseline:

- A, 96,380 bytes: `3a39eb931613d2a538eaf3415816e6459aa0ba9bd3d94d4c8f0ca968467f5d43`.
- B, 3,329 bytes: `ac757845e84629b627e18faea306583ec7dfabd22925e05b481a066d5f0e0771`.
- C, 58,060 bytes: `dd64fc72a11615f82f8e1319b7cfbea89e00923ec41d4fa207163a1a49387e27` (retained baseline generation; same fixture).
- RED second-read splice: `adae3b9f26140d45138151d04415d4be92f1d36d07f4f04db55270cf84a796d7`.

`red.log`, `green.log` and `floor.log` retain exact response headers, status, received lengths and body hashes, including dynamic Date/Expires and validator fields. Successful full-response assertions are distinct from legitimate empty304 and sliced206 responses. Conditional/range controls verify unchanged ETag →304 with empty body; `bytes=10-99` with matching If-Range →206 with exactly A[10:100], Content-Length90 and `Content-Range: bytes 10-99/96380`; unsatisfiable range →416; changed ETag →complete200; mismatched If-Range →complete200. The changed-generation case forces equal encoded length and identical restored file mtime.

Failure coverage injects false/empty/error encoding, temporary creation failure, a real partial temporary write followed by OSError, and replacement failure, each with and without an existing preview. It verifies no leftover temporary entry, exact prior-byte preservation or no file, consumed throttle interval, suppression before the next interval, and successful retry/HTTP read at the next interval. Helper Boolean status, unexpected programmer errors, termination and response acquisition errors are separately covered. No tolerant JPEG-decoding-only oracle or source inspection is used for the races.

The only initial tooling setup hiccup was using unavailable bare `python` before sourcing an environment; it made no source change. Existing Python3 tools were used to prepare the task harness. No dependency repair/install was needed.

## Stabilized verification

After focused GREEN, final source changes were limited to continuation indentation and the necessary README discovery-command correction; the following full/build/floor/runtime set all used the final committed bytes. There was one stabilized full-suite run, with no failures or skips:

```sh
. /tmp/openscrub-task5/env.sh
python /tmp/openscrub-task5/verify_imports.py /home/tahv0/.codex/worktrees/c832/OpenScrub
python -m pytest -q --basetemp=/tmp/openscrub-task5/full-tmp
```

**160 passed in 84.36s** (`full.log`). `imports312.log` asserts both engine and web module imports resolve to the active native worktree and records active OpenCV/NumPy imports.

Offline package build reused the already available pure-Python hatchling/pathspec/trove-classifiers symlinks under task108; installed tools were not changed:

```sh
. /tmp/openscrub-task5/env.sh
export PYTHONPATH=/tmp/openscrub-task108/build-tools:$PYTHONPATH
python -m build --no-isolation --outdir /tmp/openscrub-task5/dist
python /tmp/openscrub-task5/check_package.py
```

`build.log` confirms **sdist then wheel from that sdist succeeded**. `package-evidence.json` records all members, exact active source/test/config/README bytes in sdist, exact web source in wheel, tests absent from wheel under existing policy, unchanged `Requires-Python: >=3.9`, and Python3.9 grammar checks of all packaged Python. Artifact SHA-256:

- sdist: `66c2a12a615bc9200acf1195f86d9fb5d8ce7b1ef5a959e311ce1185e9c830d0`.
- wheel: `c0b4f3b600742de8133516bf27e29f6d6ee1c790c67167dce10427a514187427`.

Python floor used the existing CPython3.9.25/OpenCV4.14.0/NumPy2.0.2 environment, with task-local isolation overrides rather than the previous task's write-restricted hook:

```sh
. /tmp/openscrub-python39-20261117/env.sh
export PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:/tmp/openscrub-task5
export PYTEST_PLUGINS=task5_isolation
export PYTEST_ADDOPTS='-o cache_dir=/tmp/openscrub-task5/pytest-cache39'
export TMPDIR=/tmp/openscrub-task5/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task5/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task5/config
export OPENSCRUB_TASK5_RUN=floor-suite
python /tmp/openscrub-task5/verify_imports.py /home/tahv0/.codex/worktrees/c832/OpenScrub
python -m pytest tests/test_live_preview.py -q -s --basetemp=/tmp/openscrub-task5/floor-tmp
```

**26 passed in 9.69s** (`floor.log`), including actual configured Cheroot race/failure HTTP cases. `imports39.log` explicitly verifies active worktree engine/web imports and records the Python3.9/OpenCV/NumPy provenance. Floor and full verification used separate task-local runtime directories.

Fresh product-only offline installation and actual installed runtime:

```sh
. /tmp/openscrub-task5/env.sh
/tmp/openscrub-baseline-20261116/bootstrap/bin/uv pip install --python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python --no-deps --offline --target /tmp/openscrub-task5/install/lib/python3.12/site-packages /tmp/openscrub-task5/dist/openscrub-1.0.96-py3-none-any.whl
cd /tmp/openscrub-task5
python /tmp/openscrub-task5/check_installed.py
```

`install.log` confirms only this wheel was installed into the fresh task-local target. `installed-imports.log` verifies actual target engine/web imports. Both generated console scripts ran `--help` with exit0, retained in `openscrub-help.log` and `openscrub-web-help.log`. The runtime launcher configures synthetic storage, registers a synthetic preview and invokes the actual generated web entry point via runpy. Actual `main`, idle worker/watchdog startup and configured Cheroot run; they are not replaced. No work is queued for inference. Server flags are loopback HTTP, retention0 and a synthetic token. The installed preview returns exact A bytes/length and preserved MIME/filename/cache plus content ETag, and actual304/206/404 controls pass. SIGINT follows configured Cheroot shutdown and exits0. `installed-evidence.json`, `installed-server.log`, `installed-expected.jpg` and `installed-{home,preview,conditional,range,missing}.http` retain command, provenance and complete raw HTTP evidence.

Self-review checked all five changed files, catch/cleanup boundaries, descriptor/byte ownership, test event deadlines, defaults and scope, discovery, archive contents and installed provenance. `git diff --check` and staged checks passed. After commit, `verify_delivery.py` verified exact parent, clean branch, committed source/test byte equality, and artifact checks were repeated without rebuilding/rerunning tests. No further source changes occurred.

## Limits and handoff

Execution platform was Linux x86_64 on WSL2, kernel `6.18.58.1-microsoft-standard-WSL2`. Windows replacement/read semantics were not executed and are not claimed. Replacement refusal, including a platform/file-sharing OSError, retains the previous generation and allows a later throttled retry; cleanup is best effort if the filesystem itself refuses unlink. Filesystems must provide the normal same-directory atomic-replace semantics used here. Abrupt process death, storage durability, browser error rendering, throughput and lifecycle/deletion/vault ownership are outside this independent P05 patch. C01 remains responsible for later ownership-boundary integration.

No unresolved implementation concern was found in self-review. Known transient-memory and Windows-validation limits remain as described. Ready for independent review; do not publish without separate authorization.
