#!/usr/bin/env python3
"""Synchronize the opt-in inference-only CUDA Dockerfile with Dockerfile.cuda.

The full Windows CUDA image is intentionally left unchanged. This generator
reuses the exact CUDA/OpenCV/Paddle/ORT installation instructions and omits
only the optional PyTorch training-venv block. Maintain one authoritative
dependency recipe instead of hand-editing two almost-identical Dockerfiles.

Usage: python docker/generate_cuda_inference.py --check
       python docker/generate_cuda_inference.py --write
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Dockerfile.cuda"
OUTPUT = ROOT / "Dockerfile.cuda.inference"

TRAINING_START = "# Optional training lives in a SEPARATE venv:"
MODEL_START = "# ---- model layer:"
FULL_BASE = "ARG OPENSCRUB_CUDA_DEPS_IMAGE=cuda_deps\n"
INFERENCE_BASE = "ARG OPENSCRUB_CUDA_DEPS_IMAGE=cuda_inference_deps\n"
FULL_FROM = "FROM ghcr.io/austinmabry/opencv-cuda:4.10.0-cu126 AS cuda_deps\n"
INFERENCE_FROM = "FROM ghcr.io/austinmabry/opencv-cuda:4.10.0-cu126 AS cuda_inference_deps\n"
FINGERPRINT_LABEL = 'LABEL org.openscrub.cuda.deps-fingerprint="${OPENSCRUB_DEPS_FINGERPRINT}"\n'

NOTICE = (
    "# GENERATED FROM Dockerfile.cuda BY docker/generate_cuda_inference.py.\n"
    "# DO NOT EDIT. Run: python docker/generate_cuda_inference.py --write\n"
    "# EXPERIMENTAL scan-only CUDA image: no PyTorch/Ultralytics training venv.\n"
    "# Does not change the existing full CUDA image or Compose configuration.\n\n"
)


def _exactly_once(source: str, marker: str) -> None:
    if source.count(marker) != 1:
        raise ValueError("Dockerfile.cuda contract changed: expected one occurrence of %r" % marker)


def render(source: str) -> str:
    """Derive the inference target without modifying CUDA package installs."""
    for marker in (
        TRAINING_START, MODEL_START, FULL_BASE, FULL_FROM,
        FINGERPRINT_LABEL, "FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app\n",
    ):
        _exactly_once(source, marker)

    training_start = source.index(TRAINING_START)
    model_start = source.index(MODEL_START, training_start)
    app_start = source.index("FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app\n")
    if not (source.index(FULL_FROM) < training_start < model_start < app_start):
        raise ValueError("Unexpected CUDA dependency stage order")
    training = source[training_start:model_start]
    for required in (
        "ARG OPENSCRUB_ENABLE_TRAINING=0",
        "COPY requirements.training.txt /tmp/requirements.training.txt",
        "python3 -m venv /opt/openscrub-training",
        "torch==2.10.0 torchvision==0.25.0",
    ):
        if required not in training:
            raise ValueError("Cannot safely omit training block; missing: " + required)
    if "COPY docker/prefetch_models.py" not in source[model_start:app_start]:
        raise ValueError("Model prefetch must remain in the inference image")

    # Keep the expensive runtime install RUN/COPY instructions byte-identical
    # so BuildKit can share the cached CUDA/OpenCV/Paddle/ORT layers.
    body = source[:training_start] + source[model_start:]
    body = body.replace(FULL_BASE, INFERENCE_BASE, 1)
    body = body.replace(FULL_FROM, INFERENCE_FROM, 1)
    body = body.replace(FINGERPRINT_LABEL,
                        FINGERPRINT_LABEL + 'LABEL org.openscrub.cuda.flavor="inference-only"\n', 1)

    deps = body[:body.index("FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app\n")]
    for forbidden in ("ARG OPENSCRUB_ENABLE_TRAINING", "COPY requirements.training.txt",
                      "pip install torch", "torch==2.10.0", "ultralytics=="):
        if forbidden in deps:
            raise ValueError("Training dependency leaked into inference image: " + forbidden)
    return NOTICE + body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="fail if the committed inference Dockerfile is stale")
    mode.add_argument("--write", action="store_true",
                      help="regenerate the inference Dockerfile after a full CUDA update")
    args = parser.parse_args(argv)

    expected = render(SOURCE.read_text(encoding="utf-8"))
    if args.write:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            OUTPUT.write_text(expected, encoding="utf-8")
            print("Updated", OUTPUT.name)
        else:
            print("Unchanged", OUTPUT.name)
        return 0

    actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
    if actual == expected:
        print("Inference Dockerfile matches the full CUDA runtime recipe")
        return 0
    diff = difflib.unified_diff(actual.splitlines(), expected.splitlines(),
                                fromfile="committed", tofile="generated", lineterm="")
    print("\n".join(diff))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
