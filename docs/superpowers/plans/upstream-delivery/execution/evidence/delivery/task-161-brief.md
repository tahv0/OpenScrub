## Task 161: preserve every chroma cell touched by the existing luma mask

### Global constraints

Preserve Austin's Python>=3.9, existing face/mask/padding/encoder defaults and report geometry. No compound holes, schema additions, training, optional plate modes, new dependency/version, general raster framework or root helper. New tests under tests/, synthetic media only. No original-checkout/user-data edits, publication or subagents.

### What, why and when

Nearest-neighbor resizing of an ordinary silhouette mask to half-resolution chroma drops cells at sparse edges and odd origins. Existing actual-function research finds26/48 missed cases; actual HDR encoder input also loses a touched cell. A fully filled square control passes the old code and is insufficient evidence. Read `mask-fidelity-research.md` N02 and its retained oracle/media recipe. This is an independent small P16A PR, before optional plate features. The supervisor creates `pr/hdr-chroma-coverage` from Austin-plus-test-only `e21ebdf6e3ee46e6c65050dc956a9a3459152269` in the native worktree before dispatch. Donor `8697c2811db6cfda644f730284e037f7294b47cc` is provenance only; do not import its rasterizer/schema/default changes.

### Implementation contract

1. Change only luma-to-chroma mask mapping in existing `_blur_silhouette_yuv10`: each global U/V cell is selected exactly when any existing selected luma pixel belongs to its global2×2 cell. Account for odd origins, odd ROI sizes, final partial cells and frame clipping. Preserve the existing luma mask, dilation/padding and effect calculation, with unrelated U/V pixels unchanged.
2. Keep SDR rendering bit-for-bit unchanged for identical inputs/settings. Preserve supported redaction modes and current face/rectangle paths. No new shape fields, custom masks, coordinate ceilings or geometry-repair policy. Invalid geometry and comprehensive output/resource lifecycle stay P16B/C/N09.
3. Add `tests/test_hdr_chroma_coverage.py` with independent oracle built from global selected-luma coordinates, not the implementation's reduction. Establish sparse-triangle RED, keep filled-square control; cover all four origin parities, thin/diagonal edges, clipped/frame edges, odd sizes and padding0/1/3. Check exact luma and U/V cell identity; exercise every mode supported by this owner with values that make the coverage assertion meaningful.
4. Exercise actual ordinary report→run_render→HDR with a tiny lossless10-bit PQ/BT.2020 input and actual libx265, observing the exact bytes passed to the encoder without altering them. Preserve current SDR output control and HDR frame count/format/colour signalling. Lossy decoded pixels are not an exact mask oracle and do not establish quantified privacy improvement. Observe/clean actual children/streams in the harness, including RED failures; this task does not claim broad production exception cleanup.

### Evidence and delivery

Run focused RED→GREEN, one full discovered suite after stabilization, sdist→wheel plus source/test bytes and installed CLI/web smoke; focused actual-source Python3.9 checks using prepared environment. No browser change means no unrelated browser run. Necessary tests/ discovery and README/CONTRIBUTING python -m pytest guidance only; no model downloads, new dependencies, timing benchmark or hardware claims. Artifacts `/tmp/openscrub-task161`. Reuse existing env-opencv4.sh, Python3.9 env and offline build tools, asserting import paths. Native worktree/Git edits may need already-authorized require_escalated.

Self-review and commit; write `task-161-report.md` and `task-161-pr.md` in this SDD workspace with exact base/head, original failure, coverage/mode matrix, real pre-encode/output distinctions, commands/results, changed files and limitations. Lead with the concrete subsampling defect and unchanged luma/defaults. No publication or nested agents.
