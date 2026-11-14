"""The retained CUDA training image must be reusable without rebuilding PyTorch.

Static tests run on CI without downloading NVIDIA images or requiring a GPU.
The full multi-GB CUDA build is verified separately on a Docker Desktop host.
"""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PersistentCudaDependencyImageTests(unittest.TestCase):
    def test_default_release_build_and_tagged_local_base_share_app_layer(self):
        dockerfile = (ROOT / "Dockerfile.cuda").read_text(encoding="utf-8")
        base_arg = dockerfile.index("ARG OPENSCRUB_CUDA_DEPS_IMAGE=cuda_deps")
        base_stage = dockerfile.index(" AS cuda_deps")
        training = dockerfile.index("ARG OPENSCRUB_ENABLE_TRAINING=0")
        model_prefetch = dockerfile.index("RUN python prefetch_models.py")
        fingerprint = dockerfile.index("ARG OPENSCRUB_DEPS_FINGERPRINT=unmanaged")
        label = dockerfile.index('LABEL org.openscrub.cuda.deps-fingerprint=')
        app_stage = dockerfile.index("FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app")
        refresh = dockerfile.index("ARG SECURITY_REFRESH=0")
        app_copy = dockerfile.index("COPY pyproject.toml")
        self.assertLess(base_arg, base_stage)
        self.assertLess(base_stage, training)
        self.assertLess(training, model_prefetch)
        self.assertLess(model_prefetch, fingerprint)
        self.assertLess(fingerprint, label)
        self.assertLess(label, app_stage)
        self.assertLess(app_stage, refresh)
        self.assertLess(refresh, app_copy)
        self.assertEqual(dockerfile.count(" AS cuda_deps"), 1)
        self.assertNotIn("COPY openscrub.py", dockerfile[:app_stage])
        self.assertNotIn("pip install torch", dockerfile[app_stage:])
        self.assertIn(
            'torch==2.10.0 torchvision==0.25.0',
            dockerfile[training:app_stage],
        )

    def test_windows_compose_training_argument_is_stable(self):
        compose = (ROOT / "compose.windows-cuda.yml").read_text(encoding="utf-8")
        self.assertIn('OPENSCRUB_ENABLE_TRAINING: "${OPENSCRUB_ENABLE_TRAINING:-1}"', compose)
        self.assertIn(
            'OPENSCRUB_CUDA_DEPS_IMAGE: "${OPENSCRUB_CUDA_DEPS_IMAGE:-cuda_deps}"',
            compose,
        )
        self.assertIn("capabilities: [gpu]", compose)

    def test_windows_script_retains_a_dependency_image_and_rebuilds_on_change(self):
        script = (ROOT / "scripts/build-windows-cuda.ps1").read_text(encoding="utf-8")
        self.assertIn("'openscrub-cuda-deps:local'", script)
        self.assertIn('--target cuda_deps', script)
        # The builder must match Docker Desktop's active context (usually
        # desktop-linux), NOT the hard-coded default context.
        self.assertNotIn('--builder default', script)
        self.assertIn('docker context show', script)
        self.assertIn('$builderName = $dockerContext', script)
        self.assertIn('docker --context $dockerContext buildx inspect $builderName', script)
        self.assertIn("'(?m)^Driver:\\s*docker\\s*$'", script)
        self.assertIn('buildx build --builder $builderName', script)
        # CUDA dependencies are built with direct Buildx; the app must use
        # the proven context-only Compose build without any --builder flag.
        self.assertEqual(
            script.count('docker --context $dockerContext buildx build --builder $builderName'),
            1,
        )
        self.assertNotIn("--target app", script)
        self.assertNotIn("--tag $appImage", script)
        self.assertIn("docker --context $dockerContext compose --progress plain", script)
        self.assertIn("compose.windows-cuda.yml build", script)
        self.assertNotIn("compose.windows-cuda.yml build --builder", script)
        self.assertIn("docker --context $dockerContext compose -f", script)
        self.assertIn("up -d --no-build", script)
        self.assertIn('--builder $builderName --progress plain --load', script)
        self.assertIn('--load', script)
        self.assertIn('--build-arg OPENSCRUB_ENABLE_TRAINING=1', script)
        self.assertIn('docker --context $dockerContext image inspect', script)
        self.assertIn('org.openscrub.cuda.deps-fingerprint', script)
        self.assertIn('$existingFingerprint -ne $fingerprint', script)
        self.assertIn("dockerfile.Substring(0, $index)", script)
        self.assertIn('requirements.training.txt', script)
        self.assertIn('docker/prefetch_models.py', script)
        self.assertIn('--no-build', script)
        self.assertIn('finally {', script)

    def test_no_source_changes_in_dependency_hash(self):
        script = (ROOT / "scripts/build-windows-cuda.ps1").read_text(encoding="utf-8")
        self.assertNotIn("ReadAllText((Join-Path $repoRoot 'openscrub.py'))", script)
        self.assertIn("'FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app'", script)


if __name__ == "__main__":
    unittest.main()
