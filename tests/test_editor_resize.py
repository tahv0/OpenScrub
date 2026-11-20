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


def launch_editor_page(tmp_path,script,render=False,reopen=None,restart=True):
    if not os.environ.get("OPENSCRUB_PLAYWRIGHT_MODULE") or not os.environ.get("OPENSCRUB_CHROMIUM") or not shutil.which("node"):
        pytest.skip("Set OPENSCRUB_PLAYWRIGHT_MODULE and OPENSCRUB_CHROMIUM for real-page QA")
    artifacts = Path(os.environ.get("OPENSCRUB_RESIZE_ARTIFACTS", str(tmp_path))) / script.removesuffix(".cjs")
    if reopen:
        artifacts = Path(reopen["previous"]) / "fresh-process"
    artifacts.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = artifacts / "server.log"
    env = os.environ.copy()
    env["OPENSCRUB_NO_AUTOFETCH"] = "1"
    with log.open("w") as output:
        server = subprocess.Popen([sys.executable, str(ROOT / "tests/editor_resize_server.py"),
                                   str(ROOT), str(artifacts / "runtime"), str(port)] +
                                  ([str(reopen["report"]), reopen["job"]] if reopen else []),
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
            result = subprocess.run(["node", str(ROOT / "tests" / script),
                                     f"http://127.0.0.1:{port}", str(artifacts)] +
                                    (["reopen", str(reopen["previous"]), reopen["job"]] if reopen else []),
                                    env=env, capture_output=True, text=True, timeout=180)
            (artifacts / "browser.log").write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stdout + result.stderr
            if render:
                verify_render(artifacts)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()

    if not reopen and restart:
        # The original server is terminated and reaped before a separate actual
        # Python process restores the UI-saved raw report and opens a fresh PAGE.
        job = "resize" if render else "cfr24"
        launch_editor_page(tmp_path, "exact_editor_browser.cjs", reopen={
            "report": artifacts / "saved-report.json", "previous": artifacts, "job": job})


def test_editor_live_resize_pixels_and_pointer(tmp_path):
    launch_editor_page(tmp_path, "editor_resize_browser.cjs", render=True)


def test_exact_editor_samples_and_track(tmp_path):
    if not os.environ.get("OPENSCRUB_EXACT_MEDIA"):
        pytest.skip("Set OPENSCRUB_EXACT_MEDIA for the retained-media PAGE gate")
    launch_editor_page(tmp_path, "exact_editor_browser.cjs")


def test_editor_supersedes_auto_review_and_reopens_deliberately(tmp_path):
    if not os.environ.get("OPENSCRUB_EXACT_MEDIA"):
        pytest.skip("Set OPENSCRUB_EXACT_MEDIA for the retained-media PAGE gate")
    launch_editor_page(tmp_path, "editor_recovery_browser.cjs", restart=False)


def test_plate_corner_editor_real_page_and_render_pixels(tmp_path):
    launch_editor_page(tmp_path, "plate_quad_browser.cjs", restart=False)
    import cv2
    artifacts = Path(os.environ.get("OPENSCRUB_RESIZE_ARTIFACTS", str(tmp_path))) / "plate_quad_browser"
    cap = cv2.VideoCapture(str(artifacts / "actual-output.mp4"))
    try:
        ok0, first = cap.read()
        ok1, second = cap.read()
    finally:
        cap.release()
    assert ok0 and ok1 and first.shape == second.shape == (360, 640, 3)
    # The saved polygon covers the center of only frame 0; the next frame
    # retains ordinary full-plate coverage, including the top-left margin.
    assert int(first[150, 240].max()) < 30
    assert int(first[110, 150].max()) > 100
    assert int(second[110, 150].max()) < 30
    cap = cv2.VideoCapture(str(artifacts / "resized-output.mp4"))
    try:
        resized_ok, resized_frame = cap.read()
    finally:
        cap.release()
    assert resized_ok and resized_frame.shape == (360, 640, 3)
    # This pixel lies outside the original box and saved polygon, but inside
    # the expanded box.  It proves the resized box covers its new full extent.
    assert int(resized_frame[150, 350].max()) < 30
    assert int(resized_frame[110, 150].max()) < 30
    cv2.imwrite(str(artifacts / "resized-frame-0.png"), resized_frame)
    cap = cv2.VideoCapture(str(artifacts / "reset-output.mp4"))
    try:
        reset_ok, reset_frame = cap.read()
    finally:
        cap.release()
    assert reset_ok and reset_frame.shape == (360, 640, 3)
    assert int(reset_frame[110, 150].max()) < 30
    cv2.imwrite(str(artifacts / "reset-frame-0.png"), reset_frame)
    cv2.imwrite(str(artifacts / "render-frame-0.png"), first)
    cv2.imwrite(str(artifacts / "render-frame-1.png"), second)
    (artifacts / "render-pixels.json").write_text(json.dumps({
        "frame0_inside": first[150, 240].tolist(),
        "frame0_outside_quad_inside_box": first[110, 150].tolist(),
        "frame1_full_plate": second[110, 150].tolist(),
        "resized_frame0_new_extent": resized_frame[150, 350].tolist(),
        "resized_frame0_original_quad_margin": resized_frame[110, 150].tolist(),
        "reset_frame0_full_plate": reset_frame[110, 150].tolist(),
    }, indent=2))


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
