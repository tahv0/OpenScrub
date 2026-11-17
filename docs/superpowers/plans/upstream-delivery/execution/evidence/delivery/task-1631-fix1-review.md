# Task 1631 fix round 1 — scoped re-review

## Finding Verdicts

- **I1 — Added negative frame-count rejection is outside geometry scope and changes tolerated behavior — ADDRESSED.** `openscrub.py:3208` now requires only positive usable dimensions; removing `or total < 0` preserves finite negative counts unchanged. The surrounding finite numeric checks, integer conversion, capture release on metadata failure and return values remain unchanged. The runtime diff contains exactly this condition removal, with no new normalization or progress policy.
- **Owning coverage is appropriate.** `tests/test_render_geometry.py:295` exercises both public SDR/HDR wrappers with count 1 and -1 and expects a distinct marker at the next native acquisition boundary. The HDR case also observes metadata-capture release and the dimension-derived decoder buffer size. `tests/test_render_geometry.py:323` preserves rejection/release checks for unusable dimensions and nonfinite counts before native acquisition. Deliberately interrupted SDR cleanup is explicitly harness-owned.

## New Breakage in the Fix Diff

None found. The one-condition runtime correction and 20 added parametrized metadata cases address I1 without changing unrelated geometry, public signatures, coverage rounding, painting, report behavior or resource/publication ownership. The added tests assert public-boundary behavior rather than merely calling the metadata helper.

## Checks and Evidence

- Reviewed the supplied fix package once, in full: `7415e5a7526696a33f78a8c209bf062239a31d1c` → `83af23b5fd3c5922d0d476ba2a6ae21a3598ced2`, one commit, two files, 61 insertions/one deletion. Read the fix report and retained covering outputs. No Git diff was regenerated and no unrelated code was re-reviewed.
- Retained owning RED is specific: **2 failed, 18 passed, 109 deselected**. Both count -1 cases fail in `_geometry_metadata` with the old sign rejection; positive-count and unusable-metadata controls pass (`task1631-fix1-evidence/red312.log:7`, `red312.log:18`, `red312.log:32`). The guarded active source hash is the prior `fdabaea16f12be75b8410ed1be998f8866a0fea151ff9c0b904fea6950403926` (`red312.log:4`).
- Confirmed the retained RED runtime configuration and all GREEN/final runtime configurations pin the identical test hash, `c62297f0dd3aacc4124b9f6bbcfd9308696224b765fcdb6ff63a6f8edc8eee00`. Retained `owning-tests.py` bytes equal the selected native test file. Development GREEN is **129 passed** (`task1631-fix1-evidence/green-development312.log:7`).
- Frozen final records select exact head 83af23b and actual Python **3.12.16** / **3.9.25**, each with **129 passed**, no deselection and no warning/failure output (`task1631-fix1-evidence/final312.log:1`, `final312.log:4`, `final312.log:7`; `final39.log:1`, `final39.log:4`, `final39.log:7`). Both execute core hash `870c217e517e55b812158768c96f2e85c77e41176c625cd4acca83c3afe6e06f`.
- Read the complete retained package output, including the extracted-source wheel command, offline/no-deps installation, installed identity/default and CLI success, then actual listening HTTP and owned-server reaping (`task1631-fix1-evidence/package.log:10`, `package.log:18`, `package.log:27`, `package.log:325`, `package.log:329`, `package.log:330`). Installed children select the same final core bytes (`package.log:26`, `package.log:31`, `package.log:328`).
- Independently inspected retained artifact bytes, without extraction/execution: final native pins match `source-final.json`; the 529486-byte sdist and 435680-byte wheel match their recorded SHA-256 values; pinned source/test entries in the sdist match, and all six runtime modules in the wheel equal the selected native bytes (`task1631-fix1-evidence/package.log:332`). Helper identity records match the previous adoption records, and the copied listener/fixture adapters are byte-identical to their prior evidence versions.
- No tests, package build, server or other product workload was rerun. No fix-specific doubt remained that required execution. No source/index/HEAD/branch mutation, subagent dispatch or publication occurred; this report is the only authored artifact of the re-review.

## Out-of-Scope Observations

None. Comprehensive exceptional cleanup remains R; previous-output publication remains P; complete disabled/additive post-render raw-row retention remains P06D/C01. D01 adoption closure remains supervisor-owned. The metadata tests establish controlled public-boundary admission, not the prevalence or behavior of real backends returning negative counts.

## Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.

**SpecCompliance:** Compliant for the accepted Task1631 scope after I1 correction.

**TaskQuality:** Approved, scoped to exact head `83af23b5fd3c5922d0d476ba2a6ae21a3598ced2` and the prior task review plus this fix review. The previous 243-test full-suite evidence remains tied to 7415e5a; it is not relabeled as an 83af23b run. The final-byte targeted/interpreter/package evidence supports this one-condition correction. Existing platform, performance, native/cooperative-isolation and R/P/P06D/C01 limits remain unchanged.
