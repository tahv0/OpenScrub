#!/usr/bin/env python3
"""Research screen, never imported by the application or used for redaction."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import statistics
import time
import urllib.request

import cv2
import numpy as np
import torch

from fixtures import make_cases
from hq_adapter import LightHQSamAdapter, CHECKPOINT_URL, CHECKPOINT_SHA256


def fetch_checkpoint(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(CHECKPOINT_URL, timeout=90) as response:
            path.write_bytes(response.read())
    if hashlib.sha256(path.read_bytes()).hexdigest() != CHECKPOINT_SHA256:
        raise ValueError("Unexpected official checkpoint hash")


def geometry(mask):
    contours, hierarchy = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP,
                                          cv2.CHAIN_APPROX_SIMPLE)
    parents = hierarchy[0, :, 3] if hierarchy is not None else []
    return {"components": int(sum(p < 0 for p in parents)),
            "holes": int(sum(p >= 0 for p in parents))}


def measure(mask, visible, full, glyphs):
    occluder = full & ~visible
    return dict(visible_pixels=int(visible.sum()),
                missed_visible_pixels=int((visible & ~mask).sum()),
                glyph_pixels=int(glyphs.sum()),
                missed_glyph_pixels=int((glyphs & ~mask).sum()),
                unwanted_pixels=int((mask & ~visible).sum()),
                occluder_pixels=int(occluder.sum()),
                occluder_pixels_redacted=int((occluder & mask).sum()),
                **geometry(mask))


def infer(adapter, frame, box, verify=False):
    # Same crop/context policy as the previous EfficientSAM experiment.
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = map(int, box)
    mx, my = max(12, int((x2-x1)*.25)), max(12, int((y2-y1)*.35))
    cx1, cy1 = max(0, x1-mx), max(0, y1-my)
    cx2, cy2 = min(width, x2+mx), min(height, y2+my)
    crop = frame[cy1:cy2, cx1:cx2]
    local_box = [x1-cx1, y1-cy1, x2-1-cx1, y2-1-cy1]
    result = adapter.predict(np.ascontiguousarray(crop[..., ::-1]), local_box,
                             verify_api=verify)
    masks = np.zeros((4, height, width), bool)
    masks[:, cy1:cy2, cx1:cx2] = result["combined_masks"]
    return masks, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(1)
    args.out.mkdir(parents=True, exist_ok=True)
    fetch_checkpoint(args.checkpoint)
    adapter = LightHQSamAdapter(args.source, args.checkpoint)
    cases = make_cases()
    infer(adapter, cases[0].frame, cases[0].detector_box)  # warmup excluded
    rows, panels = [], []
    for case in cases:
        masks, result = infer(adapter, case.frame, case.detector_box, verify=True)
        variants = {"box_default": masks[0],
                    "model_score_alternate": masks[result["selected_multimask_index"]]}
        # Report dilation as a tradeoff, never as evidence that holes survive it.
        variants["box_default_dilate3"] = cv2.dilate(
            masks[0].astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
        metrics = {name: measure(mask, case.visible_mask, case.full_mask, case.text_mask)
                   for name, mask in variants.items()}
        row = dict(case=case.name, variants=metrics,
                   model_scores=[float(x) for x in result["sam_scores"]],
                   alternate_index=result["selected_multimask_index"],
                   milliseconds={k: round(1000*v, 3)
                                 for k, v in result["timings_seconds"].items()},
                   api_verified=result["api_verified"],
                   expected_topology=geometry(case.visible_mask))
        rows.append(row)
        cv2.imwrite(str(args.out / (case.name+"-source.png")), case.frame)
        for name, mask in variants.items():
            cv2.imwrite(str(args.out / (case.name+"-"+name+".png")),
                        mask.astype(np.uint8)*255)
        preview = case.frame.copy()
        preview[masks[0]] = (30, 30, 205)
        cv2.imwrite(str(args.out / (case.name+"-preview.png")), preview)
        panels.append(f"<section><h2>{html.escape(case.name)}</h2>"
                      f"<img src='{case.name}-source.png' alt='Synthetic source'>"
                      f"<img src='{case.name}-preview.png' alt='Default mask in red'>"
                      f"<pre>{html.escape(json.dumps(row, indent=2))}</pre></section>")
        print(json.dumps(row), flush=True)
    totals = {}
    for name in rows[0]["variants"]:
        totals[name] = {key: sum(row["variants"][name][key] for row in rows)
                        for key in rows[0]["variants"][name] if key not in ("components", "holes")}
    times = [row["milliseconds"]["total"] for row in rows]
    summary = dict(scope="Synthetic rejection screen, supplied locator boxes; not real-world validation",
                   model="Light HQ-SAM vit_tiny", model_class=adapter.predictor.model.__class__.__name__,
                   source_revision=result["source_revision"], checkpoint_sha256=CHECKPOINT_SHA256,
                   checkpoint_bytes=args.checkpoint.stat().st_size,
                   python=platform.python_version(), torch=torch.__version__,
                   opencv=cv2.__version__, numpy=np.__version__,
                   cpu_threads=2, warmup_frames=1, cases=len(rows),
                   p50_milliseconds=statistics.median(times),
                   p95_milliseconds=float(np.percentile(times, 95)),
                   totals=totals, load_info=result["load_info"])
    (args.out/"metrics.json").write_text(json.dumps(dict(summary=summary, cases=rows), indent=2))
    (args.out/"comparison.html").write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Light HQ-SAM research</title>"
        "<style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:16px}"
        "img{width:48%;max-width:480px}pre{white-space:pre-wrap}section{border-top:1px solid #aaa}</style>"
        "<h1>Light HQ-SAM: synthetic rejection screen</h1>"
        "<p>Red shows the raw default mask. No application feature was added. "
        "Only the locator box is supplied; truth is used after inference for measurement.</p>"
        f"<pre>{html.escape(json.dumps(summary, indent=2))}</pre>"+"".join(panels))
    print("SUMMARY "+json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
