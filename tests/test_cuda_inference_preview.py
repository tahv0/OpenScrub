"""Conservative, no-download checks for the optional CUDA inference preview.

These tests deliberately do not import PyTorch, Paddle or require a GPU.
Real GPU regression testing is required before deployment or swapping images.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "docker" / "generate_cuda_inference.py"
FULL = ROOT / "Dockerfile.cuda"
SLIM = ROOT / "Dockerfile.cuda.inference"

spec = importlib.util.spec_from_file_location("generate_cuda_inference", GENERATOR)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CudaInferencePreviewTests(unittest.TestCase):
    def setUp(self):
        self.full = FULL.read_text("utf-8")
        self.slim = SLIM.read_text("utf-8")

    def test_generated_dockerfile_exactly_matches_full_runtime_recipe(self):
        self.assertEqual(self.slim, module.render(self.full))
        check = subprocess.run([sys.executable, str(GENERATOR), "--check"],
                               cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_parser_directive_must_remain_first(self):
        self.assertTrue(self.slim.startswith("# syntax=docker/dockerfile:1\n"))
        self.assertEqual(self.slim.count("# syntax=docker/dockerfile:1"), 1)
        self.assertIn("# GENERATED FROM Dockerfile.cuda", self.slim)

    def test_heavy_runtime_install_steps_are_identical_for_layer_reuse(self):
        # Stage naming and the global stage-selection ARG may differ, but
        # the expensive actual RUN/COPY steps must remain byte-for-byte.
        start = "ENV DEBIAN_FRONTEND=noninteractive"
        full_runtime = self.full[self.full.index(start):
                                 self.full.index(module.TRAINING_START)]
        slim_runtime = self.slim[self.slim.index(start):
                                 self.slim.index(module.MODEL_START)]
        self.assertEqual(full_runtime, slim_runtime)
        self.assertIn("paddlepaddle-gpu==3.2.2", slim_runtime)
        self.assertIn("ONNXRUNTIME_GPU_VERSION=1.20.2", slim_runtime)
        self.assertIn("COPY requirements.txt ./", slim_runtime)
        self.assertIn("pip install --force-reinstall --no-deps", slim_runtime)

    def test_inference_stage_has_models_but_no_pytorch_training_venv(self):
        self.assertIn("AS cuda_inference_deps", self.slim)
        self.assertIn("ARG OPENSCRUB_CUDA_DEPS_IMAGE=cuda_inference_deps", self.slim)
        self.assertIn("LABEL org.openscrub.cuda.flavor=\"inference-only\"", self.slim)
        model = self.slim.index("# ---- model layer:")
        app = self.slim.index("FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app")
        self.assertLess(model, app)
        self.assertIn("RUN python prefetch_models.py yunet sface vittrack ppdet plate_t640",
                      self.slim[:app])
        for forbidden in ("ARG OPENSCRUB_ENABLE_TRAINING=0",
                          "COPY requirements.training.txt", "torch==2.10.0",
                          "python3 -m venv /opt/openscrub-training",
                          "pip install -r /tmp/requirements.training.txt"):
            self.assertNotIn(forbidden, self.slim[:app])
        self.assertIn("torch==2.10.0", self.full[:self.full.index(" AS app\n")])

    def test_app_copy_and_security_refresh_remain_identical(self):
        marker = "FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app\n"
        self.assertEqual(self.slim[self.slim.index(marker):],
                         self.full[self.full.index(marker):])
        self.assertIn("COPY scripts/ scripts/", self.slim)
        self.assertIn("ENV OPENSCRUB_IN_DOCKER=1", self.slim)

    def test_fail_closed_when_full_stage_contract_changes(self):
        with self.assertRaises(ValueError):
            module.render(self.full.replace("python3 -m venv /opt/openscrub-training",
                                            "python3 -m venv /opt/renamed-training"))
        with self.assertRaises(ValueError):
            module.render(self.full.replace("AS cuda_deps", "AS different_stage"))
        with self.assertRaises(ValueError):
            module.render(self.full.replace("# syntax=docker/dockerfile:1",
                                            "# syntax=unknown"))

    def test_windows_preview_script_does_not_mutate_running_full_stack(self):
        script = (ROOT / "scripts/build-windows-cuda-inference.ps1").read_text("utf-8")
        self.assertIn("'openscrub-cuda-inference-deps:local'", script)
        self.assertIn("'openscrub-cuda-inference:local'", script)
        self.assertIn("--target cuda_inference_deps", script)
        self.assertIn("--target app", script)
        self.assertIn("OPENSCRUB_CUDA_DEPS_IMAGE=$depsImage", script)
        self.assertIn("docker --context $DockerContext buildx build", script)
        self.assertIn("Using retained inference-only dependencies", script)
        self.assertNotIn("requirements.training.txt", script)
        self.assertNotIn("compose up", script)
        self.assertNotIn("up -d", script)
        self.assertNotIn("docker image rm", script)
        self.assertNotIn("docker builder prune", script)
        self.assertIn("if ($SmokeTest)", script)
        self.assertIn("--network none --gpus all", script)

    def test_production_cuda_build_and_compose_remain_full(self):
        compose = (ROOT / "compose.windows-cuda.yml").read_text("utf-8")
        wrapper = (ROOT / "scripts/build-windows-cuda.ps1").read_text("utf-8")
        self.assertIn("ARG OPENSCRUB_CUDA_DEPS_IMAGE=cuda_deps", self.full)
        self.assertIn("FROM ghcr.io/austinmabry/opencv-cuda:4.10.0-cu126 AS cuda_deps",
                      self.full)
        self.assertIn("OPENSCRUB_ENABLE_TRAINING=1", wrapper)
        self.assertIn("'openscrub-cuda-deps:local'", wrapper)
        self.assertIn("dockerfile: Dockerfile.cuda", compose)
        self.assertNotIn("Dockerfile.cuda.inference", compose)


if __name__ == "__main__":
    unittest.main()
