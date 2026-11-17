# Task652 — third intermediate C01 assembly

Implemented locally on `integration/upstream-focused` in native `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Exact base `ac6496810b03d8b062ab9da150aeea1e62285fed` → exact final/tested/measured head `4b9bd7e576a8ae30369672b4b4722fc9752e233f`. Independent supervisor review remains pending. This is an intermediate assembly; no final C01 approval, C02 adoption or publication is claimed. Original checkout product files/user data and every candidate branch remain untouched. No new worktree/branch, merge, squash, nested agent, dependency/model download or external message/publication.

## Provenance and intersections

| Candidate | Original reviewed commit | Actual `-x` pick |
| --- | --- | --- |
| P06C.2 readable serialization | `4a62e49d2f0896b737081cc92e1f92e9bcaee93f` | `0dce3d32965449effe5876237ffc85faf74e8d89` |
| N09 HDR decoder closure | `ded411cbec308333d1416ae3d58b4f6e918d7849` | `864e62857493612bd142f7c4d8bd8d6b9fb6abb6` |
| P16A HDR chroma | `0c648c2e7d3e40304dce9ae878d14709966b1fe1` | `5408f87b965dcd66089677385b9ac9c0f4e24a3b` |
| P16B known-box fallback | `a3c3193e8dff41ec0588e66443398048a5c15ece` | `fe4b22f17b35c12ad2f35c95c0d7b89cd37faf37` |
| P10C manual cancellation | `2004b22002b8317c26ea508ff8187acbcd0cfab2` | `533919313d293d2fab8fc15407c8a30d4dbca1a6` |

Sixth commit `4b9bd7e576a8ae30369672b4b4722fc9752e233f` is test-only: **Reconcile combined HDR oracle and cover default report rendering**. No runtime integration correction was needed. All engine intersections auto-merged. Actual conflicts: serialization pick met the existing benchmark's already-optimized baseline expectation/reusable-count documentation and old `report_dump` counter. Retained explicit before-noop0 control and recovery guidance, selected candidate's common `report_encode` plus method-specific counters. N09/A/B met cumulative contributor/README guidance and sdist test/benchmark inclusion; retained combined discovered-suite, Node, HDR prerequisites and all source inclusions. No unrelated source transplantation.

Read the Task652 brief, Task651 report/review and relevant Task632/109/161/162/110 candidate contracts/reviews. Standalone candidate results stay attributed to their original heads. The combined native runtime preserves Austin defaults (`auto/auto/auto/blur/8/tight/archival`), Python>=3.9, OpenCV<5 declarations and existing private-owner contracts. `self-review.json` confirms web function/class ASTs unchanged and existing engine owners changed only in the four reviewed functions; the new silhouette helper is local to B. No broader worker, replay, admission, output or coverage-policy rewrite.

## Combined renderer and oracle

Initial combined A/B test run (`oracle-red.log`) produced **884 passed, 16 failed**. Exactly B's valid-HDR bowtie/outside-triangle controls expected its old nearest sampling; those standalone expectations were intentional. The correction enumerates each nonzero luma pixel's global `(row//2,col//2)` cell independently of production's aligned reduction. All SDR/luma/exact unrelated/full-box assertions remain; every A parity/odd/clipped/padding/mode case and B usable-contour/fallback mode remains. No loosened comparison or product revert.

`tests/test_batch_integration.py::test_combined_report_run_render_default_coverage_exact_input` exercises ordinary raw report load → actual `run_render` → actual SDR/HDR renderer → real CPU FFmpeg encoder. It parses normal CLI defaults, keeps **tight coverage/archival quality**, requests box fill/pad1, and explicitly chooses the prepared CPU encoders. One 64×64 two-frame document combines a sparse usable triangle, malformed missing-coordinate polygon with a valid separate box, independent rectangle and disabled/kept collinear row. The independent oracle enumerates literal sparse-pixel padding and rectangle coordinates then their global chroma membership. Actual pre-write BGR/YUV bytes equal the **whole expected frames**, including unrelated/kept cells; real output has two frames and expected pixel format, dimensions and PQ/BT.2020 tags. Existing A tests additionally prove literal unpadded extra chroma cells and default `run_render` sparse/unmasked SDR/HDR controls; B's malformed/degenerate/full-box/usable controls remain exact.

No coverage transform bypassed fallback in these actual default-tight controls; no concrete pipeline-owner change or default-option workaround was needed. The new test does not call a leaf in place of orchestration. HDR context is explicitly supplied for the CPU synthetic source; it does not certify automatic device selection or a new HDR intake platform. Exact encoder input is separate from lossy decoded output. Existing retained-exception N09 tests ran on combined source: real frame-zero cancellation and killed actual encoder first-write failure, actual `run_render`/`render_hdr` traceback, closed decoder stdout/encoder stdin and independently reaped children before harness cleanup. Harness defensive closes/waits are never credited as production cleanup.

## Actual HTTP/PAGE, persistence and output

Browser plugin unavailable in this session; used prepared Playwright/Chromium per frontend testing skill. `/tmp/openscrub-task652/serve_browser.py` reuses Task651's mixed 13-row fixture at a declared imported-report boundary with synthetic 60-frame 160×96 video. No detection-accuracy claim. The actual PAGE, Flask save route, new shared serializer, job worker, renderer, report publisher and actual HTTP responses remain production implementations. The only faults are a held client acknowledgement and an explicit publisher OSError on the named save request. Update-check response is controlled to avoid external network.

`browser.cjs` verified desktop 1365×1000 and fresh mobile 390×844 PAGE identity, meaningful content, no framework overlay, zero page exceptions, actual controls and screenshots. An equal-value save returned200 without any publisher call or inode/byte change. While that real successful response was held, a newer opposite draft remained; releasing the acknowledgement did not render or acknowledge the newer edit. An actual changed-save publisher failure returned500, retained the draft and old report, and made no render request. Restoring the equal stored value then saved no-op and **did render**.

Render completion waits for **accepted POST/render200 and a newly completed real report-publication event**, together with job done, avoiding stale pre-request done. The following changed save applied repeated group Keep/track Blur plus independent outside-zone Blur and a new `manual_id=batch652:replay`; the real worker rendered again. All 14 raw rows/indices/flags, original 13 geometry/times/text/confidence/metadata, render state and all audio_redactions/audio_suggestions/audio_transcript/additive fields were compared exactly. Same-ID replay preserved 14 rows. A fresh browser fetched exact raw report and indices/choices; a fresh interpreter rehydrated disk jobs and used real HTTP report/detections and replay, proving unchanged bytes/inode and zero response owners.

`check_output.py` independently decodes actual output: **all60 frames and every 14 selected/kept region center** satisfy expected black/visible choice. Region minima/maxima retained in `output-check.json`; this is decoded-output evidence, not an exact lossless-pixel or audio-waveform claim. Browser request/response/fault details: `browser-results.json`, `publications.json`; fresh interpreter: `fresh.log`; screenshots: `browser-draft-desktop.png`, `browser-after-render-mobile.png`. Healthy browser controls produced no diagnostic; exactly one 500 console resource diagnostic matched the injected save scenario **and exact /api/jobs/<alpha>/detections URL**. No prior polling/stream matrix was repeated.

## Cancellation and ownership

Combined Task110 tests ran actual native NCC matching and full retained uncancelled steady/loss arrays. Forward cancellation after completed match 1 observes totals2 grabs / 3 reads / 3 matches, with **0 later grabs / reads / held appends**, while the remaining 2 matches finish the same existing three-scale sample. Backward match 22 observes9 grabs / 16 reads / 24 matches, again0 later grabs/reads and2 same-sample matches. These observed read totals are not universal native decoder bounds. Natural loss/hold and final-return checkpoints, precancelled invalid inputs, ordinary helper failure and cancellation propagation remain covered.

The actual Flask track_object/cancel/track_status/delete test calls the real tracker against synthetic registered media. It controls unrelated person construction and gates only completed native match/capture cleanup boundaries. Start/cancel200; cancelled status has added0 and no report changes/partial publication. Delete409 while one work/source owner exists, including **after actual capture closure**; measured capture released once and closed while owner count remains 1. After cleanup resumes: owners/work/live threads0/0/0, tracker lease released, delete200. `MANUAL_CANCEL_COUNTS`/`MANUAL_WEB_COUNTS` in focused/floor logs retain counts. Existing tests establish ordering before defensive harness cleanup.

The bounded `test_batch_integration` lifecycle overlap also exercises real scan/preview cancellation/retry, held response source ownership, delete/vault409, eventual release and fresh HTTP replay. Focused transaction/large-report/replay tests retain atomic failure, busy/deleting/vault/latest-document and manual-replay gates. Serializer compatibility/error cases retain readable bytes and exact original exceptions for encoding/flush/fsync/replace failures. No-op still goes through admission/fresh parse/lock/replay checks; no shortcut bypass.

## Validation and identity

Artifacts and executable recipes: `/tmp/openscrub-task652`. Native cwd plus actual engine/web/zones imports and real code filenames asserted before **every** test run. Prepared Python3.12.16/OpenCV4.14 and actual Python3.9.25 reused. Task-local floor hook changed its allowed root to Task652 **before collection**. Cached YuNet reused only after SHA256 pin `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` verification; new actual media gates are model-independent CPU.

| Check | Accepted result | Artifact |
| --- | --- | --- |
| A/B owning first integration RED | 884 passed/16 expected old HDR oracle failures | oracle-red.log |
| Corrected exact controls + new default pipeline | 98 passed/807 deselected | combined-first.log |
| Combined focused 3.12 | **1,242 passed**,35.42s | focused.log |
| One stabilized full discovered suite | **1,643 passed/1 optional browser skipped**,132.17s | full.log |
| Actual3.9 combined owning set | **1,242 passed**,40.05s | floor.log |
| Actual PAGE/HTTP/draft/save/render/fresh browser | passed; one exactly accounted injected500 | browser.log/browser-results.json |
| Actual decoded video and fresh interpreter replay/owners | 60 frames/all14 rows; passed | output-check.json/fresh.log |
| Offline sdist→wheel | success, cached Hatchling1.33.0 | build.log |
| Exact archives/Python3.9grammar/defaults/declarations/evaluated JS parse | passed | packaging.log/json |
| Correct-runtime installed CLI/web/HTTP/vault/allowlist, SIGTERM | passed, exit0 | installed-startup.log/json |
| Installed compat/read-only ownership consumers3.12/3.9 | passed/no network | installed-compat-final.log/installed-compat39.log |
| Tiny both-source common count smoke | six actual HTTP200; zero noop/one changed publication | count-smoke.log/results.json |
| Self-review runtime/test/package binding | 144 frozen blobs;10 wheel Python files installed/native exact; candidate refs intact | verification-source.json/self-review.json |

Focused commands in3.12/3.9 used the following exact files: `tests/test_hdr_decoder_cleanup.py tests/test_hdr_chroma_coverage.py tests/test_polygon_fallback.py tests/test_manual_tracker_cancel.py tests/test_report_serialization.py tests/test_batch_integration.py tests/test_large_report_io.py tests/test_report_transactions.py tests/test_manual_addition_replay.py tests/test_job_lifecycle.py tests/test_job_response_lifetime.py tests/test_job_source_allowlist_lifecycle.py tests/test_review_choices.py tests/test_review_save_failures.py`, via `python -m pytest ... -q -s` with task basetemp/cache. Full command: `python -m pytest -q --basetemp=/tmp/openscrub-task652/full-tmp -o cache_dir=/tmp/openscrub-task652/cache`. Source/test bytes were frozen before the full run, unchanged through floor/build/commit/timing; postcommit checker binds all to final Git blobs. Optional browser skip is covered for the affected flow by the separate actual PAGE run, not claimed as execution of the skipped historical matrix.

Build used `PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse` and the existing build frontend. Installed the produced wheel with **prepared3.12**, using cached pip code through `PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --upgrade --target /tmp/openscrub-task652/installed/site-packages WHEEL`. Bootstrap3.14 interpreter was not used. Installed shebang/import gates and real CLI/web startup passed. Sdist contains all 25 focused test files plus root suite/guidance/benchmark; runtime wheel includes all 10 runtime Python sources including recursive private helpers. Dependencies/defaults unchanged from reviewed base; no new resolver/platform certification.

Retained failed tooling attempts: `initial-browser.log` completed behavior through fresh reopen but rejected Chromium's actual uppercase `INTERNAL SERVER ERROR` against title-case expected text; corrected exact diagnostic text and reran a fresh task fixture (`browser.log`). `installed-compat.log` initially imported native source because it inherited source PYTHONPATH; corrected to installed-only paths and actual3.12/3.9 checks passed (`installed-compat-final.log`, `installed-compat39.log`). These failures are not counted as product or accepted passes. Expected missing-model fallback/LOST tracker logs, synthetic invalid-media `moov atom not found`, controlled500 Flask traceback, optional NER setup note, and explicit local plain-HTTP startup notices are expected diagnostic boundaries; no cleanup expansion or unexplained healthy browser diagnostic.

## Performance interaction

One approved exclusive slot compared exact `ac6496810b03d8b062ab9da150aeea1e62285fed` → exact `4b9bd7e576a8ae30369672b4b4722fc9752e233f`. Supervisor and implementer exchanged start/end notices; all other own servers/suites/build/install work stopped. Supervisor avoided competing workloads. The host itself was not reserved. No source change or amendment followed measurement; all samples remain attributed to their actual commits. No selective rerun.

Exact native command (prepared3.12/env.sh):

```sh
python benchmark/review_io.py --scenario saves --rows 100000 \
  --repository /home/tahv0/.codex/worktrees/c832/OpenScrub \
  --before-ref ac6496810b03d8b062ab9da150aeea1e62285fed \
  --after-ref 4b9bd7e576a8ae30369672b4b4722fc9752e233f \
  --before-noop-publications 0 --warmups 3 --samples 5 \
  --evidence-dir /tmp/openscrub-task652/measurement \
  --output /tmp/openscrub-task652/measurement/results.json
```

Command completed **exit0**. `measurement.log/results.json` retain every warmup/sample/status/RSS array/client observation/import/export hash. Actual loopback Cheroot requests include complete response reads. Payload/fixture/reset/expected hashing are outside timing; instrumented workers are separate after timing. Before and after both skip no-op publication; the common counter works with both serializers. Tiny6-row counted smoke ran first and passed. Only the required100k interaction set ran: **48 uninstrumented HTTP200 requests (18 warmup / 30 recorded), six separate counted HTTP200**, all owners 0. No1k / 10k, attribution, large-token or old matrix rerun.

All times ms, five observations per cell. Reported maxima describe these five samples; they are not estimates of population tail latency. Raw benchmark JSON is retained unchanged, including its historical percentile fields.

| Operation100k | Before min / median / maximum | After min / median / maximum | Median change |
| --- | --- | --- | --- |
| noop | 949.785 / 1026.342 / 1207.489 | 956.871 / 1143.987 / 1317.210 | +11.46% |
| sparse | 5055.757 / 5118.368 / 5333.521 | 4083.921 / 4152.754 / 4411.719 | -18.87% |
| bulk | 5278.286 / 5319.679 / 5338.922 | 4383.997 / 4403.840 / 4423.394 | -17.22% |

Every recorded sample, in per-version request order:

| Operation | Before ms | After ms |
| --- | --- | --- |
| noop | 965.414856, 1207.488890, 1026.341558, 1149.599230, 949.784663 | 1317.209811, 1143.987447, 1019.519816, 1179.140024, 956.870631 |
| sparse | 5088.960358, 5333.520838, 5118.367834, 5318.822061, 5055.756993 | 4152.753835, 4411.719382, 4146.461136, 4345.321939, 4083.921459 |
| bulk | 5319.678724, 5338.921755, 5298.616383, 5278.285881, 5324.842647 | 4399.144719, 4383.996539, 4423.393703, 4412.202530, 4403.839888 |

Every warmup, in per-version request order:

| Operation | Before ms | After ms |
| --- | --- | --- |
| noop | 1999.198299, 3431.347419, 2040.207930 | 2690.805100, 1576.339210, 1709.153696 |
| sparse | 5140.114898, 5095.993925, 5290.528951 | 4166.639359, 4199.301081, 4398.889025 |
| bulk | 5349.570800, 5354.956427, 5323.388679 | 4398.134505, 4371.325868, 4450.120513 |

Peak observed worker RSS KiB across warmup/recorded samples:

| Operation | Before | After |
| --- | --- | --- |
| noop | 451432 | 451792 |
| sparse | 452168 | 452528 |
| bulk | 465612 | 469704 |

RSS is sampled5 ms and can miss peaks; VmHWM includes imports/reset/fixtures and prior operations. It is not request-only memory or a hard allocation bound. Full worker/client memory and per-sample timing order remain in JSON. Changed-save improvements 17.22–18.87% are a bounded local interaction observation. **No-op median regressed 11.46%** (1026.342→1143.987 ms); retain this measured concern, alongside the prior standalone Task632 +9.97% control observation. Zero-publication counts and unchanged no-op route bytes establish scope, not cause or repeatability. No scheduling/GC attribution or general untouched-feature speed claim.

Separate counts, per request: both versions parse/report request JSON/response JSON1; no-op report_encode/stage/fsync/replace/write/writelines0. Sparse/bulk encode/stage/fsync/replace1 each. Before uses one json.dump call,12,460,177 Python staging writes,0 explicit encoder instances/writelines/chunks. After uses0 json.dump / 0 Python staging writes, one public encoder instance and one writelines call,12,460,177 iterator chunks. Serialized characters agree across versions:69,956,371 sparse,70,038,188 bulk. These are Python dispatch/piece counts, **not OS syscalls or an output-format change**.

`check_evidence.py` independently checked all54 statuses/owners, every no-op bytes/inode/mtime observation and exact final metadata/hash, every changed-request inode replacement, every expected complete final hash, retained actual final timed bytes and separate counted bulk phase 1 bytes. `expected-final-100000.json` is69,956,372 bytes, SHA256 `74f6909e2997cc763ecdbd8601986a5ae784217a4a7270e2863b3ffb7b814681`; expected counted changed output is retained separately. All 3 scenarios finish their 8 phases at the original choices; final physical timed files are last bulk phase 8. No intermediate physical file is falsely labelled as still retained. `committed-evidence.json` records complete-output checks.

Both exported subject inventories were verified before imports and after measurement:139 before / 144 after Git blobs; actual engine/web/report imports resolve within their pinned export roots. The final driver intentionally runs both source versions with its common counters; tooling identity is the measured-after `benchmark/review_io.py`, distinct from subjects' serializer implementations. `check_committed.py` proves all 144 frozen files match final Git/native bytes, all 10 wheel Python sources equal installed/native/commit, all five -x markers/candidate refs intact, clean head. No runtime-identity amendment or SHA relabelling was needed.


## Limits and disposition

The runtime delta is exactly the five reviewed candidate contracts; the only separate correction is combined tests. This bounded intermediate gate does **not** certify comprehensive P16C geometry/resource/staged-video publication. Nonfinite/reversed/zero-area primary cboxes have no usable known fallback here; arbitrary malformed report-container admission, primary-box repair, preview-outline malformed geometry, arbitrary compute exceptions, all-exception stderr/capture/encoder cleanup, short reads/final encoder-wait failures, prior-output preservation/restoration and staged video publication remain separate. N09 covers its existing cancellation/write-error cleanup calls only. Cancellation is cooperative Python-boundary observation; native open/read/recovery/model/match/inference can block and the current three-scale sweep can complete. No native interruption/deadline claim.

Synthetic Linux CPU/OpenCV/FFmpeg/Chromium and focused 3.9 evidence do not establish all encoders, Windows/macOS/frozen/container/GPU, Safari/Firefox/native picker, inference accuracy, audio waveform correctness, long/4K throughput, cross-process/crash/Windows durability or hard memory allocation bounds. Readable JSON bytes/errors, complete raw reports, manual replay, source/operation lifetime and browser draft/ACK behavior remain the inherited reviewed owners. No untouched-feature speed claim. Self-review found no outstanding task-scoped product concern; supervisor owns independent exact base→head review and acceptance transfer. Final C01/C02 remain open.

Final package hashes: wheel `bc13cab502da52977ffaa657a3896f8f341f9ae2ee9056c3c301842c20daece0`; sdist `61179e0ffb94fba541a1e304c9d8d547e424497fea3a617ed2ce006fcd58f914`. Final runtime import ASTs equal base across all 10 runtime Python sources except P16B's reviewed stdlib `import math`; no removed-system or new dependency imports were introduced (`imports.json`). An auxiliary final checker initially expected every import exact and failed on that reviewed addition (`imports-red.log`); the corrected explicit permitted-delta checker passed (`imports.log`). This was tooling, with no source/test/measurement change.
