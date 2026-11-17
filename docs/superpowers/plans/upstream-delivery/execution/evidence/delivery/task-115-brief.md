## Task 115: make the existing low-word-count sanity check independent of backtracking

### Global constraints and exact base

Preserve Python>=3.9, upstream parser/defaults, report/Detection fields/order, OCR and warning thresholds, backtracking disabled state and existing normal decoding/cleanup. No custom models/training/workbench, dependency, broad image-validation/refactor, new root helper, original-checkout/user-data change, publication or nested agents. New tests under tests/; synthetic media and prepared offline tools only.

Supervisor creates pr/no-backtrack-scan-sanity from exact e21ebdf6e3ee46e6c65050dc956a9a3459152269 after Task113 review. Read first-scan-sanity-research.md and its retained task113-evidence/contract-integration-prototype.log. The observed failure was on an initial reverse-index prototype before reverse finalization; base applicability is source-confirmed, not an executed exact-base RED yet. Do not include Task113 indexing/tests/benchmark or repeat its timings. Source handoff anchors are exact-base6936–6938,7519–7524,7644–7645,7862–7868,8029–8040.

### What, why and when

Ordinary --no-backtrack leaves small=None, while the first processed OCR result with fewer than3 words feeds small into Canny and fails before returning a report. Repair this separate generic crash before further optional/performance work. Default backtracking already supplies the image; disabling backtracking must not disable the intended sanity warning or enable tracking work.

1. Establish actual exact-base RED using full run_scan and write_report, real lossless tiny video decoding/actual Canny/primary detection, controlling only make_ocr at its existing inference interface. Parameterize first processed OCR word counts0/1/2 on edge-rich frames; retain the exact failure boundary. Do not mock Canny or preinitialize small in the test.
2. Change only the existing first-scan/low-word-count sanity owner: reuse small when available, otherwise lazily derive a local half-resolution grayscale sanity image from the already decoded current frame using existing BT_SCALE. Do not fill/enable backtracking buffers or compute an extra image on every frame. Keep the original OCR-present/n_scans==0/len(words)<3 guard, Canny60/180, strict edge density>.02 and existing warning text/flow. No broad exception suppression or warning removal.
3. Complete actual scan/report cases for0/1/2 words and at least one real primary email with literal complete returned/report expectations. Independently verify the fixture's edge density meets the intended warning/non-warning boundary. Add edge-free low-word-count control, default enabled-backtracking control, disabled-backtracking first3word control, and later low-word-count after initial3word control. Capture/assert deliberate warning output so QA remains clear. Preserve all existing report metadata/order/enabled choices and resource release; no OCR-model quality or throughput claim.
4. Keep production diff small/local; place tests in tests/test_first_scan_sanity.py and add only required test-discovery/sdist inclusion. No benchmark or new private module is justified. If the proposed local repair exposes a supported-input contradiction, report the concrete case before broadening.

### Verification and delivery

After targeted RED→GREEN and source/tests stabilize, run owning scan/reverse controls and one normal full discovered suite. Use actual prepared Python3.9 active-source tests; offline sdist→wheel, exact changed-source/test inclusion, installed CLI/web/default parser smoke and installed owning controls. Actual installed Flask test-client smoke is sufficient for this unchanged interface; do not claim bound-port/browser coverage. Reuse prepared isolated environments with task-specific hooks under /tmp/openscrub-task115, assert import source before each base/native/floor/installed run, use cached build tools and no new models/dependencies. Current editable-path and task-temp-root isolation lessons apply; never alter the prepared venv.

Self-review and commit. Write task-115-report.md/task-115-pr.md with exact base/head, ordinary trigger, measured synthetic warning boundary, unchanged defaults/backtracking, actual full/floor/package counts/source identities, failed attempts and platform/inference limits. Native/Git edits may use existing authorized escalation. No publication or nested agents.
