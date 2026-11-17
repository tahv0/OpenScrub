### Spec Compliance

- ❌ Issues found: the deliberate repair policy treats a known runtime/wheel disagreement as identified normal-wheel ownership whenever either version is 5 or newer. `openscrub_internal/opencv_compat.py:116` runs before the mismatch guard at line 124, and `opencv_repair_hint` at line 151 then recommends reinstalling the normal wheel. This violates the requirement to avoid ownership inference and normal-wheel repair advice for uncertain installations.
- ✅ The three direct declarations use only the requested `opencv-python<5` change (`pyproject.toml:37`, `requirements.txt:1`, `install.py:42`). The helper is stdlib-only, runs self-contained collection in a fresh bounded child, checks all four distributions and actual Haar API/data/construction, and separates fallback capability from managed health (`openscrub_internal/opencv_compat.py:14`, `:65`, `:104`).
- ✅ Fresh installation remains restricted to an affirmative missing-state decision, then reprobes; existing broken/unsupported/mixed/alternate/unmanaged cases do not trigger automatic OpenCV pip repair (`install.py:131`). The installer performs a final read-only OpenCV assessment after Paddle and suppresses the blanket fallback reassurance when that result is unhealthy (`install.py:416`, `:429`). Flask stays separate (`openscrub_setup.py:219`).
- ✅ The namespace is included in wheel/sdist and each of the three application Dockerfile copy layers (`pyproject.toml:92`, `:103`, `Dockerfile:63`, `Dockerfile.cuda:135`, `Dockerfile.intel:97`). New tests live under `tests/`; the diff contains no engine/default/provider/updater mutation or speculative frozen hidden imports.
- ⚠️ Cannot verify native Windows/macOS/frozen/container/CUDA execution from this diff or the available Linux evidence. The report explicitly does not claim those passes. The source-built CUDA classification is controlled metadata/capability evidence, not a real CUDA build or inference result.

### Strengths

- `openscrub_internal/opencv_compat.py:21` distinguishes a missing cv2 module from a dependency import failure; lines 30–48 distinguish missing API, missing/unreadable/empty XML, constructor errors and an empty classifier. Lines 67–96 bound execution and reject failed or malformed child evidence instead of assuming a fresh installation.
- `openscrub_internal/opencv_compat.py:107` retains observed fallback capability despite metadata uncertainty, while lines 110–133 prevent working mixed/alternate/unmanaged imports from becoming normal managed-wheel health. Source-built CUDA guidance avoids automatic CPU-wheel replacement (`:155`).
- `tests/test_opencv_compat.py:23` covers every two-, three- and four-flavor combination. The actual selected-executable wrapper test (`:104`) excludes site-packages/OpenScrub, and the real-child controlled-module checks (`:129`) exercise collection beyond mocked return values. The production FaceDetector regression (`:155`) blocks fetching and distinguishes empty-cache Haar from a verified cached YuNet fixture without changing production detectors.
- Consumer boundary tests cover missing-install acceptance/reprobe, failed reprobe, declined/check nonmutation, existing-install nonmutation, independent core packages, and post-Paddle summary behavior (`tests/test_install_opencv_compat.py:45`, `:57`, `:65`, `:80`, `:87`, `:109`).
- Existing final evidence files contain clean results: `focused-final-312.txt` and `focused-final-39.txt` each report 79 passed; `full-release-312.txt` reports 213 passed. `package-updater-release.txt` records successful source/built metadata, payload, synthetic nested updater preservation/nonmutation and provider/default preservation checks. These are existing implementer runs, not review reruns.

### Issues

#### Critical (Must Fix)

- None found.

#### Important (Should Fix)

- **Runtime/wheel disagreement receives a normal-wheel repair command.** `openscrub_internal/opencv_compat.py:116` classifies runtime `5.0.0` with sole `opencv-python==4.14.0.94` metadata as `unsupported` before reaching the mismatch check at line 124. At line 151, the combination of that state and the sole distribution name authorizes the printed `--force-reinstall "opencv-python<5"` command. A shadowing source/distro installation or other ownership mismatch is not established to belong to that distribution, so reinstalling the normal wheel may leave the imported runtime unchanged. Preserve the unsupported-policy information if desired, but make repair eligibility require trustworthy runtime/distribution agreement; disagreement must receive reconciliation/clean-environment guidance. Add a regression for runtime 5 + normal-wheel 4 metadata and the reverse mismatch. The existing version-5 fixture at `tests/test_opencv_compat.py:37` checks unsupported classification but does not check this repair prohibition.

#### Minor (Nice to Have)

- None found.

### Focused Checks and Limits

- Ran one focused check for the unanswered ownership/repair doubt: executed only the helper reconstructed from the packaged diff and supplied `{status: ok, version: 5.0.0, distributions: {opencv-python: 4.14.0.94}, capability: missing_api}`. It returned `state=unsupported` and printed `/actual/python -m pip install --force-reinstall "opencv-python<5"`, confirming the Important finding. No packages or product files were changed.
- Named consumer risk: a frozen executable may not accept ordinary Python flags. The diff cuts `install.py::resolve_python` off mid-function; I read that complete function at `install.py:48–61`. It explicitly resolves an external Python when frozen, and `step_opencv` uses that selected `PYTHON`. The related focused consumer check inspected `windows/openscrub.spec` and searched `openscrub_gui.py`, `openscrub_web.py`, `windows/build_installer.bat` and `windows/installer.iss` for setup invocation. The spec lists setup as a hidden import (`windows/openscrub.spec:49`), but those consumers did not reveal a frozen setup invocation. `openscrub_setup.py:209` uses `sys.executable`; its behavior when directly invoked inside a frozen process remains unverified, rather than a demonstrated reachable failure or a passing native-platform claim.
- Read the existing test/package/installed-smoke evidence summaries; did not rerun suites, builds, resolver work, browser checks or the earlier OpenCV4/5 comparison. The installed-smoke tails show successful result records, but I did not independently replay installation, inspect every generated artifact or execute the synthetic updater. Those broader claims remain supported by the implementer's recorded validation, not fresh review execution.
- The first combined read was output-truncated; I reread the report and the missing diff segments to recover the evidence. No separate changed-file inspection was performed beyond the explicitly cut-off `resolve_python` function; no Git commands, environment migrations, branch/index changes, remote publication or subagents were used.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The implementation is compact, preserves the requested provider/source-build scope, and has meaningful capability, ownership and nonmutation coverage. The mismatch repair case crosses an explicit ownership boundary in the contract and needs correction before this task passes its gate.
