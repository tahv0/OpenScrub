# P16 mask fidelity research — N02 and N03

Date: 2026-11-17. **Research complete; no product fix implemented.** These are
two independently scoped ordinary-render candidates. Neither requires custom
training, compound holes, `mask_pad`, another report schema, or plate quads.
This supplements [preservation-audit.md](../../preservation/preservation-audit.md),
[core-semantic-audit.md](../../preservation/core-semantic-audit.md), and the
[P16 card](../../../03-packaging-and-review-features.md).

| Candidate | Disposition | Result and extraction boundary |
| --- | --- | --- |
| N02 native HDR silhouette chroma coverage | **Confirmed → minimal coverage contract/tests.** | Actual pinned production function misses required 4:2:0 cells in 26/48 sparse/edge/origin/padding cases; donor covers every touched cell without changing luma in these cases. A real short HDR render reproduces the missing cell before encoding. Extract only the luma-to-chroma union, retaining current rasterization/dilation/defaults. |
| N03 malformed/degenerate silhouette geometry | **Confirmed → minimal valid-box fallback contract/tests.** | Actual functions and ordinary report → actual HDR renderer throw on malformed/nonfinite polygons despite a valid finite box. Collinear/repeated contours produce tiny nonempty masks rather than full-box fallback. Two-point, empty, and wholly outside empty masks already fall back; retain them. Invalid-box handling is a separate unresolved P16 validation candidate below; polygon validation does not fix it. |

## Pinned source and execution provenance

