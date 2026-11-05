#!/usr/bin/env python3
"""Local numeric-only smoke test. Never writes input pixels or transcribed text.

Annotation and image are caller-supplied external files, deliberately excluded
from the repository. Annotate before seeing a model output. Boxes alone cross
the inference boundary; all visible regions/patches are evaluation-only data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform

import cv2
import numpy as np
import torch

from evaluate_hq import infer
from hq_adapter import LightHQSamAdapter


def polygons(shape, regions):
    mask = np.zeros(shape, np.uint8)
    for region in regions:
        cv2.fillPoly(mask, [np.asarray(region["polygon"], np.int32)], 1)
    return mask.astype(bool)


def patches(mask, rows):
    result = []
    for row in rows:
        x1, y1, x2, y2 = row["bbox_xyxy"]
        patch = mask[y1:y2, x1:x2]
        result.append(dict(id=row["id"], pixels=int(patch.size),
                           masked_pixels=int(patch.sum())))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--annotation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    doc = json.loads(args.annotation.read_text())
    digest = hashlib.sha256(args.image.read_bytes()).hexdigest()
    if digest != doc["source"]["sha256"]:
        raise ValueError("Input photograph does not match the frozen annotation")
    image = cv2.imread(str(args.image))
    if image is None:
        raise ValueError("Unreadable external input")
    shape = image.shape[:2]
    visible = polygons(shape, doc["visible_components"])
    visible &= ~polygons(shape, doc.get("holes", []))
    radius = doc["uncertainty"]["default_boundary_band_radius_px"]
    certain = cv2.erode(visible.astype(np.uint8),
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                  (2*radius+1, 2*radius+1))) != 0
    certain &= ~polygons(shape, doc["uncertainty"]["regions"])
    # Polylines supplement polygon-boundary erosion at complicated overlaps.
    ignore = np.zeros(shape, np.uint8)
    for line in doc.get("occluder_boundary_polylines", []):
        cv2.polylines(ignore, [np.asarray(line["points"], np.int32)], False,
                      1, 2*radius+1)
    certain &= ignore == 0
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(1)
    adapter = LightHQSamAdapter(args.source, args.checkpoint)
    box = doc["prompt_bbox_xyxy"]
    rows = []
    for scale in (1.0, .125):
        frame = image if scale == 1 else cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        x1, y1, x2, y2 = box
        local_box = [int(x1*scale), int(y1*scale),
                     min(frame.shape[1], int(np.ceil(x2*scale))),
                     min(frame.shape[0], int(np.ceil(y2*scale)))]
        masks, result = infer(adapter, frame, local_box, verify=True)
        choices = {"box_default": 0,
                   "model_score_alternate": result["selected_multimask_index"]}
        for name, index in choices.items():
            mask = masks[index]
            if scale != 1:
                mask = cv2.resize(mask.astype(np.uint8),
                                  (shape[1], shape[0]),
                                  interpolation=cv2.INTER_NEAREST) != 0
            row = dict(variant=name, input_scale=scale,
                       input_dimensions=list(frame.shape[:2][::-1]),
                       score=float(result["sam_scores"][index]),
                       certain_visible_pixels=int(certain.sum()),
                       certain_visible_pixels_missed=int((certain & ~mask).sum()),
                       visible_patch_coverage=patches(mask, doc["certain_visible_glyph_patches"]),
                       occluder_patch_coverage=patches(mask, doc["certain_occluder_patches"]),
                       milliseconds=1000*result["timings_seconds"]["total"],
                       api_verified=result["api_verified"])
            rows.append(row)
            print(json.dumps(row), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = dict(scope="One independently annotated genuine physical-occlusion still; no enclosed hole or temporal validation",
                  source_image_sha256=digest,
                  annotation_sha256=hashlib.sha256(args.annotation.read_bytes()).hexdigest(),
                  annotation_method=doc["annotation_provenance"]["method"],
                  boundary_uncertainty_radius_pixels=radius,
                  python=platform.python_version(), torch=torch.__version__,
                  opencv=cv2.__version__, cpu_threads=2,
                  no_real_pixels_saved=True, cases=rows)
    args.out.write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
