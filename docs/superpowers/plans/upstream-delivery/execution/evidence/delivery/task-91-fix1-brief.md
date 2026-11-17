# Task91 fix round 1

Fix base: a4f064f1b12cb0a22e5090d7fddfa3fc6055b5d7. The native pr/opencv-fallback-compatibility checkout is yours again for this scoped correction. Original task-91-brief.md remains binding. Root read fix-loop guidance before this round.

## Open finding (verbatim)

- **Runtime/wheel disagreement receives a normal-wheel repair command.** `openscrub_internal/opencv_compat.py:116` classifies runtime `5.0.0` with sole `opencv-python==4.14.0.94` metadata as `unsupported` before reaching the mismatch check at line 124. At line 151, the combination of that state and the sole distribution name authorizes the printed `--force-reinstall "opencv-python<5"` command. A shadowing source/distro installation or other ownership mismatch is not established to belong to that distribution, so reinstalling the normal wheel may leave the imported runtime unchanged. Preserve the unsupported-policy information if desired, but make repair eligibility require trustworthy runtime/distribution agreement; disagreement must receive reconciliation/clean-environment guidance. Add a regression for runtime 5 + normal-wheel 4 metadata and the reverse mismatch. The existing version-5 fixture at `tests/test_opencv_compat.py:37` checks unsupported classification but does not check this repair prohibition.

## Scope and checks

Correct the ownership/repair decision without introducing automatic repair, altering the selected core bound or provider choices, or broadening the task. Preserve clear unsupported-version information if useful, but a known runtime/distribution disagreement must not recommend normal-wheel reinstall. Include positive controls for a consistently identified unsupported normal wheel and existing normal broken-wheel advice, alongside both mismatch directions and the existing mixed/alternate/unmanaged/unknown matrix.

Run owning RED then focused tests/test_opencv_compat.py and tests/test_install_opencv_compat.py on the prepared Python3.12 and3.9 runtimes. Refresh affected sdist→wheel/package-byte/installed-helper/setup/installer checks because shipped helper bytes change. Reuse exact unchanged dependency-resolution and provider evidence, with explicit source-byte comparison where needed. The existing full213 run belongs to the original head; do not claim a new full count or repeat the whole suite for this localized branch unless a concrete new failure/concern warrants it. Preserve original logs; fix artifacts go under /tmp/openscrub-task91/fix1.

Self-review, commit the fix, append a fix-round section to task-91-report.md, and optionally write task-91-fix1-report.md. Include exact fix base/head, covering test files/commands/outputs, package/installed source identities, any new limits and the disposition of the finding. Update the local PR draft to final behavior/evidence. No nested agents, other product work, publication or user-environment changes. Root dispatches scoped re-review of a4f064f..newHEAD.
