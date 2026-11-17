# Fix first OCR sanity check when backtracking is disabled

With `--no-backtrack`, a first OCR scan returning fewer than three words passed a missing tracking thumbnail to Canny and crashed before returning its review/report state. Reuse the thumbnail when present, or lazily derive the same half-resolution grayscale image locally for that first sanity check. The intended warning, edge thresholds, parser/defaults and disabled backtracking remain intact.

Add seven real decoded-video scan/report regression cases, controlling only OCR inference: first counts 0/1/2, a flat-frame control, default backtracking, initial three words and a later sparse scan. Assert complete returned state and report records/settings, including a primary email. Include the test file in the sdist.

Validated against exact base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`; local head `17dfe5d575306dea395b680205038e606ad598a2`:

- Exact-base RED: all three low-word-count cases fail at the actual Canny boundary; unchanged default/three-word controls pass3.
- Final targeted 7; owning 28; normal full discovered suite 141 passed on Python 3.12.16.
- Actual Python 3.9.25 owning controls 28 passed.
- Offline sdist→extracted-sdist wheel→isolated installation; installed owning controls 28 passed, exact package inclusion/source identity, Requires-Python>=3.9 and unchanged full parser defaults verified.
- Both installed CLI help commands and five actual Flask test-client routes passed. No browser/bound-port claim.

The busy/flat sanity images measured 35.8333%/0% edge density against the unchanged strict 2% warning threshold. New regressions use synthetic lossless media and controlled OCR inference; they do not measure OCR quality or throughput. Preliminary fixture/isolation mistakes and one invalid shared-basetemp full run are retained in the task report/evidence; a sequential rerun supplied the valid 141-pass result. No publication or adoption performed.