- Baseline engine: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f` (Austin 1.0.96).
  `git diff --stat 5d3a15a e21ebdf -- openscrub.py` produced no differences;
  test-only `e21ebdf6e3ee46e6c65050dc956a9a3459152269` has the same engine.
- Donor: `8697c2811db6cfda644f730284e037f7294b47cc` (mixed compound-mask
  change; engine version 1.0.87). Imported solely as a reference namespace;
  do not copy its older whole file.
- Full engine files were exported with `git show <sha>:openscrub.py` and
  imported from task-owned `/tmp/openscrub-mask-fidelity-research`. The
  probes execute the actual functions, not a miniature renderer. Their
  independent coverage oracle enumerates global changed-luma coordinates and
  assigns each to `(row // 2, column // 2)`.
- Environment: sourced `/tmp/openscrub-baseline-20261116/env-opencv4.sh`;
  OpenCV 4.14.0, NumPy version recorded in results, installed FFmpeg
  `8.0.1-3ubuntu2`. One CPU affinity limits interference with P07; no timing
  measurements. No GPU, OCR, inference, model downloads, user media, network,
  product edits, Git mutations, app suite, browser tests or build.

Exact `openscrub.py` ranges, obtained from the pinned source AST:

| Owner | Baseline inclusive lines | Donor inclusive lines |
| --- | --- | --- |
| `Detection` / existing ordinary `poly` field | 731–748 | 705–727 (additional donor fields excluded) |
| `blur_silhouette` | 3181–3229 | 3070–3091 |
| `_blur_silhouette_yuv10` | 3684–3746 | 3429–3471 |
| `rasterize_mask` | absent | 3023–3067 |
| `render_hdr` | 3887–4059 | 3614–3775 |
| `render` | 4062–4299 | 3778–3992 |
| `load_report` | 6336–6364 | 5978–6010 |

## N02 — nearest resizing drops touched chroma cells

Baseline `_blur_silhouette_yuv10` lines 3734–3738 resizes the luma mask with
`INTER_NEAREST` to the half-resolution chroma ROI. Selecting samples from a
mask does not preserve the union of luma pixels that share a chroma cell.
Odd origins also change the alignment between the ROI and the global 2×2
subsampling grid. Donor lines 3436–3440 align the luma mask to that grid and
reduce every corresponding 2×2 cell with `max`; lines 3460–3463 use that
chroma mask. This behavior is separate from its new rasterizer/schema.

The 48 direct production-function cases combine four polygon shapes
(full square, sparse triangle, right-edge triangle, diagonal triangle), four
origin parities `(4,4)`, `(5,4)`, `(4,5)`, `(5,5)`, and padding 0, 1, 3.
They use 32×32 native 10-bit Y/U/V planes, the ordinary `box` redaction mode,
and ordinary normalized polygon coordinates. Baseline and donor luma masks
match in all 48. Baseline misses cells in 26 cases and adds an unrelated cell
in one case. Donor has no missed or extra cells; both chroma planes match the
oracle and all unrelated chroma cells retain their original values.

A particularly small regression is the triangle with local pixel vertices
`(1,1), (2,1), (1,2)` in a 12×12 box starting at `(4,4)`. It covers three luma
pixels and touches three chroma cells. Baseline changes **zero** chroma cells;
donor changes all three. At odd-x origin `(5,4)`, the same triangle touches
two chroma cells and baseline changes only one.

The donor's `test_hdr_odd_origin_covers_every_touched_chroma_cell` uses a filled
square at `(1,1,5,5)`. Its exact assertions pass on **both** production
implementations. Keep it as a control, not proof that N02 regressed.

### Actual 3-frame HDR render

The script creates a 64×64, 3 fps, 3-frame lossless HEVC source from synthetic
constant Y/U/V planes 900/800/300. Input color properties are explicitly set
before encoding; decoded source planes equal the raw input exactly. The
source and rendered outputs probe as `hevc`, `yuv420p10le`, `bt2020nc`,
`smpte2084`, `bt2020`; rendered outputs have three frames.

An ordinary report supplies `cbox=[5,4,17,16]` and the sparse triangle. The
baseline `load_report` and actual baseline `render_hdr` run with `libx265`,
ordinary `box` mode, pad 0, and no audio. A pipe observer copies bytes passed
to the encoder without changing commands or data. The contrast run replaces
only baseline `_blur_silhouette_yuv10` with the donor production leaf function
in the exported Python namespace; the baseline render loop and encoder remain
the same. This is an experiment, not an adapted product patch.

| Evidence | Baseline | Donor leaf in baseline renderer |
| --- | --- | --- |
| Luma pixels changed before encoding | `(y,x)=(5,6),(5,7),(6,6)` | same three |
| Required chroma cells | `(2,3),(3,3)` | same two |
| U before encoding at required cells | `800,512` | `512,512` |
| V before encoding at required cells | `300,512` | `512,512` |
| Unrelated chroma before encoding | unchanged | unchanged |
| Decoded output U at required cells | `614,556` | `520,518` |
| Decoded output V at required cells | `402,489` | `499,498` |

The exact encoder-input planes also equal a direct invocation of each
corresponding production leaf. The decoded output is lossy and may undergo
encoder/colorspace effects; its maximum plane differences from exact input
are recorded. Even unrelated decoded pixels change. **Use pre-encode plane
evidence for coverage, and ffprobe for output format/signalling.** This does
not establish a visible privacy leak or a quantified privacy improvement.

### Minimal delivery contract and gates

1. Keep the existing luma mask and fill modes. Each U/V cell is redacted iff
   any covered global luma pixel belongs to that 2×2 cell. Account for odd
   origins, final partial cells and clipped bounds; preserve unrelated cells.
2. Extract only the chroma mapping inside the existing owner. No new generic
   graphics framework, schema, mask padding override or hole semantics.
3. Add an independent touched-cell assertion that fails baseline for the sparse
   cases above; retain full-square controls. Include all origin parities,
   clipped/frame-edge cases, thin/diagonal edges, nonzero current padding and
   odd ROI sizes. This research covered frame-interior regions of even size;
   odd-size and clipped/frame-edge regression cases remain delivery gates.
4. Verify valid luma coverage and unrelated chroma unchanged, default blur and
   supported fill modes, current face/border behavior, requested P16 suite and
   real SDR/HDR outputs. The current direct and media probes use `box` for an
   exact sentinel; they do not certify every fill mode or packaged builds.

## N03 — validation/fallback differs from absent fallback geometry

Baseline `blur_silhouette` lines 3193–3214 and HDR counterpart 3691–3714
convert region bounds, unpack `poly_box`, convert/round point coordinates,
then call `fillPoly`. Empty resulting masks fall back to `blur_region` /
`_blur_yuv10`. There is no exception boundary around those conversions.
The SDR/HDR direct-function matrix contains 19 cases each, on both versions:

| Input with finite positive box `(4,4,16,16)` | Baseline SDR and HDR | Donor SDR and HDR |
| --- | --- | --- |
| Valid square | full-box coverage | same |
| NaN point | `ValueError` | full-box fallback |
| Infinite point | `OverflowError` | full-box fallback |
| Missing/extra point coordinate; nonnumeric coordinate | `ValueError` | full-box fallback |
| Two points; empty polygon; wholly outside polygon with empty mask | **already full-box fallback** | full-box fallback |
| Three collinear points | 12 luma pixels / 144-pixel box; no fallback | full-box fallback |
| Same point repeated three times | 1 luma pixel / 144; no fallback | full-box fallback |
| Invalid `poly_box`, valid separately supplied render region | conversion error for NaN | full-box fallback |

Donor `rasterize_mask` lines 3034–3066 validates finite polygon bounds,
point shape/finite values and contour area, then catches conversion/raster
errors and fills the **known valid region**. Its broad compound handling,
strict 0..1 coordinate rejection, arbitrary 10,000,000 coordinate ceiling,
padding changes and hole processing are not a minimal N03 extraction.
This research does not establish that all those extra restrictions are
appropriate for current upstream.

The actual HDR media probes read ordinary reports with existing `cbox` and
`poly` fields through baseline `load_report`, then call baseline `render_hdr`:

- NaN/Inf polygon coordinates and a one-coordinate point fail at the actual
  rasterization lines 3704–3706, reached from render line 4006. Ordinary
  malformed points are strict JSON. Python's loader also accepts its
  nonstandard JSON `NaN`/`Infinity` sentinels; these are synthetic corrupt
  inputs, not claims that a particular detector naturally emits them.
- A two-point polygon successfully renders with pre-encode changed counts
  Y/U/V = `144/36/36`, confirming existing full-box fallback.
- A collinear polygon successfully renders with `12/6/6`, confirming that
  nonempty degenerate rasterization bypasses fallback. Lossy decoded counts
  are not used to assess coverage.

### Invalid boxes are a different boundary

**Disposition: unresolved P16 input-validation/output-failure candidate.**
The runtime behavior is reproduced below, but its safe failure/publication
contract still needs implementation and validation independently of the
donor polygon fallback. A successful unredacted render is not a fixed result.

When the **render region itself** contains NaN, Inf or nonnumeric coordinates,
both baseline and donor throw before any guarded polygon fallback. Donor
`rasterize_mask` lines 3027–3033 convert the region before its `try` block.
Reversed and zero-width regions simply return without coverage in both
versions. The actual baseline report → HDR-render probes reproduce NaN-box
failure and reversed-box success with **zero changed pre-encode pixels**.

`load_report` lines 6353–6363 rehydrates `cbox`/`poly` without validating their
geometry. In the ordinary render path, that same translated `cbox` provides
both the render region and `poly_box`; a nonfinite/invalid cbox therefore
cannot be repaired by pretending its box is usable. The separate valid-region
with invalid-`poly_box` direct test is useful for the leaf contract but does
not establish that ordinary reports have independent fallback geometry.

### Minimal safe contract and gates

1. **Known finite positive box, invalid polygon:** use the existing full-box
   redaction over the clipped padded region in the selected mode. Preserve
   already-working empty-mask fallbacks. Validate point structure, finite
   conversion/int32 safety and degenerate raster geometry before painting;
   handle relevant conversion/OpenCV errors locally. Do not blanket-catch
   resource failures or silently skip the detection.
2. **Invalid source/translated box:** fail with a clear geometry error before
   successful output publication. Validate four finite numeric coordinates
   with positive extents; retain legitimate finite boxes extending outside
   the frame and ordinary clipping. An ordered finite box wholly outside
   the current frame can remain a known no-intersection case. A reversed,
   zero-area or nonfinite box has no justified fallback. Do not invent a
   full-frame blur or treat this error as an unredacted successful render.
3. Prefer validation before opening output encoders, retaining a defensive
   render boundary for callers that bypass report loading. Test preservation
   of existing reports/output on failure, explicit errors and process/partial
   output cleanup. Geometry exceptions currently escape after opening decoder
   and encoder subprocesses; the research harness terminates/tracks those
   subprocesses in `finally`. That observer cleanup is not a product fix.
4. Add ordinary report → actual SDR/HDR-render regressions for malformed and
   nonfinite polygons, two-point/empty controls, collinear/repeated contours,
   invalid boxes and valid clipped boxes. Assert full known-box coverage and
   unchanged outside pixels, or explicit unsuccessful output for invalid
   boxes. Preserve current padding/face defaults and valid contour behavior.
   No new fields, hole semantics, P17 quad policy or custom-model dependency.

This research confirms the conversion failures and degenerate-mask behavior;
the proposed safe validation/failure contract is not implemented or certified
across web/save/worker paths. Invalid-box error presentation, output lifecycle,
actual SDR end-to-end rendering, and the requested full P16 validation remain
delivery work. Neither this evidence nor the source audit closes P16 or B03.

## Reproduction and recorded artifacts

From the repository root, with only the installed synthetic environment:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/mask-fidelity-research-evidence/probe_masks.py \
  --output .superpowers/sdd/README/mask-fidelity-research-evidence/results.json \
  > /tmp/openscrub-mask-fidelity-research/run.log 2>&1
python .superpowers/sdd/README/mask-fidelity-research-evidence/verify_results.py \
  > .superpowers/sdd/README/mask-fidelity-research-evidence/summary.json
```

- [probe_masks.py](mask-fidelity-research-evidence/probe_masks.py): pinned full
  production imports, independent oracle, direct matrix, actual render and
  encoder-input observer. No Git checkout/index changes or downloads.
- [results.json](mask-fidelity-research-evidence/results.json): source ranges,
  all direct outcomes, exact masks/cells/counts, exception traces, real source
  and output probes, exact pre-encode versus lossy decode observations.
- [verify_results.py](mask-fidelity-research-evidence/verify_results.py) and
  [summary.json](mask-fidelity-research-evidence/summary.json): assertions of
  the recorded outcomes; verification passed. These are research checks,
  not the application test suite or a product patch regression suite.
- Exported modules, generated reports, raw input/pre-encode planes and small
  media remain under `/tmp/openscrub-mask-fidelity-research`, outside Git.

No fix branch, commit, PR, publication, build, app-suite pass or hardware
inference claim is made by this report.
