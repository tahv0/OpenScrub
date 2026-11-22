# License-plate detection (optional)

OpenScrub can blur license plates in video, but — unlike face detection — the
plate model is **not bundled**. Plate detection is opt-in: without a model, the
`plate` category is simply inactive (it never errors, it just finds nothing).

## Why no bundled model

A good plate detector is a trained neural network (tens of MB) with its own
license terms, and plate appearance varies enough by region that no single small
model is universally "right." Rather than ship one and imply a guarantee,
OpenScrub lets you drop in the model that fits your footage and licensing needs.

## What OpenScrub expects

A **single-class plate detector exported to ONNX**, in either of two output
formats (auto-detected):

- **raw YOLOv8**: input `(1, 3, 640, 640)`, output `(1, 5, 8400)` — the
  default export from Ultralytics YOLOv8
  (`model.export(format="onnx", imgsz=640, opset=12)`)
- **end2end**: output `(1, N, 6)` = (x1, y1, x2, y2, score, class) — what
  the open-image-models YOLOv9 exports emit

OpenScrub runs either through OpenCV's DNN module, so **no PyTorch or
ultralytics runtime dependency** is needed to *use* a model — only to
train/export one.

## Getting a model

**Since v1.0.85 you usually don't have to do anything:** the first scan that
selects the plate category and finds no model downloads the recommended
registry model automatically (MIT-licensed, SHA-256-pinned — the same
zero-setup treatment the face detector gets), and the Docker images ship it
pre-installed. If the server is offline and no model is present, the scan
refuses to run as a plate-only job (fail closed) and the log says how to fix
it.

