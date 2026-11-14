# Safe, frame-specific license plate boundaries

OpenScrub separates **finding a candidate plate** from **deciding the exact
pixels that may be hidden**, and from **human classification**.

## What the colored geometry means

- **Yellow dashed rectangle**: primary YOLO detector proposal. Its corners
  are computed from a bounding box, not measured physical plate corners.
- **Red area**: actual protected mask on the pictured source frame.
- **Green**: output remains visible due to the indicated decision. A secondary
  model decision is not the same as human evidence.
- **Cyan corner handles**: a human-editable quadrilateral on the exact source
  frame that was loaded.

Review now displays the geometry source alongside the picture:
`Human corrected corners`, `Learned perspective boundary`,
`Learned rotated rectangle`, `YOLO detector rectangle`,
`Detector box · learned outline rejected`, or
`Tracked detector box · corners not tracked`.

**A group of 120 sightings has 120 source-dependent proposals.**
Choosing *Is a plate* or *Not a plate* may classify the whole physical track;
dragging corners only establishes geometry for **the displayed source frame**.
Other frames keep independently learned geometry, their own verified human
geometry, or protective detector coverage. Normalized corners from one
rotation are never reused blindly on another source frame.

## Source binding

A cached review JPEG can come from a nearby frame of the same track. This is
useful for fast scanning through findings but is *not* proof that its geometry
belongs to every frame in the group.

If Review loaded such a picture, its editor offers **Load exact frame for
corners**. Until that exact frame is displayed, new corner edits are disabled
and the server rejects attempts to attach the borrowed picture's narrow
polygon to the requested source frame. Loading the exact frame on demand may
decode original video and take longer than an ordinary cached thumbnail.

## Learned mask to four corners

For every actual source frame evaluated by a reusable segmentation model:

1. If the learned mask score is below the selected model's accepted
   refinement threshold, keep protective detector coverage.
2. For a sufficiently strong mask, fit a convex, perspective-aware four
   corner polygon to its contour, including a small safety expansion.
   Only use a rotated-rectangle approximation when no enclosing perspective
   quadrilateral can be found.
3. Require at least 99.5% coverage of the *predicted dilated mask* and
   validate plausible extent, non-degeneracy, source-frame bounds, size and
   alignment with the original detector proposal. A small unrelated blob
   must not replace a large detector box.
4. Check adjacent learned source frames for major contradictions. Such
   frames fall back to their individual detector boxes rather than
   interpolating an unverified narrow mask across rotation or dropout.

These checks prevent known geometry failure modes. **Predicted-mask coverage
is not ground-truth plate-character coverage.** It does not prove no
characters will leak from an unseen or poorly trained model. Automatic
mask refinement must still pass human/held-out validation and be reviewed
on real footage. When in doubt, retain the original full-plate box.

Unlike per-frame segmentation, manually tracked regions retain their
**continuous time-spanning** tracked bounding boxes, including between the
sampled tracker positions. Only at the exact drawn source frame may they
substitute the human quadrilateral; a distinct `plate_quad_frame` marker
controls that use without restricting the tracked box's active time span.
The existing tracker predicts box positions, *not* physical corner motion.
All other covered frames remain enabled with the protective box.

When reopening older jobs, a plate quadrilateral lacking trusted source
provenance is treated as detector-box coverage, unless there is source-bound
human confirmation or independently established learned geometry. This
guards against old review code that duplicated the same narrow corners over
multiple different frames in a track.

## Training feedback and model scores

Only explicit saved human corrections are training evidence. A corrected
quadrilateral is a plate *boundary example on that source frame*, not a
perfect outline for every frame of a track. Confirmed false positives
(e.g. tools or hands) become negative examples through **Not a plate**;
the output-only **Keep visible** control is not an equivalent training label.

The secondary verifier's `plate score` and the primary YOLO confidence are
different model outputs, not comparable calibrated probabilities. A real
plate receiving a 1–3% verifier score is reason to audit the model, crop,
proposal-association and held-out validation, **not** to expose it
automatically or to trust its boundary. Review suggestions and explicit
validated filter mode remain separate from physical-boundary refinement.

## Tests

`test_plate_boundaries.py` validates trapezoid fitting, perspective,
coverage, source bounds, tiny false-positive masks and temporal fallback.
`test_video_learning.py` exercises independent per-frame inference and
human-authoritative shapes. `test_findings_web.py` and
`test_plate_quad_editor.py` prove source-bound human geometry is not
propagated to sibling frames, while human classification still applies to
the group. `test_review_browser.py` tests exact-frame loading in Review.

This change does **not** train or benchmark a new model on the user's
private video. A reliable segmentation model and representative manually
corrected positive/negative examples are still necessary for physical-edge
accuracy on that footage.
