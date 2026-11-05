# Precise and narrow plate modes: first application preview

## Intent

Support the full shape-aware redaction scope discussed with the user, including
rotated plates, perspective-skewed trapezoids and arbitrary quadrilaterals,
separate visible plate pieces, and foreground objects covering part of a plate.
Only the visible target surface should be processed when its geometry is known.

Also provide a separate narrow mode that hides the license-number lettering
while leaving plate background and borders visible. Its chosen extra safety
margin is zero by default; one pixel or another nonnegative margin can be
selected explicitly. Narrow mode complements precise visible-plate masking;
it does not replace it. The original full-plate mode remains the default.

This document proposes the first application integration. The experiments are
already published separately on `prototype/precise-plate-masks`; they are not an
installed application feature.

## Scope and approaches

The first application-preview scope includes both precise visible-plate masks
and narrow lettering masks. A narrow-only implementation must not be described
as completing this design. Implementation can be staged internally, but rotated
and angled outlines, separate visible pieces, and occluder exclusions remain
requirements rather than deferred follow-ups.

## Pull-request boundaries

Deliver this scope through focused PRs rather than one combined change:

| PR | One cohesive change | Dependency |
| --- | --- | --- |
| Mask geometry and review fidelity | Topology-preserving contours/components/exclusions, per-mask margins, additive report round-trips, matching SDR/HDR output and review overlays, invalid-mask fallback, and their tests. | Upstream main |
| Precise plate masking | Automatic rotated/perspective outlines, separate visible plate parts and occluder exclusions, frame-to-frame updates, a validated refinement backend, mode controls and documentation, and their tests. | Mask geometry PR |
| Narrow plate lettering | Plate-local text regions, zero-extra-margin option, lettering-specific fallback checks, frame handling, CLI/UI controls and documentation, and their tests. | Mask geometry PR; independent of precise backend |

Engine, report, UI, documentation and tests necessary for one complete behavior
belong together in that behavior's PR. Do not split a working feature into
separate backend/UI/test PRs. Precise and narrow may be developed independently
once the shared geometry contract is stable; neither is removed from this
application-preview scope if the other finishes first.

Keep the published exploratory scripts and this planning history outside the
production PR branches. Each PR must contain only its own functional delta,
tests and relevant user/developer documentation. Open the foundation PR against
upstream main first. Feature branches may develop from it in parallel; once it
merges, rebase each feature's own commits onto the updated upstream main before
opening its upstream PR. Optional fork-internal draft reviews can target the
foundation branch, but an internal PR cannot change its base repository: create
a new upstream PR after the dependency is available there.

The foundation has independent value for existing polygon-bearing reports,
including person silhouettes: review their actual geometry, edit safely, and
export matching SDR/HDR output. Each feature PR exposes only its implemented
coverage mode, so narrow-mode UI does not require unfinished precise-mode code
and precise-mode UI does not require unfinished narrow-mode code.

Alternatives considered:

- Whole-plate segmentation: the EfficientSAM prototype reduced excess coverage,
  but missed an interior occluder and cost about 1.9 seconds per crop on the
  available CPU host. It is a research candidate, not an accepted backend. Its
  limitations require a better method or further validation, not removal of
  visible-surface segmentation from the scope.
- Four-corner plate detection: useful for perspective, but targets the plate
  surface rather than lettering and cannot identify separate visible fragments.
- Plate-localized text regions: directly fits narrow mode and reuses the existing
  pinned 4,826,518-byte detector. It cannot alone satisfy precise plate masking.

The proposed architecture keeps the existing plate detector as a locator, adds
shape refinement for precise mode, and uses plate-localized text for narrow
mode. Additional local models are allowed only when small enough to be practical,
appropriately licensed, hash-pinned, and measurably useful for the requested
geometry. No new model has yet met that acceptance bar for all occlusion cases.

## Resulting behavior

1. Add `full`, `precise`, and `narrow` plate-coverage choices to the CLI and scan
   setup UI. Full is the existing behavior and default. Precise masks the actual
   visible plate surface; narrow targets the number lettering. Expose explicit
   extra margins in source-image pixels. Narrow defaults to zero; negative or
   nonfinite margins must be rejected. Precise uses an explicit small margin
   chosen through validation, without inheriting the two existing box buffers.
2. In precise mode, preserve actual orientation and perspective: tilted
   rectangles, trapezoids, and scalene quadrilaterals must not be converted back
   into axis-aligned or rotated rectangular covers. Retain non-convex outlines
   where needed. Four corners are useful for an intact plate but insufficient
   for an occluded plate.
3. Represent all separate visible regions of one physical plate in the same
   frame. Do not join them with a convex hull or cover the intervening space.
   Support enclosed holes/exclusions for foreground occluders as well as
   disconnected regions; do not fill holes during contour extraction,
   simplification, serialization, rendering, or padding. Apply known exclusions
   after outward padding so padding cannot erase them. Newly exposed lettering
   must be covered when an occluder moves away.
