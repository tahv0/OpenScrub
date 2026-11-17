# Task 115 / N12 independent review

**Spec Compliance: PASS.** The candidate implements the requested narrow repair and supplies the required controlled pipeline coverage and retained verification evidence.

**Task Quality: PASS with one minor test-assertion nit.** No Critical or Important finding. The nit below does not block integration.

Reviewed exact base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` to candidate `17dfe5d575306dea395b680205038e606ad598a2` using the supplied commit/stat/diff package, brief, report, research handoff and retained evidence. I did not rerun Git inspection, suites, benchmarks or product execution, and made no product/native/ref changes.

## Strengths and compliance

- The repair stays inside the existing first-OCR sanity owner. `openscrub.py:8029` retains `ocr is not None`, `n_scans == 0` and `len(words) < 3`. `openscrub.py:8033` reuses `small`; the fallback at `openscrub.py:8035` computes only a local grayscale thumbnail, only when that guard fires and `small` is absent. It never assigns the fallback to `small`, changes `bt_on`, or populates tracking buffers. The existing enabled-backtracking path therefore continues using its original thumbnail.
- Canny remains 60/180 at `openscrub.py:8038`, the comparison remains strictly greater than `.02` at `openscrub.py:8039`, and the existing warning text and ordinary flow remain intact. There is no broad exception handling or warning suppression. The diff contains no parser, Detection/report serialization, OCR inference, decoder or cleanup change and introduces no Python-floor-incompatible syntax or dependency.
- The tests exercise real FFV1 encoding and byte-identical decoding (`tests/test_first_scan_sanity.py:34`, `tests/test_first_scan_sanity.py:46`), real Canny (`tests/test_first_scan_sanity.py:52`), production `run_scan` (`tests/test_first_scan_sanity.py:78`) and `write_report` (`tests/test_first_scan_sanity.py:83`). Only `make_ocr` is controlled at its ordinary interface (`tests/test_first_scan_sanity.py:64`). The email reaches real primary matching and finalization.
- Literal complete state and report expectations cover all Detection fields, tracking IDs, raw/merged counts, audio/dropped lists, render state, provenance and settings (`tests/test_first_scan_sanity.py:91`, `tests/test_first_scan_sanity.py:97`, `tests/test_first_scan_sanity.py:106`, `tests/test_first_scan_sanity.py:117`). Warning output is captured and asserted rather than left as unexplained QA output.
- Counts 0/1/2 exercise the disabled-backtracking trigger (`tests/test_first_scan_sanity.py:151`). The independent busy/flat Canny measurement at `tests/test_first_scan_sanity.py:49` establishes opposite sides of the actual warning decision; flat, default-backtracking, first-three-word and later-sparse controls appear at `tests/test_first_scan_sanity.py:160`, `tests/test_first_scan_sanity.py:168` and `tests/test_first_scan_sanity.py:176`. The retained measured densities are 0.35833333333333334 and 0.0, not a claim to measure equality at exactly 2%.
- The only packaging addition is the requested new test's sdist inclusion (`pyproject.toml:119`). No root helper, benchmark, custom model or unrelated refactor appears in the three-file patch.

## Findings

**Critical:** none.

**Important:** none.

**Minor — the Detection-order coverage comment overstates its assertion.** `tests/test_first_scan_sanity.py:105` says the following assertions pin fields “including order,” but the per-Detection comparisons at `tests/test_first_scan_sanity.py:97` and `tests/test_first_scan_sanity.py:106` compare dictionaries, whose equality ignores key order. `tests/test_first_scan_sanity.py:114` explicitly checks only the top-level report key order. A reordered Detection record would still pass these comparisons. If per-record order is intended to be pinned, add an explicit key-list assertion; otherwise narrow the comment. This is a test precision nit: the production patch does not touch Detection serialization or its order.

## Evidence assessed

The retained exact-base RED records three failures at the original Canny-density boundary (`base/openscrub.py:8034`) for counts 0/1/2. The earlier Task 113 prototype failure is correctly kept separate. The exact-base unaffected controls show three passes (`task115-evidence/exact-base-controls.log:3`). Final evidence records seven new tests, native owning 28, a valid full discovered 141 (`task115-evidence/full-native.log:4`), actual Python 3.9 owning 28 (`task115-evidence/floor39.log:3`) and installed owning 28 (`task115-evidence/installed-owning.log:3`). The initial shared-basetemp run is explicitly invalidated rather than counted as a pass (`task115-evidence/failed-attempts.md:5`).

The package smoke compares native/sdist/wheel/installed bytes, checks `Requires-Python >=3.9`, compares full parser defaults to exact base, runs both installed CLI help commands and uses an actual Flask test client (`task115-evidence/package-smoke.py:13`, `task115-evidence/package-smoke.py:22`, `task115-evidence/package-smoke.py:25`, `task115-evidence/package-smoke.py:29`, `task115-evidence/package-smoke.py:34`). Recorded defaults preserve `no_backtrack=false` (`task115-evidence/package-smoke.json:97`). I independently matched the retained base, installed runtime, extracted test/pyproject and both archive hashes to their recorded identities, and verified all 23 entries in the compact evidence checksum manifest.

## Focused outside-diff check and limits

The concrete outside-diff question was whether the lazy fallback preserves thumbnail semantics. I read only the exact-base initialization/current-frame thumbnail and OCR owner context: `BT_SCALE=.5` and `bt_on` at base `openscrub.py:7523`, original grayscale/resize at base `openscrub.py:7644`, and scan use at base `openscrub.py:7861`. The fallback uses that same conversion, resize signature and scale. A bounded search in the intervening current-frame owner showed no reassignment of `frame` or mutation of `small`; no broader scan audit or focused execution was needed.

This review cannot independently establish cross-task state, earlier adoption/publication decisions, original-checkout/user-data history, or live branch/worktree cleanliness from the supplied patch. Retained execution covers prepared Linux Python 3.12 and focused Python 3.9 with OpenCV 4.14, synthetic lossless media and controlled OCR inference. It does not establish other platforms/codecs/OpenCV versions, real OCR-model quality, prevalence, throughput, browser behavior, bound-port hosting or current external/live state. Those are limits, not unfulfilled requirements of this repair.
