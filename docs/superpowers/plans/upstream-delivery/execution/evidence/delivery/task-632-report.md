# Task 632 — readable report serialization

Implementer disposition: **adopt the simple public-iterator/writelines candidate**, with the measured no-op-control regression retained as a review concern. Exact base **`3457efac574d74a7d2377cbc0d44bb0b87462c3a`**; clean committed head **`4a62e49d2f0896b737081cc92e1f92e9bcaee93f`**, local branch `pr/readable-report-serialization`, native `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Independent supervisor review remains pending. No remote publication or messages, integration/docs branch pull, original-checkout product/runtime edits, subagents, new dependencies/models/toolchain, browser rerun or container work occurred. This report and task-632-pr.md are the requested handoff files in the supervisor SDD workspace. All raw evidence/scripts/logs and actual expected reports are under `/tmp/openscrub-task632`.

## Why, what and when

Reviewed Task 631 established that changed publication remained material: its 100k readable report is 69,956,372 bytes; changed-save medians 5,370.674 ms sparse and 5,545.423 ms bulk, versus 1,189.387 ms for its already-skipped no-op path. That difference includes route work as well as publication, and the 12,460,177 separate Python stream-write observations are not syscalls or a speedup prediction. `report-noop-scope-research.md` and `task-631-report.md` were read before experimentation. No historical instrumented timings or no-op savings are reattributed to this change.

The only runtime change is in the existing private owner `openscrub_internal.reports.atomic_report`: replace `json.dump(report, stream, indent=1)` with `stream.writelines(json.JSONEncoder(indent=1).iterencode(report))`. Both use the public stdlib encoder with the same defaults. There is no encoder-private API, compact encoding, full dumps/join, cache/state, caller-specific path, buffer framework or changed persistence requirement. The shared owner still creates same-directory exclusive 0600 staging, explicitly flushes/fsyncs, closes before replace, cleans temporary files and propagates failures. Engine/web callers, raw-report shape and insertion/list order, separators, ensure_ascii escapes, key handling, allow_nan/circular policy, no trailing newline, transaction/lifetime/replay/ACK behavior and Austin defaults are preserved.

The optimization removes the Python `json.dump` loop's per-token dispatch to the temporary wrapper. The public encoder still produces the same pieces, and TextIOWrapper still performs text encoding/buffering and internal writes. Fewer observable Python calls establish no syscall-count reduction. In particular, this change does not remove the large token produced when encoding a single large string.

## Bounded attribution and candidate selection

The first coordinated exclusive slot ran only `/tmp/openscrub-task632/attribution.py`, exact native base `3457efa`, prepared Python 3.12.16. The retained script contains all three experimental bodies: unchanged dump, direct public iterator→writelines, and 65536-character target aggregation using a list/join. Each uses the same atomic stage/flush/fsync/close/replace pattern over the deterministic 10k fixture, with 3 warmups/5 recorded publications per candidate, rotated order. GC, complete-output hashes, stats and memory-after snapshots are outside the publication timer. This is bounded publication attribution, not HTTP timing. All 24 outputs were byte-identical 6,955,571 bytes, SHA256 `1942d80822b70f4527d81c879515421ae04a6f393b37a67626ed58238520148c`.

| Candidate | Recorded median ms | Disposition |
| --- | --- | --- |
| dump | 430.925988 | unchanged baseline |
| writelines | 327.686559 | selected for HTTP trial |
| aggregate 65536 | 326.239102 | not adopted: essentially equal median with more retention/code |

| Index | Kind | dump ms | writelines ms | aggregate 65536 ms |
| --- | --- | --- | --- | --- |
| 0 | warmup | 426.458273 | 323.116502 | 321.439707 |
| 1 | warmup | 424.225554 | 320.012743 | 317.514070 |
| 2 | warmup | 443.628702 | 317.903259 | 318.166854 |
| 3 | recorded | 416.295181 | 319.857343 | 317.245253 |
| 4 | recorded | 425.417184 | 320.331583 | 329.042521 |
| 5 | recorded | 430.925988 | 327.686559 | 320.507340 |
| 6 | recorded | 457.856058 | 330.703426 | 352.575384 |
| 7 | recorded | 435.323365 | 366.288937 | 326.239102 |

Direct writelines improved this median by 23.96%; aggregation by 24.29%. Their near-equal result favors the smaller direct candidate. The experimental aggregation list retains references to token strings plus joined output; its 65536 target is not a hard cap when one token exceeds it. No failed/unused variant was added to runtime. A full dumps/join candidate was unnecessary once a simple streamed candidate justified the actual-route trial; no unmeasured full-materialization benefit or memory result is claimed.

Attribution memory is a cumulative in-process observation, **not** isolated per-candidate allocation: initial RSS 43,016 KiB/HWM 44,920 KiB, largest observed after-publication RSS 43,432 KiB/HWM 45,288 KiB, with fixture and previous candidates retained. Every individual memory snapshot, sample ordering, interpreter/source path and baseline helper SHA is retained in `attribution-10000-results.json`; final candidate memory is assessed separately below.

## Tests, verification and exact source provenance

`tests/test_report_serialization.py` adds 16 real-publication compatibility/failure cases: literal golden readable bytes for nested additive fields, scalar distinctions including signed zero, Unicode/BMP/non-BMP/quote/backslash/control escapes, numeric/null/bool keys, explicit NaN/±Infinity default spellings; a large individually escaped string compared to public stdlib expected bytes; unsupported values/keys and circular references; injected streaming encoding, explicit flush, fsync and replace failures with both absent/existing destinations. Real partial staging bytes precede the encoding failure. Exact exception objects propagate, old files remain, and staging is cleaned. The unchanged private/complete-first-publication tests cover 0600 permissions; existing reader/writer and actual-route suites cover atomic visibility and transaction/admission/lifetime behavior. The new bytes/error tests intentionally also pass baseline; they protect the unchanged contract.

A preliminary implementation-prescribing dispatch test was run RED against `json.dump` (16 compatibility cases passed), then removed after review because it required one particular method. It is preserved in `add_tests.py` and `red.log`, not shipped. The owning performance RED is the bounded baseline attribution; the adopted change has no intended behavior delta to force into a failing compatibility test.

Two existing test-only instruments were adapted to the explicit public encoder: `test_large_report_io.py` retains its legacy internal `dump` counter as encoding-start count and now truthfully calls pieces `encoder_chunks`; the transaction serialization injection isolates `reports.json` so it cannot intercept client JSON. Route sparse/bulk/replay/no-op and P06 transaction/lifetime assertions were not removed or weakened.

Only the narrow reviewed Task 651 driver corrections were carried from `ac6496810b03d8b062ab9da150aeea1e62285fed`: explicit supported tar `filter='data'` with capability fallback, historical baseline default 1 and explicit already-optimized expectation 0, plus reusable `count_operations`. No application/assembled source from Task 651 was used. Task 632 additionally adapts **separate counted workers** to observe both encoding entrypoints. `report_encode` counts actual publication encoding starts; `json_dump_calls` and `encoder_instances` retain method identity; `stream_writes`/`stream_writelines` count Python calls at the actual staging wrapper; `encoder_chunks` observes the explicit encoder iterator. Those counts do not instrument timed workers or measure syscalls. The historical default remains 1 for before `12919c9`, while this run explicitly uses 0 for before `3457efa`. Tiny six-row smoke asserts the preserved helper default and both exact pinned versions' actual HTTP counts before the timed comparison.

| Check | Actual result | Evidence |
| --- | --- | --- |
| Focused active-source reports/transactions/replay/reopen/response lifetime | 168 passed in 12.60 s | focused-final.log; `task632_isolation.py` asserts native imports |
| Full discovered stable source | 456 passed in 101.32 s; zero skips/warnings | full.log, complete python -m pytest -q |
| Actual Python 3.9.25 affected cases | 159 passed in 9.21 s; zero skips/warnings | floor.log, floor-version.log, task-local audit/sitecustomize; public encoding, engine/route/replay/fresh-process tests |
| Offline sdist→wheel | exit 0, Hatchling 1.33.0; wheel built from sdist | build.log; existing offline wheelhouse |
| Exact archive contents/defaults/grammar | exit 0; exact source/test/benchmark inclusion, Python 3.9 grammar, metadata/defaults/JS | check_packaging.py, packaging.log/json |
| Installed CLI/web entrypoints | exit 0; installed CLI help, real Cheroot homepage/jobs, vault lock/unlock/allowlist, idle SIGTERM 0 | installed-startup-runtime.log; installed-startup.json; actual installed paths asserted |
| Tiny separate count harness | 6 actual HTTP 200; exact imports/bytes and zero-noop/one-changed encoding/stage/fsync/replace | count_smoke.py / count-smoke.log; count-smoke/results.json |
| Pinned main benchmark | 96 uninstrumented+12 counted HTTP 200; complete final bytes, expected reports, exact exports | measurement.log; measurement/results.json; committed-evidence.json |
| Source/commit self-review | 127 frozen blobs equal commit, clean head, diff --check passes | verification-source.json; committed-evidence.log/json |

Actual commands, working directories, environment, exact scripts and retained failed attempts are in `/tmp/openscrub-task632/evidence-commands.md`. The prepared 3.12 executable is `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python`; actual 3.9 is `/tmp/openscrub-python39-20261117/venv/bin/python` (3.9.25, Clang 21.1.4). Runtime-source imports were asserted before final tests. Existing verified YuNet was reused only through the owning full-suite harness; no model was downloaded. The 3.9 result covers affected active-source behavior and packaged grammar/floor metadata, not whole-app floor certification.

Full tests and packaging ran on stable source/test bytes before the local commit; the 127-blob frozen manifest and later exact committed checks bind them to `4a62e49`. No source/test change followed those final tests. `packaging.json`'s captured precommit HEAD was `3457efa` and is not relabelled; archived and installed runtime bytes match the tested final commit. The real engine `write_report` success/failure and actual render/fresh interpreter report-reopen tests ran in the owning focused/full/3.9 sets. No additional broad browser matrix was justified: engine/web/JS/response sources are byte-identical between pinned versions and publication bytes remain exact.

Retained failures are not concealed or counted as passes:

- Initial `red.log`: 1 exploratory dispatch failure/16 passes plus 2 read-only pytest cache warnings; cache redirected, dispatch test removed as above.
- Initial `focused.log`: 132 failed/27 passed/10 errors from original-cwd module shadowing and sandbox-denied loopback sockets. Native `sys.path` insertion/import assertions, native cwd and already-authorized escalation corrected the harness. This run provides no candidate correctness claim.
- Corrected `focused-active.log`: 1 failed/168 passed; global JSONEncoder monkeypatch intercepted client request JSON before the intended lock schedule. Isolating the report module's JSON namespace corrected only the test injection; final 168 passed.
- `install.log`: prepared runtime had no pip. `installed-startup.log` therefore could not assert a missing installed module. Existing bootstrap pip then installed the wheel but generated dependency-less Python 3.14 entrypoint shebangs (`install-bootstrap.log`, `installed-startup-final.log`). Running that existing pip code through the prepared 3.12 interpreter installed identical wheel bytes with correct shebangs; `install-runtime.log` and final smoke passed. No new toolchain/dependencies/network.

## Final HTTP protocol, source identities and actual expected reports

The second coordinated exclusive slot compared only exact `3457efa`→`4a62e49` exports. The supervisor confirmed no competing agent suite/browser/build/container/benchmark; only small source/docs IO occurred elsewhere. Own suite/build/install/server processes were stopped before the notice. The host was not reserved: user/system activity, CPU scheduling, storage and cache variation remain uncontrolled. Both timed slots were announced to the supervisor before/after; no own validation overlapped timing and no selective rerun was made to improve the noisy no-op control.

The committed driver ran 10k/100k deterministic fixtures, each with dense/person/polygon tracks, manual creation metadata, three motion/band frames per row, audio/transcript/suggestions and nested unknown fields. Each operation/version receives 3 warmups then 5 recorded requests, alternating versions and which goes first. Sparse/bulk choices alternate every request; 8 total phases restore original choices. Timing is actual loopback Cheroot HTTP in the separate client from request construction/send through reading response bytes. Payload generation, reset/fixture construction, expected-output hashing, response decoding/statistics are outside the timer. Server module imports and fixture construction are outside request timing. No inference/media/download occurs. External 5 ms RSS sampling has no route-function wrappers. Fresh counted workers run only after timing and their recorded elapsed values are excluded from latency tables.

Reproduce from native cwd with a **fresh evidence/output directory**:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python benchmark/review_io.py --scenario saves --rows 10000 100000 \
  --repository /home/tahv0/.codex/worktrees/c832/OpenScrub \
  --before-ref 3457efac574d74a7d2377cbc0d44bb0b87462c3a \
  --after-ref 4a62e49d2f0896b737081cc92e1f92e9bcaee93f \
  --before-noop-publications 0 \
  --evidence-dir /tmp/openscrub-task632/measurement \
  --output /tmp/openscrub-task632/measurement/results.json
```

