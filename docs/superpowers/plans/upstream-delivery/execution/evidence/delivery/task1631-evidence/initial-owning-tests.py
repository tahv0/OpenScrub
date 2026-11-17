"""Geometry is rejected before coverage/native acquisition, not by a backend."""
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import openscrub as o


def detection(box=(2, 2, 10, 10), **kw):
    return o.Detection(0, 0, box, "person", "private", 1., **kw)


def boundary(monkeypatch, where, dets, cum=((0, 0),), bands=((0, 0),), **kw):
    def acquired(*a, **k):
        pytest.fail("native acquisition or coverage happened before validation")
    monkeypatch.setattr(o.cv2, "VideoCapture", acquired)
    if where == "run":
        monkeypatch.setattr(o, "apply_coverage", acquired)
        args = SimpleNamespace(output="out", video="in", preview=False,
                               report=None, pad=kw.get("pad", 0), mode="box",
                               encoder="cpu", coverage="concealed")
        return o.run_render(args, dict(detections=dets, cum=cum, bands=bands,
                                      fps=kw.get("fps", 1), stats={}))
    options = dict(src="in", dst="out", detections=dets, cum=cum, bands=bands,
                   fps=kw.get("fps", 1), pad=kw.get("pad", 0), mode="box")
    if where == "hdr":
        return o.render_hdr(**options, encoder="libx265", tags={})
    return o.render(**options, preview=False)


@pytest.mark.parametrize("where", ["run", "sdr", "hdr"])
@pytest.mark.parametrize("box", [(0, 0, 0, 1), (2, 0, 1, 1), (0, 3, 1, 2),
                                  (0, 0, np.nan, 1), (0, 0, 1, np.inf),
                                  (0, 1, 2), (0, 0, "secret", 1)])
def test_primary_before_acquisition(monkeypatch, where, box):
    with pytest.raises(ValueError, match=r"geometry.*detection 1.*cbox") as exc:
        boundary(monkeypatch, where, [detection(box)])
    assert "private" not in str(exc.value) and "secret" not in str(exc.value)


@pytest.mark.parametrize("where", ["run", "sdr", "hdr"])
@pytest.mark.parametrize("field,value", [("fps", 0), ("fps", np.inf),
                                         ("pad", np.nan), ("cum", []),
                                         ("cum", [(0, np.inf)]),
                                         ("bands", [(np.nan, 0)])])
def test_prerequisites_before_acquisition(monkeypatch, where, field, value):
    with pytest.raises(ValueError, match="geometry.*" + field):
        boundary(monkeypatch, where, [detection()], **{field: value})


@pytest.mark.parametrize("field,value", [("aoff", (0, np.inf)),
                                         ("t_start", np.nan), ("t_end", -1)])
def test_detection_prerequisites(monkeypatch, field, value):
    d = detection()
    setattr(d, field, value)
    with pytest.raises(ValueError, match="geometry.*detection 1.*" + field):
        boundary(monkeypatch, "sdr", [d])


@pytest.mark.parametrize("name", ["blur_region", "blur_silhouette", "_blur_yuv10", "_blur_silhouette_yuv10"])
def test_direct_paint_finite_guard(name):
    frame = np.full((16, 16, 3), 100, np.uint8)
    planes = (np.full((16, 16), 300, np.uint16),
              np.full((8, 8), 512, np.uint16), np.full((8, 8), 512, np.uint16))
    args = planes if "yuv10" in name else (frame,)
    extra = dict(polys=(), poly_box=(1, 1, 4, 4)) if "silhouette" in name else {}
    with pytest.raises(ValueError, match=r"geometry.*paint.*box"):
        getattr(o, name)(*args, np.nan, 0, 4, 4, "box", **extra)
    getattr(o, name)(*args, 5, 5, 1, 1, "box", **extra)  # legal empty request


def tiny_video(tmp_path):
    src = tmp_path / "tiny.avi"
    out = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"MJPG"), 1, (16, 16))
    assert out.isOpened()
    out.write(np.full((16, 16, 3), 200, np.uint8))
    out.release()
    return src


@pytest.mark.parametrize("preview", [False, True])
def test_actual_frame_derived_overflow(tmp_path, monkeypatch, preview):
    src = tiny_video(tmp_path)
    monkeypatch.setattr(o, "nvenc_available", lambda *a: None)
    # Observe the real frame calculation; keep this G test independent of R cleanup.
    captures, writers = [], []
    capture, writer = o.cv2.VideoCapture, o.cv2.VideoWriter
    def cap(*a):
        result = capture(*a); captures.append(result); return result
    def sink(*a):
        result = writer(*a); writers.append(result); return result
    monkeypatch.setattr(o.cv2, "VideoCapture", cap)
    monkeypatch.setattr(o.cv2, "VideoWriter", sink)
    try:
        with pytest.raises(ValueError, match=r"geometry.*detection 1.*frame 0.*drift"):
            o.render(str(src), str(tmp_path / "out.avi"),
                     [detection(aoff=(-1e308, 0))], [(1e308, 0)], [(0, 0)],
                     1, 0, "box", preview)
    finally:
        for resource in captures + writers:
            resource.release()
