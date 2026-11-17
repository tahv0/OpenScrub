# Task 91 / B02b: preserve the model-unavailable face fallback

Status: DONE. Local implementation and self-review complete; supervisor review remains separate. Nothing published.

The normal OpenCV 5 wheel can import while lacking the constructor and XML required by OpenScrub's existing unavailable-model Haar fallback. This change bounds the normal core wheel to `opencv-python<5` and replaces import-only installer/setup success with a fresh, capability-aware diagnostic. It retains YuNet → Haar behavior and existing provider choices.

- Branch/worktree: `pr/opencv-fallback-compatibility`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
- Exact base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
- Initial implementation head: `a4f064f1b12cb0a22e5090d7fddfa3fc6055b5d7`.
- Current correction head: `a10e485962571a566f99225541735ab1ada1f4c0` (fix round 1 below).
- Commit: `a4f064f fix: preserve OpenCV face fallback compatibility`.
- Product worktree clean after commit; `git diff HEAD^ HEAD --check` passed.
- Artifacts and isolated synthetic profiles: `/tmp/openscrub-task91`.

## Implementation and repair policy

The three direct declarations (`pyproject.toml`, `requirements.txt`, `install.py::CORE_PKGS`) now specify exactly `opencv-python<5`. Python remains `>=3.9`; no new lower bound, exact global pin, wheel-flavor change, model, provider, or toolchain was added.

`openscrub_internal/opencv_compat.py` is a private stdlib-only helper shared by the two existing checks. It runs self-contained code in a fresh child of the actual selected interpreter with a 15-second timeout. External Python selected by a frozen installer need not have OpenScrub installed. It collects runtime version/path, metadata for all four cv2 wheel names, callable `CascadeClassifier`, readable/nonempty frontal-face XML, and successful nonempty classifier construction. It does not run inference, download models, import the engine, or invoke pip.

The diagnostic separates observed `fallback_usable` from installation health. Metadata-query uncertainty does not erase successfully observed fallback capability. Import failures, missing API, missing/unreadable XML, construction exceptions, empty classifiers, unknown versions, runtime/distribution disagreement, malformed output, launch errors, child crashes, and timeout remain distinguishable through state and evidence.

| Observed installation | Classification and behavior |
| --- | --- |
| Sole normal wheel, matching runtime/distribution release below 5, working Haar | `healthy`; no mutation. OpenCV's wheel build suffix is excluded when comparing its runtime release tuple. |
| Two, three, or four cv2 distributions | `conflict`, including when imported Haar works. All names/versions and imported path are shown; no ownership guessing or single-main repair. |
| Singleton alternate wheel below 5 with working Haar | `alternate`, capability retained; setup prints a note rather than certifying the normal core wheel or adding another flavor. |
| Importable source/distro/frozen cv2 without wheel metadata, known runtime below 5, working Haar | `unmanaged`, capability retained; setup prints a note. It is not classified as a missing installation or automatically replaced. |
| Known runtime or singleton distribution version >=5 | `unsupported`; working cached YuNet/Haar capability cannot certify it under this selected core policy. Mixed flavors remain a conflict. |
| Existing sole normal wheel with known incompatible/broken state | Print a deliberate repair using the actual interpreter: `-m pip install --force-reinstall "opencv-python<5"`, then rerun health checks in a fresh process. Normal mode and `--yes` do not execute this repair. |
| Missing `cv2` import and no cv2 wheel metadata | `missing`; the standalone installer may use the existing accepted install prompt to install bounded normal OpenCV, then freshly reprobe. Decline and `--check` leave it missing. |
| Uncertain, mixed, alternate, or unmanaged ownership | Show evidence and suggest deliberate ownership reconciliation or a clean core environment. Source-built CUDA guidance names the constructor/XML requirement; no uninstall/migration or automatic normal-wheel addition. |

OpenCV is separated from the installer's generic missing-import list. Other core package prompts remain in use. Flask is checked independently in setup. Setup's existing overall return-code policy is preserved.

