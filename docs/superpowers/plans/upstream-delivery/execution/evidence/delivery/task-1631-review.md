# Task 1631 / P16C-G independent review

## SpecCompliance

**Issues found.** The primary geometry work and corrected source/coverage boundary match the accepted scope. One new metadata policy rejects a finite frame-count value that the previous renderer tolerated, despite the explicit restriction against adding progress/control policy (Important I1).

Reviewed exact base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` to head `7415e5a7526696a33f78a8c209bf062239a31d1c`, using the supplied 945-line diff once in four bounded, nonoverlapping chunks. Its three changed files match the report: `openscrub.py`, `tests/test_render_geometry.py`, and the sdist test inventory in `pyproject.toml`.

## Strengths

- Original source validation occurs before coverage/native acquisition in `run_render` (`openscrub.py:8559`) and the public SDR/HDR wrappers (`openscrub.py:4184`, `openscrub.py:4001`). The accepted boundary correction preserves the public signatures/defaults and lets checked coverage produce a legal rounded empty box before entering the private render bodies (`openscrub.py:4196`, `openscrub.py:4026`). It does not skip the detection or fabricate a substitute box.
- Shared frame geometry checks protect drift intermediates before the cap, translated boxes, effective padding and padded endpoints; local arithmetic trapping is limited to geometry/coverage. The SDR/HDR bodies both call that same calculation before painting (`openscrub.py:4327`, `openscrub.py:4119`). The local painter guards preserve the existing early empty-intersection returns, and do not inspect polygon/poly_box content ahead of P16B fallback (`openscrub.py:3282`, `openscrub.py:3784`).
- Coverage validates the original boxes and checks expanded endpoints before integer conversion, retaining existing ordinary arithmetic/rounding (`openscrub.py:3858`). Preflight traverses existing entries without a trajectory copy or frame expansion. The added ordinal maps store diagnostic identity, not validation results.
- Owning tests observe acquisition/coverage ordering, exercise actual tiny-frame SDR/preview paths, distinguish source-invalid boxes from derived empties, and test ordinary Python/NumPy containers and signed padding. The deliberate routing spy now targets the private body; the separate unchanged actual-render adapter observes exact paint coordinates rather than relying only on that spy (`tests/test_render_geometry.py:1`; `task1631-evidence/adapters/test_coverage_rounding.py:9`).
- The retained evidence is candid about chronology and ownership: original 48-case RED/GREEN, later scalar-wrap regression evidence, the initial rounded-coverage regression, and final-source gates are distinct. It makes no R/P/P06D/C01 cleanup/publication/complete-row-retention claim (`task-1631-report.md:21`, `task-1631-report.md:36`, `task-1631-report.md:63`).

## Issues

### Critical

None found.

### Important

**I1 — Added negative frame-count rejection is outside geometry scope and changes tolerated behavior.** `openscrub.py:3208` rejects `total < 0` together with unusable dimensions. A finite negative `CAP_PROP_FRAME_COUNT` already converts successfully to `int`; it does not make width, height, decoding, frame allocation or encoder setup unusable. In the actual render bodies, `total` is used only for progress callbacks and log text: HDR uses `max(total, idx)` for completion/logging (`openscrub.py:4165`, `openscrub.py:4167`, `openscrub.py:4171`); SDR protects its percentage divisor with `max(total, 1)` and otherwise passes the value to callbacks (`openscrub.py:4406`, `openscrub.py:4408`, `openscrub.py:4411`). The default progress callback accepts it without computation (`openscrub.py:3546`). The baseline metadata `int(...)` lines in the supplied diff did not reject this value. Thus a capture returning valid dimensions, readable frames and a finite negative count now fails before encoding solely because of a new count-sign policy. This conflicts with brief item 6 and the superseding control-policy boundary (`task-1631-brief.md:18`; `render-delivery-contract-research.md:237`). Remove the `total < 0` condition while retaining the dimension prerequisites and safe handling of already unusable conversions. A focused SDR/HDR metadata control with positive dimensions and a finite negative count should establish that the new geometry guard admits the same value as the baseline. No real-backend claim about how frequently such metadata occurs is needed for this scope/compatibility finding.

### Minor

None found.

## Checks and evidence

- Read the task brief, report and supplied review package, plus the accepted policy amendment and the owning rounded-coverage, scalar-wrap, fixture-seeding and listening-server adapters. No public OSS lookup was needed.
- Named outside-diff risk: a metadata guard might impose a policy unrelated to its mathematical consumer. The SDR/HDR diff hunks stop before the later `total` consumers, so I made one focused search for `total`/progress uses and read the small omitted progress/completion excerpts plus `Callbacks.progress`. This established I1; no broader renderer or repository crawl was performed.
- Retained initial owning logs show **48 failed** on baseline and **48 passed** after implementation (`task1631-evidence/runs/task1631-cf317cc67d7c44b6bff73f9a0a42675f/logs/command.log:1656`; `task1631-evidence/runs/task1631-9f04bb15f9584106b0bbd2a575380d55/logs/command.log:4`). The original test adapter is retained separately, hash `718f05f7239414a2579b9ac65090e7dc0dd53d06f95db68b07df04c5b827ed93`.
- Rounded-empty compatibility evidence shows baseline success for zero/positive padding, bddf016 rejection with `invalid cbox extents`, owning routing RED, and corrected focused GREEN: **2 passed**, **2 failed**, **2 failed**, then **111 passed**, respectively (`task1631-evidence/rounding-padded-baseline.log:6`, `rounding-padded-red.log:40`, `rounding-owning-red.log:40`, `split-focused-final-development.log:7`). The actual-render adapter asserts `(-pad, -pad, pad, pad)` painting coordinates. Its final actual Python 3.9 selection includes both rounded-coverage parameters. Scalar-wrap evidence retains the exact public-boundary baseline `DID NOT RAISE` and unchanged-adapter candidate success; this is regression evidence added after implementation, not additional test-first evidence (`numpy-wrap-red.log:11`, `model-seed-wrap-green.log:6`).
- Final retained logs establish **243 passed** with no deselection on actual Python 3.12.16 and **118 passed, 128 deselected** on actual Python 3.9.25. Their frozen preflight records select head 7415e5a and the same core hash (`task1631-evidence/final-full312.log:1`, `final-full312.log:9`, `final-floor39.log:1`, `final-floor39.log:7`). No warnings appeared in those two final test outputs.
- Read the final package record and commands: offline sdist build, wheel built from extracted sdist, no-index/no-deps installation, installed defaults/CLI, and actual listening HTTP (`task1631-evidence/final-package.log:1`, `final-package.log:329`, `final-package.log:330`, `final-package.log:332`). The server adapter starts the actual installed entry point, requests `/api/jobs` and `/`, then terminates/waits with a kill/wait fallback in `finally` (`task1631-evidence/listening_smoke.py:19`). This supports listening-server and adapter-cleanup claims; it is not production R evidence.
- Independently inspected retained artifact bytes without extracting or executing them: actual sdist and wheel sizes/hashes match the report; sdist entries match all five `source-final.json` pins; all six wheel runtime modules equal the selected native bytes. Native core hash is `fdabaea16f12be75b8410ed1be998f8866a0fea151ff9c0b904fea6950403926`. The retained signature record is consistent with the unchanged public signature/default lines in the diff (`task1631-evidence/signature-check.json:1`).
- No suite/build/server/product workload was rerun for this review. I1 follows from the new condition, baseline conversion and actual consumers; a new workload was unnecessary. No native/index/HEAD/branch/product mutation or publication occurred. This review report is the only authored review artifact.

## Limits

Complete post-render raw-row retention remains P06D/C01; comprehensive exception cleanup remains R; previous-output publication remains P. The disabled/additive-row case here establishes admission only. Later G/R composition must update the private bodies while retaining the validating public wrappers. Existing helper M1 extraction behavior is already deferred and is not a new product finding. Retained Linux/actual-interpreter evidence does not establish other platforms, performance, universal numeric behavior, OS/native isolation or arbitrary native cancellation.

## TaskQuality

**Needs fixes.** The geometry validation, boundary separation and retained final-source evidence are otherwise strong and appropriately scoped. Remove the new frame-count sign policy in I1 before accepting this candidate.
