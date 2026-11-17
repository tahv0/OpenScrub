## Task 162: retain full known-box coverage when polygon data is unusable

### Global constraints

Preserve Austin defaults, Python>=3.9, supported redaction modes, existing report/Detection shape and valid polygon behaviour. No compound holes, mask_pad, schema/custom model/training additions, arbitrary coordinate caps or whole-frame fallback. Tests under tests/, synthetic fixtures only. No original-checkout/user-data edits, publication or subagents.

### What, why and when

Malformed/nonfinite polygon coordinates currently throw despite a valid known box; collinear/repeated points create tiny nonempty masks that evade existing fallback. The actual baseline/control evidence is `mask-fidelity-research.md` N03. This separate P16B PR extracts the ordinary safe fallback from mixed donor `8697c2811db6cfda644f730284e037f7294b47cc`, independently of P16A and plate features. Supervisor creates `pr/invalid-polygon-fallback` from `e21ebdf6e3ee46e6c65050dc956a9a3459152269` before dispatch. Read the report/recipe and only relevant source; do not copy donor whole files or repeat all research.

### Implementation contract

1. Given a valid finite positive render box, unusable polygon or poly_box data must select the existing full-box redaction over the same clipped/padded region in the requested mode. Preserve already-working absent/empty/two-point/empty-clipped fallback. Never silently drop a detection because its polygon is malformed.
2. Validate point shape and finite representability before conversion; guard int32 conversion and degenerate raster geometry. Preserve valid clipped contours, including coordinates outside0..1 when the existing path clips them legitimately. Use real representational/geometry bounds, not the donor's arbitrary10000000 cutoff. Handle only relevant conversion/OpenCV failures locally; resource/programmer errors are not permission to suppress output failures.
3. SDR and HDR must use equivalent fallback decisions without broad renderer rewrite. A small local shared helper is justified if it eliminates duplicated validation/raster decisions; if one owner remains small, no module merely for structure. Preserve existing padding/dilation, luma coverage, colour/encoder policy and P16A's separately scoped chroma behaviour on this base.
4. Invalid cbox is NOT a usable known fallback: keep the P16C-G rejection/publication contract separate. Do not claim this PR repairs nonfinite/reversed/zero-area boxes or preserves prior video on arbitrary failures. Valid boxes extending outside the frame and normal empty intersections remain legal.

### Evidence and delivery

Add meaningful regressions in `tests/test_polygon_fallback.py`: malformed/nonnumeric/nonfinite/extra-or-missing coordinate/unsafe-int conversion polygons, invalid poly_box with a separately valid render box, collinear/repeated points, existing empty controls, valid clipped/concave shapes and each supported mode. Expected fallback compares actual full-box renderer output; valid paths compare original behaviour and unrelated pixels. Establish RED through production functions and actual ordinary report→SDR/HDR rendering with synthetic small clips. Keep pre-encode exact coverage distinct from lossy decoded output. Give test harness unconditional real child/stream cleanup, particularly for baseline exceptions; no production resource-lifecycle claim from harness cleanup.

Run focused RED→GREEN, relevant geometry/render checks, one stabilized full discovered suite, sdist→wheel/source/test inclusion and installed CLI/web smoke, plus focused active-source Python3.9. No browser UI change, models/downloads/heavy benchmark needed. Necessary branch-local discovery/docs only. Artifacts `/tmp/openscrub-task162`; reuse existing isolated env-opencv4.sh, Python3.9 env and offline build tools. Native worktree/Git writes may need already-authorized require_escalated.

Self-review and commit. Report/draft `task-162-report.md` / `task-162-pr.md` in this SDD workspace: exact base/head, known-box trigger, validation/fallback policy, preserved controls, real versus controlled execution, commands/results and separate invalid-box/output-lifecycle limitations. No publication or nested agents.

### Degeneracy compatibility clarification

Choose the degeneracy rule against usable two-dimensional shape geometry, not zero signed contour area alone. Preserve existing supported concave and usable self-intersecting contours; include an actual baseline control before deciding that a contour must fall back. Collinear/repeated/quantized-unusable geometry still needs the known-box fallback. This does not add compound holes or new polygon semantics; it prevents a validation shortcut from unnecessarily widening an already usable upstream mask. G's primary-box rejection must not preempt this task's invalid-poly_box fallback when the separate render box is valid.