The standalone installer runs one final read-only OpenCV-only assessment after its optional Paddle step. A newly introduced conflict cannot end as `Install complete` or with blanket reassurance that other fallbacks cover gaps. The check does not rerun full core installation or reconcile flavors.

The helper is included in explicit wheel/sdist payloads and all three app Dockerfile source-copy layers. New tests are included in the sdist. No speculative frozen hidden imports were added. README and contribution guidance document the bounded deliberate repair, source-update checks, and separate optional-Paddle limitation.

## TDD and self-review evidence

All logs below are under `/tmp/openscrub-task91`.

- Initial RED: `. /tmp/openscrub-baseline-20261116/env-opencv4.sh; python -m pytest tests/test_install_opencv_compat.py -q`. `red.txt`: `1 failed`; an importable controlled normal5 returned `[OK] Core Python packages — all present`, violating the new compatibility assertion. This is the owning behavioral failure before production implementation.
- Helper matrix was written before its implementation. `red-helper.txt` records the expected missing-helper collection error, supplementary to the owning behavioral RED.
- Initial implementation GREEN: `green-2.txt`, `49 passed`.
- Unknown-version edge RED: `red-edges.txt`, `2 failed, 71 passed`; unknown wheel metadata with import failure was classified broken instead of uncertain, and missing runtime version was collapsed into malformed output. Both were fixed and the focused matrix passed.
- Self-review source-label RED: `red-source-label.txt`, `1 failed`; setup printed `[missing]` for usable unmanaged source cv2. It now prints a note, preserving the CUDA/source distinction.
- Self-review metadata/capability RED: `red-metadata-capability.txt`, `1 failed`; metadata uncertainty incorrectly erased observed Haar usability. The final helper retains capability while still classifying installation state uncertain.
- Final focused GREEN on both active runtimes: `focused-final-312.txt` and `focused-final-39.txt`, each **79 passed**, no failures/skips/warnings.

Self-review read the complete implementation diff and checked the contract against the actual evidence. The final small fixes above caused focused/full/build/installed checks to be refreshed because source changed. Broad checks were not repeated after an unchanged final pass. No nested implementers or reviewers were dispatched.

## Actual runtime evidence versus controlled cases

**Actually executed:** Linux x86_64 CPython 3.12.16 and 3.9.25 with existing normal `opencv-python==4.14.0.94` / runtime `4.14.0`. `source-identity-312.json` and `source-identity-39.json` assert exact active native engine/helper paths and record the active interpreter and cv2 paths. Dedicated task-local harness/profiles were used for final focused, production, full, and installed checks; prepared environments were read/reused without package changes.

The production `FaceDetector` regression runs four cases on each interpreter: empty isolated model cache, and an existing verified cached YuNet, each with and without a missing optional ONNX path. `_fetch_model` is explicitly blocked. Actual Haar constructs nonempty and `find()` executes on a black frame and seeded synthetic noise at scales 1.0 and 0.4. Cached cases use YuNet, make zero fetch attempts, and execute the same calls. Empty-cache cases make one intercepted fetch attempt and remain empty. No constructor/default/provider code was changed.

