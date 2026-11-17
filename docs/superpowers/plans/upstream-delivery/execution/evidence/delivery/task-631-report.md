# Task631 / P06C.1: unchanged report saves

Successful saves now skip report encoding, staging, fsync and replacement when the request's final effective assignments and additions leave the raw report unchanged. Every request still validates against a freshly parsed report under the existing transaction. The measured benefit is limited to no-op publication; sparse/bulk remain regression controls.

- Exact reviewed P07b base: `12919c96c6f7558136b50d7b4d85e5e6b62f1971`.
- Exact committed head: `3457efac574d74a7d2377cbc0d44bb0b87462c3a` (`Skip publication for effectively unchanged report saves`).
- Branch/worktree: `pr/unchanged-report-saves`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
- Local work only. No publication, subagents, dependencies, version/default changes, user files, models/downloads, environment migration or original-checkout product edits. These requested handoff documents are in the supervisor's SDD directory. Artifacts are under `/tmp/openscrub-task631`.

## Implementation and compatibility

`job_save_edits` retains auth/vault/file admission, current-job/deleting/worker gates, one existing per-job report lock, required `detections`/`render_state` accesses and a fresh parse on every request. It performs the same ordered enabled, box, time, manual/replay and audio operations before deciding persistence. Conversion errors, missing/malformed reports, supplied ID/creation validation and atomic rejection all retain their existing paths. There is no empty-request shortcut, cache, second lock, revision or edited flag.

A local `assign` helper records the original presence/value only before each effective destination's first assignment. The ledger keys the actual target dictionary and field, so `"0"` and `"00"` can change then restore a box/time destination. Original containers remain referenced, never copied: the existing operations replace those containers rather than mutate them. The final comparison covers only touched fields; appended detection count separately forces publication. No unrelated motion/band/transcript/unknown subtree is copied or traversed for equality. Existing full enabled, identity lookup and suggestion loops still run.

The private `_same_json_value` recursively compares JSON-shaped touched values. It preserves missing versus stored defaults, exact scalar types (including bool/number and int/float), signed floating zero, list order and complete dictionary keys/values. Explicit audio remains whole-list replacement: removing an additive span field is a change. Existing float conversion, ignored indices/invalid intervals, last_seen insertion/clamping and normalization remain unchanged. Nonfinite or unusual **touched** values conservatively require publication, even when the encoder would emit equal nonfinite text; tests cover this. Untouched nonfinite/additive data does not itself force a write. The JSON encoder/import policy is unchanged.

Any effective change or appended legacy/identified row publishes exactly once through unchanged `atomic_report(..., indent=1)`, with acknowledgement after success. Replay-only still validates the complete existing Task72 identity and immutable creation contract, preserves mutable current fields and can skip publication. Replay plus edit publishes; conflicts fail atomically; distinct IDs/equal geometry and legacy additions stay distinct. Both paths derive the existing `ok`/`total`/`suggest_allowlist` response from the locked current document. Browser code is byte-for-byte unchanged, including deliberate same-value actions, response checks, identity/value acknowledgements and newer-edit retention.

A true no-op preserves exact original bytes/formatting, inode/device, mtime/ctime and mode on the exercised Linux filesystem. Atime is not promised. Retention uses job-directory mtime, not report mtime; skipping creation/replacement of staging entries also avoids their incidental directory-mtime refresh. A no-op save is therefore not a new retention-activity update. The existing admission/lease protection remains held during the request; no new touch/activity policy was added. Existing atomic replacement/platform/durability limits remain; no Windows/macOS or network-filesystem identity claim was tested.

## Files changed

- `openscrub_web.py`: private type/presence-preserving comparison and bounded touched-destination ledger; conditional call to the existing publisher.
- `tests/test_large_report_io.py`: 46 additional actual-route cases (59 total in this file) covering no-ops, normalization/ignored edits, aliases, type/presence/signed zero, last_seen, audio, unknown raw fields, replay/conflict and failure/waiter release. Existing lifecycle/transaction fixtures/owners remain authoritative.
- `benchmark/review_io.py`: reproducible pinned-export actual loopback HTTP save benchmark; uninstrumented route timing and separate counted workers, exact report-content checks, every sample/status/source identity and RSS observations.
- `benchmark/README.md`: invocation, isolation and measurement limits.
- `pyproject.toml`: add `benchmark` to sdist inclusion only. Dependencies/version/CLI and web defaults are unchanged.

## RED / GREEN and stabilized validation

