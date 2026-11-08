# Corrected-polygon training crop fix

Goal: a polygon successfully saved in the review UI must not be rejected merely
because it extends outside the original detector's training crop.

Scope: learning_session.py and test_learning_session.py; document retry steps
in docs/VIDEO_LEARNING.md. Do not change inference crops, source/frame identity,
reviewed geometry, dataset thresholds, model dependencies, or CUDA setup.

- [x] Reproduce the reported error using actual Flask corner autosaves on
      synthetic video, including small boxes, skew, scroll offsets and edges.
- [x] Compute the verified polygon in source coordinates before cropping. Include
      its bounds and the original proposal in the training crop; normalize once
      against the actual clipped crop. Retain the original proposal for matching
      and baseline comparison. Never clip a real correction to the detector box.
- [x] Tolerate only the source-boundary error introduced by six-decimal saved
      coordinates. Reject malformed, crossed and genuinely off-frame polygons
      with the finding index/frame and recovery action. Preserve saved state.
- [ ] Run new tests red then green, focused regressions, full-suite attempt,
      syntax checks and CI. Publish through a PR to integration/all-prs only.

Review focus: positive/negative distinction; retry without reannotation;
unaltered report/manifest; frame-relative scroll offsets; subpixel rounding.
