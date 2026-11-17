# Task112 / P11B — chronological tail-history index

Status: implemented and committed for fresh review. The detector-consistent sparse fixture reduces the measured **complete `merge_detections` call, including tail extension and index construction**, from a median of 12.272 ms to 3.384 ms (−72.42%). This is not the entire scan-finalization boundary: reverse recall, dense smoothing, report generation, decoding and OCR inference are outside these timed calls. Tiny unique/repeated differences are not claimed as established gains; the original repeated control's +27 µs / +1.97% observation remains in the evidence.

## Source and scope

- Exact base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, tree `795af785b672d397d2e287b5b963c10dcc4dbdf8`. All 113 exported files verified against Git blob identities in [base-identity.json](task112-evidence/base-identity.json).
- Candidate: `e96deb59e1b3c36585672be4c74d90eb6d0a49b5` (`perf: skip irrelevant chronological OCR tail history`).
- Final head: `952af20da205133886ba69799e134b86d1654137` (`bench: model sparse OCR history with a benign prefix`), tree `8341225c0efacecaae691c6ce92623a3067f1747`. The second commit changes only the benchmark fixture. Native branch `pr/tail-history-index`, worktree `/home/tahv0/.codex/worktrees/c832/OpenScrub`, clean after commit.
- Runtime SHA256, identical through timing, full/focused/floor checks, both commits and installed wheel: `2ea608fa18eaa197d356e50e52abff67938f4d53416a9af4c0ebfbe915898b6a`. Base runtime: `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`.
- Final benchmark SHA256: `027f588469c6c5159dbcccf581fa4c1731c94c1b5dec4e66dbf03e99ba28f475`. Original comparison benchmark: `299dbe5aed1a45a0a765e7ece1901b9dc4ecde6e0b6384dcdf45cf59ba198efa`, retained as [tail_history-original.py](task112-evidence/tail_history-original.py) and in commit e96deb5.
- Final semantic test SHA256: `581578199f2441cbea0edc3bdcab4ff02ecab92b1028ebce467b050e6b60fa32`. Full-suite earlier test bytes: `ecfae9cb1ba68ab0d7e31c40d733fa7ea676c28f7ddf1363ef921e491e9a60da`, retained as [test-tail-history-full-suite.py](task112-evidence/test-tail-history-full-suite.py).

[Final source identity](task112-evidence/final-source-identity.json) binds all six changed files to final Git blobs and SHA256. No P11A smoothing, P11C reverse indexing, P11D candidate-priority rewrite, contradiction indexing, donor preview/cache subsystem, dependency/version/default or detector/matcher threshold changes. No original-checkout product/user-data changes, model/dependency downloads, nested agents, push, published PR or external messages.

## What changed and why

`merge_detections` repeatedly restarted the OCR history before rejecting timestamps at/before each span's `last_seen + .01`. A local list of existing timestamp references is built once for ordinary chronological list/tuple histories with multiple non-dense regions and text to process. It is validated without sorting. Each eligible span uses `bisect_right` at the exact existing boundary and walks the original rows by index through a generator; there is no per-span history slice or copied OCR payload.

The original in-loop boundary remains, which matters after supporting rows advance `last_seen`: equal/nearby duplicates still skip, and supporting rows, contradictory/missing support, geometry, confidence, fuzzy thresholds and bridge-gap stops retain their original ordering and predicates. Other Detection fields remain untouched. Nonchronological, nonfinite, unusual-numeric, malformed-row and unsupported-container histories use the original traversal, including prior exceptions and unreachable-malformed behavior. One merged region uses the original traversal without index construction; empty/no-text/dense-only/fuzz-disabled cases keep their behavior. No history-age cap or caller-input mutation was added.

Changed files are `openscrub.py`, `tests/test_tail_history_index.py`, `benchmark/tail_history.py`, `benchmark/README.md`, `test_openscrub.py` (whole-discovery command guidance only), and `pyproject.toml` (source-distribution inclusions for owning tests/benchmark/guidance). The wheel still includes the same six runtime modules.

## RED and measurements

