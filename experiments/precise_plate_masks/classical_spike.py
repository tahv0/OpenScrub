#!/usr/bin/env python3
"""Throwaway, bbox-only OpenCV experiment. Never imported by OpenScrub.

Frozen before evaluating any masks: rectangular GrabCut, five iterations, then
one 3x3-ish closing and recovery of bounded background regions whose maximum
inscribed radius is <=4% of the detector's short dimension (floor 1.5 pixels).
There is no plate-color assumption, quadrilateral truth, model, oracle seed,
largest-component selection, per-case rule, or fallback chosen using truth.

The thin-hole rule is explicitly a heuristic: a narrow/very small real occluder
can be indistinguishable from dark ink and will also be filled. A broad real
occluder is retained only if GrabCut already labels it as background. Closing
can merge components across narrow true gaps. No precision guarantee follows.

OpenCV describes foreground/background GMM color statistics and demonstrates
missing dark foreground (hair) requiring manual foreground strokes:
https://docs.opencv.org/4.13.0/d8/d83/tutorial_py_grabcut.html
Loss of plate glyphs is a hypothesis derived from that mechanism and measured
here, not a claim that the documentation specifically studies license plates.
"""

import os

os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import statistics
import time

import cv2
import numpy as np

from fixtures import make_cases


PREREGISTRATION = {
    "status": "frozen before first evaluation; no tuning against fixture truth",
    "baseline": "OpenCV rectangular GrabCut; all FGD and PR_FGD pixels retained",
    "candidate": "same GrabCut + one closing + bounded thin-hole recovery",
    "grabcut_iterations": 5,
    "rng_seed_each_inference": 1729,
    "opencv_threads": 1,
    "closing_radius": "max(1, round(0.0125 * min(detector_width, detector_height)))",
    "closing_kernel": "elliptical; 2*radius+1; one closing",
    "thin_hole_max_radius": "max(1.5, 0.04 * min(detector_width, detector_height))",
    "hole_connectivity": 8,
    "distance_transform": "DIST_L2 / DIST_MASK_PRECISE",
    "components": "all retained; no largest-component filtering; closing can merge thin gaps",
    "inference_inputs": ["BGR frame", "exclusive integer detector bounding box"],
    "truth_use": "evaluation and synthetic fixture construction only",
    "stress_variants": [
        "original twelve fixtures",
        "global Gaussian blur sigma=1.5, unchanged truth",
        "global contrast x0.35 about 128, unchanged truth",
        "detector box expanded 25% each side, unchanged image and truth",
        "small dark occluder: circle at bbox-relative (0.72, 0.42), radius=max(2,round(0.045*short_dimension)); color=15th percentile of bbox BGR; truth updated by known synthetic disk",
    ],
    "timing": "one untimed warmup, one inference per input, process CPU and wall ms, one OpenCV thread",
    "success_check": "strict visible-only objective: zero missed visible glyph/plate pixels, zero predicted background/occluder pixels, exact component/hole counts",
    "limits": [
        "Entirely synthetic geometry tests, not real-world validation.",
        "Correct detector boxes isolate segmentation; no detector recall test.",
        "No threshold sweep, validation split, oracle prompt or per-case selection.",
        "Thin-hole rule can erase a true small occluder or narrow foreground gap.",
        "A large enclosed occluder can be modeled as foreground by GrabCut.",
        "Foreground/background color statistics can discard dark plate glyphs.",
        "Temporal frames run independently; no propagation or tracking claim.",
    ],
    "primary_reference": "https://docs.opencv.org/4.13.0/d8/d83/tutorial_py_grabcut.html",
}