Python3.12 commands sourced `/tmp/openscrub-baseline-20261116/env-opencv4.sh`; active engine/web/report imports were asserted in `imports.log`. Tests used synthetic temporary stores and existing real publication/file-owner boundaries. Local HTTP/media operations used authorized native execution. Python3.9 used its prepared runtime and task-local audited profile/harness with outward network and writes outside the task artifact root blocked.

| Command/check | Result and artifact |
| --- | --- |
| `python -m pytest tests/test_large_report_io.py -k unchanged_save -q -o cache_dir=/tmp/openscrub-task631/cache --basetemp=/tmp/openscrub-task631/red-tmp` before implementation | **14 failed, 41 deselected**; `red.log`. Compact originals changed bytes; canonical originals still changed inode/mtime/mode (0640→0600). This is the required expected regression RED. |
| `python -m pytest tests/test_large_report_io.py -q ...` after implementation | **55 passed**; `green.log`. Four further compatibility/fresh-response cases were subsequently added. |
| `python -m pytest tests/test_large_report_io.py tests/test_report_transactions.py tests/test_manual_addition_replay.py tests/test_review_save_failures.py tests/test_report_roundtrip.py -q ...` | **226 passed in17.02s**; `focused.log`. Includes real HTTP render/reopen and emitted-JS same-value/newer-edit/error paths. |
| `python -m pytest -q -o cache_dir=/tmp/openscrub-task631/cache --basetemp=/tmp/openscrub-task631/full-tmp` | **440 passed in99.31s**; `full.log`. Full combined suite ran once; no failures or warnings. |
| Python3.9 `python -m pytest tests/test_large_report_io.py tests/test_manual_addition_replay.py -q -o cache_dir=/tmp/openscrub-task631/cache39 --basetemp=/tmp/openscrub-task631/python39/tmp` | **96 passed in3.21s**; `python39-final.log`, active-source/interpreter/hook assertions in `python39-imports.log`. Includes actual HTTP and real render/fresh-process replay cases. |
| `TMPDIR=/tmp/openscrub-task631/build-tmp PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PIP_CACHE_DIR=/tmp/openscrub-task631/pip-cache python -m build --outdir /tmp/openscrub-task631/dist` | Exit0, isolated Hatchling1.33.0; sdist then wheel built from that sdist; `build.log`. No network or package-system changes. |
| `python /tmp/openscrub-task631/check_packaging.py` | Exact source/tests/benchmark content in sdist, exact runtime source in wheel, all packaged Python3.9 grammar, unchanged engine/defaults/web build_args, unchanged APP_JS syntax and supported source inclusion checks; `packaging.log`, `packaging.json`. |
| Built project wheel installed with prepared bootstrap pip, `--no-index --no-deps --target /tmp/openscrub-task631/installed/site-packages`, then `check_installed.py` | Exit0; actual installed module paths, CLI `--help`, Austin CLI/web defaults, actual Cheroot entrypoint/homepage/jobs, vault setup/lock/unlock and allowlist admission, graceful idle SIGTERM exit0; `install.log`, `installed-startup.log/json`, `installed-web.log`. |
| Actual Chromium schedule and fresh process HTTP reopen (below) | Passed; `browser-verified.log`, `browser-results.json`, `browser-publications.json`, `reopen.log`; no page errors. |
| `git diff --check`, self-review and frozen-source check before local commit | Clean. `verification-source.json` records32 source/test/metadata files; committed-byte check is retained separately. |

Product route/tests were stable before focused/full verification. The benchmark's response/content assertions were finalized during the full run; build/packaging and the real benchmark smoke exercise the final driver. No product/test changes followed that verification. The first Python3.9 attempt failed before test collection because the reused environment's TMPDIR was outside the new task audit root; only process-local TMPDIR was corrected, then all96 cases passed. This is tooling setup failure, not a product RED.

The route instrumentation counts **report** parse/dump/stage/fsync/replace and stream-write calls without replacing the route or coupling counters to request/response JSON. No-op tests assert one fresh report parse and zero publication operations plus exact file preservation. Changed cases assert one complete real publication and hand-checked effective changes/raw preservation. The failure/waiter schedule blocks a real replacement, starts a second request waiting on the actual lock, raises the write failure, then verifies the waiting empty save freshly parses the old snapshot and succeeds without publishing. Existing P06B overlap/gates/lifetimes and Task72 manual creation/conflict tests remain in the focused/full sets.

