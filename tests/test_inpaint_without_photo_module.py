"""The CUDA image's OpenCV is built without the photo module (no cv2.inpaint).
Inpaint mode must still render: a flat fill from the surroundings, which
keeps nothing of the original pixels inside the region."""
import numpy as np

import openscrub


def _frame():
    rng = np.random.default_rng(7)
    frame = np.full((120, 160, 3), (30, 90, 150), np.uint8)
    frame[40:80, 60:100] = rng.integers(0, 256, (40, 40, 3), dtype=np.uint8)  # "plate"
    return frame


def test_inpaint_mode_renders_without_cv2_inpaint(monkeypatch):
    monkeypatch.delattr(openscrub.cv2, "inpaint", raising=False)
    frame = _frame()
    before = frame.copy()
    openscrub.blur_region(frame, 60, 40, 100, 80, "inpaint")
    region = frame[40:80, 60:100].reshape(-1, 3)
    assert (region == region[0]).all()                  # flat: nothing of the original
    assert tuple(region[0]) == (30, 90, 150)            # the surroundings' colour
    outside = np.ones(frame.shape[:2], bool)
    outside[40:80, 60:100] = False
    assert (frame[outside] == before[outside]).all()     # nothing else touched


def test_inpaint_fill_10bit_plane_without_cv2_inpaint(monkeypatch):
    monkeypatch.delattr(openscrub.cv2, "inpaint", raising=False)
    plane = np.full((64, 64), 400, np.uint16)
    plane[20:40, 20:40] = 1000
    out = openscrub._inpaint_fill(plane, 20, 20, 40, 40)
    assert out.dtype == np.uint16 and out.shape == (20, 20)
    assert (out == 400).all()


def test_render_log_says_inpaint_is_replaced(monkeypatch):
    monkeypatch.delattr(openscrub.cv2, "inpaint", raising=False)
    logs = []
    openscrub._note_inpaint_support({"inpaint"}, logs.append)
    assert any("inpaint is not available" in m for m in logs)
    logs.clear()
    openscrub._note_inpaint_support({"blur"}, logs.append)
    assert not logs