This exact command completed exit 0. `measurement/results.json` retains Python 3.12.16/Clang 23.1.3, platform, all source SHA256 inventories, actual engine/web/report import paths and worker/client memory. All 126 before and 127 after Git blobs were verified against pinned objects before import and after measurement. Engine/web source hashes are identical across versions; only the shared report helper's runtime bytes differ. Actual imports resolve under `/tmp/openscrub-task632/measurement/export-before` and `export-after`, never the original checkout. Helper SHA256 values:

| Version | Exact revision | reports.py SHA256 |
| --- | --- | --- |
| before | 3457efac574d74a7d2377cbc0d44bb0b87462c3a | e8a7429c0b5430ee290f6635ca5d5a93445d3f0fe9bb0f58e57fec891ee01b7f |
| after | 4a62e49d2f0896b737081cc92e1f92e9bcaee93f | eec9d568fc18f08ee35469ba864c5526120ae11152e8fe6f4d15007ab42d2427 |

All 108 main requests returned 200/ok and released owners to 0; 96 are uninstrumented (36 warmups/60 recorded),12 separate counted. Every timed response has expected total/suggestions. Each scenario's complete final report SHA equals its deterministic expected full canonical report. Post-run `check_evidence.py` additionally writes the actual expected reports below, compares retained final timed files and counted final bulk-phase 1 files byte-by-byte, checks every changed request replaced its inode and every no-op sample/final snapshot retained exact bytes/metadata. The benchmark records per-scenario final hashes before subsequent fixture resets; the retained physical worker file is the final bulk phase 8 output. All scenarios'8 phases finish at the same original document, rather than requiring differently named expected documents.