The existing model was copied only into the synthetic task-local fixture. SHA256 is asserted before/after: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` (232,589 bytes). No new model was fetched or bundled. These negative synthetic frames establish API execution and fallback selection; they do not establish positive-face recall, accuracy, or end-to-end redaction quality.

The actual target-selection test launches a distinct executable wrapper with Python `-S`, excluding site-packages/OpenScrub, and gets a valid missing-install snapshot. It proves that child collection is self-contained. This POSIX wrapper test is explicitly skipped on Windows; target argv is also covered by subprocess-boundary tests. Actual health probes and installed smokes execute in both prepared Python runtimes.

**Controlled, not real damaged environments:** normal5 rejection, all six pairwise conflicts, all four triple combinations and the four-flavor conflict; singleton alternate flavors; source/CUDA-like 4.10.0 without wheel metadata; unsupported/mismatched/unknown versions; metadata uncertainty; broken imports; fresh install/decline/reprobe; corrupt child output, timeout/crash/launch failure; post-Paddle mutation. Diagnostic fixtures and subprocess/pip boundary spies never install, uninstall, or damage shared environments. Missing API/XML and construction/empty-classifier cases also run the actual child collector against task-local cv2 test modules. No actual source-built CUDA4.10 or alternate-wheel binary runtime is claimed.

The new tests cover existing normal/alternate/unmanaged/mixed/uncertain installations in check, interactive, and `--yes` modes with zero OpenCV pip calls; fresh accepted installation uses the selected interpreter and exactly bounded normal OpenCV, and a failed reprobe remains unhealthy even after pip returns success. Other missing core package installation remains separate. Setup tests check visible normal5 rejection and independent Flask checking. Final-summary tests simulate a Paddle-introduced conflict without executing Paddle.

The previous actual OpenCV4-versus5 comparison was reused from the named research, not rerun.

## Final verification

Commands run from the isolated worktree unless otherwise stated:

1. `. /tmp/openscrub-task91/env312.sh; python -m pytest tests/test_opencv_compat.py tests/test_install_opencv_compat.py -q` → **79 passed in 0.61s** (`focused-final-312.txt`).
2. `. /tmp/openscrub-task91/env39.sh; python -m pytest tests/test_opencv_compat.py tests/test_install_opencv_compat.py -q` → **79 passed in 0.69s** (`focused-final-39.txt`). Active Python floor is 3.9.25, not an emulated syntax check.
3. `. /tmp/openscrub-task91/env312.sh; python -m pytest -q` → **213 passed in 76.69s**, exit 0 (`full-release-312.txt`). This includes the existing 134 root tests and 79 added cases. Earlier full runs were 211/212 before the documented added self-review regressions; those were refreshed after changed source, not claimed as final results.
4. Prepared Python3.9 build frontend/backend: `python -m build --no-isolation --sdist --outdir /tmp/openscrub-task91/dist .`, then extract the actual sdist and `python -m build --no-isolation --wheel --outdir /tmp/openscrub-task91/dist SDIST_SOURCE` → exit 0, `openscrub-1.0.96.tar.gz` and `openscrub-1.0.96-py3-none-any.whl` (`build-release-sdist.txt`, `build-release-wheel.txt`). No build dependency installation into shared environments.
5. `python /tmp/openscrub-task91/validate_packages.py` → PASS for declarations, archive metadata/payloads, synthetic updater preservation/nonmutation and unchanged provider/default sources (`package-updater-release.txt`, `package-updater-evidence.json`).
6. Task-local `uv pip install --no-deps --target /tmp/openscrub-task91/installed-release WHEEL` → installed only OpenScrub into the synthetic target (`install-wheel-release.txt`). This is not a new full dependency install/resolution.
7. From `/tmp/openscrub-task91`, run `installed_smoke.py` with `PYTHONPATH` preferring `installed-release`, using each prepared Python → exit 0 (`installed-release-312.txt`, `installed-release-39.txt`). Asserts installed engine/setup/helper import paths; normal4 health; actual `openscrub_setup.main(['--check'])`; standalone installer import and `step_core(check=True)` using the installed helper. A network audit guard records zero events. No pip repair invoked.
8. `git diff HEAD^ HEAD --check` → exit 0; committed worktree clean.

The initial isolated Python3.9 build attempt with the prepared offline wheelhouse failed because the wheelhouse lacks Hatchling's pre-3.11 `tomli` wheel. The already prepared Python3.9 environment has its complete backend, so `--no-isolation` performed the real sdist→wheel build without installing or downloading tools. A first wheel invocation used a wrong assumed directory version and was corrected to derive it from the actual sdist. An early edit-shell `python` lookup preceded environment sourcing; integration was applied with the exact existing interpreter. These tooling attempts are retained, not presented as passing builds.

Final artifact SHA256s:

- Wheel: `3572a54a4f90f71b874390376a1b9ecb59caf9e3ceb59bd809f2eba9808e791d`.
- Sdist: `a901146b2dca9bd98500d10eb7929491651cf957ce91df39d01c2d7a2f390395`.

## Resolution, packaging and source-update evidence

The completed public-PyPI package-core resolution is reused from `opencv-resolution-research.md`; no resolver or older 4/5 comparison was repeated. The exact ten-declaration candidate SHA256 is `a953b90959297225f8b361917b7e1e733262b128e7b0275fd126b13cf86463ca`. The validation script independently reads every source declaration and both built metadata records. All ten core declarations match that candidate exactly after name/specifier normalization; source requirements retain only their original extra `spacy`; installer retains its original seven-package subset except the requested OpenCV cap. Built `Requires-Python` is `>=3.9`; the two original spaCy extras remain intact. Thus the prior Linux3.12/3.9 metadata-only core resolution applies to these final declarations. It is not a full requirements/spaCy, optional Paddle, installed-clean-environment, or universal platform claim.

Wheel/sdist contain the helper. Sdist contains the new tests. Wheel retains all three registries, the branded icon, and third-party notices; existing license/notice payloads remain. No ONNX/XML/model payload was added. Source/container packaging only gains the namespace copy; no unrelated dependency/provider command changes.

The real unchanged `openscrub_update.update_source` was run against the final built sdist over local `file://` transport in a synthetic source folder. It copies the nested helper, backs up the old nested file, preserves synthetic local jobs/cert key/models/zones/allowlist and locally pinned plate-registry hashes. Its subprocess boundary was made fatal, proving this update performed no pip/subprocess reconciliation. The updater product file is byte-identical to base. Logs and preservation hashes are in `package-updater-evidence.json`. README correctly instructs a post-source-update compatibility check rather than promising automatic dependency migration.