Task112 explicitly permits performance RED as exact-base work/cost evidence instead of inventing a method-count unit-test failure. The semantic controls passed the base; initial fixture-assumption failures listed below are not claimed as RED. Before product edits, [baseline-attribution.py](task112-evidence/baseline-attribution.py) executed the actual complete exact-base engine, with normal GC, three warmups / five uninstrumented recorded calls, and a separate traced call. [Raw baseline attribution](task112-evidence/baseline-attribution.json) retains complete records and counts:

| Scans / supplied detections | Mode | Base median merge ms | Base tail timestamp visits | Prior merge-candidate visits |
| --- | --- | ---: | ---: | ---: |
|100/100|unique|20.669|5,149|4,950|
|300/300|unique|188.377|45,449|44,850|
|10,000/30|sparse unique|12.661|299,594|435|
|1,000/1,000|repeated|1.418|1,000|999|

Instrumented tail/total durations are stored separately and carry tracing overhead; they are attribution evidence, not uninstrumented timing estimates. The large unique merge-candidate counts show unrelated quadratic work remains. The initial sparse history deliberately supplied only the final 30 detections while all OCR rows were emails: valid controlled merge inputs, but not detector-consistent scan history. That limitation was found during self-review, escalated and corrected, not hidden or relabeled.

The original complete paired comparison is preserved under its original [JSON](task112-evidence/final-comparison.json) and [log](task112-evidence/final-comparison.log). Base→candidate medians were unique10021.083→20.939ms (−0.68%), unique300186.020→184.260ms (−0.95%), sparse12.126→3.251ms (−73.19%), repeated1.377→1.404ms (+1.97%, +27.180µs). These are all retained, including the regression. Unchanged-path counts do not establish the cause of that repeated-control observation.

The corrected fixture makes the first 9,970 OCR rows benign `pending`, followed by the same 30 deterministic unique email rows/detections. Actual `group_lines → detect_phi → email-category filtering` confirms both checked benign-prefix endpoints produce 0 email detections and all 30 suffix rows produce 1 each; all prefix strings are explicitly checked as `pending`. [Boundary evidence](task112-evidence/sparse-detector-boundary.log). This was a bounded matcher check, without a new video or model workload. The supervisor authorized a complete four-case repeat for that named representativeness concern. Settings and all controls were retained; nothing was selectively rerun for a favorable result.

The acceptance comparison, [complete JSON](task112-evidence/final-comparison-detector-consistent.json) and [log](task112-evidence/final-comparison-detector-consistent.log), imports both complete modules, fixes OpenCV threads to1, prepares fresh mutable inputs outside timing, keeps ordinary GC enabled, performs three warmup pairs and five alternating recorded pairs, compares every returned Detection field on every call, and finishes all timing before separate tracing/tracemalloc instrumentation. Warmup timings/digests, all five samples, call order and full final output records for both versions are retained. Hold=.5s, bridge_gap=4s, timestamps every1/3s, actual RapidFuzz and deterministic seed83011+i email strings. Inputs and algorithm settings are identical between base/head.

| Scans / detections | Mode | Base median ms | Candidate median ms | Observed change | Tail visits base→candidate | Index entries / queries |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
|100/100|unique|21.264551|20.807811|−2.15%|5,149→99|100/100|
|300/300|unique|186.222872|185.608111|−0.33%|45,449→299|300/300|
|10,000/30|sparse unique, benign prefix|12.271633|3.384366|−72.42%|299,594→29|10,000/30|
|1,000/1,000|repeated|1.390948|1.387058|−0.28%|1,000→1,000|0/0|

These are bounded fixture observations. Small unique/repeated variations across both runs are not promoted as proven gains. The cost-inclusive sparse improvement is the adoption basis. Prior-candidate visits are unchanged at4,950/44,850/435/999 respectively; neither candidate nor evidence claims that unrelated work was fixed. All full-output equality assertions passed in both comparisons and separate work runs.

## Construction, allocation and limits

Every timed candidate call includes validation, index construction, binary lookups and iterator creation. The index retains only references to existing timestamp objects during the merge, and is local to that call. No cross-call cache or OCR-word copy is retained.

