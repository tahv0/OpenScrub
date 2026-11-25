"""Stop and continue: a stopped-and-continued scan equals an uninterrupted one.

Fake detectors find a bright square that moves 3 px a frame and is hidden on
frames 14-16, so tracks cross the stop points. Every report field must match
except the timing/log fields named in _VOLATILE.
"""
import json
import os

import cv2
import numpy as np
import pytest

import openscrub
from openscrub_internal import scan_progress as sp

N = 40
W, H = 160, 96


@pytest.fixture(autouse=True)
def _no_downloads(monkeypatch):
    monkeypatch.setenv("OPENSCRUB_NO_AUTOFETCH", "1")


def _write_video(path, *, cut_at=20, changed_frame=None):
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"FFV1"), 10, (W, H))
    assert out.isOpened()
    for i in range(N):
        bg = (40, 160, 220) if i < cut_at else (200, 60, 30)
        image = np.full((H, W, 3), bg, np.uint8)
        # a little texture so frames differ and template matching has edges
        cv2.putText(image, str(i), (4, 90), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 0), 1)
        if not 14 <= i <= 16:
            x = 10 + 3 * i
            cv2.rectangle(image, (x, 30), (x + 24, 46), (255, 255, 255), -1)
        if changed_frame == i:
            image[0:8, 0:8] = 0
        out.write(image)
    out.release()


def _square(frame):
    mask = (frame.min(axis=2) > 245).astype(np.uint8)
    pts = cv2.findNonZero(mask)
    if pts is None:
        return []
    x, y, w, h = cv2.boundingRect(pts)
    return [(float(x), float(y), float(x + w), float(y + h), 0.9)]


class _Base:
    INPUT = 640

    def __init__(self, *a, **kw):
        pass

    def available(self):
        return True


class _Plate(_Base):
    def find(self, frame, scale):
        return _square(frame)


class _Person(_Base):
    def find(self, frame, scale):
        return [r + (((((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))),)) for r in _square(frame)]


class _Face(_Base):
    def find(self, frame, scale=1.0):
        return _square(frame)


class _QR(_Base):
    def find(self, frame, scale=1.0):
        return _square(frame)


class _Text(_Base):
    def find_letters_many(self, frame, boxes):
        self.last_sizes_many = [(320,) for _ in boxes]
        return [[np.array([[b[0] + 2, b[1] + 2], [b[2] - 2, b[1] + 2],
                           [b[2] - 2, b[3] - 2], [b[0] + 2, b[3] - 2]], np.float32)]
                for b in boxes]

    def find(self, frame, scale=1.0):
        return _square(frame)


KINDS = {
    "plate-full": ["--categories", "plate"],
    "plate-assisted": ["--categories", "plate", "--plate-coverage", "assisted",
                       "--no-box-fallback"],
    "face": ["--categories", "face"],
    "person": ["--categories", "person"],
    "qrcode": ["--categories", "qrcode"],
}


def _patch(monkeypatch):
    monkeypatch.setattr(openscrub, "PlateDetector", _Plate)
    monkeypatch.setattr(openscrub, "PersonDetector", _Person)
    monkeypatch.setattr(openscrub, "FaceDetector", _Face)
    monkeypatch.setattr(openscrub, "QRDetector", _QR)
    monkeypatch.setattr(openscrub, "TextRegionDetector", _Text)


def _args(video, extra):
    parser = openscrub.build_parser()
    return openscrub._prep_args(parser.parse_args(
        [video, *extra, "--tile", "off", "--no-vfr-fix"]), parser)


class _Quiet(openscrub.Callbacks):
    def __init__(self):
        super().__init__()
        self.logs = []

    def log(self, msg):
        self.logs.append(msg)


# Fields that legitimately differ between runs: none of them reach a render.
_VOLATILE = {
    "timestamp",    # provenance wall-clock time of writing the report
}


def _scrub(value):
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if k not in _VOLATILE}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _report(tmp_path, name, args, state):
    path = str(tmp_path / (name + ".json"))
    openscrub.write_report(path, args, state)
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    return _scrub(doc)