| Rows | Actual expected final path | Complete bytes | SHA256 |
| --- | --- | --- | --- |
| 10000 | /tmp/openscrub-task632/expected-final-10000.json | 6955571 | 1942d80822b70f4527d81c879515421ae04a6f393b37a67626ed58238520148c |
| 100000 | /tmp/openscrub-task632/expected-final-100000.json | 69956372 | 74f6909e2997cc763ecdbd8601986a5ae784217a4a7270e2863b3ffb7b814681 |

The separately retained `expected-counted-bulk-10000.json` and `expected-counted-bulk-100000.json` encode actual phase 1 inverted enabled choices and match both remaining counted worker files byte-for-byte. Intermediate counted scenarios retain work/status/size observations; complete per-scenario final hashes belong to the uninstrumented run. Expected-fixture/client work is outside the measured requests and is not claimed as server serialization cost.

### All uninstrumented timing samples

Milliseconds below. Five observations per cell; nearest-rank p 95 equals max and no confidence/population claim is made.

| Rows | Operation | Before min / median / p 95=max | After min / median / p 95=max | Median change |
| --- | --- | --- | --- | --- |
| 10000 | noop | 56.171 / 62.375 / 68.522 | 55.685 / 61.635 / 65.725 | -1.19% |
| 10000 | sparse | 467.004 / 497.377 / 502.642 | 371.671 / 382.362 / 422.108 | -23.12% |
| 10000 | bulk | 473.833 / 488.563 / 500.906 | 375.790 / 380.536 / 397.854 | -22.11% |
| 100000 | noop | 984.822 / 1029.429 / 2524.512 | 952.419 / 1132.037 / 1563.412 | +9.97% |
| 100000 | sparse | 5081.832 / 5315.352 / 5755.315 | 4198.249 / 4298.434 / 4449.405 | -19.13% |
| 100000 | bulk | 5420.894 / 5583.610 / 5729.425 | 4422.953 / 4557.726 / 4915.533 | -18.37% |

