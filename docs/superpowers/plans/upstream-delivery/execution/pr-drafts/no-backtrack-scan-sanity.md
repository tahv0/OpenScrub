# Fix first OCR sanity check when backtracking is disabled

With `--no-backtrack`, a first OCR result containing fewer than three words passes a missing image to Canny and crashes before returning a report. Reuse the existing thumbnail when present, or lazily construct the same half-resolution grayscale image inside that sanity check. Its warning, thresholds and backtracking setting remain intact.

Seven regression cases use real decoded video, Canny, scan and report output, with controlled OCR inference. They cover zero/one/two words, busy/flat frames, default backtracking, three initial words and later sparse results. Exact-base failures become passing complete-state/report checks.

Validation: 141 full tests; 28 owning checks each on native Python 3.12, actual Python 3.9 and the installed wheel. Offline sdist-to-wheel, source/test inclusion, parser defaults, CLI help and Flask test-client smoke pass. These synthetic Linux checks do not establish OCR-model quality or other platforms.

Base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`; head `17dfe5d575306dea395b680205038e606ad598a2`. Detailed results, failed setup attempts and limitations are in the [report](../evidence/delivery/task-115-report.md) and [independent review](../evidence/delivery/task-115-review.md).