def infer_one(frame, detector_box):
    """Input boundary deliberately excludes case names and all truth arrays."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(int, detector_box)
    if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
        raise ValueError("Invalid exclusive detector box")
    if x1 == 0 and y1 == 0 and x2 == w and y2 == h:
        raise ValueError("GrabCut rectangle requires at least one exterior background pixel")
    cv2.setRNGSeed(PREREGISTRATION["rng_seed_each_inference"])
    labels = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cpu0, wall0 = time.process_time(), time.perf_counter()
    cv2.grabCut(frame, labels, (x1, y1, x2-x1, y2-y1), bgd, fgd,
                PREREGISTRATION["grabcut_iterations"], cv2.GC_INIT_WITH_RECT)
    raw = (labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)
    cpu1, wall1 = time.process_time(), time.perf_counter()

    short = min(x2-x1, y2-y1)
    radius = max(1, round(.0125 * short))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1))
    refined = cv2.morphologyEx(raw.astype(np.uint8), cv2.MORPH_CLOSE, kernel) != 0
    allowed = np.zeros_like(refined)
    allowed[y1:y2, x1:x2] = True
    refined &= allowed
    inverted = (~refined).astype(np.uint8)
    n, holes, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    exterior = set(map(int, np.unique(np.concatenate(
        (holes[0], holes[-1], holes[:, 0], holes[:, -1])))))
    distances = cv2.distanceTransform(inverted, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    threshold = max(1.5, .04 * short)
    recovered_holes = recovered_pixels = 0
    preserved_holes = 0
    for label in range(1, n):
        if label in exterior:
            continue
        component = holes == label
        if float(distances[component].max()) <= threshold:
            refined[component] = True
            recovered_holes += 1
            recovered_pixels += int(stats[label, cv2.CC_STAT_AREA])
        else:
            preserved_holes += 1
    cpu2, wall2 = time.process_time(), time.perf_counter()
    assert not np.any(raw & ~refined), "Refinement must not discard a proposal component"
    return raw, refined, {
        "grabcut_cpu_ms": (cpu1-cpu0)*1000,
        "grabcut_wall_ms": (wall1-wall0)*1000,
        "candidate_cpu_ms": (cpu2-cpu0)*1000,
        "candidate_wall_ms": (wall2-wall0)*1000,
        "refinement_cpu_ms": (cpu2-cpu1)*1000,
        "recovered_thin_holes": recovered_holes,
        "recovered_thin_hole_pixels": recovered_pixels,
        "preserved_large_holes": preserved_holes,
        "closing_radius_pixels": radius,
        "thin_hole_radius_limit_pixels": threshold,
    }


def topology(mask):
    components = int(cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)[0]-1)
    inv = (~mask).astype(np.uint8)
    n, labels = cv2.connectedComponents(inv, connectivity=8)
    outside = set(map(int, np.unique(np.concatenate(
        (labels[0], labels[-1], labels[:, 0], labels[:, -1])))))
    holes = sum(label not in outside for label in range(1, n))
    return {"components": components, "holes": holes}


def measure(mask, case):
    """Only this evaluation function reads truth for scoring an inferred mask."""
    visible, full, glyph = case.visible_mask, case.full_mask, case.text_mask
    hidden = full & ~visible
    tp = int(np.count_nonzero(mask & visible))
    plate_n, glyph_n, hidden_n = int(visible.sum()), int(glyph.sum()), int(hidden.sum())
    missed = int(np.count_nonzero(visible & ~mask))
    missed_glyph = int(np.count_nonzero(glyph & ~mask))
    bg = int(np.count_nonzero(mask & ~full))
    covered_hidden = int(np.count_nonzero(mask & hidden))
    predicted_topology, truth_topology = topology(mask), topology(visible)
    return {
        "visible_plate_pixels": plate_n,
        "missed_visible_plate_pixels": missed,
        "missed_visible_plate_pct": 100*missed/max(1, plate_n),
        "visible_glyph_pixels": glyph_n,
        "missed_visible_glyph_pixels": missed_glyph,
        "missed_visible_glyph_pct": 100*missed_glyph/max(1, glyph_n),
        "unwanted_background_pixels": bg,
        "occluder_pixels_over_plate": hidden_n,
        "occluder_pixels_covered": covered_hidden,
        "occluder_covered_pct": 100*covered_hidden/hidden_n if hidden_n else None,
        "iou_visible_plate": tp/max(1, plate_n+bg+covered_hidden),
        "predicted_topology": predicted_topology,
        "truth_topology": truth_topology,
        "topology_exact": predicted_topology == truth_topology,
        "strict_visible_only_pass": not (missed or bg or covered_hidden) and predicted_topology == truth_topology,
    }


def variants(cases):
    """Generic predetermined perturbations; no per-case choices or rejection."""
    for case in cases:
        yield "original", case
    for case in cases:
        yield "blur_sigma_1p5", replace(case, frame=cv2.GaussianBlur(case.frame, (0, 0), 1.5))
    for case in cases:
        low = np.clip(128 + .35*(case.frame.astype(np.float32)-128), 0, 255).astype(np.uint8)
        yield "contrast_0p35", replace(case, frame=low)
    for case in cases:
        x1, y1, x2, y2 = case.detector_box
        px, py = round((x2-x1)*.25), round((y2-y1)*.25)
        h, w = case.frame.shape[:2]
        box = (max(0, x1-px), max(0, y1-py), min(w, x2+px), min(h, y2+py))
        yield "box_expand_25pct", replace(case, detector_box=box)
    for case in cases:
        # This is fixture construction, not an inference seed: only the resulting
        # image and original detector box cross the infer_one boundary.
        x1, y1, x2, y2 = case.detector_box
        center = (round(x1+.72*(x2-x1)), round(y1+.42*(y2-y1)))
        radius = max(2, round(.045*min(x2-x1, y2-y1)))
        cover = np.zeros(case.visible_mask.shape, np.uint8)
        cv2.circle(cover, center, radius, 255, -1)
        cover = cover != 0
        frame = case.frame.copy()
        color = np.percentile(frame[y1:y2, x1:x2].reshape(-1, 3), 15, axis=0).astype(np.uint8)
        frame[cover] = color
        yield "small_ink_like_occluder", replace(
            case, frame=frame, visible_mask=case.visible_mask & ~cover,
            text_mask=case.text_mask & ~cover)


def aggregate(rows, variant, method):
    selected = [row for row in rows if variant == "all" or row["variant"] == variant]
    metrics = [row[method] for row in selected]
    summed = {key: sum(m[key] for m in metrics) for key in (
        "visible_plate_pixels", "missed_visible_plate_pixels", "visible_glyph_pixels",
        "missed_visible_glyph_pixels", "unwanted_background_pixels",
        "occluder_pixels_over_plate", "occluder_pixels_covered")}
    summed.update({
        "cases": len(selected),
        "missed_visible_plate_pct": 100*summed["missed_visible_plate_pixels"]/max(1, summed["visible_plate_pixels"]),
        "missed_visible_glyph_pct": 100*summed["missed_visible_glyph_pixels"]/max(1, summed["visible_glyph_pixels"]),
        "occluder_covered_pct": 100*summed["occluder_pixels_covered"]/max(1, summed["occluder_pixels_over_plate"]),
        "cases_with_glyph_miss": sum(m["missed_visible_glyph_pixels"] > 0 for m in metrics),
        "cases_with_plate_miss": sum(m["missed_visible_plate_pixels"] > 0 for m in metrics),
        "topology_exact_cases": sum(m["topology_exact"] for m in metrics),
        "strict_visible_only_pass_cases": sum(m["strict_visible_only_pass"] for m in metrics),
        "median_cpu_ms": statistics.median(row["timing"]["grabcut_cpu_ms" if method == "grabcut" else "candidate_cpu_ms"] for row in selected),
        "median_wall_ms": statistics.median(row["timing"]["grabcut_wall_ms" if method == "grabcut" else "candidate_wall_ms"] for row in selected),
    })
    return summed


def evaluation_crop(image, box):
    x1, y1, x2, y2 = box
    h, w = image.shape[:2]
    crop = image[max(0, y1-8):min(h, y2+8), max(0, x1-8):min(w, x2+8)]
    return cv2.resize(crop, (350, 145), interpolation=cv2.INTER_NEAREST)


def error_image(frame, prediction, case):
    result = (frame.astype(np.float32)*.45).astype(np.uint8)
    result[prediction & case.visible_mask] = (80, 170, 70)
    result[case.visible_mask & ~prediction] = (40, 40, 245)
    result[prediction & ~case.full_mask] = (240, 100, 40)
    result[prediction & case.full_mask & ~case.visible_mask] = (210, 50, 210)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("classical-evidence"))
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    # Write all decisions, including stress tests, BEFORE make_cases or inference.
    prereg = dict(PREREGISTRATION)
    prereg["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out / "preregistration.json").write_text(json.dumps(prereg, indent=2)+"\n")
    cv2.setNumThreads(PREREGISTRATION["opencv_threads"])
    cases = make_cases()
    infer_one(cases[0].frame, cases[0].detector_box)  # untimed warmup, no scoring
    rows, sheet_rows = [], []
    for variant, case in variants(cases):
        raw, refined, timing = infer_one(case.frame, case.detector_box)
        row = {"variant": variant, "name": case.name, "detector_box": list(case.detector_box),
               "grabcut": measure(raw, case), "thin_hole_refinement": measure(refined, case),
               "timing": timing}
        rows.append(row)
        prefix = out / f"{variant}--{case.name}"
        cv2.imwrite(str(prefix)+"--source.png", case.frame)
        cv2.imwrite(str(prefix)+"--grabcut.png", raw.astype(np.uint8)*255)
        cv2.imwrite(str(prefix)+"--refined.png", refined.astype(np.uint8)*255)
        cv2.imwrite(str(prefix)+"--truth.png", case.visible_mask.astype(np.uint8)*255)
        cv2.imwrite(str(prefix)+"--error.png", error_image(case.frame, refined, case))
        if variant == "original":
            images = [case.frame, error_image(case.frame, raw, case), error_image(case.frame, refined, case)]
            tiles = [evaluation_crop(image, case.detector_box) for image in images]
            strip = np.concatenate(tiles, axis=1)
            strip = cv2.copyMakeBorder(strip, 28, 4, 0, 0, cv2.BORDER_CONSTANT, value=(245,245,245))
            cv2.putText(strip, case.name+" | source / GrabCut error / thin-hole error", (8, 19),
                        cv2.FONT_HERSHEY_SIMPLEX, .48, (20,20,20), 1, cv2.LINE_AA)
            sheet_rows.append(strip)
        print(f"{variant}/{case.name}: glyph missed {row['grabcut']['missed_visible_glyph_pixels']} -> {row['thin_hole_refinement']['missed_visible_glyph_pixels']}; occluder covered {row['grabcut']['occluder_pixels_covered']} -> {row['thin_hole_refinement']['occluder_pixels_covered']}", flush=True)
    groups = list(dict.fromkeys(row["variant"] for row in rows)) + ["all"]
    summary = {variant: {method: aggregate(rows, variant, method) for method in ("grabcut", "thin_hole_refinement")} for variant in groups}
    report = {"preregistration": prereg, "environment": {"python": platform.python_version(),
        "opencv": cv2.__version__, "numpy": np.__version__, "platform": platform.platform()},
        "summary": summary, "cases": rows,
        "conclusion": "Report observed failures without a tuning loop. Synthetic success cannot establish generalization or production readiness."}
    (out / "metrics.json").write_text(json.dumps(report, indent=2)+"\n")
    cv2.imwrite(str(out / "original_contact_sheet.png"), np.concatenate(sheet_rows, axis=0))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
