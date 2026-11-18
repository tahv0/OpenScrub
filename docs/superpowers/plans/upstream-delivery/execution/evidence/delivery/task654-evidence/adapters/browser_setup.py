"""Create the helper-assigned browser artifact directory; no product stubs."""
from pathlib import Path
import os
import pytest


@pytest.fixture(scope='session', autouse=True)
def browser_artifacts():
    root = Path(os.environ['VERIFY_RUN']).resolve()
    target = Path(os.environ['POLLING_ARTIFACTS']).resolve()
    assert target.parent == root and target.name == 'browser'
    target.mkdir(exist_ok=True)
