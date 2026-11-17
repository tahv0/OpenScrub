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
    if where.startswith("run"):
        monkeypatch.setattr(o, "apply_coverage", acquired)
        args = SimpleNamespace(output="out", video="in", preview=False,
                               report=None, pad=kw.get("pad", 0), mode="box",
                               encoder="cpu", coverage=("tight" if where == "run_tight" else "concealed"))
        return o.run_render(args, dict(detections=dets, cum=cum, bands=bands,
                                      fps=kw.get("fps", 1), stats={}))
    options = dict(src="in", dst="out", detections=dets, cum=cum, bands=bands,
                   fps=kw.get("fps", 1), pad=kw.get("pad", 0), mode="box")
    if where == "hdr":
        return o.render_hdr(**options, encoder="libx265", tags={})
    return o.render(**options, preview=False)


@pytest.mark.parametrize("where", ["run", "run_tight", "sdr", "hdr"])
@pytest.mark.parametrize("box", [(0, 0, 0, 1), (2, 0, 1, 1), (0, 3, 1, 2),
                                  (0, 0, np.nan, 1), (0, 0, 1, np.inf),
                                  (0, 1, 2), (0, 0, "secret", 1)])
def test_primary_before_acquisition(monkeypatch, where, box):
    with pytest.raises(ValueError, match=r"geometry.*detection 1.*cbox") as exc:
        boundary(monkeypatch, where, [detection(box)])
    assert "private" not in str(exc.value) and "secret" not in str(exc.value)


@pytest.mark.parametrize("where", ["run", "run_tight", "sdr", "hdr"])
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


@pytest.mark.parametrize("coverage", ["tight", "box", "concealed"])
def test_bad_source_not_hidden_by_coverage(coverage):
    with pytest.raises(ValueError, match=r"geometry.*detection 1.*cbox"):
        o.apply_coverage([detection((4, 0, 2, 5), dense=True, track=1),
                          detection((0, 0, 10, 10), dense=True, track=1)], coverage)


def test_coverage_overflow_before_integer_conversion():
    with pytest.raises(ValueError, match=r"geometry.*coverage detection 1.*expanded cbox"):
        o.apply_coverage([detection((-1e308, 0, 1e308, 10), dense=True, track=1)],
                         "concealed")


@pytest.mark.parametrize("container", [list, tuple, np.array])
@pytest.mark.parametrize("scalar", [float, np.float64, np.int64])
def test_ordinary_inputs_unchanged(container, scalar):
    d = detection(container([scalar(x) for x in (1, 1, 5, 5)]),
                  aoff=container([scalar(0), scalar(0)]))
    cum = container([container([scalar(1), scalar(2)])])
    bands = container([container([scalar(0), scalar(0)])])
    o._geometry_preflight([d], cum, bands, scalar(1), scalar(-1), scalar(-2), "test")
    actual, pbox, px = o._geometry_box(d, *cum[0], scalar(-1), "test")
    drift = min(24., .05 * (abs(cum[0][0] - d.aoff[0]) + abs(cum[0][1] - d.aoff[1])))
    assert px == scalar(-1) + drift
    assert actual == (d.cbox[0] + cum[0][0] - px, d.cbox[1] + cum[0][1] - px,
                      d.cbox[2] + cum[0][0] + px, d.cbox[3] + cum[0][1] + px)
    assert o.apply_coverage([d], "tight")[0] is d


@pytest.mark.parametrize("box", [(-20, -20, -10, -10), (.1, .1, .2, .2), (1, 1, 4, 4)])
@pytest.mark.parametrize("pad", [-20, -1, 0, 2])
def test_legal_empty_and_signed_padding(box, pad):
    d = detection(box)
    o._geometry_preflight([d], [(0, 0)], [(0, 0)], 1, pad, -1, "test")
    frame = np.full((8, 8, 3), 200, np.uint8)
    translated, _, _ = o._geometry_box(d, 0, 0, pad, "test")
    o.blur_region(frame, *translated, "box")


@pytest.mark.parametrize("field,value", [("pad", np.inf), ("band_margin", np.nan)])
@pytest.mark.parametrize("hdr", [False, True])
def test_direct_options_before_acquisition(monkeypatch, field, value, hdr):
    def acquired(*a):
        pytest.fail("native acquisition before option validation")
    monkeypatch.setattr(o.cv2, "VideoCapture", acquired)
    args = dict(src="in", dst="out", detections=[detection()], cum=[(0, 0)],
                bands=[(0, 0)], fps=1, pad=0, mode="box")
    args[field] = value
    with pytest.raises(ValueError, match="geometry.*" + field):
        if hdr:
            o.render_hdr(**args, encoder="libx265", tags={})
        else:
            o.render(**args, preview=True)