**Every warmup sample, per-version request order:**

| Rows | Operation | Before ms | After ms |
| --- | --- | --- | --- |
| 10000 | noop | 69.661280, 69.518146, 66.812553 | 68.774397, 73.932996, 70.903994 |
| 10000 | sparse | 506.202877, 539.200607, 514.963236 | 397.753519, 404.245969, 392.037692 |
| 10000 | bulk | 481.613965, 475.421637, 480.959068 | 379.863126, 379.633921, 385.869449 |
| 100000 | noop | 1893.512181, 980.587114, 1199.130405 | 2258.342367, 1203.933577, 2065.924537 |
| 100000 | sparse | 5417.993419, 5124.491969, 5511.022841 | 4208.430189, 4165.721438, 4652.622144 |
| 100000 | bulk | 6702.160236, 5459.363897, 5411.405454 | 4613.348157, 4665.522882, 4489.460012 |

**Every recorded sample, per-version request order:**

| Rows | Operation | Before ms | After ms |
| --- | --- | --- | --- |
| 10000 | noop | 64.144049, 59.883884, 68.522056, 56.171088, 62.375258 | 65.724953, 57.582717, 64.025873, 55.684576, 61.634880 |
| 10000 | sparse | 497.377255, 501.581701, 481.325484, 467.004468, 502.642039 | 422.108361, 384.060775, 382.362248, 371.670858, 379.622794 |
| 10000 | bulk | 488.562992, 499.595592, 500.906249, 473.832893, 477.144714 | 380.536416, 397.854084, 387.797382, 375.790486, 377.726699 |
| 100000 | noop | 1029.428774, 2524.512121, 984.822446, 1154.659116, 996.173228 | 1132.036556, 1177.185158, 953.676446, 1563.411724, 952.419215 |
| 100000 | sparse | 5081.831944, 5345.190969, 5315.352101, 5755.314659, 5260.083680 | 4198.249375, 4449.404882, 4223.950793, 4357.213494, 4298.434099 |
| 100000 | bulk | 5660.115831, 5420.893916, 5457.729573, 5583.610168, 5729.424896 | 4557.725623, 4422.952579, 4606.457440, 4466.670476, 4915.533186 |

