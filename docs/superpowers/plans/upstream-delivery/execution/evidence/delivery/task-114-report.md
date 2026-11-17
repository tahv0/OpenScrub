# Task114 / P11D — decline sorted-left merge discovery

**No adoption; no PR proposed.** The tested small stdlib index reduced final predicate visits but regressed complete merge time in every predeclared case. Its guards, prefix traversal, list maintenance and birth-order restoration erased the proposed benefit. Supervisor approved this disposition. The unique-history candidate-discovery cost remains unresolved; this closes this particular proposal, not all possible merge optimizations.

## Exact source and product disposition

- Native branch: `pr/merge-candidate-discovery`, base and final HEAD both `e21ebdf6e3ee46e6c65050dc956a9a3459152269`; final native `git status --short` and `git diff --stat <base>` empty. No product/runtime/test/package commit was made.
- Full base engine SHA256: `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`. All113 exact exported files were rechecked against the retained export manifest after the experiment.
- Disposable full candidate engine SHA256: `0d3c47ac3a6a30867c7678145275ee72cd5765d9674aaa016f754881e58d88ea`; patch SHA256 `bfd4f6cb4d057adb287a3496f64132655afc38b882557d2d1ca5bff8a7469d4b`. The complete actual modules are losslessly retained, alongside the patch/generator. The candidate was never copied into native product source.
- Original baseline/validation harness SHA256 `5ee7d18f9af4c30cc7b7f35cdbcafbdc37a6fa8b99ae44141b2f54e6c53ddf01` is retained unchanged as `benchmark/baseline_measure_merge.py`. Final comparison harness SHA256 `ab85aeb3e94ec21ea4f0402a02494120c4ce5966390b77978d2fa7c668b731c6` adds only separately executed work/profile/allocation collection. Timed invocation/fixture code was unchanged.

## What was evaluated

The disposable variation keeps stable time sort, original result/mergeable objects and complete authoritative predicates, contradiction and tail bodies. It partitions non-dense region entries by current ordinary string category in sorted `(left, birth, object)` lists. It bisects the inclusive left bound, reads current right bounds, restores descending birth order and updates placement when a union decreases the left endpoint. No text shortcuts, age limits, track/person keys or dependency were added.

A concrete prepass accepts exact Detection objects, distinct input references, ordinary finite ordered boxes/timestamps and ordinary categories; unsupported data/aliases use the original traversal. This is an experimental compatibility subset, not a generic callback-purity framework or proof for arbitrary Python mutation. Ordinary visual callbacks were not disabled by the candidate. Their actual source-frame integration was deliberately not reached after the cost gate failed. Existing malformed/unreached error behavior was checked in the bounded controls. The original traversal was preserved for the tested fallback data; untested exotic side effects are not certified.

Index cost is real: original `mergeable` still retains O(M) region references; category lists retain O(M) three-field tuples, a birth dictionary adds O(M) integer/id metadata, and the guard temporarily stores O(N) raw-object ids before releasing them. Each query can traverse an O(M) prefix, allocate O(C) references and sort C candidates in O(C log C); insertion/removal shifts O(M) references. This is not a general subquadratic bound or a memory ceiling. In measured fixtures insertion shifts occurred; left-update removals did not occur because duplicates reuse boxes. Mirrored union-growth controls exercised left updates for correctness, not timed update throughput.

## Controlled fixtures and validation

All eight cases use120 or480 scans at .5s intervals, a stated1280×720 frame extent, hold .8, bridge4 and actual RapidFuzz. Grid cases repeat48 fixed positions in four columns/twelve rows: x=25+300×column, y=20+55×row, width220/height28. The growing history does not widen the canvas. Colocated controls use the same single bounded box. Elapsed synthetic history is59.5 or239.5 seconds.

`mixed_grid` cycles actual built-in email/phone/MRN inputs; `email_grid` uses different seeded24-letter email local parts; `email_colocated` puts those distinct readings at one position; `repeated_colocated` repeats one email. **The merge input is supported controlled primary plus duplicate-recall-shaped records**,2N mutable Detection objects. It is not an actual reverse_pass result, video/OCR inference run, or actual run_scan fixture. Actual `detect_phi` produced exactly one asserted category/box/text per primary with no namer/models. Primary copies were duplicated to represent the observed primary+recall shape without benchmarking another owner.

