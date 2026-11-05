#!/usr/bin/env python3
"""Verify the resolved plate model really executes nodes on CUDA.

Pipe this file into the CUDA container's ``python -`` (see the Windows
Compose guide). A blank model probe checks execution, not detection recall.
"""

import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")


def main():
    if os.environ.get("OPENSCRUB_CPU_DNN", "").lower() in ("1", "true", "yes"):
        raise RuntimeError("OPENSCRUB_CPU_DNN forces CPU; remove it and recreate the container")

    import numpy as np
    import onnxruntime as ort

    available = ort.get_available_providers()
    print(f"ONNX Runtime {ort.__version__}: {available}", flush=True)
    if "CUDAExecutionProvider" not in available:
        raise RuntimeError("CUDA provider is missing: rebuild using Dockerfile.cuda")

    from openscrub import PlateDetector

    model, input_size = PlateDetector.resolve_model()
    if not model:
        raise RuntimeError("No plate model found; install one in Settings → Detection models")
    print(f"Plate model: {model}", flush=True)
    size = input_size or 640
    probe = np.full((1, 3, size, size), 114.0 / 255.0, dtype=np.float32)
    options = ort.SessionOptions()
    options.enable_profiling = True
    with tempfile.TemporaryDirectory(prefix="openscrub-cuda-") as directory:
        options.profile_file_prefix = str(Path(directory) / "plate")
        session = ort.InferenceSession(
            model, sess_options=options,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        session.disable_fallback()
        active = session.get_providers()
        print(f"Initialized session: {active}", flush=True)
        if "CUDAExecutionProvider" not in active:
            raise RuntimeError("CUDA initialization failed; inspect the CUDA/driver errors above")
        session.run(None, {session.get_inputs()[0].name: probe})
        events = json.loads(Path(session.end_profiling()).read_text())
        cuda_nodes = sum(
            event.get("cat") == "Node"
            and event.get("args", {}).get("provider") == "CUDAExecutionProvider"
            for event in events)
        if not cuda_nodes:
            raise RuntimeError("The plate inference executed no CUDA nodes")
        print(f"PASS: real plate inference executed {cuda_nodes} CUDA node events.")
        print("Some CPU shape/NMS nodes are normal. Start a new scan to use CUDA.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"CUDA check failed: {error}", file=sys.stderr)
        sys.exit(1)