All four changed-save median comparisons improve 18.37–23.12%; every recorded candidate changed-save sample is faster than every baseline sample in its matching cell. At 100k this saves 1,016.918 ms sparse and 1,025.885 ms bulk median in this local run. That reproducible effect across sparse/bulk and both sizes, together with the acceptable measured memory observations below, justifies adopting the simpler candidate.

The **100k no-op median regresses 9.97%** (1,029.429→1,132.037 ms); its spreads and warmups are retained above, including before max 2,524.512 ms and after max 1,563.412 ms. The 10k no-op median is−1.19%. No-op route sources are unchanged and separate counts still show zero publication, which defines the optimization's scope but **does not establish the cause** of the observed control difference. The control was not selectively rerun. This PR claims changed-publication benefit in these fixtures, not no-op improvement, overall capacity or latency guarantees.

### Separate actual publication work

Every row below has report parse 1, request JSON parse 1, response JSON serialization 1, owners 0. `Encode/publish` is the count of each report_encode/staging/fsync/replace. `write`/`writelines` are Python calls at the staging wrapper, never syscalls; `pieces` comes from the explicit public iterator in the candidate (baseline JSON dump owns its iterator internally). Serialized characters equal bytes here because default ensure_ascii output is ASCII. Fresh counted workers' elapsed values and every count/RSS snapshot are retained under each run's `instrumented` key and are excluded from uninstrumented timing.

