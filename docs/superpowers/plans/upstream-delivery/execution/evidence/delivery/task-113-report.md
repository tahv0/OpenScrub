# Task 113 / P11C reverse-recall candidate index

**Adopted with measured limitations.** Commit `9d888708d08cccf6e5f0ec8c9cf81740d3868fa1` (`Index reverse recall candidates by length and digit type`) on `pr/reverse-recall-index`, based exactly on `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. Native worktree `/home/tahv0/.codex/worktrees/c832/OpenScrub` is clean. P11A, reviewed P11B `952af20`, and P11D are independent and excluded.

The supported heterogeneous history's measured **reverse plus merge** median changed from **51.924 to 9.248 ms**. The repeated-memory control regressed **0.204 ms in reverse** and **0.166 ms (+6.0%) in reverse plus merge** in the final comparison. The first candidate comparison also observed a **1.1% same-length combination regression**. Neither regression is dismissed, averaged away, or tuned out. The supervisor accepted these bounded tradeoffs before completing verification.

## Implementation and preserved behavior

Only `reverse_pass` runtime behavior changed. After the first eligible, non-allowlisted OCR word, a local index reads the actual current `memory.items` insertion order. Numeric keys use same-length digit buckets; nonnumeric keys use query length±2 buckets. At most five ordered lists are merged by insertion serial. The original category, `_gated`, numeric mismatch, fuzzy threshold, and Detection construction predicate remains authoritative and unchanged. An earlier eligible fuzzy match still beats a later exact match.

Query normalization, original-word allowlist calls, minimum query length 4, STOPWORDS, Unicode `str.isdigit`, equal numeric length/two mismatches, inclusive alpha length/score boundaries, low/negative confidence, scan/word order, duplicate words/timestamps, one-shot scans, every Detection field/default, conversion errors and pre-call mapping/count/threshold changes are covered at the complete active-module boundary. There is no exact shortcut, highest-score choice, forward recall/cache reuse, persistent cache, history cap, new dependency, threshold change, or merge/tail/contradiction change.

Concrete malformed mappings/keys/categories/counters/thresholds use original insertion traversal rather than dropping data or raising early. A plain-dict/string-data/int-counter/int-threshold domain receives the index; defaultdict/OrderedDict/custom mappings preserve behavior through fallback. Guards do not classify arbitrary Python hook purity. Mutation during lookup and side-effecting custom gate/category/allowlist objects are outside the acceleration claim; ordinary actual callers and pre-call edits are supported. Empty/no-eligible scans do not construct the index or eagerly consume scans.

Files changed: `openscrub.py`, `tests/test_reverse_recall_index.py`, `benchmark/reverse_recall.py`, `benchmark/README.md`, and `pyproject.toml` (include these controls/benchmark in sdist).

## Evidence identities and retention

The compact, self-contained handoff is [task113-evidence](task113-evidence/manifest.json), approximately 10.8 MB. It contains losslessly compressed complete JSON, all timing/warmup/output values and fixture inputs, source/fixture/package identities, relevant scripts/hooks/tests, logs, patches and build artifacts. No media, environment, installed tree or source export tree is copied there. Every gzip was decoded, hash/size checked against its original and reparsed as JSON; manifest entries retain compressed and uncompressed hashes/sizes.

| Identity | SHA-256 |
| --- | --- |
| Exact-base `openscrub.py` | `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7` |
| Initial candidate, before malformed-gate correction | `a98dbcbe139af76b7178a972470a53321acb80a7aaee1fa5d30a9623ac7870f5` |
| Final/native/installed `openscrub.py` | `5c97862c9d1ce6e40cd5a37af7e24430b3c8b0933a2ff68c108a6e8113f62d9e` |
| Final 40-contract test file | `ceb4adcef576903899727aad728f3f4520b910e3355b000dbf3b4a585165a118` |
| Both complete comparisons' benchmark | `2ca0008bb9e03a48df1fe95542ca8e13615f8abdf3cf67952e4410f7d12d5573` |

`source-manifest.json` verifies every tracked file against its Git blob: 113 exact-base files and 115 final-head files. `full-source-sha256.txt` binds the unchanged original suite and final source/tests/benchmark to the stable full run. `package-smoke.json` binds all six product modules across native, sdist, wheel and installed target, plus exact sdist test/benchmark/config bytes. Source assertions preceded base/native/floor/installed application execution. The initial candidate patch reconstructs the measured initial hash independently of the final correction.

## Cost attribution, fixture correction and timing protocol

The initial actual-base attribution used 500 ordinary scan records, 1000 words, 500 actual primary email detections, and 500 remembered strings (one repeated string for the repeated case). Each primary is accepted by actual `detect_phi`; only primary results populate PhiMemory, and benign words do not receive forward recall. The initial alleged unmatched word `pending` proved to be a STOPWORD. That valid **stopword-control** result is retained as `baseline-attribution.json.gz`, not unmatched evidence: reverse/merge/combination medians were 18.835/2.333/21.490 ms heterogeneous, 148.797/522.329/675.572 ms same-length, 1.051/1.436/2.465 ms repeated. A wrongly located global tracer initially counted zero; source-scoped corrected counts 116928/375250/500 are retained separately. No baseline timing was selectively repeated for that correction.

Both complete comparisons use literal `unmatched` for heterogeneous/repeated benign words, asserting normalized length>=4 and notSTOPWORDS **before every timed call**. Same-length benign words are deterministic random non-email letters exactly as long as the email keys. Actual primary matcher results, forward-recall absence and memory sizes are validated outside timing. Complete input scans and insertion-ordered memory/counters are retained, with literal seeds/settings and per-output digests. The lesson from P11B's late sparse-fixture correction was applied: these are detector-consistent ordinary record histories, not a sparse-history performance claim.

All cases use 500 scans at 1/3 s intervals, two words/scan, seed 83011+i (seed 83011 repeated), email categories, lenient 76, hold 1/3+.3, actual RapidFuzz, OpenCV threads 1 and normal enabled Python GC. Heterogeneous email local lengths span 4..80 (full key lengths 19..95, 77 buckets); same-length local parts are 24 (full keys 39); repeated memory size 1. Primary counts 500 in every case. Heterogeneous/repeated merge to one region under unchanged common-suffix/support behavior; same-length returns 500 regions. This is explicitly reflected in outputs and metadata.

Each boundary/case gets three warmups and five recorded alternating base/head samples, with fresh mutable fixtures prepared outside timing. **Reverse** includes dispatch, construction, bucket merge/order restoration and complete output creation. **Reverse plus merge** includes that reverse call and unchanged `merge_detections(raw+extra, hold, scans, fuzz)`. It excludes inference, decoding/scanning, scope filtering, backtracking, dense processing, other later run_scan steps, and report writing. It is not all finalization or end-to-end throughput. Every warmup and recorded full result, raw mutation, extra mutation, memory/count value and digest is retained and equal between full base/head modules. The fixture contains no ignored/zoned categories at this timed boundary; zone behavior is verified separately below.

The supervisor granted exclusive **agent-owned** workload slots for the initial and corrected complete matrices, with explicit release after all timing/instrumentation. The host was not globally reserved. All tracing/allocation measurements ran after all timing in each matrix. Five samples support reported medians only, not a p95/population estimate. No P11A/P11B program or large/default/4K/inference benchmark was rerun.

| Final corrected matrix (ms) | Reverse base → head | Reverse plus merge base → head |
| --- | --- | --- |
| Heterogeneous/unmatched |48.826 → 6.976 |51.924 → 9.248 |
| Same-length worst case |143.466 → 142.366 |665.409 → 665.070 |
| Repeated/early winner |1.128 → 1.332 |2.757 → 2.923 |

| Initial complete candidate matrix (ms), retained | Reverse base → head | Reverse plus merge base → head |
| --- | --- | --- |
| Heterogeneous/unmatched |49.238 → 7.070 |53.592 → 9.376 |
| Same-length worst case |146.477 → 148.952 |682.880 → 690.279 |
| Repeated/early winner |1.170 → 1.326 |2.856 → 2.808 |

The second complete matrix was necessary after a semantic compatibility correction, not to obtain a better sample. Initial source could skip an original malformed-gate exception for an impossible-length name. Three regression controls reproduced this failure; final guards choose original traversal. The ordinary dispatch change required the entire same matrix to be repeated, preserving both sets. There were no favorable-only reruns or later tuning.

## Work and retained allocation

| Case | Original candidate visits | Final candidate visits | Indexed entries/buckets | Live shallow index bytes | Traced reverse peak base → head bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Heterogeneous |366928 |7781 |500/77 |57624 |134513 → 150325 |
| Same length |375250 |375250 |500/1 |50560 |134520 → 145652 |
| Repeated |1000 |500 |1/1 |524 |134520 → 134720 |

Source-scoped tracing observes the unchanged actual predicate and 500/500/1 index-entry construction visits, separately from query visits. The final eligibility guard also inspects the ordinary counter values once (500/500/1 here); those checks are included in timing, but not mislabeled as candidate visits or omitted from total complexity. There is no meaningful reduction within a still-eligible same-length bucket.

The index retains O(M) key/category references and insertion serials plus bucket/list metadata until return; alpha query ordering adds at most five heap streams. Shallow `getsizeof` totals cover the local index tuple, dictionaries, lists, entry tuples and serial integer sizes. They exclude borrowed key/category string payloads, fixture/input/output records, and are not an allocator-complete owned-byte total (small serial integers can be shared; length keys are not separately charged). `tracemalloc` starts after fixture construction and reports current/peak allocations for actual reverse calls; final current bytes are 133760/134040 heterogeneous, 133784/133784 same-length and 133760/133760 repeated, base/head. Allocation reuse and shared objects make shallow live totals and traced allocation peaks different observations; subtracting them is not a process-memory bound. No RSS/memory-ceiling claim follows.

## Behavioral, integration and TDD evidence

`tests/test_reverse_recall_index.py` imports the complete active module, uses literal complete Detection records and never imports Git/old checkout or copies a miniature matcher. Its 40 contracts cover first eligible fuzzy priority across length buckets; category/gate rejection followed by later winner; two/three numeric mismatches and Unicode digits; alpha±2/±3 and lenient 72/76/custom inclusive score boundaries; remembered 3/query 4; normalization/original-word allowlist; unordered one-shot scans/duplicate observations; all metadata/defaults; fresh pre-call memory/count/threshold edits; mappings/defaultdict counters; malformed key/category/gate data and conversion failures.

The performance RED is the exact-base actual-module work/cost above, not a manufactured unit-dispatch failure. Compatibility characterizations passed on base before implementation. The later malformed-gate bug has an ordinary RED/GREEN cycle: `malformed-gate-red.log` reports three `DID NOT RAISE` failures against initial candidate; `malformed-gate-base.log` passes those three on the exact base; final `contracts-gate-green.log` passes 38 at that stage, then final 40 base contracts and 46 focused native/floor controls pass. This correction changed dispatch only, preserving old failure order rather than sanitizing errors.

One tiny **actual run_scan → reverse → merge → write_report** path uses 12 lossless 160×96 frames at 6 fps and six controlled OCR calls. Only `make_ocr` is replaced at the inference interface; decoding, primary matching, memory, reverse recall, filtering, merge and report serialization are real. First scan confirms two emails; later near-misses score below forward 82 and above reverse 76. An email zone accepts the left box and drops the right box. Observed stats: scans 6, raw_hits 7, regions 1, recalls 0, remembered 2, zone_dropped email 7. The test asserts both complete accepted and dropped Detection records, original text, t_end 2.3/last_seen 5/3, defaults and report enabled/zone_dropped flags plus all 12 offset/band rows. The exact base and final/installed/floor modules all pass the same literal integration expectations. `controlled-ocr-report.json` preserves one resulting report. This verifies controlled integration, not pretrained OCR/model inference, browser behavior or throughput.

## Verification, packaging and commands

No source/test edits followed the final stable full run. `commands.sh`, environment hooks and `build-package.sh` retain executed commands/settings. Important commands/results:

| Command/boundary | Result/log |
| --- | --- |
| Exact-base 40 contracts, expected source asserted |40 passed; `final-contracts-base40.log` |
| `python -m pytest -q tests/test_reverse_recall_index.py test_openscrub.py -k 'reverse or memory or merge_tail or dense_hold or mixed_dense'` |46 passed, 128 deselected; `focused-final.log` |
| Native `python -m pytest -q` |**174 passed in 56.94 s**; `full-native.log` |
| Same owning focused command, actual Python 3.9.25/native source |46 passed, 128 deselected; `floor39.log` |
| Offline sdist → wheel → target installation |Succeeded; `package-build.log`, artifacts/manifest |
| Installed wheel imports + sdist test file with `--import-mode=importlib` |40 passed; `installed-contracts.log` |
| Installed CLI `openscrub --help` / `openscrub-web --help` |Both exit 0; stdout hashes in `package-smoke.json` |
| Installed Flask test client `/`, `/api/jobs`, `/api/models/face`, `/api/model_status`, `/api/vault` |All 200, jobs empty; `package-smoke.json` |
| All parser defaults vs exact base |Equal; complete values in `package-smoke.json` |
| `git diff --cached --check`, commit, final clean status |Passed; commit 9d 88870 |

Prepared 3.12.16 uses OpenCV4.14.0/NumPy 2.5.5/RapidFuzz 3.14.6/pytest 9.2.0. Actual 3.9.25 uses OpenCV4.14.0/NumPy 2.0.2/RapidFuzz 3.13.0/pytest 8.4.2. Floor hooks were copied/retargeted to task 113 before collection; all models/profiles/jobs/settings/cache/temp remained task-local. Only cached YuNet was copied, with outward network/downloads disabled. No dependency/model downloads or environment mutation occurred.

Actual prepared 3.12 performed the offline build. Cached wheelhouse installed Hatch tooling into task-local build-tools using temporary bootstrap-PYTHONPATH pip; the bootstrap 3.14 Python was never run. No-isolation sdist build was followed by wheel build **from that extracted sdist**, then no-dependency target installation. Installed-only checks removed bootstrap and filtered pre-existing editable native paths only in task-local sitecustomize, without modifying the venv. Native/product/tests/benchmark/sdist/wheel/install byte identities and `Requires-Python: >=3.9` are asserted.

Artifacts: wheel SHA256 `88ea8a63ec690a81089df7d57e6f85b1f486cae7f390f27de2945e26fde45275`; sdist SHA256 `088bb0bc93e291232ff919875ec3ed7dc3a4c83d72fbde12a7e618e5d320c7ad`.

All preliminary failures and fixture corrections, including the initially invalid editable candidate import and unrelated no-backtrack/first-scan low-word fixture failure, are disclosed with retained logs in `failed-attempts.md`. They are not counted as successful verification or product RED evidence.

## Self-review and remaining limits

Self-review found and fixed the concrete malformed-gate exception issue before the stable full suite. The final diff has one small runtime owner, actual behavior controls, an offline full-module benchmark and justified sdist inclusions. It adds no general hook framework or unrelated runtime changes. Final source/test/benchmark identities match both the final matrix and package validation. The local commit is complete; no push, PR publication or external messages were performed.

The measured heterogeneous benefit supports this bounded adoption. Tiny/repeated histories can regress; same-length memories retain full candidate work and unchanged merge/tail work can dominate. Arbitrary side-effecting hooks/mid-call mutations, process RSS ceilings, real inference/model throughput, default settings, long/4K media, browser rendering and multi-platform results remain unverified. The actual controlled no-backtrack scan sanity issue found during fixture preparation is pre-existing and outside this reverse-only task. Fresh independent review is the supervisor's next step.
