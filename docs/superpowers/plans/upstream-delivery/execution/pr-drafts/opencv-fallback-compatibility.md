# Keep the face fallback working with supported OpenCV installations

When YuNet is unavailable, OpenScrub falls back to Haar. The normal OpenCV 5 wheel can import successfully while lacking that fallback's constructor/XML, causing face detector construction to fail. Bound the existing normal core requirement to `opencv-python<5` across package/source/installer declarations, preserving Python >=3.9 and current detector/provider defaults.

Installer and setup checks now collect runtime/path, all four cv2 wheel distributions, and actual Haar construction capability in a bounded fresh selected-interpreter process. Existing unsupported/broken sole normal wheels receive a deliberate bounded reinstall command only when known runtime and wheel release versions agree; mismatches or unknown runtime versions receive ownership-reconciliation guidance; checks and `--yes` do not execute repairs. Mixed, alternate, source-built and uncertain installations retain explicit ownership/capability diagnostics. Standalone installation rechecks OpenCV after optional Paddle and reports conflicts honestly. Package/container source paths include the shared private helper, and documentation explains source-update checks and the separate Paddle coexistence limitation.

Validation:

- Full suite: 213 passed at initial implementation head `a4f064f`. After the scoped repair-ownership correction, 92 focused cases passed on both actual Linux Python3.12.16 and Python3.9.25; the full suite was not repeated.
- Real production model-unavailable Haar and verified cached-YuNet execution on both interpreters; no model download or accuracy claim.
- Sdist→wheel build, final installed helper/setup/installer-core checks on both interpreters, built metadata matched to the exact completed core-resolution candidate.
- Synthetic source update copies the nested helper and preserves local data/pins without invoking pip; provider/default source and optional commands preserved.

Optional Paddle cv2 flavor reconciliation and actual Windows/macOS/frozen/container/GPU validation remain separate; none is claimed complete here.

Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`
Head: `a10e485962571a566f99225541735ab1ada1f4c0`
Branch: `pr/opencv-fallback-compatibility`
[Detailed evidence](../evidence/delivery/task-91-report.md) / [scoped fix review](../evidence/delivery/task-91-fix1-review.md).

Local draft only; no remote branch or PR published.