| Rows | Operation | Version | Encode/publish each | dump calls | encoder instances | Python write | Python writelines | Observed pieces | Characters |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10000 | noop | before | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 10000 | noop | after | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 10000 | sparse | before | 1 | 1 | 0 | 1246177 | 0 | 0 | 6955570 |
| 10000 | sparse | after | 1 | 0 | 1 | 0 | 1 | 1246177 | 6955570 |
| 10000 | bulk | before | 1 | 1 | 0 | 1246177 | 0 | 0 | 6963749 |
| 10000 | bulk | after | 1 | 0 | 1 | 0 | 1 | 1246177 | 6963749 |
| 100000 | noop | before | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 100000 | noop | after | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 100000 | sparse | before | 1 | 1 | 0 | 12460177 | 0 | 0 | 69956371 |
| 100000 | sparse | after | 1 | 0 | 1 | 0 | 1 | 12460177 | 69956371 |
| 100000 | bulk | before | 1 | 1 | 0 | 12460177 | 0 | 0 | 70038188 |
| 100000 | bulk | after | 1 | 0 | 1 | 0 | 1 | 12460177 | 70038188 |

At 100k changed publication still encodes 12,460,177 pieces; Python staging `write` dispatches become 0 and one `writelines` invocation consumes the real iterable. Encoding/staging/fsync/replace remain exactly 1. Internal TextIOWrapper writes and OS syscalls were not counted. No-op retains its Task 631 skip with one fresh report parse and no encoding/publication.

### RSS/high-water observations and retention limits

RSS tables are MiB (KiB/1024); exact KiB and every sampled 5 ms array remain in `measurement/results.json`, separate from timing claims. Import RSS follows actual module imports. Fixture HWM includes fixture construction/serialization; ready RSS is after fixture release/GC/server startup. Request-start RSS is the median first sample of the five recorded requests; during max is the largest recorded sampled RSS. HWM is the largest observed cumulative counter across samples and after snapshots, not per-request temporary allocation. Some post-GC kernel HWM readings are lower than in-flight RSS/counter observations on this host; the table retains the maximum observed value, not only the last reading. Sampling may miss shorter peaks and allocator retention/prior scenarios confound attribution.

| Rows | Version | Import RSS MiB | Fixture HWM MiB | Initial ready RSS MiB |
| --- | --- | --- | --- | --- |
| 10000 | before | 90.285 | 111.266 | 92.633 |
| 10000 | after | 90.555 | 111.578 | 92.887 |
| 100000 | before | 90.289 | 305.766 | 92.719 |
| 100000 | after | 90.352 | 305.750 | 91.723 |

| Rows | Operation | Version | Request-start RSS median | During RSS max | Cumulative HWM max |
| --- | --- | --- | --- | --- | --- |
| 10000 | noop | before | 125.004 | 145.789 | 145.789 |
| 10000 | noop | after | 125.277 | 146.066 | 146.066 |
| 10000 | sparse | before | 131.926 | 145.824 | 145.824 |
| 10000 | sparse | after | 132.199 | 146.098 | 146.098 |
| 10000 | bulk | before | 116.574 | 135.184 | 147.867 |
| 10000 | bulk | after | 117.844 | 135.457 | 148.215 |
| 100000 | noop | before | 120.129 | 441.215 | 441.215 |
| 100000 | noop | after | 114.891 | 441.320 | 441.320 |
| 100000 | sparse | before | 130.840 | 441.938 | 441.938 |
| 100000 | sparse | after | 122.582 | 442.043 | 442.043 |
| 100000 | bulk | before | 150.824 | 458.719 | 458.719 |
| 100000 | bulk | after | 142.168 | 455.152 | 455.152 |

