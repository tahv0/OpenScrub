# Precise visible-plate backend validation

## Decision: blocked

No tested backend establishes the requested automatic visible-only mask behavior. EfficientSAM-Ti is a real local pixel-mask model and handles some rotated, perspective and disconnected shapes on the existing synthetic fixtures, but fills the entire enclosed occluder and its raw masks miss visible plate pixels. Its own quality score did not flag that failure. A second, smaller TFLite model was run on 12 synthetic full-frame fixtures in CI; it missed substantial visible plate and lettering pixels and filled the interior occluder. Neither tested model meets the requested objective. These observations are not real-footage validation.

## Existing measured EfficientSAM-Ti experiment

The prior run used 10 synthetic scenes and geometry-derived boxes, hence it tests refinement conditional on a correct detection, not detection recall. The model selects its highest predicted-quality output, without using the truth mask to choose a candidate. The two-CPU-thread ORT run was warmed once; median encoder plus decoder time was 1,860.5 ms/crop, excluding initialization, on a shared host. This is not a portable performance benchmark. Results below are observations of that prior run, not a newly performed comparison.

| Measure | Result |
|---|---|
| Raw visible plate | 99,193 / 100,638 pixels covered; 1,445 missed |
| Three-pixel dilation | 100,638 / 100,638 covered; 17,425 extra pixels |
| Eight-pixel dilation | 100,638 / 100,638 covered; 47,989 extra pixels |
| Current padded rectangle | 100,638 / 100,638 covered; 124,212 extra pixels |
| Interior occluder, raw | 441 / 441 occluder pixels redacted, 0% retained; model quality 0.978 |
| Disconnected cross occlusion, raw | 235 / 3,335 occluder pixels redacted; 92.95% retained; 249 visible plate pixels missed |
| Disconnected cross occlusion, 3 px / 8 px dilation | 48.8% / 4.2% occluder retained |
| Rotated / perspective, raw | 12,452 / 12,687 and 9,811 / 9,937 visible pixels covered, respectively |

The score gate >= 0.85 rejected none of the fixtures; it cannot establish mask completeness or foreground exclusion. Dilating the masks improves these fixtures' coverage while damaging exclusions. A raster format capable of holes does not imply the model can detect holes. No synthetic metric establishes real-world accuracy or safety.

The ONNX encoder and decoder total 41,365,489 bytes. Recomputed local SHA-256: encoder `84ed466ffcc5c1f8d08409bc34a23bb364ab2c15e402cb12d4335a42be0e0951`, decoder `a62f8fa5ea080447c0689418d69e58f1e83e0b7adf9c142e2bd9bcc8045c0b11`. The [model repository](https://huggingface.co/yunyangx/EfficientSAM/tree/main) lists Apache-2.0. Prior evaluator and fixtures are in branch `prototype/precise-plate-masks`, `experiments/precise_plate_masks/`; the result data is `plate-prototype-results/metrics.json`.

## Smaller TFLite candidate: measured and rejected

The [U-Net / MobileNetV2 model](https://github.com/amirreza-hos/tflite-license-plate-segmentation) was evaluated in the successful [synthetic CI run](https://github.com/tahv0/OpenScrub/actions/runs/42019014348). The runner downloaded the official release, verified 8,320,992 bytes and SHA-256 `96b2f877d3c055c8e0bc4e538420bd54f4f856554e4ca9886a4f3be8569f21c4`, and ran LiteRT 1.4.0 with two threads. Model input and output were float32 tensors of shapes 1×512×512×3 and 1×512×512×1. The author's full-frame normalized RGB example was used, with a fixed >0.5 output threshold, nearest-neighbor mapping and no padding, fallback or truth-guided selection. This full-frame evaluation and EfficientSAM's box-prompted crop evaluation use different inputs and environments, so their timings and scores are not controlled head-to-head comparisons.

| Synthetic measure | TFLite result |
|---|---|
| All 12 fixtures: visible plate | 55,732 / 126,352 covered (44.11%); 70,620 missed |
| All 12 fixtures: visible main lettering | 11,007 / 21,081 covered (52.21%); 10,074 missed |
| Rotated: visible lettering | 1,013 / 2,353 covered; 1,340 missed |
| Disconnected cross: visible plate and lettering | 0 / 9,275 and 0 / 1,320 covered |
| Interior occluder | 441 / 441 occluder pixels redacted, 0% retained |
| Low contrast/glare and small plate | 0% visible-plate coverage in each case |
| Latency | 214.3 ms median invoke only after one warmup; model setup and preprocessing excluded |

Preserving the cross occluder in this run is a consequence of an empty mask, not successful segmentation. These synthetic fixtures are a rejection screen, not real-footage accuracy evidence. The model's output and the raw masks are in `ci-model-results/metrics.json` and companion images; the standalone evaluator and method are in `ci-evidence/`. The repository's [MIT license](https://github.com/amirreza-hos/tflite-license-plate-segmentation/blob/main/LICENSE) does not separately clarify application to released weights, so weight redistribution remains unresolved.

## Integration contract if a backend is later validated

A detector produces a source-frame bounding box and confidence; per-box inference returns a frame-aligned binary raster or equivalent representation retaining every component and every enclosed hole, plus model identity, version, preprocessing transform, and score. Never use the ground truth to choose an output. Rasterization and coordinate mapping must be consistent in preview, saved output, reports, video and HDR; preserve exclusions without hole-filling or unconditional dilation. Document any pixel padding and measure its impact on both leakage and occluder preservation. Explicitly handle inference errors, empty masks and unvalidated confidence via a conservative rectangle fallback and expose the fallback to review; a score threshold is not proof of privacy. Test temporal stability, selection/review/edit behavior, detector misses, multiple plates, real-world frames and independent visible-plate/occluder annotations before claiming the objective is met. Rectangular fallback protects coverage at the cost of retaining an occluder; do not present it as precise visible-only behavior.
