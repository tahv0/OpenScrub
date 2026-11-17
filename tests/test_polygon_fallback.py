"""Known-box fallback and usable-contour compatibility, without model inference."""
import inspect
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager

import cv2
import numpy as np
import pytest

import openscrub as scrub


SQUARE = [[(0, 0), (1, 0), (1, 1), (0, 1)]]
CONCAVE = [[(0, 0), (1, 0), (1, .25), (.25, .25), (.25, 1), (0, 1)]]
BOWTIE = [[(0, 0), (1, 1), (0, 1), (1, 0)]]  # zero signed area, usable fill
BAD = {
    "nan": [[(float("nan"), 0), (1, 0), (1, 1)]],
    "infinity": [[(0, 0), (float("inf"), 0), (1, 1)]],
    "nonnumeric": [[("bad", 0), (1, 0), (1, 1)]],
    "missing_coordinate": [[(0,), (1, 0), (1, 1)]],
    "extra_coordinate": [[(0, 0, 0), (1, 0), (1, 1)]],
    "null_point": [[None, (1, 0), (1, 1)]],
    "null_contour": [None],
    "scalar_polygons": 7,
    "string_point": [["00", (1, 0), (1, 1)]],
    "unsafe_int32": [[(2**32, 0), (2**32 + 1, 0), (2**32, 1)]],
    "float_overflow": [[(1e308, 0), (1, 0), (1, 1)]],
    "integer_overflow": [[(10**400, 0), (1, 0), (1, 1)]],
    "collinear": [[(0, 0), (.5, .5), (1, 1)]],
    "repeated": [[(.5, .5)] * 3],
    "quantized_line": [[(0, 0), (.01, .02), (1, 0)]],
    "valid_then_bad": SQUARE + [[(0,), (1, 0), (1, 1)]],
}
EMPTY = {
    "absent": None, "empty": [], "empty_contour": [[]],
    "two_points": [[(0, 0), (1, 1)]],
    "clipped_empty": [[(2, 2), (3, 2), (3, 3)]],
}
MODES = ["box", "blur", "mosaic", "inpaint"]


def source_planes(path):
    rng = np.random.RandomState(162)
    if path == "sdr":
        return [rng.randint(30, 230, (32, 32, 3)).astype(np.uint8)]
    return [rng.randint(100, 950, shape).astype(np.uint16)
            for shape in [(32, 32), (16, 16), (16, 16)]]


def apply(path, planes, region, mode, polys, poly_box, pad=0):
    if path == "sdr":
        scrub.blur_silhouette(planes[0], *region, mode, polys, poly_box, pad_px=pad)
    else:
        scrub._blur_silhouette_yuv10(*planes, *region, mode, polys, poly_box, pad_px=pad)


def full_box(path, planes, region, mode):
    if path == "sdr":
        scrub.blur_region(planes[0], *region, mode)
    else:
        scrub._blur_yuv10(*planes, *region, mode)


@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name,polys", list(BAD.items()) + list(EMPTY.items()))
@pytest.mark.parametrize("region,poly_box,pad", [
    ((4, 4, 16, 16), (4, 4, 16, 16), 0),
    ((-2, 2, 18, 20), (1, 5, 15, 17), 3),
])
def test_unusable_polygon_matches_actual_full_box(path, mode, name, polys, region, poly_box, pad):
    # Removing validation or accepting a line would leave known-box pixels exposed.
    actual = source_planes(path)
    expected = [p.copy() for p in actual]
    full_box(path, expected, region, mode)
    apply(path, actual, region, mode, polys, poly_box, pad)
    for a, e in zip(actual, expected):
        np.testing.assert_array_equal(a, e)


@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("poly_box", [None, "4488", {"4": 0, "5": 0, "16": 0, "17": 0}, (4, 4, 16), (4, 4, 16, 16, 20),
    (float("nan"), 4, 16, 16), (4, 4, float("inf"), 16), ("bad", 4, 16, 16),
    (16, 4, 4, 16), (4, 4, 4, 16), (4, 4, 16, 4)])
def test_invalid_poly_box_uses_separate_valid_render_box(path, mode, poly_box):
    actual = source_planes(path)
    expected = [p.copy() for p in actual]
    full_box(path, expected, (2, 2, 18, 18), mode)
    apply(path, actual, (2, 2, 18, 18), mode, SQUARE, poly_box, 2)
    for a, e in zip(actual, expected):
        np.testing.assert_array_equal(a, e)


