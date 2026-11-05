# Compound mask implementation

Goal: deliver PR1 as a useful, compatible engine and review improvement, with no new plate backend or experimental sources in its diff.

## Global Constraints

- Python >=3.9. Follow existing monolith structure; no unrelated refactor, version bump, or new model.
- Fail closed: invalid, empty, nonfinite or degenerate geometry renders the entire detection box. Legacy reports and poly-only silhouettes keep working.
- Additive report fields: `poly_holes`, aligned to `poly` (each entry is a list of exclusion rings for that outer component), and `mask_pad`, default -1 meaning inherit global padding; finite nonnegative values override base padding. Empty poly_holes means all components have no holes.
- Compose each outer minus its own holes, then union components, so another positive island inside a hole remains masked. Dilate positive coverage, then retain explicit hole exclusions belonging to each component. No hole may erase a different positive component.
- Rendering and review consume the same raster mask, including padding. Both SDR and 10-bit YUV must preserve exclusions; chroma uses conservative coverage aligned to frame pixels.
- Generated temporal interpolation must never copy compound holes into unobserved frames: use a box fallback for generated compound samples; preserve observed sample geometry. This foundation does not promise automatic plate inference.
- UI must show actual mask boundaries, disconnected parts and holes; plain bbox editing must explicitly convert shaped detections to full box masks rather than silently deform a hidden mask. Keep human review prominent.
- Synthetic fixtures only. No committed screenshots, models, plans or experimental scripts. Include production tests and concise report-format documentation with implementation.
- Required verification: full pytest suite, full python -m build, synthetic SDR video render and report inspection, HDR pixel tests, evaluated PAGE JavaScript syntax and actual browser interactions/screenshots (controller handles browser artifacts).

### Task 1: Implement compound masks across reports, rendering and review

Worktree: /workspace/scratch/3981d868e79c/openscrub-mask-foundation, branch feature/compound-redaction-masks, base 0852b127e4beea73e5ee3973f7268c08707afcc9.

1. Read project instructions and relevant Detection, report loading, interpolation, coverage, SDR/HDR silhouette render, web boxes_at, detframe and review canvas/edit routes.
2. Use TDD for meaningful behavior: first add focused tests and observe failures for compound exclusions and disconnected components, separate positive island in another component's hole, explicit zero margin, invalid geometry safe fallback, additive/legacy report roundtrip, HDR odd-coordinate conservative chroma, generated temporal sample fallback and review API/edit behavior. Extend test_openscrub.py; use hand-derived pixel expectations.
3. Add the two Detection fields above. Implement one shared mask rasterizer with bounded finite coordinate validation and safe fallback. Keep old blur_silhouette callers compatible through optional arguments. Route SDR/HDR through it; effective margin is explicit mask_pad or inherited global pad plus existing motion uncertainty. Handle companion fields anywhere poly is copied or cleared.
4. Extend load_report and serialize through existing asdict. Document field units and nesting plus invalid geometry fallback in relevant existing docs or a small docs/mask-geometry.md.
5. Expose effective mask outlines to review from the same rasterizer (including all contour topology). Draw mask areas and holes faithfully in canvas and full-frame review; keep bbox handles for interaction. Add a clear edit hint that moving/resizing a shaped mask converts it to a box. Edit route must clear shape fields and per-mask override on a bbox change. Existing unedited geometry survives save/load.
6. Run focused tests during iteration, then full python -m pytest test_openscrub.py -q once green; full python -m build; run a real synthetic video render through production render and inspect report. Extract PAGE's evaluated script bodies and node --check. Use workspace TMPDIR because /tmp is unavailable. Dependencies available in /workspace/scratch/3981d868e79c/plate-prototype-env/bin/python.
7. Self-review complete diff, commit focused implementation and tests/docs. Write full report including RED/GREEN and verification evidence to the assigned report path. Controller independently reviews and exercises browser UI.

No subagents. Ask controller for consequential ambiguities. Do not open PRs or push from this task.
