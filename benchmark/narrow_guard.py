#!/usr/bin/env python3
"""Compare narrow CPU validation with the original narrow PR implementation.

Runs synthetic crops without model downloads or inference. This measures the
CPU guard only, not complete video scanning. Requires a Git checkout, numpy,
and OpenCV. No video, job, or model files are written.
"""

import argparse
import ast
import json
from pathlib import Path
import statistics
import subprocess
import time

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "77755f075425331081d7f2b747f803f5dbf02131"


def guard_from_source(source):
    # Isolate the pure CPU guard; importing the application is unnecessary.
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef)
                and n.name == "_narrow_from_probability")
    namespace = {"cv2": cv2, "np": np}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 "<narrow-guard>", "exec"), namespace)
    return namespace[node.name]


def noisy_plate(height, width):
    crop = np.full((height, width, 3), 240, np.uint8)
    for x in range(width // 4, 3 * width // 4, max(8, width // 80)):
        cv2.rectangle(crop, (x, height // 3),
                      (x + max(2, width // 200), 2 * height // 3),
                      (20, 20, 20), -1)
    for y in range(height // 6, 5 * height // 6, 5):
        for x in range(width // 6, 5 * width // 6, 7):
            if crop[y, x, 0] == 240:
                crop[y, x] = 20
    probability = np.zeros((height, width), np.float32)
    probability[height // 3 + 2:2 * height // 3 - 1,
                width // 4 + 2:3 * width // 4 - 2] = .9
    return crop, probability


def fixtures():
    clean = np.full((80, 220, 3), 240, np.uint8)
    probability = np.zeros((80, 220), np.float32)
    for x in (35, 145):
        cv2.rectangle(clean, (x, 25), (x + 20, 55), (20, 20, 20), -1)
        probability[27:54, x + 2:x + 19] = .9
    yield "clean-disconnected", clean, probability
    missing = probability.copy()
    missing[:, 100:] = 0
    yield "uncovered-letter-fallback", clean, missing
    yield "low-contrast-fallback", np.full_like(clean, 240), probability
    occluded = clean.copy()
    cv2.rectangle(occluded, (155, 0), (175, 79), (20, 20, 20), -1)
    yield "occlusion-fallback", occluded, missing
    for height, width in ((80, 240), (160, 640), (320, 1280)):
        yield f"noisy-{width}x{height}", *noisy_plate(height, width)


def signature(result):
    polygons, reason = result
    return reason, [p.tolist() for p in polygons]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--variants", type=int, default=48,
                        help="deterministic exposure/noise/polarity equivalence cases")
    parser.add_argument("--min-noisy-speedup", type=float, default=0,
                        help="optional local benchmark gate; not a CI timing test")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    original = subprocess.check_output(
        ["git", "show", f"{args.baseline_ref}:openscrub.py"],
        cwd=ROOT, text=True)
    baseline = guard_from_source(original)
    candidate = guard_from_source((ROOT / "openscrub.py").read_text())
    cases = list(fixtures())
    rng = np.random.default_rng(20261105)
    for index in range(args.variants):
        name, crop, probability = cases[index % len(cases)]
        noisy = np.clip(crop.astype(np.int16) + rng.integers(
            -15, 16, size=crop.shape, dtype=np.int16), 0, 255).astype(np.uint8)
        if index % 2:
            noisy = 255 - noisy
        altered = probability * rng.uniform(.4, 1.0)
        if index % 3 == 0:
            noisy, altered = noisy[:, ::-1], altered[:, ::-1]
        assert signature(candidate(noisy, altered)) == signature(
            baseline(noisy, altered)), (name, index)
    results = []
    for name, crop, probability in cases:
        expected = signature(baseline(crop, probability))
        assert signature(candidate(crop, probability)) == expected, name
        elapsed = [[], []]
        for iteration in range(args.iterations):
            # Alternate order to limit warm-cache/order bias.
            for index in ((0, 1) if iteration % 2 == 0 else (1, 0)):
                start = time.perf_counter()
                result = (baseline, candidate)[index](crop, probability)
                elapsed[index].append(time.perf_counter() - start)
                assert signature(result) == expected, name
        old_ms, new_ms = [1000 * statistics.median(samples) for samples in elapsed]
        results.append(dict(case=name, baseline_ms=round(old_ms, 3),
                            candidate_ms=round(new_ms, 3),
                            speedup=round(old_ms / new_ms, 3),
                            fallback=expected[0], polygons=len(expected[1])))
    print(json.dumps(dict(scope="synthetic CPU guard only; no model inference",
                          baseline_ref=args.baseline_ref,
                          equivalent_variants=args.variants,
                          iterations=args.iterations, opencv=cv2.__version__,
                          numpy=np.__version__, cases=results), indent=2))
    largest = results[-1]
    assert largest["speedup"] >= args.min_noisy_speedup, (
        f"Large noisy guard speedup {largest['speedup']}x "
        f"is below {args.min_noisy_speedup}x")


if __name__ == "__main__":
    main()
