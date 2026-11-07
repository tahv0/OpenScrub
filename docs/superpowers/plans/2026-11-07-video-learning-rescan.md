# Video-specific learning and full rescan

Approved goal: optional checkpoint review, review a useful uncertainty sample,
train locally, use the trained model alongside the original detectors in a full
rescan, preserve human corrections across changing detection IDs, and compare
passes before explicit rendering. Do not claim perfect anonymisation from model
confidence or a synthetic test.

Implementation:
- [x] Test source/frame/geometry correction snapshots and negative intervals.
- [x] Decode actual single-class YOLO segmentation ONNX outputs, preserving
      letterboxing and mask geometry; fail closed on unsupported outputs.
- [x] Connect the optional trainer to a transactionally staged full rescan.
      Preserve the last report on failure; never substitute ordinary Resume.
- [x] Expose Train & rescan, 10% sample review, rollback, setup/failure states.
- [x] Preserve rejected findings and annotation row identities after rendering.
- [x] Verify production browser/API, real CPU training/export/inference/scan/
      render, packaging and focused regressions on Python 3.10.

Verification: Actions run 42424630173 passed targeted tests, real HTTP Chromium,
actual synthetic CPU training and ONNX execution, the scan loop and rendering,
and wheel/sdist build plus installed-module imports. The synthetic smoke uses
an injected original proposal detector; it does not measure plate-locator
recall. CUDA hardware, the complete CUDA image build and user footage remain
unverified. A broader local run stopped after a custom-regex/OCR assertion and
local browser networking restrictions; full-suite success is not claimed.

Rulings: keep original detectors as proposal sources. A crop-trained model is
not represented as detecting plates every original detector missed. Known human
geometry overrides predictions at matched source frames. Ambiguous negative
matches stay visible in review rather than blindly suppressing another object.
Empty model predictions never automatically unblur new objects. Only integrate
into integration/all-prs, never main. Training-enabled CUDA dependencies are
isolated from the application's CUDA OpenCV installation.