@pytest.mark.parametrize("hdr", [False, True])
def test_bad_metadata_releases_capture(monkeypatch, hdr):
    class Capture:
        released = False
        def get(self, key):
            return np.nan
        def release(self):
            self.released = True
    cap = Capture()
    monkeypatch.setattr(o.cv2, "VideoCapture", lambda *a: cap)
    args = dict(src="in", dst="out", detections=[], cum=[(0, 0)], bands=[(0, 0)],
                fps=1, pad=0, mode="box")
    with pytest.raises(ValueError, match=r"geometry.*video dimensions/count"):
        if hdr:
            o.render_hdr(**args, encoder="libx265", tags={})
        else:
            o.render(**args, preview=False)
    assert cap.released


@pytest.mark.parametrize("preview", [False, True])
def test_actual_sdr_valid_output(tmp_path, monkeypatch, preview):
    src = tiny_video(tmp_path)
    monkeypatch.setattr(o, "nvenc_available", lambda *a: None)
    dst = tmp_path / "valid.avi"
    # Point/negative times and trajectories shorter than the video remain usable.
    dets = [detection((2, 2, 14, 14)), detection((-20, -20, -10, -10))]
    dets[1].t_start = -1
    o.render(str(src), str(dst), dets, np.array([[0., 0.]]), [(0, 3)],
             np.float64(1), -1., "box", preview, band_margin=-2)
    cap = cv2.VideoCapture(str(dst))
    try:
        ok, frame = cap.read()
        assert ok and frame.shape == (16, 16, 3)
        assert frame[6:10, 6:10].mean() < (100 if not preview else 210)
        if preview:
            assert frame[:, :, 2].max() > frame[:, :, 0].min()
    finally:
        cap.release()


def test_disabled_additive_report_row_not_validated(tmp_path):
    import json
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"detections": [dict(t_start=0, t_end=0,
                    cbox=[0, 0, 4, 4], category="person", text="", confidence=1),
                    {"enabled": False, "cbox": [0, 0, 0, 0], "unknown": "kept"}],
                    "render_state": {"fps": 1, "cum": [[0, 0]], "bands": [[0, 0]]}}))
    dets, state, _ = o.load_report(str(path))
    assert len(dets) == 1
    o._geometry_preflight(dets, state["cum"], state["bands"], state["fps"], 0, 25, "test")
    assert json.loads(path.read_text())["detections"][1]["unknown"] == "kept"


@pytest.mark.parametrize("d,ox,oy,pad,field", [
    (detection(aoff=(-8e307, -8e307)), 8e307, 8e307, 0, "drift distance"),
    (detection((8e307, 0, 1e308, 10), aoff=(1e308, 0)), 1e308, 0, 0, "translated box"),
    (detection((8e307, 0, 1e308, 10)), 0, 0, 1e308, "padded box"),
])
def test_derived_overflow_stage(d, ox, oy, pad, field):
    with pytest.raises(ValueError, match="geometry.*test.*" + field):
        o._geometry_box(d, ox, oy, pad, "test")


@pytest.mark.parametrize("hdr", [False, True])
def test_polygon_fallback_not_preempted_by_primary_guard(hdr):
    # P16B owns polygon/poly_box validity. G checks only the known paint box.
    if hdr:
        y = np.full((8, 8), 300, np.uint16)
        u = np.full((4, 4), 512, np.uint16); v = u.copy()
        o._blur_silhouette_yuv10(y, u, v, 1, 1, 7, 7, "box", (), (np.nan,))
        assert np.all(y[1:7, 1:7] == 64)
    else:
        frame = np.full((8, 8, 3), 200, np.uint8)
        o.blur_silhouette(frame, 1, 1, 7, 7, "box", (), (np.nan,))
        assert not frame[1:7, 1:7].any()


@pytest.mark.parametrize("start,end,expected", [(-1, 2, (-1, 2)), (0, 0, None),
                                                (2, -1, (2, None))])
def test_existing_clip_policy(monkeypatch, start, end, expected):
    observed = []
    monkeypatch.setattr(o, "_render", lambda *a, **kw: observed.append(kw["clip"]))
    args = SimpleNamespace(output="out", video="in", preview=False, report=None,
                           pad=0, mode="box", encoder="cpu", clip_start=start,
                           clip_end=end)
    o.run_render(args, dict(detections=[], cum=[(0, 0)], bands=[(0, 0)], fps=1, stats={}))
    assert observed == [expected]