| Case | Index list bytes | Full-merge traced peak base→candidate bytes | Traced current after merge base→candidate bytes |
| --- | ---: | ---: | ---: |
|unique100|920|6,008→8,104|2,696→2,856|
|unique300|2,520|15,608→19,364|7,496→7,656|
|sparse10,000/30|85,176|2,552→88,964|1,016→1,176|
|repeated1,000|0|33,088→33,088|24,448→24,448|

List bytes are `sys.getsizeof` of the actual local list observed in the separate traced call. Tracemalloc describes Python allocations for the complete merge and excludes native heaps; its current values do not mean the timestamp list survives return. Whole-process cumulative maximum RSS after all corrected cases was92,992KiB (original paired run95,064KiB), including both full module imports, all fixtures and native libraries; it cannot attribute index memory or establish a process-memory ceiling. The extra index storage is O(history), not constant-space.

All timed slots were explicitly coordinated/released with the supervisor as the only owned runtime/benchmark workload. The host itself was not globally reserved. Five samples do not support p95/population claims, and these synthetic cases do not establish real pretrained OCR/inference throughput, end-to-end scan acceleration, all-finalization acceleration, default-settings long/4K performance, or multi-platform memory/time behavior. No arbitrary cutoff is inferred from these fixtures.

## Verification and source binding

[Executed command record](task112-evidence/commands.md), [delivery checks](task112-evidence/delivery-verification.json), and [evidence hashes](task112-evidence/SHA256SUMS.json) accompany the raw logs.

Prepared 3.12 was `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` (3.12.16, OpenCV 4.14.0, NumPy 2.5.5, RapidFuzz 3.14.6, FFmpeg 8.0.1 tools). Active floor was `/tmp/openscrub-python39-20261117/venv/bin/python` (actual 3.9.25). Task-local copied isolation hooks route profile/models/jobs/settings/cache/temp under `/tmp/openscrub-task112`, reject outward connections and model fetches, and guard writes. Cached YuNet was copied into that task's model directory; no new model was downloaded. Source import assertions select the actual intended native/export/installed module before acceptance execution.

- Base semantic controls: final 20/20 passed, [log](task112-evidence/semantic-base-amended.log). They call the active complete module and assert literal/full records across chronological, tuple, repeated, duplicate and updated `.01` boundaries, confidence/geometry, missing/contradictory support, bridge gaps, caller order, unusual/nonfinite timestamps, generator fallback, malformed errors and malformed rows beyond a stop, and empty/no-tail cases. No unit test requires Git, an old checkout, an index dispatch count, or a miniature implementation.
- Candidate focused 3.12: 27 passed / 127 deselected,3.36 s, [log](task112-evidence/focused-head-final.log). Command selection: `tests/test_tail_history_index.py test_openscrub.py -k 'tail or merge or bridge or detector_only_scan' -q`.
- Actual 3.9.25 focused: same 27 passed / 127 deselected,3.42 s, [log](task112-evidence/python39-focused-final.log). Task-specific hooks were copied/retargeted before collection; active native source path was asserted. This is focused floor coverage, not a full 3.9 suite claim.
- One full discovered suite:153/153 passed, 72.42 s, [log](task112-evidence/full-discovered.log). It includes all 134 baseline tests plus the then 19 candidate cases. Runtime SHA remains final `2ea608…`; baseline-test SHA remains `feef977385df4f689317a73c6ff913cba22a0260d0afaf8a0a03d02b32de2636`. The tail-test SHA for that run is explicitly **ecfae9cb…**, not final 58157819…. Self-review then strengthened malformed controls to two eligible text regions, added the generator case, and strengthened the fuzz-disabled full-record assertion. Final 27 focused cases passed on 3.12/3.9 and final 20 passed on exact base. No runtime change or new broad-suite concern justified repeating the full 153 run. The benchmark-only second commit does not change test/runtime bytes. No full 154-case claim is made.
- Tiny real integration is among those controls: lossless FFV1 160×96, 6 fps, 8 frames; only `make_ocr` is controlled at the existing interface, returning two separated email regions and a benign token. Actual decoding, forward memory, reverse recall, merge and `write_report` run. Four OCR scans yield two full literal records with `last_seen=1`, `t_end=1.6333333333333333`, original boxes/confidence/fields; report records including `enabled` and cumulative motion are checked. This verifies the pipeline boundary, not model throughput.
- Offline source distribution then wheel build passed, [final build log](task112-evidence/build-fixture-final.log). All six runtime modules match native bytes in sdist/wheel/installed target. Candidate tests, benchmark script/guidance, baseline regression file and pyproject match exact final bytes in sdist. Python >=3.9 metadata remains unchanged. [Final package identity](task112-evidence/package-fixture-final-identity.json).
- Installed CLI `openscrub --help` and `openscrub-web --help` both exit0. Installed core/web paths are asserted, native/editable checkout paths removed from installed-only sys.path and CLI subprocesses by task-only hooks. Flask test client `/`, `/api/jobs`, `/api/models/face`, `/api/model_status`, `/api/vault` all return 200; jobs empty. Parser defaults match complete exact-base parser defaults. [Installed smoke log](task112-evidence/package-smoke-isolated.log), [structured results/defaults](task112-evidence/package-smoke.json). This does not claim a bound-port server or browser run. No UI change required browser matrix work.
- Rebuilt wheel after test/benchmark-only corrections is byte-identical to the already installed/smoked wheel, so startup was not repeated. Final wheel SHA256 `4981a41cf9b22bcb79e9ab4d8dddc58054f267c250c827fef013f0dfe4f1a4af`; final sdist SHA256 `e44802a25d5d368438c3ee975254b19ba2cb1930d45c4bb864de09ded61a71c6`.
- Final `git diff --check`, measured-runtime/benchmark identity checks and committed-file Git-blob checks pass; worktree clean. No push/publication occurred.