def straight(tmp_path, video, extra, control=None):
    args = _args(video, extra)
    state = openscrub.run_scan(args, _Quiet(), progress=control)
    return _report(tmp_path, "straight", args, state)


def stopped(tmp_path, video, extra, stop_at, *, clock=None):
    path = str(tmp_path / sp.PROGRESS_NAME)
    pending = list(stop_at)
    resume, runs = False, 0
    while True:
        runs += 1
        assert runs <= len(stop_at) + 1

        def stop(control_box=[]):
            control = control_box[0]
            if pending and control.next_frame == pending[0]:
                pending.pop(0)
                return True
            return False
        box = []
        control = sp.ScanProgressControl(path, stop_requested=lambda: stop(box),
                                         resume=resume, autosave_seconds=None)
        box.append(control)
        args = _args(video, extra)
        try:
            state = openscrub.run_scan(args, _Quiet(), progress=control)
        except openscrub.ScanStopped as stop_info:
            assert os.path.exists(path)
            assert stop_info.total == N
            resume = True
            continue
        assert not pending
        return _report(tmp_path, "stopped", args, state)


@pytest.mark.parametrize("kind", sorted(KINDS))
@pytest.mark.parametrize("stop_at", [[1], [13], [20], [N - 1], [5, 13, 30]],
                         ids=["first", "in-track", "at-cut", "last", "three"])
def test_stop_continue_equals_straight_scan(tmp_path, monkeypatch, kind, stop_at):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    expected = straight(tmp_path, video, KINDS[kind])
    assert expected["detections"] if "detections" in expected else expected
    got = stopped(tmp_path, video, KINDS[kind], stop_at)
    assert got == expected


def test_stop_in_fast_skip_gap_equals_straight_scan(tmp_path, monkeypatch):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    extra = KINDS["plate-assisted"] + ["--detect-windows-frac", "0-0.2,0.8-1.0"]
    expected = straight(tmp_path, video, extra)
    for stop_at in ([9], [33], [8, 34]):
        assert stopped(tmp_path, video, extra, stop_at) == expected


def test_autosave_then_crash_continues_equal(tmp_path, monkeypatch):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    extra = KINDS["plate-assisted"]
    expected = straight(tmp_path, video, extra)
    path = str(tmp_path / sp.PROGRESS_NAME)
    now = [0.0]

    class Crashy(_Plate):
        calls = 0

        def find(self, frame, scale):
            Crashy.calls += 1
            if Crashy.calls == 31:
                raise RuntimeError("crash")
            now[0] += 1.0 if Crashy.calls == 25 else 0.0
            return _square(frame)
    monkeypatch.setattr(openscrub, "PlateDetector", Crashy)
    control = sp.ScanProgressControl(path, stop_requested=lambda: False, resume=False,
                                     autosave_seconds=0.5, clock=lambda: now[0])
    with pytest.raises(RuntimeError, match="crash"):
        openscrub.run_scan(_args(video, extra), _Quiet(), progress=control)
    assert sp.load(path)["next_frame"] == 25
    monkeypatch.setattr(openscrub, "PlateDetector", _Plate)
    control = sp.ScanProgressControl(path, stop_requested=lambda: False, resume=True,
                                     autosave_seconds=None)
    args = _args(video, extra)
    state = openscrub.run_scan(args, _Quiet(), progress=control)
    assert _report(tmp_path, "continued", args, state) == expected


def test_changed_video_refuses_continue(tmp_path, monkeypatch):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    path = str(tmp_path / sp.PROGRESS_NAME)
    control = sp.ScanProgressControl(path, stop_requested=lambda: control.next_frame == 10,
                                     resume=False, autosave_seconds=None)
    with pytest.raises(openscrub.ScanStopped):
        openscrub.run_scan(_args(video, KINDS["plate-full"]), _Quiet(), progress=control)
    _write_video(video, changed_frame=30)
    control = sp.ScanProgressControl(path, stop_requested=lambda: False, resume=True,
                                     autosave_seconds=None)
    with pytest.raises(sp.ProgressMismatch) as err:
        openscrub.run_scan(_args(video, KINDS["plate-full"]), _Quiet(), progress=control)
    assert err.value.what == "the video file changed"
    assert os.path.exists(path)


