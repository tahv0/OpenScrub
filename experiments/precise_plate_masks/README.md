# Precise plate masks: evaluation prototype

This is a throwaway experiment, not a supported OpenScrub feature. The approved
scope is to compare current rectangles with EfficientSAM-Ti masks on entirely
synthetic rotated, perspective, moving, and partially occluded plates. Measure
missed plate pixels, unwanted coverage, and CPU processing time before proposing
a production change. Production engine files and defaults remain untouched.

## Run

Use Python 3.10+ with `numpy`, `opencv-python-headless`, and `onnxruntime`.
The evaluated environment's exact versions are recorded in `metrics.json`.

```sh
python experiments/precise_plate_masks/evaluate.py \
  --models /path/to/model-cache \
  --output /path/to/results --threads 2
```

The command downloads only the two official EfficientSAM-Ti ONNX files if missing,
then checks pinned SHA256 digests before inference. Total: 41,365,489 bytes.
Model source: <https://huggingface.co/yunyangx/EfficientSAM/tree/main> (listed
Apache-2.0). The optional model is not registered, bundled, or enabled in OpenScrub.
No PyTorch runtime or OCR/recognition of plate identifiers is involved.

## Method

- Correct bounding boxes derived from fixture geometry stand in for detector
  outputs. This isolates mask refinement; it does not test detection recall.
- Boxes expand 8% per side. The reference uses the actual OpenScrub rectangle
  renderer and its default eight-pixel render padding.
- Each model input is a crop with context. Two box-corner prompts, labels 2/3,
  identify the target. The highest predicted-IoU mask is selected, without access
  to ground truth. All pixels/components/holes are retained as a raster mask.
- Record raw masks, masks dilated eight pixels (the same render padding as the
  reference), and masks dilated three pixels. Report redacted occluder pixels
  separately from background; a filled interior occluder is a failure to preserve
  that object, even when total plate coverage is complete. For illustration, a proposed
  score rule accepts quality >=0.85 and nonempty masks, otherwise using the
  baseline rectangle. This rule is not validated and cannot certify safety.
- Warm the model once; record encoder and decoder latency for each remaining
  case with two ORT CPU threads. Shared-host timings are indicative, not portable
  hardware benchmarks. Initial model load/download is excluded.
- Solid black fill makes mask boundaries visible. Comparison includes source,
  current rectangle, eight-pixel refined mask, and three-pixel refined mask.
  Score-based fallback is recorded numerically; it is not a validated safety rule.

## Limits and next decisions

Synthetic performance cannot establish real-world plate segmentation quality.
Small text, glare, plate surrounds, similar-colored objects and changing
occlusions can produce confidently incomplete masks. No precision/area heuristic
can establish full coverage without a validated domain-specific method.

The application's positive-polygon renderer cannot yet represent enclosed holes;
this prototype uses direct raster compositing, not a claim that holes already work
in production. Production integration would also need validated mask confidence,
temporal handling, additive report serialization, consistent review overlays,
HDR sampling, and synthetic render regressions.

If the model misses visible plate pixels, the experiment must report that openly;
it is not a reason to enable the model by default or silently trust its score.

## Initial observed result (10 synthetic cases)

Both the eight-pixel and three-pixel refined candidates covered all 100,638
labeled visible plate pixels. With the same eight-pixel render padding, extra
coverage fell from 124,212 to 47,989 pixels (61.4% reduction). Three-pixel
padding reduced extra coverage further to 17,425 pixels (86.0%), but changes the
safety-margin choice and is not a like-for-like padding comparison.

Raw masks missed 1,445 plate pixels. The model completely covered the 441-pixel
interior occluder even before dilation; it did not meet the full visible-only
objective. On the disconnected-cross case, raw masks preserved 93.0% of occluder
pixels over the plate, versus 48.8% after 3px dilation and 4.2% after 8px dilation.
Padding therefore needs explicit treatment around foreground exclusions.

The score rule rejected none of these ten samples, so this run does not validate
fallback behavior. Warmed median inference was about 1.86 seconds per crop with
two CPU threads on a shared execution host. ORT warned that CPU feature detection
was unavailable; this is an observation, not a representative hardware benchmark.

Conclusion: the shape-refinement direction is promising, but these results do
not justify production integration or default enablement of this model.

## Narrow mode: hide the lettering, retain the plate background

The follow-up `narrow.py` prototype changes the target from the whole visible
plate to the main number lettering. It reuses OpenScrub's existing PP-OCRv5
text detector (4,826,518 bytes), without recognizing, logging or storing the
number. EfficientSAM is not needed for this path.

```sh
python experiments/precise_plate_masks/narrow.py \
  --models /path/to/model-cache \
  --output /path/to/narrow-results --narrow-padding 0
```

`--narrow-padding` is an explicit extra outward margin in source-image pixels;
it defaults to **zero**. The report also shows one pixel more. This parameter
comparison shares the zero-padding rejection decision for both variants.
The extra-pixel column isolates padding; it is not an independently gated run.
The parameter
does not shrink or erode a text detection. DB's shrunken text kernels still
need geometric restoration, separately from the user's extra margin. Text
regions are rotated rectangles, not a pixel-perfect mask of individual ink.

The prototype crops each supplied plate box, detects text at a 640-pixel long
side, restores DB minimum-area boxes using `1.5 * area / perimeter`, and filters
tiny captions by relative text height. It retains multiple text rows/regions.
Same-size auxiliary plate text cannot reliably be distinguished by this
geometric heuristic. The first 10 fixture images remain byte-identical;
visible glyph ground truth was added, plus two-row and hyphenated examples.

An empty text result falls back to the whole plate. A second image-only check
looks for uncovered character-sized contrast strokes aligned with the detected
text. It uses black/top-hat morphology to avoid merging an exposed character
into a foreground pole, then size/alignment filters. Residual evidence also
falls back to whole-plate coverage, with an explicit reason in the report.
Passing this check is not a proof of complete text coverage.

In the current 12-case synthetic run, zero-extra-padding results cover all
21,015 labeled visible glyph pixels after fallback. Five cases fall back:
the cross obstruction has no detected text; the interior obstruction and one
moving pole have residual-text evidence; glare and two rows are false-positive
rejections. The ungated detector misses visible characters in an occlusion
case, so zero padding alone must not be presented as sufficient. Including
fallbacks, the zero-padding variant preserves 35.1% of visible plate-background
pixels that the existing rectangle hides. Some detected text regions are still
larger than desired, particularly the rotated example.

This is an opt-in prototype comparison, not an enabled production mode. Review
overlays, manual correction, temporal consistency and real-footage validation
remain necessary before preparing an application integration PR.
