"""Output directories for optional test evidence."""
import os
from pathlib import Path


def artifact_directory(tmp_path: Path) -> Path:
    configured = os.environ.get("VERIFY_RUN")
    directory = Path(configured) / "logs" if configured else tmp_path / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    return directory
