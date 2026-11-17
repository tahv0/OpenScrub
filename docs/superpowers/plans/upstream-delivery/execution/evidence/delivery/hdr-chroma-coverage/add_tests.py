from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
(root/'tests').mkdir(exist_ok=True)
(root/'tests/test_hdr_chroma_coverage.py').write_text('''"""Global chroma membership of the existing ordinary silhouette luma mask.

Synthetic native planes and real tiny report renders; decoded lossy pixels
are never the mask oracle. Process containment belongs only to this harness.
"""
import ast
from contextlib import contextmanager
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import openscrub

MODES = ("box", "blur", "mosaic", "inpaint")
SQUARE = ((0, 0), (12, 0), (12, 12), (0, 12))
SPARSE = ((1, 1), (2, 1), (1, 2))
SHAPES = (SQUARE, SPARSE, ((10, 0), (12, 0), (12, 2)),
          ((0, 0), (12, 12), (10, 12)))
REGIONS = ((4, 4, 16, 16), (5, 4, 17, 16),
           (4, 5, 16, 17), (5, 5, 17, 17),
           (5, 5, 18, 16), (-2, -1, 11, 12),
           (23, 23, 36, 36), (-2, 23, 11, 36), (23, -1, 36, 12))
TAGS = {"-color_primaries": "bt2020", "-color_trc": "smpte2084",
        "-colorspace": "bt2020nc"}


def _masks(region, vertices, pad, shape=(32, 32)):
    """Rasterize literal integer vertices, then enumerate global coordinates.

    Padding is an explicit square-neighbourhood union, independent of the
    production dilation and its global-alignment/reduction implementation.
    """
    h, w = shape
    left, top = max(0, region[0]), max(0, region[1])
    right, bottom = min(w, region[2]), min(h, region[3])
    local = np.zeros((bottom - top, right - left), np.uint8)
    points = np.array([(region[0] + x - left, region[1] + y - top)
                       for x, y in vertices], np.int32)
    cv2.fillPoly(local, [points], 1)
    selected = {(top + int(row), left + int(col))
                for row, col in np.argwhere(local)}
    expanded = {(row + dy, col + dx) for row, col in selected
                for dy in range(-pad, pad + 1) for dx in range(-pad, pad + 1)
                if top <= row + dy < bottom and left <= col + dx < right}
    luma = np.zeros(shape, bool)
    chroma = np.zeros((h // 2, w // 2), bool)
    for row, col in expanded:
        luma[row, col] = True
        chroma[row // 2, col // 2] = True
    return luma, chroma


def _poly(region, vertices):
    return (tuple((x / (region[2] - region[0]),
                   y / (region[3] - region[1])) for x, y in vertices),)


def _planes():
    # Odd source values make inpaint's multiples of four distinguishable;
    # checkerboard contrast makes blur/mosaic meaningful even at sparse edges.
    planes = []
    for size, low, high in ((32, 101, 901), (16, 53, 853), (16, 153, 953)):
        row, col = np.indices((size, size))
        planes.append(np.where((row + col) % 2, low, high).astype(np.uint16))
    return planes


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pad", (0, 1, 3))
@pytest.mark.parametrize("vertices", SHAPES, ids=("square-control", "sparse", "thin-edge", "diagonal"))
@pytest.mark.parametrize("region", REGIONS)
def test_every_touched_global_chroma_cell(region, vertices, pad, mode):
    """Nearest sampling, misalignment or over-expansion breaks exact planes."""
    masks = _masks(region, vertices, pad)
    source = _planes()
    full = [p.copy() for p in source]
    # Existing rectangle owner provides the unchanged mode effect, not mask
    # membership. Its mode calculations match this owner's full-ROI effects.
    openscrub._blur_yuv10(*full, *region, mode)
    actual = [p.copy() for p in source]
    openscrub._blur_silhouette_yuv10(*actual, *region, mode,
                                    _poly(region, vertices), region, pad_px=pad)
    for name, before, filled, result, mask in zip(
            ("Y", "U", "V"), source, full, actual, (masks[0], masks[1], masks[1])):
        assert mask.any(), (region, vertices)
        assert np.all(filled[mask] != before[mask]), ("ineffective fixture", mode, name)
        expected = before.copy()
        expected[mask] = filled[mask]
        np.testing.assert_array_equal(result, expected, err_msg=name)
        np.testing.assert_array_equal(result != before, mask, err_msg=name + " cell identity")


def test_sparse_triangle_literal_cells_and_filled_square_control():
    luma, chroma = _masks((4, 4, 16, 16), SPARSE, 0)
    assert np.argwhere(luma).tolist() == [[5, 5], [5, 6], [6, 5]]
    assert np.argwhere(chroma).tolist() == [[2, 2], [2, 3], [3, 2]]
    y = np.full((8, 8), 900, np.uint16)
    u = np.full((4, 4), 800, np.uint16)
    v = np.full((4, 4), 300, np.uint16)
    openscrub._blur_silhouette_yuv10(y, u, v, 1, 1, 5, 5, "box",
                                    (((0, 0), (1, 0), (1, 1), (0, 1)),), (1, 1, 5, 5))
    expected = np.zeros((4, 4), bool)
    expected[:3, :3] = True
    np.testing.assert_array_equal(u == 512, expected)
    np.testing.assert_array_equal(v == 512, expected)


def _command(args):
    return subprocess.run(args, check=True, capture_output=True, timeout=30).stdout


def _decode(path, pix_fmt):
    return _command(["ffmpeg", "-v", "error", "-i", str(path),
                     "-f", "rawvideo", "-pix_fmt", pix_fmt, "pipe:1"])


def _metadata(path):
    return json.loads(_command([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_frames,"
        "color_transfer,color_primaries,color_space", "-of", "json", str(path)
    ]))["streams"][0]


@pytest.fixture
def hdr_source(tmp_path):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg/ffprobe required")
    if b"libx265" not in _command(["ffmpeg", "-hide_banner", "-encoders"]):
        pytest.skip("libx265 required for actual ten-bit PQ fixture")
    raw = np.concatenate([np.full(4096, 900, np.uint16),
                          np.full(1024, 800, np.uint16),
                          np.full(1024, 300, np.uint16)]).tobytes() * 3
    source_raw = tmp_path / "source.yuv"
    source_raw.write_bytes(raw)
    src = tmp_path / "source.mp4"
    colors = [a for item in TAGS.items() for a in item]
    _command(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f",
              "rawvideo", "-pix_fmt", "yuv420p10le", "-s", "64x64", "-r", "3",
              *colors, "-i", str(source_raw), "-c:v", "libx265", "-x265-params",
              "lossless=1:pools=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
              *colors, str(src)])
    assert _decode(src, "yuv420p10le") == raw
    return src, raw


@contextmanager
def _observe_encoder(monkeypatch, owner):
    """Read the real encoder-write argument without replacing commands or IO."""
    children, error_files, captured = [], [], []
    popen = subprocess.Popen
    temporary_file = openscrub.tempfile.TemporaryFile
    lines, start = inspect.getsourcelines(owner)
    writes = {start + n.lineno - 1 for n in ast.walk(ast.parse("".join(lines)))
              if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
              and isinstance(n.value.func, ast.Attribute)
              and n.value.func.attr == "write"}

    class ObservedPopen(popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            children.append(self)

    def observe_file(*args, **kwargs):
        file = temporary_file(*args, **kwargs)
        error_files.append(file)
        return file

    def trace(frame, event, arg):
        if frame.f_code is owner.__code__:
            if event == "line" and frame.f_lineno in writes:
                data = frame.f_locals["buf"] if owner is openscrub.render_hdr else frame.f_locals["frame"]
                captured.append(data.tobytes())
            return trace
        return None

    previous = sys.gettrace()
    with monkeypatch.context() as patch:
        patch.setattr(openscrub.subprocess, "Popen", ObservedPopen)
        patch.setattr(openscrub.tempfile, "TemporaryFile", observe_file)
        try:
            sys.settrace(trace)
            yield captured, children
        finally:
            sys.settrace(previous)
            # Always contain actual children/streams, including RED failures.
            # These closes are harness work, not production cleanup evidence.
            for child in children:
                if child.poll() is None:
                    child.terminate()
                for name in ("stdin", "stdout", "stderr"):
                    stream = getattr(child, name)
                    if stream is not None and not stream.closed:
                        stream.close()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            for file in error_files:
                file.close()


def _report_state(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"detections": [{"t_start": 0, "t_end": 1,
        "cbox": [5, 4, 17, 16], "category": "person", "text": "",
        "confidence": 1, "enabled": True,
        "poly": _poly((5, 4, 17, 16), SPARSE)}],
        "render_state": {"fps": 3, "cum": [[0, 0]] * 3, "bands": [[0, 0]] * 3}}))
    detections, state, _ = openscrub.load_report(str(report))
    return dict(state, detections=detections, stats={"synthetic": True})


def _args(source, output, hdr):
    return SimpleNamespace(video=str(source), output=str(output), preview=False,
                           hdr_source=str(source) if hdr else None,
                           hdr_encoder="libx265", hdr_tags=TAGS, encoder="x264",
                           pad=0, mode="box", report=None)


def _assert_children_finished(children):
    render_children = [p for p in children if "pipe:0" in p.args or "pipe:1" in p.args]
    assert render_children
    for child in render_children:
        assert child.returncode == 0
        for stream in (child.stdin, child.stdout):
            if stream is not None:
                assert stream.closed
        if os.name == "posix":
            with pytest.raises(ChildProcessError):
                os.waitpid(child.pid, os.WNOHANG)
    print("ENCODER_CHILDREN " + json.dumps([
        {"pid": p.pid, "returncode": p.returncode} for p in render_children]))


@pytest.mark.parametrize("masked", (True, False), ids=("sparse-report", "unmasked-control"))
def test_report_run_render_hdr_exact_encoder_input(masked, hdr_source, tmp_path, monkeypatch):
    source, raw = hdr_source
    output = tmp_path / "hdr.mp4"
    state = _report_state(tmp_path)
    if not masked:
        state["detections"] = []
    with _observe_encoder(monkeypatch, openscrub.render_hdr) as (captured, children):
        result = openscrub.run_render(_args(source, output, True), state)
        _assert_children_finished(children)
        assert result == {"synthetic": True, "output": str(output)}
        assert len(captured) == 3
        (tmp_path / "preencode.yuv").write_bytes(b"".join(captured))
        expected = np.frombuffer(raw[:12288], np.uint16).copy()
        if masked:
            # Hand-derived global cells for origin (5,4), independent of leaf.
            expected[:4096].reshape(64, 64)[(5, 5, 6), (6, 7, 6)] = 64
            expected[4096:5120].reshape(32, 32)[(2, 3), (3, 3)] = 512
            expected[5120:].reshape(32, 32)[(2, 3), (3, 3)] = 512
        assert b"".join(captured) == expected.tobytes() * 3
    assert _metadata(source) == _metadata(output) == {
        "codec_name": "hevc", "width": 64, "height": 64,
        "pix_fmt": "yuv420p10le", "color_space": "bt2020nc",
        "color_transfer": "smpte2084", "color_primaries": "bt2020",
        "nb_read_frames": "3"}
    decoded = _decode(output, "yuv420p10le")
    (tmp_path / "decoded.yuv").write_bytes(decoded)
    assert len(decoded) == len(raw)  # decoded lossy values are not a mask oracle


def test_report_run_render_sdr_control(hdr_source, tmp_path, monkeypatch):
    source, _ = hdr_source
    output = tmp_path / "sdr.mp4"
    decoded_source = _decode(source, "bgr24")
    expected = np.frombuffer(decoded_source, np.uint8).copy().reshape(3, 64, 64, 3)
    expected[:, (5, 5, 6), (6, 7, 6)] = 0
    with _observe_encoder(monkeypatch, openscrub.render) as (captured, children):
        openscrub.run_render(_args(source, output, False), _report_state(tmp_path))
        _assert_children_finished(children)
        assert len(captured) == 3
        (tmp_path / "preencode.bgr").write_bytes(b"".join(captured))
        assert b"".join(captured) == expected.tobytes()
    assert _metadata(output)["nb_read_frames"] == "3"
    assert _metadata(output)["pix_fmt"] == "yuv420p"
    (tmp_path / "decoded.bgr").write_bytes(_decode(output, "bgr24"))
''')
