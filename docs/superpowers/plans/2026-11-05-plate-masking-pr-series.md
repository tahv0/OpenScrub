# Plate masking PR series

This delivery plan records the user's request to group closely related changes
and separate independently useful features. It does not claim that the
production features have been implemented or that upstream PRs already exist.

Design: `docs/superpowers/specs/2026-11-05-narrow-plate-mode-design.md`.

## Branches and review units

### 1. Compound mask geometry and faithful review

Branch: `feature/compound-redaction-masks`.
Initial base: upstream `main` (currently `0852b127e4beea73e5ee3973f7268c08707afcc9`).

Keep these related changes together:

- Preserve arbitrary polygon orientation, disconnected components and enclosed
  exclusions through a backward-compatible report representation.
- Rasterize the same geometry in SDR, HDR and review previews. Support explicit
  per-mask margins without refilling known occluders.
- Make malformed geometry fail closed, and make review edits handle geometry
  explicitly instead of silently changing a hidden mask.
- Include synthetic geometry, report, render, padding and review regressions.

This PR supplies usable mask support; it does not add a plate model, a new
automatic plate mode, or an unrelated UI redesign. Its standalone acceptance
example loads an existing polygon-bearing report (such as person silhouettes),
shows the actual mask during review, handles edits safely, and exports matching
SDR/HDR geometry.

### 2. Automatic precise plate masks

Branch: `feature/precise-plate-masks`.
Base: compound-mask foundation, updated to upstream main after foundation merges.

Keep these related changes together:

- Detect/refine rotated rectangles, perspective trapezoids and arbitrary
  quadrilaterals; preserve non-convex visible outlines where required.
- Retain separate visible plate pieces and occluder holes, including when
  obstructions move and plate content becomes visible again.
- Integrate and document a validated, practical refinement method, plus any
  necessary optional model registration, hash pins and attribution.
- Add precise-mode settings, frame handling, visible fallback reasons and tests
  demonstrating both target coverage and reduced unwanted coverage.

The refinement/model acceptance check is a real prerequisite. The failed
EfficientSAM hole case cannot be relabeled complete or replaced by a permanent
full-box fallback. Do not open a ready-for-review implementation PR containing
only an empty backend or a model whose benefit has not been established.

### 3. Narrow number-lettering masks

Branch: `feature/narrow-plate-mode`.
Base: compound-mask foundation; no dependency on precise-mode model work.

Keep these related changes together:

- Reuse plate-local text detection without reading or storing the number.
- Target lettering groups, hyphens and multiple rows, leaving plate background
  visible; default to zero additional source-pixel margin.
- Include configurable margin, temporal handling, full-plate fallback for
  uncertain text, CLI/UI controls and report/settings persistence.
- Test actual lettering coverage, retained background and explicit fallback
  behavior; retain known false-positive fallback cases in the documentation.

This can be reviewed independently of automatic visible-surface segmentation,
but it must not be described as completing the precise-mode requirement.

## Review and merge process

- Keep `prototype/precise-plate-masks` as the research branch. Keep design/planning
  commits on `planning/plate-masking`; neither is a production PR base.
- Start the foundation branch directly from upstream main. Start each feature
  branch from the reviewed foundation commit, not from the other feature branch.
- Open the foundation PR against `austinmabry/OpenScrub:main`. Once it merges,
  replay/rebase each feature's own commits onto the updated upstream main and
  open its separate upstream PR with only that feature's delta.
- Optional early draft reviews within `tahv0/OpenScrub` can target the foundation
  branch and show clean feature-only diffs. Those are internal reviews: a PR
  cannot switch its base repository, so create a new upstream PR when ready.
- Each feature exposes only its implemented mode; shared controls must not
  expose placeholders for the other feature or force a dependency on its code.
- Before publishing a production PR, inspect its file list and diff. Exclude
  prototype scripts, generated reports/images, downloaded weights, internal
  planning documents, unrelated formatting, and unrelated version changes.
- Each functional PR includes the tests and relevant docs needed to review it;
  no separate tests-only or docs-only PR for the same behavior.
- Run the full existing pytest gate and full sdist-to-wheel build for each PR.
  For engine changes, render a synthetic video and check the report. For web
  changes, check evaluated JavaScript and exercise the affected UI.
- Open drafts for concrete work in progress, promote them after the applicable
  checks pass, and record dependencies and remaining limitations in each body.
- Preserve all requested geometry/occlusion/narrow-mode acceptance cases across
  the series. The final testing build includes both features when validated.

## Preparation status

- [x] Research branch published in the user's fork.
- [x] Full requirements retained in the design.
- [x] PR boundaries and dependencies recorded.
- [x] Foundation implemented and verified (149 tests, build, render and real browser).
- [ ] Precise backend validated, implemented and verified.
- [x] Narrow mode implemented and verified in the application (192 tests, build,
  real text-model inference and real browser).
- [x] Fork review PRs opened with clean feature-only diffs and screenshots:
  [compound masks](https://github.com/tahv0/OpenScrub/pull/1) and
  [narrow mode](https://github.com/tahv0/OpenScrub/pull/3), stacked in that order.
- [ ] Upstream PRs submitted. The integration rejected upstream creation with
  `Resource not accessible by integration`; fork access remains functional.

Automatic precise segmentation remains blocked: both evaluated candidates
missed visible lettering or redacted occluders. The foundation supports shaped
geometry but does not supply that missing automatic backend. Narrow mode uses
conservative full-plate fallbacks; 11 of the 12 harder synthetic cases fell back.
It supports SDR export only, and exact late-frame review can be slow because
it decodes from the start. The full requirements remain in the design.

Verified screenshot/evidence commit:
`94319da56d2fec2c31bdedea2fc5ca1f27b5c7b6` on the fork's
`evidence/plate-pr-screenshots-20261105` branch. Production diffs exclude the
evidence and validation machinery. Nothing was merged or released.