# Literal pixel contours use the baseline round/map rule for this 12px box.
VALID = [
    (SQUARE, [(0, 0), (12, 0), (12, 12), (0, 12)]),
    (CONCAVE, [(0, 0), (12, 0), (12, 3), (3, 3), (3, 12), (0, 12)]),
    (BOWTIE, [(0, 0), (12, 12), (0, 12), (12, 0)]),
    ([[(-.5, .25), (.5, -.5), (1.5, 1.5)]], [(-6, 3), (6, -6), (18, 18)]),
    ([[(-10000001, 0), (.5, 0), (.5, .5)]], [(-120000012, 0), (6, 0), (6, 6)]),
    ([[], *CONCAVE], [(0, 0), (12, 0), (12, 3), (3, 3), (3, 12), (0, 12)]),
]


@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("polys,pixels", VALID)
@pytest.mark.parametrize("pad", [0, 2])
def test_usable_contours_keep_baseline_pixels(path, mode, polys, pixels, pad):
    before = source_planes(path)
    filled = [p.copy() for p in before]
    full_box(path, filled, (4, 4, 16, 16), mode)
    mask = np.zeros((12, 12), np.uint8)
    cv2.fillPoly(mask, [np.array(pixels, np.int32)], 255)
    if pad:
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    expected = [p.copy() for p in before]
    for index, plane in enumerate(expected):
        if index:
            m = cv2.resize(mask, (6, 6), interpolation=cv2.INTER_NEAREST)
            roi = plane[2:8, 2:8]
            cv2.copyTo(filled[index][2:8, 2:8], m, roi)
        else:
            cv2.copyTo(filled[index][4:16, 4:16], mask, plane[4:16, 4:16])
    actual = [p.copy() for p in before]
    apply(path, actual, (4, 4, 16, 16), mode, polys, (4, 4, 16, 16), pad)
    for a, e in zip(actual, expected):
        np.testing.assert_array_equal(a, e)
    if polys in (CONCAVE, BOWTIE) and not pad:
        assert not np.array_equal(actual[0], filled[0]), "usable shape must not widen to box"


@pytest.mark.parametrize("path", ["sdr", "hdr"])
def test_valid_box_with_empty_frame_intersection_stays_noop(path):
    actual = source_planes(path)
    before = [p.copy() for p in actual]
    apply(path, actual, (40, 4, 50, 16), "box", BAD["nan"], (40, 4, 50, 16))
    for a, b in zip(actual, before):
        np.testing.assert_array_equal(a, b)


def opencv_error(code):
    failure = cv2.error("synthetic OpenCV failure")
    failure.code = code  # cv2.error constructor arguments do not populate .code
    return failure


@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("code", [cv2.Error.StsBadArg, cv2.Error.StsOutOfRange, cv2.Error.StsAssert])
def test_geometry_raster_failure_uses_known_box(path, code, monkeypatch):
    actual = source_planes(path)
    expected = [p.copy() for p in actual]
    full_box(path, expected, (4, 4, 16, 16), "box")

    def reject_geometry(*args, **kwargs):
        raise opencv_error(code)

    monkeypatch.setattr(cv2, "fillPoly", reject_geometry)
    apply(path, actual, (4, 4, 16, 16), "box", SQUARE, (4, 4, 16, 16))
    for a, e in zip(actual, expected):
        np.testing.assert_array_equal(a, e)


@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("failure", [MemoryError("allocation failed"), RuntimeError("programmer failure"),
    opencv_error(cv2.Error.StsNoMem)])
def test_resource_and_unrelated_failures_propagate(path, failure, monkeypatch):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cv2, "fillPoly", fail)
    with pytest.raises(type(failure)) as caught:
        apply(path, source_planes(path), (4, 4, 16, 16), "box", SQUARE, (4, 4, 16, 16))
    assert caught.value is failure


def ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                          capture_output=True, check=True).stdout


