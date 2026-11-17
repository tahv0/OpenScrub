# Task114 / P11D independent no-adoption review

SpecCompliance verdict: PASS for the evidence-backed no-adoption closure. Quality verdict: PASS. No Critical, Important, or Minor findings requiring correction were found within the reviewed scope. This verdict approves declining the disposable proposal; it does not certify that proposal for adoption.

The brief explicitly permits declining when maintenance or order-restoration costs erase useful gains (`task-114-brief.md:11`). The report and PR note do exactly that, retain the unresolved merge-history cost, and propose no runtime feature (`task-114-report.md:3`, `task-114-pr.md:3`). The supplied native proof package records base and final HEAD both as `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, with empty status/log/stat/diff output (`review-task114-no-adoption.diff:1`). An empty commit is neither necessary nor appropriate for this disposition. Native state was not independently rerun during this review, as instructed.

## Evidence checked

Read the brief, report, PR note, native proof package, evidence README/manifest, experimental patch, full measurement harness, summary derivation, behavioral controls, hook, command record, coordination record, and isolation disclosure. Decoded the retained full modules and inspected the engine import boundary and the relevant fixture/memory/merge code. This was a bounded review of experimental validity and closure quality, not a merge-ready review of discarded product code.

Read-only artifact validation independently confirmed:

- All 32 payload files match their manifest byte counts and SHA256 values (1,038,659 bytes total). All six compressed payloads match their decoded byte counts and hashes; compressed JSON reparses successfully.
- The retained patch is exactly the unified diff between the complete retained base and candidate modules. Their hashes match the report. Source-loading, fixture, validation, fresh-input, and timed-run functions are AST-identical between the original baseline harness and the final harness.
- All eight recipes match their validation, baseline, and comparison hashes. Every detection box fits the declared 1280×720 frame. Grid histories reuse 48 positions and colocated cases use one position. The scripts and report consistently label the 2N records as controlled primary plus duplicate-recall-shaped inputs, not actual reverse-pass output (`benchmark/measure_merge.py:31`, `task-114-report.md:24`).
- Each comparison case retains three warmups and five recorded samples per implementation, with the declared alternating recorded order. Independently recomputed medians match the retained summaries and the report's rounded table. Every warmup/sample digest binds the retained complete output snapshot; base and candidate snapshots, including all 12 Detection fields, all input mutations, and result-input indices, agree. The initial baseline snapshots also agree.

| Case | Base median ms | Candidate median ms | Regression |
| --- | ---: | ---: | ---: |
| mixed_grid_120 | 3.211075 | 4.104533 | 27.824% |
| mixed_grid_480 | 158.478810 | 162.807943 | 2.732% |
| email_grid_120 | 1.785257 | 2.756725 | 54.416% |
| email_grid_480 | 26.820324 | 37.256998 | 38.913% |
| email_colocated_120 | 26.001917 | 29.346649 | 12.863% |
| email_colocated_480 | 403.226823 | 453.835705 | 12.551% |
| repeated_colocated_120 | 0.343830 | 0.854418 | 148.500% |
| repeated_colocated_480 | 1.348847 | 3.309365 | 145.348% |

## Measurement and compatibility assessment

Fresh mutable fixtures are prepared before the clock. The timed operation calls the complete actual `merge_detections`, including its stable sort, candidate guards, index construction/maintenance, prefix traversal, order restoration, authoritative predicates, contradiction checks, and tail traversal (`benchmark/measure_merge.py:106`). Output serialization and identity capture happen after the clock. The complete timing matrix finishes before tracing, profiling, or allocation collection (`benchmark/measure_merge.py:182`). This is a suitable boundary for the brief's total merge-cost gate; it supports no reverse-pass, inference, dense-smoothing, serialization, or video-throughput conclusion.

The measured reduction in predicate visits does not establish a benefit: email_grid_480 falls from 115,440 to 29,040 visits while complete merge time rises 38.913%. Raw index-work records support the report's prefix, emitted-element, insertion, and shift figures. All eight retained Python peak-allocation measurements are larger for the candidate. The report correctly distinguishes those measurements from RSS and native allocations, and discloses that timed fixtures did not exercise left-update removals (`task-114-report.md:18`, `task-114-report.md:62`).

The original sort-line counter includes lambda-key events. Independently subtracting emitted key elements yields 240 or 960 sort operations in every case and agrees with retained cProfile `list.sort` call counts and the corrected summary (`benchmark/summarize.py:12`). The raw evidence remains intact, and the report prominently explains the correction (`task-114-report.md:66`).

The experimental patch retains the authoritative matching, contradiction, and tail bodies and uses birth ordering after conservative horizontal filtering. The tests use the actual complete module and literal complete records with identity/mutation assertions, rather than a miniature matcher (`tests/test_merge_candidate_index.py:6`, `tests/test_merge_candidate_index.py:17`). Their bounded controls address the brief's winner/order, geometry, fuzzy boundaries, gap callback, dense, alias, and malformed-input concerns. The corrected focused logs retain 40 passing controls for each module. Those logs and controls are evidence for this experiment, not exhaustive certification of arbitrary callback side effects or actual source-frame visual behavior.

## Isolation and limits

The early exploratory runs disabled the prepared pytest isolation plugin. That was a process defect; it is explicitly disclosed and those runs are not counted as isolated acceptance (`isolation-review.md:3`, `task-114-report.md:70`). The corrected serial command record selects task-local hooks and exact asserted modules; retained logs show 40 passes each (`commands.sh:28`). Review of the hook and test loader supports the stated source-selection protections.

Standalone validation and timing did not use a retargeted pytest/sitecustomize hook. Their exact module assertions, fixed task-local fixture/output paths, and bounded in-memory product boundary support controlled merge evidence. Inspection found no relevant model, media, settings, filesystem, or network calls in the exercised product paths. This does not prove third-party imports side-effect-free, establish a runtime network audit, or verify untouched user data. The report discloses inherited, unreached cache/model paths and avoids a retroactive hook-isolation claim (`isolation-review.md:7`, `isolation-review.md:9`, `task-114-report.md:72`). These limits do not require adopting or rerunning a proposal whose measured cost gate failed.

Historical execution, exclusive-slot enforcement, source-export rechecks, native state, and absence of all external side effects cannot be independently reconstructed solely from retained artifacts. Their documentary claims were reviewed for consistency. No runtime, suite, measurement, model, install, Git operation, or external-state audit was performed for this review.

The actual run_scan/report, source-frame visual long-gap, full-suite, Python3.9, packaging, and installed CLI/web gates were conditional on a successful measured gate. They remain explicitly **not reached and not claimed** (`task-114-report.md:76`, `task-114-pr.md:7`). Requiring them for this declined experiment would misapply the brief. Preserve the no-adoption outcome and the open residual-cost question; no follow-on implementation is requested by this review.
