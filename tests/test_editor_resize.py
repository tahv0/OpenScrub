"""Real-page resize QA using an existing Playwright and Chromium; no downloads.

Set OPENSCRUB_PLAYWRIGHT_MODULE and OPENSCRUB_CHROMIUM to opt in.
"""
import os
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_editor_live_resize_pixels_and_pointer(tmp_path):
    if not os.environ.get("OPENSCRUB_PLAYWRIGHT_MODULE") or not os.environ.get("OPENSCRUB_CHROMIUM") or not shutil.which("node"):
        pytest.skip("Set OPENSCRUB_PLAYWRIGHT_MODULE and OPENSCRUB_CHROMIUM for real-page QA")
    artifacts = Path(os.environ.get("OPENSCRUB_RESIZE_ARTIFACTS", str(tmp_path)))
    artifacts.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = artifacts / "server.log"
    env = os.environ.copy()
    env["OPENSCRUB_NO_AUTOFETCH"] = "1"
    with log.open("w") as output:
        server = subprocess.Popen([sys.executable, str(ROOT / "tests/editor_resize_server.py"),
                                   str(ROOT), str(artifacts / "runtime"), str(port)],
                                  cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                if server.poll() is not None:
                    pytest.fail(log.read_text())
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs", timeout=.5).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                pytest.fail("resize server did not start: " + log.read_text())
            result = subprocess.run(["node", str(ROOT / "tests/editor_resize_browser.cjs"),
                                     f"http://127.0.0.1:{port}", str(artifacts)],
                                    env=env, capture_output=True, text=True, timeout=180)
            (artifacts / "browser.log").write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stdout + result.stderr
            verify_render(artifacts)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def verify_render(artifacts):
    """Decode the real SDR output and independently check the edited source region."""
    import cv2
    import numpy as np

    result = json.loads((artifacts / "results-2.json").read_text())
    chosen = result["persistence"]["chosenSource"]
    cap = cv2.VideoCapture(str(artifacts / "actual-output.mp4"))
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    assert ok and frame.shape == (360, 640, 3)
    x0, y0, x1, y1 = chosen
    # A scanline above the added box isolates the moved/resized original box.
    y = round((y0 + 220) / 2)
    dark = np.flatnonzero(frame[y].max(axis=1) < 12)
    assert abs(int(dark.min()) - x0) <= 3
    assert abs(int(dark.max()) - x1) <= 3
    core = frame[round(y0)+4:round(y1)-4, round(x0)+4:round(x1)-4]
    assert float((core.max(axis=2) < 12).mean()) > .99
    assert frame[y, round(x0)-8].mean() > 100
    assert frame[y, round(x1)+8].mean() > 100
    cv2.imwrite(str(artifacts / "render-frame.png"), frame)
    evidence = {"source_box": chosen, "scanline_y": y,
                "actual_dark_edges": [int(dark.min()), int(dark.max())],
                "dark_core_fraction": float((core.max(axis=2) < 12).mean()),
                "edge_tolerance_source_px": 3, "decoded_shape": list(frame.shape)}
    (artifacts / "render-pixels.json").write_text(json.dumps(evidence, indent=2))