@pytest.fixture(scope="module")
def tiny_media(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("actual render integration requires ffmpeg")
    root = tmp_path_factory.mktemp("polygon-media")
    raw = np.concatenate([np.full(4096, 900, np.uint16),
                          np.full(1024, 800, np.uint16),
                          np.full(1024, 300, np.uint16)]).tobytes()
    (root / "source.yuv").write_bytes(raw * 2)
    hdr = root / "hdr.mp4"
    ffmpeg("-f", "rawvideo", "-pix_fmt", "yuv420p10le", "-s", "64x64", "-r", "2",
           "-i", str(root / "source.yuv"), "-c:v", "libx265", "-x265-params",
           "lossless=1:pools=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
           "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc", str(hdr))
    sdr = root / "sdr.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=64x64:rate=2:duration=1",
           "-c:v", "libx264", "-crf", "0", str(sdr))
    return {"hdr": hdr, "sdr": sdr}


@contextmanager
def observe_render(monkeypatch, path):
    """Observe real pre-write values; contain real resources even for baseline errors."""
    children, streams, captures, frames = [], [], [], []
    original_popen = subprocess.Popen
    original_capture = cv2.VideoCapture
    target = scrub.render_hdr if path == "hdr" else scrub.render
    lines, start = inspect.getsourcelines(target)
    write_line = next(start + i for i, line in enumerate(lines)
                      if ("enc.stdin.write(" if path == "hdr" else "proc.stdin.write(") in line)

    class TrackedPopen(original_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            children.append(self)
            streams.extend(s for s in (self.stdin, self.stdout, self.stderr, kwargs.get("stderr"))
                           if hasattr(s, "close"))

    def capture(*args, **kwargs):
        cap = original_capture(*args, **kwargs)
        captures.append(cap)
        return cap

    previous_trace = sys.gettrace()

    def trace(frame, event, arg):
        if frame.f_code is target.__code__ and event == "line" and frame.f_lineno == write_line:
            frames.append(frame.f_locals["buf" if path == "hdr" else "frame"].tobytes())
        return trace

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", TrackedPopen)
        patch.setattr(cv2, "VideoCapture", capture)
        sys.settrace(trace)
        try:
            yield frames
            assert frames
            for child in children:
                assert child.returncode == 0  # before harness cleanup
                if hasattr(os, "waitpid"):
                    with pytest.raises(ChildProcessError):
                        os.waitpid(child.pid, os.WNOHANG)
        finally:
            sys.settrace(previous_trace)
            for cap in captures:
                cap.release()
            # Terminate first so a decoder blocked on stdout cannot prevent containment.
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for stream in streams:
                try:
                    stream.close()
                except OSError:
                    pass
            for child in children:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("name,polys", [(n, BAD[n]) for n in ("missing_coordinate", "nan", "collinear", "repeated")]
                         + [("two_points", EMPTY["two_points"]), ("concave", CONCAVE), ("bowtie", BOWTIE)])
def test_report_to_actual_render_known_box(path, name, polys, tiny_media, tmp_path, monkeypatch):
    def render_one(label, poly):
        report = tmp_path / (label + ".json")
        report.write_text(json.dumps({"detections": [{"t_start": 0, "t_end": 1,
            "cbox": [4, 4, 16, 16], "category": "person", "text": "", "confidence": 1,
            "enabled": True, "poly": poly}],
            "render_state": {"fps": 2, "cum": [[0, 0]] * 2, "bands": [[0, 0]] * 2}}))
        detections, state, _ = scrub.load_report(str(report))
        dst = tmp_path / (label + ".mp4")
        with observe_render(monkeypatch, path) as frames:
            args = (str(tiny_media[path]), str(dst), detections, state["cum"], state["bands"], 2, 2, "box")
            if path == "hdr":
                scrub.render_hdr(*args, "libx265", {"-color_primaries": "bt2020", "-color_trc": "smpte2084", "-colorspace": "bt2020nc"})
            else:
                scrub.render(*args, False, encoder="x264")
        decoded = ffmpeg("-i", str(dst), "-f", "rawvideo", "-pix_fmt",
                         "yuv420p10le" if path == "hdr" else "bgr24", "pipe:1")
        assert len(frames) == 2 and decoded
        return frames, decoded

    actual, decoded = render_one("candidate", polys)
    if name not in ("concave", "bowtie"):
        reference, reference_decoded = render_one("full-box", None)
        assert actual == reference  # exact pre-encode coverage, including unrelated pixels
        assert decoded == reference_decoded  # separate lossy-output equivalence
    else:
        # This baseline control must remain a silhouette through the ordinary report path.
        reference, _ = render_one("full-box", None)
        assert actual != reference