## Tooling/fixture failures retained honestly

1. Initial semantic scaffolding assumed Decimal subtraction with a float last_seen was supported; the exact base raises TypeError, so it became an exception-preservation case. A single-word OCR fixture with tracking disabled reached the existing first-scan sanity path with `small=None`; the established retained recipe returns three words. The fixture now follows that interface without product changes. Initial expected hold and box separation were corrected from actual `hold=sample_interval+.3` and existing 12px box slack. These were fixture mistakes, not product RED. Raw logs retained.
2. A base-source assertion caught native current-directory shadowing before test execution. It was rerun from isolated `/tmp/openscrub-task112/runtime` with the complete base path asserted. The failing log is [semantic-base-complete.log](task112-evidence/semantic-base-complete.log); passing amended controls are separate.
3. Prepared 3.12 had `build` but no Hatchling backend, so the initial offline build failed before building. The existing cached wheelhouse was installed into task112/build-tools using the prepared 3.12 interpreter and only a temporary pure-Python pip bootstrap PYTHONPATH. No 3.14 interpreter was run and bootstrap paths are absent from installed smoke imports. Subsequent offline `--no-isolation` builds pass. [Initial failure](task112-evidence/build.log), [cached tooling install](task112-evidence/build-tool-install.log).
4. Installed-only isolation assertion caught the prepared venv's pre-existing editable `.pth` appending native paths. Core/web already resolved to installed files, but the stricter assertion correctly failed; task-only sitecustomize filters checkout paths in installed-only mode and the corrected smoke passes. The venv/user installation was not edited. [Initial smoke failure](task112-evidence/package-smoke.log).
5. Sparse-prefix representativeness correction and complete repeat are described above, with both scripts, runs, all samples and their own source identities retained. Initial scaffold pytest cache in the isolated native worktree was removed; final runtime artifacts remain task-local. No failure was hidden by a claimed full-suite rerun.

## Self-review and disposition

The change is local to the measured owner and uses stdlib bisect; scan predicates and all returned fields remain covered. Self-review produced meaningful malformed/generator controls and the separate detector-consistent fixture correction rather than hiding weak evidence. Sparse benefit survives the stricter fixture and construction/memory cost; the supervisor accepted this bounded candidate for fresh review. Remaining limitations are the explicit O(history) list allocation, the retained original repeated regression/tiny-case variability, and synthetic Linux-only timing/model-throughput limits. No unresolved correctness concern was found in self-review. Fresh independent review belongs to the supervisor.