## Preservation and limitations

`validate_packages.py` compares byte-for-byte against exact base: `openscrub.py`, `openscrub_web.py`, `openscrub_gui.py`, `openscrub_update.py`, CUDA source-base Dockerfile, OpenCV CUDA workflow, Windows spec, all model registries, notices and icon. Standalone `step_paddle` AST is identical. Removing only the new helper COPY yields byte-identical CPU/Intel/CUDA app Dockerfiles. Existing CPU/GPU/index/version commands, CUDA's source-built OpenCV/contrib4.10.0 path, NumPy1.26.4, DirectML/OpenVINO/ORT choices, security-refresh layers, and default model/provider behavior remain intact.

Optional Paddle flavor coexistence is a named separate follow-up. Current researched PaddleX OCR metadata pins contrib4.10, but that declaration is neither a resolved optional environment nor a coexistence fix. Core `<5` cannot prevent a second distribution from providing `cv2`. Standalone now reports the post-Paddle state; web/desktop optional installation commands are preserved and are not claimed protected/reconciled by this PR.

No actual Windows/macOS/frozen build, container/image build/run, source-built CUDA runtime, GPU inference, Intel inference, optional Paddle installation/resolution, new model fetch, positive-face accuracy evaluation, or clean complete dependency install was performed. Read-only host Docker/GPU capability discovered previously does not count as workload validation. No blanket support claim is made from the Linux runtimes or controlled fixtures. These are expected remaining platform/provider gates, not silently passing claims.

## Files changed

`pyproject.toml`, `requirements.txt`, `install.py`, `openscrub_setup.py`, `openscrub_internal/__init__.py`, `openscrub_internal/opencv_compat.py`, `tests/test_opencv_compat.py`, `tests/test_install_opencv_compat.py`, `Dockerfile`, `Dockerfile.cuda`, `Dockerfile.intel`, `README.md`, `CONTRIBUTING.md`.

## Fix round 1 — runtime/wheel agreement before deliberate repair

