# Secondary learned plate verifier

## Intent

Use learned negative examples to help reject false plate detections such as hands. A candidate that failed the tighter-mask gate may still be useful at distinguishing detector proposals from background. The already-exported candidate must remain discoverable and usable without another training run. All completed work is to be integrated into `integration/all-prs`, the user's combined testing branch.

## Evidence and approach

The current calibration examines only held-out positive masks. Low/empty learned predictions retain the original enabled proposal. Negative examples are trained as background, but their scores do not currently make an inference-time decision. This is a separate capability from tighter masking.

The selected approach is an explicitly selected secondary verifier using the existing ONNX crop model. Evaluate all held-out positives and negatives with the same proposal-association rule used at runtime. Offer suggestions regardless of whether useful separation is found; permit automatic filtering only when a separate assessment demonstrates rejection of some known negatives with no rejected held-out positives. This is the implementation choice, not an assertion that the user selected an exact algorithm.

Forcing a failed mask-refinement threshold to remove detections is rejected: that gate ignores missing positive predictions. Using this crop-trained model as a sole full-frame detector is outside this change; that requires full-frame training and multi-object detector integration. In filter mode the trained model makes the decision on the original detector's proposals.

## Behavior

- Existing mask refinement and schema-1 model packages retain their semantics.
- Completed candidate versions are listed from verified server-owned pass/version metadata. A candidate is never displayed as an accepted mask model merely because it is newest.
- Users can check an existing report using a candidate, with `review` (suggest) or `filter` (apply validated rejection) selected explicitly. No retraining or full detector scan is required for this operation.
- Filtering assessment uses at least four held-out positives and two held-out negatives. All positives count, including empty/low-score predictions. Choose a cutoff separating at least one negative from all observed positives; refuse filtering if that cannot be demonstrated. Suggestions remain available with a clearly unvalidated review cutoff.
- Associate prediction boxes with the original proposal before using their confidence, so an unrelated nearby plate cannot validate a hand candidate.
- Model scores are plate scores, not a probability that an object is not a plate.
- Keep machine decisions in `plate_verification`, distinct from human `verified_label`. Human decisions remain authoritative. Model-only suppression must not become a human correction or training label in later passes.
- Applying a new checker reconsiders prior machine-only decisions, but preserves explicit human overrides. Reports retain enough provenance to inspect which model/mode/threshold made a decision.
- Default new reusable verifier use is `review`; users explicitly choose `filter`. Store mode durably with each job snapshot before queueing and retain it through pause/restart/sections.
- Users can save an evaluated candidate as a reusable secondary model, export/import it, and select its use in Scan Setup. Schema 2 represents a verifier honestly and independently of mask acceptance. Packages still contain only ONNX and portable metadata.
- If mask calibration fails after successful training, explain that training completed, mask activation failed, and the candidate is available for secondary evaluation. Operational failures remain errors.
- Preserve recent progress, diagnostics, sections, vault, cancellation, atomic publication and existing review behavior.

## Trust and verification

Models remain trusted-source ONNX inputs; package checks are not an execution sandbox. Calibration reports observed counts rather than universal accuracy. Review suggestions and filtered findings remain visible and reversible through normal review controls.

Use synthetic images/video and actual small ONNX graphs for inference, transfer and browser tests. Test both old schema-1 and new schema-2 packages, corrupted candidate paths/hashes, insufficient or inseparable hold-outs, neighboring objects, human overrides, machine-label exclusion, paused boundaries, section handling and restart mode retention. Run focused tests and existing CI without hiding baseline failures.
