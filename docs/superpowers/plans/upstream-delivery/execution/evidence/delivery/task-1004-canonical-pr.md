# Bind paused edits and Track to the inspected exact frame

Paused editing now uses one decoded exact sample for the displayed frame, geometry changes and Track's starting seed. Rapid scrubbing, reopening an editor, playback and late pointer/timeline events retain their initiating owners. Requested time and inspected canonical frame are visible, and geometry becomes available only after the current image and transform are ready.

Save retains one immutable unresolved submission, validates complete paired geometry acknowledgements and preserves newer local changes. Explicit recovery can abandon an uncertain retry or discard one selected pending geometry/addition for fresh inspection while keeping independent work. The sample slot remains occupied through successful decoding and HTTP error-body settlement. Detection/blur defaults and the existing backend, engine, dependencies and report format remain unchanged.

This candidate builds on the exact-sample backend, strict Track seeds and reviewed resize/containment prerequisites. Review range: `07cfaa9539a2561c26b6f7280fae6702eb07137c..d1f056e86fcae2dcfaa01bbc7f97e79ca662faaa`. It is one coherent editor-and-Track contribution, separate from optional plate discovery and other delivery tasks.

Validation:

- Native full620 at `dcaa0e5`, including both actual Chromium PAGE scenarios at DPR1/2, real SDR output pixels, committed-but-lost save acknowledgement retry, strict Track routing and separate-process persistence.
- Final source bytes:153 owning tests on each actual Python3.12.16 and3.9.25, including twelve delayed non-JSON HTTP409/423/500 body-settlement regressions. The five-line failure-branch repair leaves the earlier successful-body browser evidence attributed to `dcaa0e5`.
- Final frozen `d1f056e` offline sdist→extracted-source wheel→no-deps installation: ten origins/defaults/CLI, strict/legacy listening HTTP, exact PAGE/custom substitutions and updater bytes.
- Independent full-task review and same-reviewer scoped repair review approved; no remaining task findings.

PAGE Track uses a deterministic engine fake to test source/route/append ownership. Browser evidence covers prepared Linux headless Chromium; real tracking quality, touch, HDR and Windows/Docker execution remain outside this contribution's validation.