def test_numpy_actual_overflow_is_diagnosed():
    d = detection(aoff=(np.int64(-1), np.int64(0)))
    with pytest.raises(ValueError, match=r"geometry.*test.*arithmetic"):
        o._geometry_box(d, np.int64(2**63 - 1), np.int64(0), 0, "test")
    with pytest.raises(ValueError, match=r"geometry.*test.*band arithmetic"):
        o._geometry_bands(np.int64(-(2**63)), np.int64(0), 16, 16, 0, "test")


def test_band_derived_overflow():
    with pytest.raises(ValueError, match=r"geometry.*test.*band box"):
        o._geometry_bands(1e308, 0, 16, 16, 1e308, "test")
    assert o._geometry_bands(0, -4, 16, 16, -5, "test") == [(0, 17, 16, 16)]


@pytest.mark.parametrize("hdr", [False, True])
@pytest.mark.parametrize("pad", [0, 1])
def test_run_coverage_rounding_keeps_legal_empty_box(monkeypatch, hdr, pad):
    observed = []
    name = "_render_hdr" if hdr else "_render"
    monkeypatch.setattr(o, name, lambda *a, **kw: observed.append(a[2][0].cbox),
                        raising=False)
    d = detection((.1, .1, .2, .2), dense=True, track=1)
    args = SimpleNamespace(output="out", video="in", preview=False, report=None,
                           pad=pad, mode="box", encoder="cpu", coverage="concealed",
                           hdr_source="in" if hdr else None, hdr_encoder="libx265")
    o.run_render(args, dict(detections=[d], cum=[(0, 0)], bands=[(0, 0)], fps=1, stats={}))
    assert observed == [(0, 0, 0, 0)]


def metadata_capture(monkeypatch, width=16, height=16, count=1):
    class Capture:
        released = False
        def get(self, field):
            return {cv2.CAP_PROP_FRAME_WIDTH: width,
                    cv2.CAP_PROP_FRAME_HEIGHT: height,
                    cv2.CAP_PROP_FRAME_COUNT: count}[field]
        def release(self):
            self.released = True
    cap = Capture()
    monkeypatch.setattr(o.cv2, "VideoCapture", lambda *a: cap)
    return cap


@pytest.mark.parametrize("hdr", [False, True])
@pytest.mark.parametrize("count", [1, -1])
def test_renderer_admits_finite_negative_frame_count(monkeypatch, hdr, count):
    cap = metadata_capture(monkeypatch, count=count)
    class EncoderReached(Exception):
        pass
    def reached(*a, **kw):
        if hdr:
            assert cap.released  # metadata capture closes before HDR decoding
            assert kw["bufsize"] == 16 * 16 * 6
        raise EncoderReached()
    monkeypatch.setattr(o, "nvenc_available", reached)
    monkeypatch.setattr(o.subprocess, "Popen", reached)
    args = dict(src="in", dst="out", detections=[], cum=[(0, 0)],
                bands=[(0, 0)], fps=1, pad=0, mode="box")
    try:
        with pytest.raises(EncoderReached):
            if hdr:
                o.render_hdr(**args, encoder="libx265", tags={})
            else:
                o.render(**args, preview=False)
    finally:
        cap.release()  # harness ownership at the deliberate acquisition fault


@pytest.mark.parametrize("hdr", [False, True])
@pytest.mark.parametrize("field,value", [("width", 0), ("width", -1),
                                         ("height", 0), ("height", -1),
                                         ("width", np.nan), ("height", np.inf),
                                         ("count", np.nan), ("count", np.inf)])
def test_renderer_rejects_unusable_metadata(monkeypatch, hdr, field, value):
    cap = metadata_capture(monkeypatch, **{field: value})
    def acquired(*a, **kw):
        pytest.fail("native decoder/encoder acquired with unusable metadata")
    monkeypatch.setattr(o, "nvenc_available", acquired)
    monkeypatch.setattr(o.subprocess, "Popen", acquired)
    args = dict(src="in", dst="out", detections=[], cum=[(0, 0)],
                bands=[(0, 0)], fps=1, pad=0, mode="box")
    with pytest.raises(ValueError, match=r"geometry.*video dimensions/count"):
        if hdr:
            o.render_hdr(**args, encoder="libx265", tags={})
        else:
            o.render(**args, preview=False)
    assert cap.released