Disposition: **fixed**. The Important review finding was verified and reproduced before implementation. Previously, an unsupported runtime or distribution version could select `unsupported` before the mismatch classification, and the sole normal-wheel name then enabled its reinstall hint. That metadata did not establish that the imported runtime belonged to the wheel.

- Exact fix base: `a4f064f1b12cb0a22e5090d7fddfa3fc6055b5d7`.
- Exact fix head: `a10e485962571a566f99225541735ab1ada1f4c0`.
- Commit: `a10e485 fix: require OpenCV version agreement for repair hints`.
- Branch/worktree unchanged; committed worktree clean.
- All new fix artifacts are under `/tmp/openscrub-task91/fix1`; original logs/build artifacts remain intact.

The repair formatter now requires a sole normal wheel **and known, equal parsed runtime/wheel release tuples** before offering the deliberate `--force-reinstall "opencv-python<5"` command for an unsupported/broken installation. Both known mismatch directions (runtime5/wheel4 and runtime4/wheel5), unknown runtime, and unavailable runtime versions receive reconciliation/clean-environment guidance instead. Unsupported-policy information is retained in the assessment/evidence; the repair decision no longer infers ownership from that policy classification. This is a guard on deliberate advice, not proof of file ownership or a new automatic repair. Consistently identified unsupported normal5 and matching normal4 with missing API/XML, construction errors, or an empty classifier retain deliberate bounded repair instructions.

The guard is intentionally conservative for existing installations: a known matching normal-wheel/runtime release with broken Haar or an unsupported version still gets deliberate repair advice; absent or unknown runtime evidence gets ownership-reconciliation guidance, even when registered metadata independently establishes an unsupported version. This does not change fresh missing-install behavior: a missing cv2 import with zero cv2 distribution metadata remains `missing`, and the existing accepted bounded install/reprobe path remains available outside `--check`. The focused matrix retains those fresh-install and nonmutation controls.

Only `openscrub_internal/opencv_compat.py` and its two compatibility test files changed from fix base. Self-review checked this complete diff and the normal/mixed/alternate/unmanaged/uncertain branches. Every other tracked file (114 files) was independently compared byte-for-byte to fix base and matched. Core declarations, all existing provider commands, source-built CUDA/NumPy behavior, installer/setup consumer code, documentation and updater implementation therefore remain unchanged by the correction.

### Covering RED/GREEN and scoped checks

All commands below were run from the native worktree, except the installed smokes run with task-local installed paths first on `PYTHONPATH`.

1. Owning RED, before the helper fix:

   ```bash
   . /tmp/openscrub-task91/env312.sh
   python -m pytest tests/test_opencv_compat.py::test_normal_repair_requires_runtime_wheel_agreement tests/test_install_opencv_compat.py::test_mismatched_runtime_cannot_receive_normal_wheel_repair -q
   ```

   `/tmp/openscrub-task91/fix1/red.txt`: **8 failed in 0.10s**. Both mismatch directions leaked `--force-reinstall` from the helper and actual installer/setup rendering; unknown/unavailable runtime with normal5 metadata also leaked it. These were expected behavioral failures, not collection errors.

2. Final focused GREEN:

   ```bash
   . /tmp/openscrub-task91/env312.sh
   python -m pytest tests/test_opencv_compat.py tests/test_install_opencv_compat.py -q
   . /tmp/openscrub-task91/env39.sh
   python -m pytest tests/test_opencv_compat.py tests/test_install_opencv_compat.py -q
   ```

   `fix1/focused-312.txt`: **92 passed in 0.65s**. `fix1/focused-39.txt`: **92 passed in 0.73s**. No failures/skips/warnings. The matrix includes both mismatch directions, missing/unknown runtime, positive agreeing unsupported/broken repair controls, existing six-pair/four-flavor ownership tests, source/alternate/unmanaged cases, and existing real supported Haar/cached-YuNet probes. The consumer cases exercise installer `--yes`/normal mode and setup `--check`, confirm visible reconciliation/unsupported information, and assert zero pip calls.