Before timing, actual normalization/STOPWORDS/`PhiMemory.add`/gating/recall were checked for every primary. All distinct email pairs are below the full70 OR partial85 merge thresholds (480-email maxima63.64/69.23). Mixed numeric texts can fuzzy-match; no pairwise-nonmatching claim is made for phone/MRN. Both benign words `velvet`/`harbor` are length-eligible, outside STOPWORDS and return no actual forward recall; source-derived explicit reverse matching gates also reject them. **No actual reverse_pass was invoked**, so this latter check is limited predicate validation, not reverse-output equivalence. Full validation/recipes are retained with decoded fixture SHA256 `47ea381ff16aa7c5228664b3246609d32ddb54db6f991c5e30a378967b282da3`.

## Baseline attribution and complete comparison

Both exclusive slots were requested/granted with exact source/harness/fixture identities before clocks, then explicitly released after all instrumentation. The host outside this agent team was not reserved. Python3.12.16, OpenCV4.14.0, NumPy2.5.5, RapidFuzz3.14.6; normal GC throughout. Fresh Detection/scans copies are prepared outside the clock. Each complete actual module executes its full `merge_detections`; the boundary includes stable sort, construction/maintenance/order restoration, predicates, contradiction and tail. It excludes reverse_pass, dense smoothing, report serialization and inference. No total-video,4K/default-scan throughput claim is supported.

Baseline attribution preceded candidate timing. Initial base-only medians (120/480 scans) were mixed3.330/158.425ms, email-grid1.909/28.810ms, colocated26.138/411.564ms and repeated .355/1.445ms. Distinct480 histories had115,440 final predicate visits and115,920 tail-loop source-line events. Mixed480 additionally had573,352 contradiction scan-loop source-line events. Repeated480 had959 predicate visits and481 tail-loop events. These show costs at the actual unchanged owners, not inference/callback progressive slowdown.

Final comparison used three warmups per implementation/case and five recorded alternating base/head samples across **all eight** cases before any instrumentation. Every elapsed value/warmup is retained; no favorable subset or rerun was selected. Median milliseconds:

| Case | Exact base | Candidate | Change |
| --- | ---: | ---: | ---: |
| mixed_grid_120 | 3.211 | 4.105 | +27.8% |
| mixed_grid_480 | 158.479 | 162.808 | +2.7% |
| email_grid_120 | 1.785 | 2.757 | +54.4% |
| email_grid_480 | 26.820 | 37.257 | +38.9% |
| email_colocated_120 | 26.002 | 29.347 | +12.9% |
| email_colocated_480 | 403.227 | 453.836 | +12.6% |
| repeated_colocated_120 | 0.344 | 0.854 | +148.5% |
| repeated_colocated_480 | 1.349 | 3.309 | +145.3% |

All warmup/recorded outputs and caller-visible mutated input records were asserted equal, including result identities expressed as indices of the actual fresh input objects. Complete common snapshots plus the digest/equality assertion for every run losslessly bind all identical run outputs without repeating identical JSON for each sample. `summary.json` retains every recorded sample in ms; `comparison.json.gz` retains all ns samples/warmups, complete records, mutation arrays, identity indices/digests and source/instrumentation records.

Separate instrumentation after **all** timings confirms why fewer predicates did not yield a useful result:

| Case | Final predicate visits base→head | Prefix entries | Emitted/order elements | Inserts / shifted refs | Actual order restorations | Python peak bytes base→head |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mixed_grid_120 | 7,260 → 660 | 3,020 | 1,200 | 120 / 890 | 240 | 8,028 → 31,570 |
| mixed_grid_480 | 115,440 → 9,840 | 48,080 | 19,200 | 480 / 14,360 | 960 | 37,576 → 142,962 |
| email_grid_120 | 7,260 → 1,860 | 9,180 | 3,600 | 120 / 2,610 | 240 | 8,062 → 29,948 |
| email_grid_480 | 115,440 → 29,040 | 144,720 | 57,600 | 480 / 42,840 | 960 | 37,374 → 144,312 |
| email_colocated_120 | 7,260 → 7,260 | 14,400 | 14,400 | 120 / 0 | 240 | 8,178 → 31,484 |
| email_colocated_480 | 115,440 → 115,440 | 230,400 | 230,400 | 480 / 0 | 960 | 37,490 → 182,712 |
| repeated_colocated_120 | 239 → 239 | 239 | 239 | 1 / 0 | 240 | 5,926 → 28,840 |
| repeated_colocated_480 | 959 → 959 | 959 | 959 | 1 / 0 | 960 | 28,966 → 128,296 |

