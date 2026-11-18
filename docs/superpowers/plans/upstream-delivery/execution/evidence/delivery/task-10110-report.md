# Task 10110 — portable optional media evidence

Candidate only, ready for fresh independent full-task review. Nothing pushed, published, merged, or adopted into the user's working version.

Branch `pr/portable-media-tests`; BASE `6fde5ad60c6d78d69dbbd8e049a9196f15e4095f`; frozen HEAD `d3d02770b8a42575236b11309b5a334170f7ec89`. Source: `.superpowers/sdd/README/worktrees/plate-text-matching`. The physical checkout was reused; the optional matcher branch/ref remains `3547f82c027323dba8e69e8aef7be62c88438d8b`. All 162 baseline refs remain present and 161 unrelated refs are unchanged; only the task ref advanced. Initial source audit matched all 132 selected-base files. Final audit matches all 130 unaffected original files, with 134 total files and the same ten runtime modules. No optional matcher modules, runtime files, package settings, defaults, schemas, media fixtures, or shared verification tooling changed.

`tests/artifact_support.py` is a ten-line stdlib helper: nonempty `VERIFY_RUN` selects `<value>/logs`; missing or empty selects `tmp_path/artifacts`; it creates parents idempotently and lets filesystem errors propagate. The only consumers changed are the two exact-media write sites and one strict-route write site. Two owners acquire pytest's existing `tmp_path`; the coarse-timebase owner already had it. The now-unused local `os` import in strict routes was removed. All three JSON write payload ASTs are identical to BASE, and filenames remain media-{cfr24,cfr5,normalized}.json, media-coarse.json, and strict-media-{cfr24,cfr5,normalized}.json. Assertions, independent pixels/PTS, source hashes, sample behavior, worker lifecycle, fixture opt-in, and product code remain unchanged.

Six helper cases cover missing/empty values, nested explicit output, idempotent reuse preserving prior content, writable independent destinations, and actual file obstructions in both configured/fallback modes. They assert concrete paths, writes, content preservation, and propagated filesystem errors without filesystem mocks. Wrong branch selection, omitted mkdir/parents/exist_ok, shared fallback destinations, and swallowed errors are observable failures. No new dependency or environment option.

## Verification commands and results

All commands use the unchanged canonical controller, SHA256 `354cf49b0c83d11f3945137fbdffc3ac6b2793f1217ac39a9b62270097940067`, and prepared environments without downloads, dependency installation, checkout export, or media regeneration. For readability below:

```bash
V=/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py
R=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task10110
S=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/worktrees/plate-text-matching
```

Each command below was run with `python3 "$V"`, prospective file/prerequisite hashes, a unique run ID, and its actual exit retained. Configs are in `task10110-evidence/inputs`; complete owning command logs are in `task10110-evidence/logs`. The actual native full/floor/package gates ran serially on the frozen commit. Development RED/GREEN are explicitly labeled development; their BASE HEAD is not relabeled as the final commit.

1. Actual unchanged owners, Python 3.12.16:

```bash
python3 "$V" --config "$R/base-red.json" --run-id owning-red run -- -m pytest "$S/tests/test_exact_media.py" "$S/tests/test_strict_tracking_routes.py" -k 'production_pixels or retained_strict' -o "pythonpath=$R" -p fallback_media -q
```

Exit 1: **7 failed, 35 deselected in 1.42s**. Every failure is `KeyError: 'VERIFY_RUN'` at an original evidence write after the independent production pixels/PTS or real strict route/engine priming assertions completed. This reproduces the documented test-tooling failure, not a fabricated product regression.

2. New helper tests before the helper existed:

```bash
python3 "$V" --config "$R/helper-red.json" --run-id helper-red run -- -m pytest "$S/tests/test_artifact_support.py" -q
```

Exit 2: **one collection error**, `ModuleNotFoundError: artifact_support`. This is the expected absent-helper RED; it is not described as an assertion failure. The subsequent GREEN exercises all six actual helper cases.

3. Development fallback GREEN, Python 3.12.16:

```bash
python3 "$V" --config "$R/development-green.json" --run-id development-green run -- -m pytest "$S/tests/test_artifact_support.py" "$S/tests/test_exact_media.py" "$S/tests/test_strict_tracking_routes.py" -o "pythonpath=$R" -p fallback_media -q
```

Exit 0: **48 passed in 3.08s**. Six new cases plus all 42 cases from the affected owner modules. Seven actual retained-media cases write the original JSON filenames under seven distinct pytest temporary artifact directories. The pinned local adapter (`fallback_media.py`, SHA256 `f0618042ef61d016325e83740b21a4d043bc3390518ddc7457730ee7a5faa2b7`) removes `VERIFY_RUN` only in the fixture for these three owning function names, after canonical startup. It uses real `tmp_path` and records locations after the test; it does not replace product behavior/assertions, disable the hook, or alter media. Canonical DEFAULT_PATHS/ACTIVE_SOURCE startup evidence remains in logs. The helper monkeypatch cases also restore the setting normally.

