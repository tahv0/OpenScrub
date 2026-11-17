### Finding Verdicts

- **Runtime/wheel disagreement receives a normal-wheel repair command** — **ADDRESSED**. `openscrub_internal/opencv_compat.py:151–155` now requires a parsed runtime version, a sole normal-wheel distribution, and equal runtime/wheel release tuples before issuing unsupported/broken reinstall advice. Both mismatch directions therefore fall through to ownership reconciliation. The same guard conservatively excludes unknown/missing runtime evidence without changing unsupported-policy assessment or the separate fresh-missing install branch.
- **Regression and positive-control coverage** — **ADDRESSED**. `tests/test_opencv_compat.py:201` covers both disagreement directions plus unknown/unavailable runtime evidence, asserting no force reinstall and visible reconciliation. The positive matrix at `:212` retains deliberate repair for agreeing unsupported normal5 and agreeing normal4 with missing API/XML, construction failure or an empty classifier. `tests/test_install_opencv_compat.py:140` checks both disagreement directions through actual installer/setup formatting and asserts reconciliation, unsupported information and zero pip calls.

### New Breakage in the Fix Diff

- None found. The production change is confined to repair-hint eligibility (`openscrub_internal/opencv_compat.py:143–162`); it preserves the existing healthy early return, selected-interpreter command formatting, fresh-missing advice, and nonmutating behavior. The stricter treatment of unavailable runtime evidence is explicit in the fix brief/report and safely retains reconciliation guidance rather than inferring ownership.

### Checks and Evidence Limits

- Read the original task brief, fix brief, appended fix report and packaged `a4f064f1b12cb0a22e5090d7fddfa3fc6055b5d7..a10e485962571a566f99225541735ab1ada1f4c0` diff. The package contains only the helper guard and the two compatibility test files; no untouched product code was re-reviewed.
- Existing `/tmp/openscrub-task91/fix1/red.txt` names all eight expected helper/consumer mismatch failures and reports `8 failed in 0.10s`. Existing `focused-312.txt` and `focused-39.txt` show clean `92 passed` results. The report supplies the covering test-file commands; the added assertions match the corrected guard.
- Existing `build-sdist.txt` and `build-wheel.txt` record successful refreshed builds. `package-updater.txt` records unchanged candidate/source/built metadata, exact shipped helper bytes and preserved updater/provider behavior. Both installed-smoke summaries report exact installed-helper/source-byte equality and empty network-event lists. I read these recorded outcomes; I did not rebuild, reinstall or independently replay their validation scripts.
- No new test execution was warranted by the scoped diff. No suites, resolver work or earlier OpenCV4/5 comparison were repeated. The original 213-test full run remains evidence for the original head only; this review does not claim a fresh full-suite or native Windows/macOS/frozen/container/GPU pass.

### Out-of-Scope Observations

- None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.

**Scoped spec compliance:** Approved. **Scoped task quality:** Approved.