No fallback queries or removals occurred in this ordinary timing matrix. Post-timing cProfile supports the attribution: profiled mixed480 base contradiction work is about141.5ms of170.6ms cumulative merge; email-grid480 geometry calls fall115,440→29,040, while head restoration alone makes960 list.sort calls over57,600 key elements. Profile times carry profiling overhead and are **not** the uninstrumented timing samples. RapidFuzz extension work can remain in enclosing self time; no exact isolated fuzzy-time claim is made. Tracemalloc records Python allocations during merge with fresh inputs outside tracing; it is not RSS, native allocation accounting or a memory limit.

## Instrumentation correction, verification and limits

The raw sort-line counter also received lambda key source-line events because the key lambda is defined on the sort line. Its original `order_restorations` label therefore overcounts operations. Original raw data/logs remain unchanged. `benchmark/summarize.py` derives actual restorations as raw sort-line events minus emitted key elements and asserts independent agreement with cProfile list.sort calls:240 or960. Prefix entries, insertions, shifted references and predicate counts do not use that lambda line. This is a corrected derived summary, not a timing/instrumentation rerun or source/fixture change.

The stabilized40 full-module controls assert literal complete records, return identities and all input mutations for birth versus update priority, callback fall-through/arguments, tie/duplicate/unordered detections, exact12 slack and negatives, mirrored union growth, ratio70/partial85/substrings/empty/fuzz=None, hold/bridge/unlimited callback gaps, strict contradiction/duplicate/unordered scans and confidence, tail final union, dense metadata/direct entries, aliases, unhashable categories, and reached versus unreached malformed geometry. Final corrected focused runs: **base40passed, candidate40passed**, serial, distinct task114 basetemps, exact module/test identities and task-local hook paths. Test SHA256 `a5e6dadfdbeee1c1273e4d5d6b9e4f5203a126f6f2f607e2c2c3bb1d164f99f8`. These are bounded behavioral controls for a declined experiment, not exhaustive acceptance of the candidate.

The initial36 and pre-comparison40 exploratory checks disabled `baseline_isolation` via `PYTEST_PLUGINS=`; they were inadequately isolated and are not counted as isolated acceptance. They retained `OPENSCRUB_NO_AUTOFETCH=1`, exact source assertions, task-local cwd/basetemps and the sandbox/network restriction. The corrected40+40 runs used a task114-local copy of that hook with model/web retargeting and asserted engine/web import paths/hashes. Original logs remain. See `isolation-review.md` for actual protections and bounded source review.

Standalone validation/timing scripts did not use a task-retargeted pytest/sitecustomize hook: the pytest plugin environment is inert there. They asserted complete engine path/SHA before execution and used task114-only recipes/outputs with no-autofetch enabled. Inherited model/UV cache paths still named the prepared baseline and were unreached. Bounded source/call inspection found no relevant filesystem/network/settings/model path in the exercised engine import/fixture/merge functions; scripts never imported the web module. This supports exact-source controlled merge evidence, **not** a retroactive hook-isolation claim or broad user-data audit.

The performance RED is the retained exact-base work/cost evidence, as authorized by the brief. The early candidate had strict-degenerate eligibility/guard-set retention adjusted before comparison and four score/missing-box controls added before the final40 suite; its original source/logs are also retained. No test/product failure drove speculative runtime changes, and no product behavior change was committed. The only measurement labeling defect was the sort-line issue above; the only verification hygiene issue was corrected plugin setup. No timing was invalidated or repeated.

Because the measured adoption gate failed, **not reached/not claimed**: actual tiny run_scan/report accepted+zone-dropped integration, source-frame visual long-gap equivalence, full regression suite, Python3.9 checks, offline sdist→wheel, exact package inclusion and installed CLI/web/default checks. No P11A/B/C probes, browser changes, models/dependencies or user media were added or repeated. P11B integration remains a later separate decision.

Self-review checked the empty native product diff, exact-source/assertion chain, all eight regressions and costs, output/mutation/identity equality, honest O(N)/O(M)/O(C) retention and source-line correction. No independent reviewer has yet signed off; root will arrange fresh review of this no-adoption evidence. No new runtime checks are needed to justify declining this candidate.

Evidence: [task114-evidence](task114-evidence/), with executable measurement/generator/summary scripts, complete compressed actual modules/fixtures/results, tests/hooks, manifests, commands, original logs and coordination/isolation notes. Media, environments, installed/source-export trees and user data are excluded. Gzip artifacts were decoded/reparsed/byte-verified; sizes/hashes are in `summary.log` and the evidence manifest.
