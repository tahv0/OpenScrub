# Retained execution evidence

These local planning records preserve synthetic research, completed-task reports, focused review findings and reproducible verification material. They are supporting documentation for separate PRs, not an umbrella code contribution or a claim that every planned task has shipped. Product commits and review status are listed in the [execution record](../status.md).

| Evidence | What it establishes |
| --- | --- |
| [Report baseline](research/report-baseline-research/README.md) / [transaction inventory](research/report-transaction-research.md) | Actual-route interrupted writes, lost sparse edits, replay and roundtrip loss; proposed ownership boundaries remain distinct from passing implementation evidence. |
| [Thumbnail baseline](research/thumbnail-baseline-research.md) | Warm-hit parse avoidance, repeated cold work and visibly stale crops after report/source changes. |
| [Review scheduling](research/review-scheduling-baseline-research.md) | Actual 1k/10k eager cards/requests, scroll and job-switch ordering, and reuse of P07a draft ownership. |
| [Scan history](research/scan-history-baseline-research.md) | Removed preview-cache donor closure and three distinct final-aggregation work-count candidates; controlled OCR input, no inference-throughput claim. |
| [Scan-option input](research/options-input-baseline-research.md) | Malformed/non-object options across actual upload/server-path routes, accepted controls and complete synthetic cleanup. |
| [HDR decoder cleanup](research/hdr-decoder-cleanup-baseline-research.md) | Actual cancellation/write-error pipe lifetime with retained exceptions, reaped children and successful HDR frame/tag controls. |
| [Live-preview baseline](research/live-preview-baseline-research.md) | Torn responses and path-stat/open length races through actual Cheroot. |
| [Editor resize](research/editor-resize-baseline-research.md) / [frame identity](research/frame-identity-baseline-research.md) | Separate display/pointer alignment and source-sample mismatches; no long-video speed claim. |
| [Mask fidelity](research/mask-fidelity-research.md) | HDR chroma coverage and invalid-polygon cases, with separate rendering/output follow-ups. |
| [OpenCV compatibility](research/opencv-compat-research.md) / [installer scope](research/opencv-install-scope-research.md) | Matched fallback defect plus primary package metadata; no product compatibility pin or optional-stack runtime acceptance yet. |
| [Python 3.9 environment](research/python39-verification-setup.md) | Reusable isolated floor environment and limited smoke/build evidence; full application-floor acceptance remains separate. |
| [Save As](delivery/task-2-report.md) | Accepted-byte progress, real HTTP/OPFS behavior and browser/platform limits. |
| [Tracker regression](delivery/task-90-report.md) | Nonvacuous identity-protection regression with a failing mutation control. |
| [Atomic reports](delivery/task-61-report.md) / [complete roundtrip](delivery/task-64-report.md) | Complete report publication and preservation; independent concurrency work follows. |
| [Browser save snapshots](delivery/task-71-report.md) / [audio fix review](delivery/task-71-fix1-review.md) | Pending/current draft ownership and the narrow reviewed audio correction. |
| [Combined report prerequisites](delivery/task-620-report.md) | Reviewed prerequisite assembly, full combined suite and actual save/render/reopen scenario. |
| [Job file lifetimes](delivery/task-621-report.md) / [fix review](delivery/task-621-fix1-review.md) | Store/job/selected-source ownership, actual WSGI close and allowlist refusal behavior, with initial and amended-head verification distinguished. |
| [Dense smoothing](dense-smoothing/task-111-report.md) | Full-module before/after measurements and exact output comparisons, with retained fixture recipes. |

The [manifest](retained-manifest.json) records hashes and sizes of the retained files. Report prose and raw results are retained; relative documentation links are adjusted for this location. Raw logs may retain original whitespace and failed harness/setup invocations. Those failures are explained in the reports rather than removed from the evidence.

Scripts retain their original temporary paths and pinned-source assumptions. Reproduction may require recreating the isolated environment or adapting those paths; this archive is not a new application runtime or dependency bundle. Environments, model binaries, personal data, generated videos and large media are excluded. Absolute `/tmp` paths identify the original local execution, while the adjacent retained scripts/results provide the durable record.

Each upstream PR should carry only its relevant recipe, concise results and required regression tests. Before publication, replace scratch-only evidence references in that PR with its attached or committed material. No external publication is recorded here.