## Actual browser and render/reopen evidence

Browser plugin unavailable; the prepared Playwright1.65.1/Chromium and runtime libraries under `/tmp/openscrub-save-as-20261116` were reused. The flow was actual review → deliberate same-value Keep → held successful acknowledgement/newer choice → real failed changed publication → restored same-value Keep → ordinary save-and-render → fresh process reopen. There is no browser implementation change.

`serve_browser.py` imports asserted active source and serves the shipped page at `http://127.0.0.1:18463` with a synthetic30-frame96×64 video and a kept row. `browser.cjs` clicks the actual bulk Keep and save buttons; the first payload explicitly includes `enabled[0]=false` although the stored value is already false. The real server completes that no-op with exact bytes/inode/mtime/mode retained and zero save publications. Only delivery of its already received acknowledgement is held in the browser fetch wrapper. Clicking the actual row toggle creates newer `true`; releasing the old response retains it and requests no render.

For the failed-save path, a task-only flag makes the publisher raise from the actual changed save route. The server returns500, the existing UI retains the pending choice and error, original bytes stay intact and rendering does not start. This is controlled failure injection, not a real disk failure or transport disconnect. Restoring the deliberate stored Keep value then saving produces another real successful no-op acknowledgement and requests the actual renderer once. The unchanged render publisher completes; the current row and additive metadata survive. Output is a real2,334-byte MP4; a fresh interpreter decodes its kept-region mean176.33 and rehydrates the report/output. It starts a fresh Cheroot server, performs GET and same-value POST over HTTP, verifies the ordinary success response and exact report identity/mtime/bytes retention, and releases all file owners (`reopen.log`).

QA checks passed for page title/identity, meaningful rendered content, no framework overlay, target interactions and screenshots (`browser-newer.png`, `browser-failed.png`, `browser-rendered.png`). No page errors; the expected HTTP500 resource console error is retained in results. Desktop1280×950 only; no new mobile, alternate-browser, long-media or broad visual validation claim.

Harness corrections are preserved, not product findings: an invented toggle selector was corrected to shipped `bb0`; an export label copied from another branch was corrected to this base's `Download redacted video`. More importantly, my initial async `waitForFunction` predicate falsely appeared to prove an early done state. Prepared Playwright `coreBundle.js:26050` calls `const success = predicate(); if (success) fulfill(success)` without awaiting: an async predicate returns a truthy Promise even when its eventual phase comparison is false. The final harness explicitly awaits HTTP polling and separately observes the real publisher returning. No actual early `job.phase=done` was demonstrated. In the unchanged source, `_run_job` waits for synchronous `run_pipeline` before setting phase done; `run_render` calls synchronous `write_report`/publisher before returning. `WebCallbacks.progress` updates progress/ETA only. There is no supported lifecycle-defect claim here and no production change for the harness.


## Measurement protocol and source identity

The common benchmark driver at the committed head exported both pinned commits from Git into `measurement/export-before` and `measurement/export-after`. Every tracked blob was verified against its Git object before imports and rechecked after all measurements. Each fresh worker asserts actual imported engine/web/report paths and SHA256 against its export manifest. `results.json` retains complete source inventories, exact SHAs, Python executable/version/platform and all worker import paths. This is the reviewed P07b base, not an earlier instrumented research baseline. No timing is borrowed from earlier research.

The supervisor kept other agent-scheduled suites/browser/build/container/benchmark workloads absent. This did not reserve the host or control unrelated user/system activity. Our own suites, browser servers/Chromium, build, installed server and reopen process were finished/stopped before the boundary notice. Only this benchmark ran sustained work during its window; source/docs reads/writes continued. Shared-machine, scheduler, storage and filesystem-cache variation remain uncontrolled.

For each row count and operation, equal deterministic fresh fixtures contain motion and bands (three frames per row), dense tracks, manual rows/immutable creation metadata, person/polygon data, audio/transcript/suggestions and nested unknown fields. Both versions receive three warmups each, then five recorded samples each; calls alternate versions and which goes first. Sparse changes one enabled value and bulk changes every enabled value; both alternate choices every request and finish with the original choices restored. Every changed request's inode changes, while every after no-op retains its initial inode/mtime. Final SHA256 equals the expected complete canonical report, proving all unrelated content survives. No media or inference runs inside this benchmark; rendered-output compatibility is the separate small actual render/reopen evidence above.

