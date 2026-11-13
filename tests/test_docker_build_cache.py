"""Regression tests for Docker caching; no Docker daemon or GPU is needed."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGES = {
    "Dockerfile": "cpu",
    "Dockerfile.cuda": "cuda",
    "Dockerfile.intel": "intel",
}


class DockerBuildCacheLayoutTests(unittest.TestCase):
    def test_security_refresh_cannot_be_invalidated_by_app_source_edits(self):
        for filename in IMAGES:
            with self.subTest(image=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                model_copy = text.index("COPY docker/prefetch_models.py")
                refresh = text.index("ARG SECURITY_REFRESH=0")
                app_copy = text.index("COPY pyproject.toml")
                self.assertLess(model_copy, refresh)
                self.assertLess(refresh, app_copy)
                self.assertEqual(text.count("ARG SECURITY_REFRESH=0"), 1)
                self.assertIn(
                    "apt-get dist-upgrade -y",
                    text[refresh:app_copy],
                )
                self.assertNotIn(
                    "apt-get update",
                    text[app_copy:],
                    "Editing application code must not cause Ubuntu/Debian updates",
                )

    def test_all_dependency_installers_use_buildkit_pip_cache(self):
        for filename, variant in IMAGES.items():
            with self.subTest(image=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("# syntax=docker/dockerfile:1\n"))
                self.assertNotIn("pip install --no-cache-dir", text)
                cache = (
                    f"--mount=type=cache,id=openscrub-pip-{variant},"
                    "target=/root/.cache/pip,sharing=locked"
                )
                self.assertGreaterEqual(text.count(cache), 4)
                requirements = text[
                    text.index("COPY requirements.txt ./"):
                    text.index("# ---- model layer:")
                ]
                self.assertIn("RUN " + cache, requirements)
                app_install = text[text.index("COPY pyproject.toml"):]
                self.assertIn("RUN " + cache, app_install)

    def test_cuda_training_venv_reuses_cache_without_leaking_into_runtime(self):
        text = (ROOT / "Dockerfile.cuda").read_text(encoding="utf-8")
        training = text[
            text.index("ARG OPENSCRUB_ENABLE_TRAINING=0"):
            text.index("# ---- model layer:")
        ]
        self.assertIn(
            "RUN --mount=type=cache,id=openscrub-pip-cuda,"
            "target=/root/.cache/pip,sharing=locked",
            training,
        )
        self.assertIn("python3 -m venv /opt/openscrub-training", training)
        self.assertIn("torch==2.10.0 torchvision==0.25.0", training)
        self.assertIn(
            '/opt/openscrub-training/bin/python -m pip install',
            training,
        )

    def test_local_media_and_secrets_excluded_from_context(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for pattern in ("**/.venv", "**/.env", "**/*.mkv", "**/*.pt"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, ignore)
        self.assertIn("!assets/openscrub.ico", ignore)


if __name__ == "__main__":
    unittest.main()