To pick a different model, use the **built-in registry** (`plate_models.json`):
curated, MIT-licensed YOLOv9 plate models from
[ankandrew/open-image-models](https://github.com/ankandrew/open-image-models).
In the web UI, pick one in the license-plate model section and click
**Download** — the file's SHA-256 is pinned on first download and verified on
every later one, and the model is picked up on the next job. (Alternative:
`python fetch_plate_models.py` on a machine with the open-image-models pip
package installed.)

Any of these also produce a compatible file:

1. **Train/fine-tune your own** on a plate dataset (e.g. the Roboflow
   "License Plate Recognition" datasets) with Ultralytics YOLOv8, then export to
   ONNX as above. This gives you a model tuned to your region and license terms.
2. **Convert an existing YOLOv8 `.pt` plate model** to ONNX with the one-line
   export above.
3. **Use your own** ONNX plate detector if it matches the input/output shapes.

## Installing the model

Registry downloads land in `models/<registry-id>.onnx` and are found
automatically. For a model you obtained yourself, put the file at either
location:

    models/plate_yolov8.onnx        (next to openscrub.py)
    plate_yolov8.onnx

…or point at it explicitly:

    export OPENSCRUB_PLATE_MODEL=/path/to/your_plate_model.onnx
    # or per-run:
    openscrub input.mp4 --categories plate --plate-model /path/to/model.onnx

`install.py --with-plates` can fetch a model for you if you supply a source with
`--plate-model-url` (no default URL ships, so you choose the model and accept its
license).

## Using it

    # CLI
    openscrub dashcam.mp4 --categories plate,face --plate-threshold 0.35

    # Web UI: check the "plate" category. If no model is loaded, the run log
    # will say "plate detector: no model found" and plates won't be touched.

Plates are treated like any other category: **zoneable** (draw a plate zone to
restrict where it looks), and they honor **per-category redaction mode**
(blur / box / mosaic). Because plates on dashcam/CCTV footage move fast,
OpenScrub re-detects them **every frame** (like dense faces), so a plate crossing
the frame stays covered.

## Experimental confidence policies

The default remains the existing plate detector and smoothing behavior. Two
optional policies retain detections at `--plate-threshold` and require an
explicit `--plate-auto-cutoff`:

    openscrub dashcam.mp4 --categories plate --report audit.json \
      --uncertain-policy manual_review --plate-threshold 0.35 --plate-auto-cutoff 0.80

The values above only illustrate the interface; they are not calibrated
recommendations. The values must be finite and satisfy
`0.05 <= plate-threshold <= plate-auto-cutoff <= 0.95`.

`manual_review` masks a plate track automatically only after two associated
direct detector observations meet the cutoff. Tracks without that support
remain visible for review. `blur_candidates` masks a track after one retained
candidate observation, accepting extra short masks. It still requires the
explicit cutoff, even though its candidate output uses the lower floor. The
association is a spatial/temporal heuristic, not proof of identity.

Output is decided per track. Once a track is masked, automatically or by an
explicit Blur, every sample of it with a usable box is masked over its smoothed
span, including interpolation, onset continuation, grace padding and lower-score
observations, exactly like the default behavior. Synthetic samples never count
as detector evidence, and Keep on a sample always wins. Only samples without a
usable box remain gaps. Selecting a lower candidate floor requires a new scan. A capable report
preserves explicit Blur and Keep decisions across policy changes; ordinary and
legacy reports retain their existing choices and are not converted. Unhandled
suggestions do not prevent export.

The options are available through the CLI, job API and the web Scan Setup's
advanced settings. Review cards identify unmasked uncertain observations,
automatic masks and unsupported samples. The frame editor does not yet show
uncertain candidates as overlays or offer post-scan policy controls. An API client can submit
`uncertain_policy`, `plate_threshold` and
`plate_auto_cutoff` in the scan options. On a capable report, a
`POST /api/jobs/<id>/detections` request may include, for example,
`{"plate_policy":{"uncertain_policy":"blur_candidates"}}`; `manual_review`
and `off` are also accepted. The report remains authoritative after scanning.

Optional reports can be rendered only against the same hashed scan source.
Distinct original/HDR render sources need a frame mapping that is not available
in this experimental path. Optional skipped windows and trimmed renders decode
forward to preserve source-frame identity, which can take longer on long clips.

## Honest limitations

- Detection quality is entirely the model's. A model trained on EU plates will
  underperform on US plates, angled/distant plates are harder, and motion blur
  hurts. **Always keep the human-review step** for anything sensitive.
- OpenScrub blurs the plate; it does **not** read it. That's deliberate — for
  redaction you only need to cover it, and not reading avoids a whole class of
  OCR-accuracy problems.

## Optional lettering-only coverage

Full-plate coverage remains the default. In Scan Setup, enable the plate
category and select **Plate lettering only (experimental)** under Advanced
settings. The selection is saved in the report and reused when rendering or
reopening the job. The web option uses zero extra lettering margin.

The CLI option `--plate-coverage narrow` asks the
stock, pretrained PP-OCRv5 text-region detector to localize lettering inside
each plate; it detects regions and does not recognize or save characters.
`--plate-narrow-margin N` adds a finite, nonnegative margin in source pixels
(default `0`; fractional values round outward at render). Narrow mode locates
plates and text on every frame at full resolution, even when a faster scan
preset is selected. This may substantially increase scan time.

A lettering mask must span at least half the width and 30% of the height of
the detected box, otherwise the full box is used. Rendering applies the same
rule, so older reports get it without a rescan.

Narrow masks are an experimental downstream option. A localization guard
can miss lettering, particularly with low contrast, clipping, occlusion,
unusual layouts or motion. Extra margin is no guarantee. A plate missed by
the plate detector is not rescued by this stage. Inspect the actual output.

**Privacy tradeoff:** lettering-only masks leave plate background, character
positions and potentially recoverable character geometry visible. Localization
fallback does not settle this concern. Select full-plate coverage where this
information must be concealed; the redaction mode also matters because blur
and mosaic may be reversible.

This first implementation supports native SDR rendering from a qualified
zero-origin CFR scan source using OpenCV's FFmpeg backend and ffprobe metadata.
VFR input must first pass the existing normalization; bypassing that step and
HDR output use ordinary full-plate boxes. A missing or corrupt text model,
uncertain geometry, or a mismatch between the rendered frame and the
inspected frame also uses the ordinary full box where a box is available.
Logs describe mode limitations and summarize detected-frame fallbacks; narrow
reports record fallback reasons. A polygon is tied to the decoded frame and
its geometry; interpolated, changed or adjacent frames never inherit it.
Frame hashes and polygons in the report belong to the job and should follow
its existing retention and deletion practices.

The desktop interface does not expose this option. An ordinary report without
narrow mode retains the existing full-coverage settings and row shape.