Latency is actual loopback Cheroot HTTP through the registered save route, measured in the separate client from request construction/send through reading the response bytes; response decoding, payload generation, reset/fixture construction, complete expected-output hashing and statistics are outside the timer. An external client thread samples worker `/proc` RSS every5ms. Timing workers have no route wrappers. Fresh separate counted workers then instrument report work and request/response JSON. There are144 uninstrumented requests (54 warmups,90 recorded),18 separate instrumented requests, all162 HTTP200; all assertions and post-run export verification pass. The tiny10-row harness smoke is preserved separately and is not included in the main performance claim.

Reproduce in the prepared3.12 runtime (fresh evidence directory required):

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python benchmark/review_io.py --scenario saves --rows 1000 10000 100000 \
  --repository /home/tahv0/.codex/worktrees/c832/OpenScrub \
  --before-ref 12919c96c6f7558136b50d7b4d85e5e6b62f1971 \
  --after-ref 3457efac574d74a7d2377cbc0d44bb0b87462c3a \
  --evidence-dir /tmp/openscrub-task631/measurement \
  --output /tmp/openscrub-task631/measurement/results.json
```

`measurement.log` and `measurement/results.json` preserve the actual run. The Python3.12 tarfile deprecation warning about Python3.14's future extraction-filter default appears during pinned local Git export, outside timing; no product/test warnings were observed. No repeated successful full suite, measurement set or build ran. The10-row smoke validated the harness before the required main sizes.


### Latency distributions and every recorded sample

All times are milliseconds. With five observations, nearest-rank p95 equals max; no population-confidence claim is made. Raw warmups, sample ordering/statuses and RSS sample arrays remain in results.

| Rows | Operation | Before min / median / p95=max | After min / median / p95=max | Median change |
| ---: | --- | --- | --- | ---: |
| 1000 | noop | 45.809 / 46.237 / 47.449 | 4.999 / 5.271 / 5.398 | -88.60% |
| 1000 | sparse | 46.592 / 47.034 / 53.299 | 46.274 / 46.666 / 49.050 | -0.78% |
| 1000 | bulk | 46.907 / 48.453 / 53.053 | 47.138 / 49.428 / 56.807 | +2.01% |
| 10000 | noop | 462.995 / 481.035 / 484.086 | 56.081 / 61.754 / 63.669 | -87.16% |
| 10000 | sparse | 461.985 / 471.786 / 479.552 | 467.579 / 475.195 / 485.404 | +0.72% |
| 10000 | bulk | 474.251 / 522.890 / 539.266 | 473.197 / 499.635 / 545.689 | -4.45% |
| 100000 | noop | 5112.259 / 5413.879 / 5538.703 | 945.298 / 1189.387 / 1353.709 | -78.03% |
| 100000 | sparse | 5140.688 / 5301.626 / 5344.111 | 5207.212 / 5370.674 / 5445.442 | +1.30% |
| 100000 | bulk | 5150.938 / 5312.664 / 5380.074 | 5363.848 / 5545.423 / 5616.509 | +4.38% |

| Rows | Operation | Before recorded samples (request order) | After recorded samples (request order) |
| ---: | --- | --- | --- |
| 1000 | noop | 47.448767, 45.809499, 46.208609, 46.496885, 46.236677 | 5.325065, 5.271436, 5.069469, 5.397995, 4.998939 |
| 1000 | sparse | 49.213408, 53.299076, 46.957171, 46.591534, 47.033580 | 49.050069, 46.666104, 48.986511, 46.274459, 46.390506 |
| 1000 | bulk | 53.053072, 48.262716, 48.453126, 46.907062, 48.558256 | 49.427776, 56.807101, 51.810722, 47.138459, 49.016970 |
| 10000 | noop | 484.085592, 481.034932, 472.735598, 462.994996, 483.261250 | 63.668991, 57.209277, 62.199245, 56.081478, 61.754081 |
| 10000 | sparse | 471.923746, 462.709290, 479.552267, 461.984907, 471.785828 | 478.764356, 470.812298, 485.404489, 467.579480, 475.195202 |
| 10000 | bulk | 480.470631, 474.250832, 522.889736, 524.003700, 539.266229 | 473.197050, 508.287176, 493.147170, 499.635239, 545.688793 |
| 100000 | noop | 5538.702708, 5413.878849, 5112.259265, 5442.723902, 5350.478497 | 1248.511684, 1189.387168, 947.023313, 1353.709349, 945.297585 |
| 100000 | sparse | 5140.687978, 5339.908659, 5301.201291, 5301.625838, 5344.110557 | 5445.441672, 5409.344201, 5247.065150, 5370.674423, 5207.212405 |
| 100000 | bulk | 5197.948576, 5378.814194, 5150.938259, 5312.664492, 5380.073514 | 5545.422606, 5587.225759, 5616.509018, 5363.847917, 5468.264070 |

The no-op median reductions are88.60% (1k),87.16% (10k) and78.03% (100k). Sparse medians vary from−0.78% to+1.30%; bulk from−4.45% to+4.38%. The100k bulk control is slower by232.76ms median (4.38%), consistent with the additional bounded ledger work; this small sample does not isolate causality. This PR claims demonstrated no-op savings only, not changed-save acceleration or general latency guarantees.


### Separate report work and sizes

Each row below has exactly one report parse, one request-JSON parse and one response-JSON serialization. `publish` means each of report dump, staging creation, explicit fsync and replacement has that count. Stream writes are Python calls, **not OS syscalls**. Instrumented timings are retained for audit but are excluded from the latency table.

| Rows | Operation | Version | Publish | Python stream writes | Serialized characters |
| ---: | --- | --- | ---: | ---: | ---: |
| 1000 | noop | before | 1 | 124777 | 693110 |
| 1000 | noop | after | 0 | 0 | 0 |
| 1000 | sparse | before | 1 | 124777 | 693109 |
| 1000 | sparse | after | 1 | 124777 | 693109 |
| 1000 | bulk | before | 1 | 124777 | 693926 |
| 1000 | bulk | after | 1 | 124777 | 693926 |
| 10000 | noop | before | 1 | 1246177 | 6955571 |
| 10000 | noop | after | 0 | 0 | 0 |
| 10000 | sparse | before | 1 | 1246177 | 6955570 |
| 10000 | sparse | after | 1 | 1246177 | 6955570 |
| 10000 | bulk | before | 1 | 1246177 | 6963749 |
| 10000 | bulk | after | 1 | 1246177 | 6963749 |
| 100000 | noop | before | 1 | 12460177 | 69956372 |
| 100000 | noop | after | 0 | 0 | 0 |
| 100000 | sparse | before | 1 | 12460177 | 69956371 |
| 100000 | sparse | after | 1 | 12460177 | 69956371 |
| 100000 | bulk | before | 1 | 12460177 | 70038188 |
| 100000 | bulk | after | 1 | 12460177 | 70038188 |

| Rows | Canonical report bytes (initial/final) | No-op payload bytes | Sparse payload bytes | Bulk payload bytes |
| ---: | ---: | ---: | --- | --- |
| 1000 | 693110 | 2 | 22–23 | 10995–11811 |
| 10000 | 6955571 | 2 | 22–23 | 119814–127992 |
| 100000 | 69956372 | 2 | 22–23 | 1297995–1379811 |

### RSS, high-water and observer boundaries

MiB below are KiB/1024; exact KiB and every external5ms observation are retained in results. Import RSS is measured after actual module imports. Fixture high-water includes fixture generation/serialization; ready RSS is after fixture release/GC and server readiness. Timed `before` is the median first RSS observation of recorded requests; `during max` is the largest sampled RSS, and HWM is the largest observed kernel VmHWM counter across in-flight and post-request snapshots. HWM may already be dominated by fixture construction or prior scenarios; it is not per-request temporary allocation. Some post-GC VmHWM reads are lower than in-flight RSS/counter observations on this host, so the table retains the maximum observed counter rather than only the final read. Sampling may miss shorter peaks.

| Rows | Version | Import RSS | Fixture HWM | Initial ready RSS |
| ---: | --- | ---: | ---: | ---: |
| 1000 | before | 89.9 | 91.8 | 91.6 |
| 1000 | after | 90.1 | 92.0 | 91.9 |
| 10000 | before | 90.1 | 111.2 | 92.6 |
| 10000 | after | 90.1 | 111.0 | 92.5 |
| 100000 | before | 90.0 | 305.3 | 92.4 |
| 100000 | after | 89.7 | 305.1 | 92.2 |

| Rows | Operation | Version | Before RSS median | During RSS max | Cumulative HWM |
| ---: | --- | --- | ---: | ---: | ---: |
| 1000 | noop | before | 96.3 | 96.3 | 96.3 |
| 1000 | noop | after | 96.6 | 96.6 | 96.6 |
| 1000 | sparse | before | 96.3 | 96.3 | 96.3 |
| 1000 | sparse | after | 96.7 | 96.7 | 96.7 |
| 1000 | bulk | before | 96.4 | 96.4 | 96.4 |
| 1000 | bulk | after | 96.9 | 96.9 | 96.9 |
| 10000 | noop | before | 125.8 | 145.6 | 145.6 |
| 10000 | noop | after | 124.9 | 145.6 | 145.6 |
| 10000 | sparse | before | 132.8 | 145.7 | 145.7 |
| 10000 | sparse | after | 131.8 | 145.6 | 145.6 |
| 10000 | bulk | before | 115.8 | 133.5 | 146.3 |
| 10000 | bulk | after | 118.4 | 135.0 | 147.6 |
| 100000 | noop | before | 122.1 | 441.2 | 441.2 |
| 100000 | noop | after | 115.7 | 440.6 | 440.6 |
| 100000 | sparse | before | 132.1 | 441.3 | 441.3 |
| 100000 | sparse | after | 124.4 | 441.4 | 441.4 |
| 100000 | bulk | before | 137.5 | 454.5 | 457.6 |
| 100000 | bulk | after | 150.2 | 458.1 | 458.1 |

Client RSS/high-water is separate from worker RSS. The client owns preencoded payloads, response buffers, result samples and expected-fixture hashing outside timed requests; no extra full-report copy was added inside the timed route. The server retains parsed raw data, and bulk assignment tracking additionally retains O(touched destinations) references/tuples.

| Rows | Client RSS range in recorded requests | Client cumulative HWM max |
| ---: | ---: | ---: |
| 1000 | 57.9–60.1 | 60.1 |
| 10000 | 60.9–66.0 | 80.5 |
| 100000 | 68.2–77.8 | 284.1 |

At100k bulk, sampled worker peak is454.5MiB before and458.1MiB after (delta+3.7MiB). This is a measured cost/control, not a claim that the ledger has zero memory cost. Import/fixture baselines, allocator retention, previous scenarios and sampled rather than continuous peaks limit attribution.


## Self-review, limits and handoff

Self-review confirmed no full-document copy/encoding/digest on the no-op route; unchanged encoder and ordering; full validation before the publication decision; correct missing/type/signed-zero and alias handling; exact replay/conflict semantics; and unchanged browser/defaults. The existing web module is large; this change stays within the existing save route plus one small private comparator, without restructuring it. Benchmark driver complexity is isolated from runtime and packaged as source, not imported by the app.

Known costs/limits: bulk touched-field storage and measured control overhead; no no-op directory-mtime retention refresh; nonfinite touched values may conservatively publish; mandatory report parsing and existing full-row traversals remain. Report/file preservation was exercised on Linux/WSL only. Timing uses one shared host, local warm-cache Cheroot HTTP, five recorded samples per pair, no concurrency/load/inference/media and no controlled unrelated host activity. RSS is sampled and cumulative high-water includes fixture/import costs. The benchmark makes no production capacity, alternate platform, compact-serialization or general sparse/bulk speed claim.

All requested implementation, validation and measurement gates completed. No correctness concerns were found in self-review; the measured bulk/memory and retention limitations are explicit review considerations. The supervisor owns independent review and any future publication. Exact final verification is in `committed-bytes.log`; all source/export inventories, raw samples, counter runs and evidence paths are retained under `/tmp/openscrub-task631`.


## Evidence preservation addendum (no rerun)

The exact Python body of the executed fresh-interpreter inline heredoc is now preserved as `/tmp/openscrub-task631/check_reopen.py`; original results remain in `/tmp/openscrub-task631/reopen.log`. The named script was created after execution and has not itself been rerun. `/tmp/openscrub-task631/evidence-commands.md` records original environment/invocation, an equivalent reusable command using a fresh log path, body hashes and limits. This copied body verifies HTTP reopen, the already-rendered output's first kept-region pixel, same-value response/file preservation and released owners; the prior real render belongs to the browser schedule.

The exact last-executed `/tmp/openscrub-task631/finalize_report.py` is additionally frozen as `/tmp/openscrub-task631/executed-finalize_report.py`. The original command `python3 /tmp/openscrub-task631/finalize_report.py` and its raw assertion block that produced `committed-bytes.log` are preserved there and referenced in `evidence-commands.md`. That script also generates handoff documents, so it should be read rather than rerun solely to inspect evidence. This addendum only preserves existing tool-history bodies/files: no product/test/benchmark/check reruns and no changes to frozen native HEAD.