3. Refreshed affected packaging:

   ```bash
   . /tmp/openscrub-task91/env39.sh
   python -m build --no-isolation --sdist --outdir /tmp/openscrub-task91/fix1/dist .
   # Extract this sdist into fix1/sdist, derive its actual source directory.
   python -m build --no-isolation --wheel --outdir /tmp/openscrub-task91/fix1/dist /tmp/openscrub-task91/fix1/sdist/openscrub-1.0.96
   python /tmp/openscrub-task91/fix1/validate_packages.py
   ```

   `fix1/build-sdist.txt` and `fix1/build-wheel.txt`: successful real sdist→wheel build, exit 0. `fix1/package-updater.txt`: PASS for exact archive helper bytes versus source, unchanged core candidate/source/built metadata, required payloads, synthetic updater copy/local-data/pin preservation/nonmutation, and provider/default preservation. The same existing complete Python3.9 build backend was reused without installation/download or shared-environment changes.

4. Fresh task-local package install:

   ```bash
   UV_CACHE_DIR=/tmp/openscrub-task91/fix1/uv-cache /tmp/openscrub-baseline-20261116/bootstrap/bin/uv pip install --no-deps --target /tmp/openscrub-task91/fix1/installed /tmp/openscrub-task91/fix1/dist/openscrub-1.0.96-py3-none-any.whl
   ```

   `fix1/install-wheel.txt`: installed only OpenScrub into the new task-local target, exit 0. This is not a full dependency installation/resolution.

5. Installed helper/setup/installer checks on both actual runtimes:

   ```bash
   . /tmp/openscrub-task91/env39.sh
   PYTHONPATH=/tmp/openscrub-task91/fix1/installed:/tmp/openscrub-task91/harness python /tmp/openscrub-task91/fix1/installed_smoke.py
   . /tmp/openscrub-task91/env312.sh
   PYTHONPATH=/tmp/openscrub-task91/fix1/installed:/tmp/openscrub-task91/harness python /tmp/openscrub-task91/fix1/installed_smoke.py
   ```

   `fix1/installed-39.txt` and `fix1/installed-312.txt`: exit 0. Active interpreters are `/tmp/openscrub-python39-20261117/venv/bin/python` (3.9.25) and `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` (3.12.16). Engine/setup/helper imports are asserted under `fix1/installed`; installed helper and setup bytes match their final source files. Actual normal4 capability probes, installed setup `--check`, and standalone installer core checks pass. Additional controlled runtime5/wheel4 and runtime4/wheel5 snapshots exercise the **installed** helper and both real consumer paths, forbid installer pip, and verify reconciliation rather than reinstall advice. Positive matching unsupported/broken controls retain the hint. Network audit events remain empty. These mismatches are controlled evidence, not damaged real installations.

6. `git diff --check` and committed `git diff a4f064f1b12cb0a22e5090d7fddfa3fc6055b5d7 HEAD --check`: clean. `fix1/fix-source-artifact-identities.json` records the exact changed-file set, all 114 unchanged tracked paths, helper and artifact hashes.

Final corrected helper SHA256: `0f568ced4e60add8adacafd8670c942eac92e218725c466c6f8b35e8cfbb8dd5`.

Corrected wheel SHA256: `9d76daeb9b5fe63664e56fd7f847b21df8134dd2c77ab9a7c67727ae8d60203a`. Corrected sdist SHA256: `f8048ce0548897f9595a2f72c9445eaa31cd20e12790c2ce99c1e68a567e4106`.

The existing **213-test full suite belongs to the initial `a4f064f` head**, not this fix head. Per scoped review instructions, no full-suite run, dependency resolver, or old OpenCV4-versus5 comparison was repeated. The exact candidate SHA256 and all dependency/provider declarations remain unchanged and were compared again against the refreshed package metadata. Windows/macOS/frozen/container/GPU/optional-Paddle limitations remain as documented above. No new platform claim, model download, user-environment mutation, nested agent, publication, or additional concern was introduced.