4. Locate plates with the existing selected plate detector. In narrow mode,
   locate dominant number-sized text regions within each plate crop. Restore
   the detector's shrunken DB kernels consistently before applying the user's
   extra margin; zero extra margin must not erode the detected lettering. Keep
   separate number groups, hyphens and multiple rows covered; surrounding plate
   background is allowed to remain visible.
5. Pass the complete target geometry through report persistence, review overlays
   and both SDR/HDR render paths. Show the shape that will actually be redacted,
   including all components and holes. Review must support correction through
   compatible controls or clearly revert to full-plate coverage when a shape
   cannot be corrected. Do not silently scale a hidden polygon through box edits.
   Existing blur, mosaic, solid-fill and inpaint choices use that same mask.
6. Missing models, empty/invalid geometry, or evidence of uncovered lettering
   use full-plate coverage and record a visible fallback reason. The prototype's
   residual-stroke check is a starting heuristic, not a completeness guarantee.
   Preserve the existing human-review workflow without adding a new mandatory
   confirmation step. Persistent fallback on a requested geometry is an unmet
   feature/quality case, not evidence that precise or narrow masking works there.
7. Fresh narrow geometry must not acquire the existing full-plate percentage
   expansion, global eight-pixel buffer or scroll-drift padding. Apply only the
   selected narrow margin. Precise mode likewise uses its own explicit margin.
   Full-plate fallbacks retain their original padding.
8. Follow motion, changes in rotation/perspective, and changing occlusions over
   time. Never stretch stale lettering masks or a stale plate outline onto
   unseen frames; never carry an old hole onto newly exposed plate content.
   Refresh or propagate valid geometry, and use conservative full-plate geometry
   for uncertain/interpolated samples. Existing scan-speed choices must not
   silently turn shape-aware geometry into stale masks or create avoidable
   alternating narrow/wide cover flicker.

## Constraints

- Base implementation on upstream `main` at `0852b127e4beea73e5ee3973f7268c08707afcc9`
  (engine version 1.0.87), incorporating its scan-speed/interpolation changes.
- Report changes are additive; old reports remain readable and re-renderable.
- Reuse the existing text detector and the model download, cache, hash
  verification and execution-provider infrastructure. Any additional model must
  meet the user's small-and-useful condition and document its size, output
  geometry, permissions and measured benefit. Add no PyTorch runtime by default.
  Do not assume EfficientSAM is accepted merely because it was prototyped.
- Preserve the package's declared Python >=3.9 compatibility and its existing
  Windows/Linux deployment paths; do not raise the version floor for this mode.
- Use synthetic committed fixtures only. Keep license and model notices.
- Keep normal full-plate jobs unchanged and keep human review prominent.
- Do not call synthetic results real-world validation. Do not claim a mask is
  complete solely because a confidence score or geometry heuristic accepts it.
- This produces a testing build and upstream PR; official release/versioning
  stays with the upstream maintainer. Do not publish a PyPI release or tag as
  part of this integration.

## Validation and readiness

The experimental 12-case narrow comparison preserved all 21,015 labeled visible
glyph pixels after five full-plate fallbacks, including two false-positive
rejections. Its ungated output missed a whole exposed character in an occluded
case. A rotated example also covered substantially more background than desired.
These are development fixtures, not independent acceptance evidence.

Required acceptance cases:

- An in-plane rotated plate: the precise mask follows its edges and spares
  background corners; narrow mode targets the number rather than the plate.
- Trapezoidal and scalene perspective views: actual quadrilateral geometry
  survives detection/refinement, report reload, review and export.
- A plate with separate visible pieces: all pieces are covered and the space
  between them stays untouched when the geometry is known.
- An occluder entirely inside a plate: its exclusion remains visible through
  masking and padding. The prototype's filled 441-pixel hole is a failing case.
- Moving plates and occluders: orientation updates, newly exposed letters are
  hidden, and old exclusions do not cause gaps in coverage.
- Narrow number text with hyphens, separate groups and two rows: zero/positive
  added margins behave explicitly, while plate borders/background can remain.
- Invalid/missing geometry or models: visible, tested full-plate fallback without
  exposing original lettering. Include false-positive fallback measurements.
- Unchanged legacy/full mode, additive report round-trips, review/render
  agreement, frame gaps, and SDR/HDR sampling.

Measure missed target pixels, unwanted background coverage, preserved occluder
pixels, fallback rates and CPU/GPU processing cost separately. Synthetic
geometry correctness and real-footage model quality are separate checks; do
not claim the automatic feature is complete from renderer-only mask tests.

Before opening the production PR, run the full `test_openscrub.py` suite, a full
sdist-to-wheel `python -m build`, a real render of a synthetic video with report
inspection, and browser checks of the changed scan/review controls. Include an
honest comparison and remaining limitations in the PR description.

## Choices left to implementation

Choose internal names, a topology-preserving mask representation and additive
report fields, module boundaries, and a frame-update strategy. The current
positive-polygon union cannot encode enclosed exclusions by itself; extend it
without breaking legacy masks. Validate an automatic shape-refinement backend
before treating it as accepted. Reuse existing review controls where possible,
adding the shape-aware overlay/correction support needed for these requirements.
Keep prototype-only code out of application imports. Do not remove a required
geometry case merely because the first candidate model fails it.