def test_text_scan_is_not_supported(tmp_path):
    video = str(tmp_path / "clip.avi")
    assert not openscrub.stop_supported(_args(video, ["--categories", "name"]))
    assert openscrub.stop_supported(_args(video, ["--categories", "plate,face,anytext"]))
    args = _args(video, ["--categories", "plate"])
    args.windows_data = [{"t0": 0, "t1": 1, "cats": ["email"]}]
    assert not openscrub.stop_supported(args)
    custom = _args(video, ["--categories", "plate,badge", "--custom-regex", "badge=B\\d+"])
    assert not openscrub.stop_supported(custom)
    assert not openscrub.stop_supported(object())   # no settings: fail closed
    control = sp.ScanProgressControl(str(tmp_path / "p"), stop_requested=lambda: False,
                                     resume=False)
    with pytest.raises(ValueError, match="text categories"):
        openscrub.run_scan(_args(video, ["--categories", "name"]), progress=control)


def test_unstopped_scan_unchanged(tmp_path, monkeypatch):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    extra = KINDS["plate-full"] + ["--detect-windows-frac", "0-0.2,0.8-1.0"]
    seeks = []
    real = cv2.VideoCapture

    class Spy:
        def __init__(self, *a, **k):
            self._cap = real(*a, **k)

        def set(self, prop, value):
            seeks.append((prop, value))
            return self._cap.set(prop, value)

        def __getattr__(self, name):
            return getattr(self._cap, name)
    monkeypatch.setattr(openscrub.cv2, "VideoCapture", Spy)
    plain = straight(tmp_path, video, extra)
    plain_seeks, seeks[:] = list(seeks), []
    control = sp.ScanProgressControl(str(tmp_path / sp.PROGRESS_NAME),
                                     stop_requested=lambda: False, resume=False,
                                     autosave_seconds=None)
    assert straight(tmp_path, video, extra, control) == plain
    assert seeks == plain_seeks and plain_seeks      # fast-skip still used
    assert not os.path.exists(str(tmp_path / sp.PROGRESS_NAME))


def test_stop_before_first_frame_saves_nothing(tmp_path, monkeypatch):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    path = str(tmp_path / sp.PROGRESS_NAME)
    control = sp.ScanProgressControl(path, stop_requested=lambda: True, resume=False)
    with pytest.raises(openscrub.PipelineCancelled):
        openscrub.run_scan(_args(video, KINDS["plate-full"]), _Quiet(), progress=control)
    assert not os.path.exists(path)


def test_autosave_failure_never_kills_an_unstopped_scan(tmp_path, monkeypatch):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    extra = KINDS["plate-full"]
    expected = straight(tmp_path, video, extra)

    def full_disk(path, state):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(sp, "save", full_disk)
    now = [0.0]
    control = sp.ScanProgressControl(str(tmp_path / sp.PROGRESS_NAME),
                                     stop_requested=lambda: False, resume=False,
                                     autosave_seconds=0.5, clock=lambda: now.__setitem__(0, now[0] + 1) or now[0])
    cb = _Quiet()
    args = _args(video, extra)
    state = openscrub.run_scan(args, cb, progress=control)
    assert _report(tmp_path, "survived", args, state) == expected
    assert any("autosave off" in m for m in cb.logs)


def test_unportable_setting_only_disables_stop(tmp_path, monkeypatch):
    _patch(monkeypatch)
    video = str(tmp_path / "clip.avi")
    _write_video(video)
    args = _args(video, KINDS["plate-full"])
    args.surprise = object()          # a value the identity cannot record
    control = sp.ScanProgressControl(str(tmp_path / sp.PROGRESS_NAME),
                                     stop_requested=lambda: False, resume=False)
    cb = _Quiet()
    openscrub.run_scan(args, cb, progress=control)
    assert any("Stop is not available for this scan" in m for m in cb.logs)
    args = _args(video, KINDS["plate-full"])
    args.surprise = object()
    resume = sp.ScanProgressControl(str(tmp_path / sp.PROGRESS_NAME),
                                    stop_requested=lambda: False, resume=True)
    with pytest.raises(sp.ProgressError):
        openscrub.run_scan(args, _Quiet(), progress=resume)
