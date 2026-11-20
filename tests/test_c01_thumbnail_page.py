"""Exercise the composed scheduler in the real embedded page."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import openscrub_web as web


def test_virtualized_thumbnail_recovery_page(tmp_path):
    node = shutil.which('node')
    if not node or not os.environ.get('OPENSCRUB_PLAYWRIGHT_MODULE') or not os.environ.get('OPENSCRUB_CHROMIUM'):
        pytest.skip('prepared Node, Playwright and Chromium are required')
    page = tmp_path / 'page.html'
    page.write_text(web.PAGE)
    env = dict(os.environ, OPENSCRUB_PAGE_HTML=str(page))
    result = subprocess.run([node, str(Path(__file__).with_name('c01_thumbnail_page.cjs'))],
                            env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