4. ONE normal native full gate, Python 3.12.16, explicit output:

```bash
python3 "$V" --config "$R/frozen-312.json" --run-id full-312 run -- -m pytest "$S/test_openscrub.py" "$S/tests" -o 'pythonpath=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task1631-evidence/adapters /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task654-evidence/adapters' -p task1631_fixture -p roundtrip_stdout_selected -q
```

Exit 0: **566 passed in 108.41s** (560 original plus six new cases). Exact proven fixture argv used; both adapter bytes and cached YuNet prospectively pinned. This run loads no fallback adapter. All seven original evidence files exist in its explicit run/logs directory. No skipped tests, failures, or warning summary. No duplicate full baseline run: the accepted identical-base coverage was reused as authorized, and actual owning RED remained mandatory and was run.

5. Actual floor Python **3.9.25**, frozen affected fallback:

```bash
python3 "$V" --config "$R/frozen-39.json" --run-id fallback-39 run -- -m pytest "$S/tests/test_artifact_support.py" "$S/tests/test_exact_media.py" "$S/tests/test_strict_tracking_routes.py" -o "pythonpath=$R" -p fallback_media -q
```

Exit 0: **48 passed in 3.43s**. All seven real media owners produce separate fallback artifacts. Used cv2/numpy loaders/native extensions are prospectively pinned to the existing actual 3.9 observation; no inference from metadata or cached build tooling.

6. Actual Python 3.9.25, frozen explicit-output compatibility:

```bash
python3 "$V" --config "$R/frozen-39.json" --run-id explicit-39 run -- -m pytest "$S/tests/test_artifact_support.py" "$S/tests/test_exact_media.py" "$S/tests/test_strict_tracking_routes.py" -q
```

Exit 0: **48 passed in 3.40s**. All seven original names exist under explicit run/logs. No unrelated Python floor/browser replay.

7. Prepared native Python 3.12.16 offline packaging:

```bash
python3 "$V" --config "$R/package-312.json" --run-id package-312 package
```

Exit 0 for sdist, wheel FROM extracted sdist, offline/no-deps/no-compile installation, installed identities/defaults, `openscrub --help`, and `openscrub-web --help`. The controller checked 39 sdist files and 13 wheel files. Independent archive/extracted-source inspection also matched the exact four owned source hashes. `tests/artifact_support.py` and its tests ship via the unchanged existing `tests` sdist include; neither helper nor any tests enter the wheel. All 13 selected wheel payloads match frozen source. Requires-Python remains `>=3.9`. No actual Python 3.9 package build claimed; no incompatible cached build-tool bundle used.

Source archive: 596817 bytes, SHA256 `9492cb975960d022e65bc40d619725686286e0249b743e341639cb351e3b1d5b`. Wheel: 457336 bytes, SHA256 `976df7bcaeb677b2c82e2bc8e0f959c0564404289837a3c14b965ecd64b66750`. `package-identities.json` retains the exact creation paths and file lists. No HTTP/browser/tracker-quality acceptance claim is added for this test-only patch.

## Self-review and handoff limits

`git diff --check` and AST parsing passed; final source is clean and all declared source hashes match frozen inputs. Reviewed all four changed files, compared JSON payload ASTs against BASE, verified seven fallback locations independently and seven explicit filenames, verified source/extracted archive bytes and wheel exclusion, and compared all baseline refs. The retained synthetic inputs remain the three original pinned files from `runtime/task1001/media.json`; their hashes and FFmpeg/FFprobe/Tesseract, cv2/numpy native loader pins are in the evidence input manifests. Runtime import checks report the same ten product modules at the expected origins.

No outstanding implementation failure. Retained negative evidence is the seven original owner failures and absent-helper collection error; no additional product failure was suppressed. The shared D01 archive-warning concern remains deferred; these logs emitted no such warning. The local hook is cooperative Python isolation, not an OS guarantee for native processes. Real retained-media cases remain opt-in and require the existing `OPENSCRUB_EXACT_MEDIA` manifest. Self-review does not substitute for root's fresh independent full-task review, which remains the next gate.

Austin dependency: this tiny submission depends only on the owning exact/strict-test contribution represented by BASE. It is not a blanket prerequisite for unrelated branches; future owners may take it explicitly or keep it with the relevant owning contribution if separate stacking costs more than it saves.

Compact product-only evidence: `task10110-evidence` (about 237 KB), with SHA256 manifest, exact input configs, adapter, full owning logs, package identities, source identities/results summary, and explicit media JSON. No source export, environment, model/media copy, installation tree, or local allocation controls are archived. Source/runtime ownership will be explicitly released after this report phase actually finishes; root then owns review. No future user decision or publication is implied.