| Rows | Separate client RSS range MiB | Client cumulative HWM max MiB |
| --- | --- | --- |
| 10000 | 57.836–64.965 | 79.133 |
| 100000 | 67.031–75.039 | 279.594 |

At 100k sampled sparse peak 441.938→442.043 MiB is+108 KiB; bulk 458.719→455.152 MiB is−3,652 KiB. These are measured paired observations, not proof of zero allocation cost or an allocation bound. Worker retained raw parsed report and existing bulk touched-field storage dominate; client fixture/hash/payload/response/result arrays and imports are separate costs, outside request timing where specified. No full document encoding/join is introduced in the runtime.

A separate fresh-process probe (`large_token_memory.py`) imports only each pinned real report helper, then retains a 4,000,000-character Unicode/control string inside nested additive metadata. External 1 ms RSS observations cover publication only; token counting occurs afterward and is excluded from those observations. Actual encoded largest token is **12,000,002 characters**, 22 pieces total, complete report 12,000,076 bytes; baseline and candidate files compare byte-for-byte, SHA256 `7fb91a6a5695fa37ea0e11b866f85b03694f40a3208817cfe4f1286be098fb20`. This demonstrates why streamed pieces do not provide a hard memory ceiling for individually large tokens. No latency measurement is claimed for this probe.

| Version | Import RSS MiB | Document-ready RSS MiB | Sampled publication max MiB | Observed cumulative HWM MiB | After-publication RSS MiB |
| --- | --- | --- | --- | --- | --- |
| before | 14.723 | 22.359 | 45.375 | 45.375 | 22.547 |
| after | 14.789 | 22.426 | 45.441 | 45.441 | 22.613 |

The 68 KiB observed peak difference is small relative to the same token's allocation in both versions; one fresh process per version and sampled RSS do not establish a worst-case bound. Public encoder traversal/circular-detection state remains proportional to nesting; the chosen candidate adds no aggregate token list, index or full encoded report copy. Individually large encoded tokens and their UTF-8 encoding/buffering remain possible allocations. Raw 1 ms observations and source paths are in `large-token-memory.json`; these are separate from the main benchmark worker/client arrays.

## Self-review and handoff limits

Self-review checked exact public encoder defaults and 3.9/3.12 bytes/errors; the unchanged shared atomic publication scaffold and cleanup; same consumer aliases; unchanged full raw engine/web source, defaults and response bytes; no publication/no-op/transaction/replay/lifetime/ACK bypass; no runtime test-only hooks or experimental aggregation. Production diff is the single encoding expression plus three explanatory comments. Test/harness changes are scoped to this owner and truthful separate measurement. Complete content preservation is supported by golden/stdlib expected bytes, actual route/engine/render/fresh-reopen regressions, full deterministic report expectations, cryptographic whole-file hashes and remaining physical-file byte comparison.

Adoption is limited to measured local changed-report publication benefit 18.37–23.12% with acceptable observed RSS, not a general JSON performance claim. The retained 100k no-op median regression, uncontrolled shared-host activity, five samples/cell, warm filesystem caches, loopback Cheroot, no load/concurrency/inference/media, cumulative/sampled rather than allocation-traced memory, and Linux/WSL-only platform evidence remain explicit review concerns. Fewer Python calls are not fewer syscalls. Atomic replacement and directory durability/platform limits remain the unchanged helper's documented limits.

Final post-timing commands were prepared 3.12 `python /tmp/openscrub-task632/large_token_memory.py` and `python /tmp/openscrub-task632/check_evidence.py`, each exit 0, writing `large-token-memory.log/json` and `committed-evidence.log/json`. No final latency/suite/build/browser repetition followed stable successful evidence. The supervisor owns independent review and any future publication; this implementation does not imply assembled-application or umbrella approval.
