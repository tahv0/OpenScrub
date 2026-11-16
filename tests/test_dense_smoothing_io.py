"""Dense smoothing must retrieve only useful pixels and own its decoder."""
from dataclasses import asdict
import os

os.environ.setdefault("OPENSCRUB_NO_AUTOFETCH", "1")

import cv2
import numpy as np
import pytest

import openscrub


class Capture:
    """Sequential decoder with frame IDs and controllable I/O failures."""
    def __init__(self, frames=200, fail_grab=None, fail_read=None, opened=True):
        self.frames = frames
        self.fail_grab, self.fail_read = fail_grab, fail_read
        self.opened = opened
        self.pos = 0
        self.reads, self.grabs = [], []
        self.releases = 0

    def isOpened(self):
        return self.opened

    def get(self, prop):
        assert prop == cv2.CAP_PROP_FPS
        return 10.0

    def read(self):
        self.reads.append(self.pos)
        if self.pos >= self.frames or self.pos == self.fail_read:
            return False, None
        frame = np.full((64, 96, 3), self.pos % 256, np.uint8)
        self.pos += 1
        return True, frame

    def grab(self):
        self.grabs.append(self.pos)
        if self.pos >= self.frames or self.pos == self.fail_grab:
            return False
        self.pos += 1
        return True

    def release(self):
        self.releases += 1


def detection(t, track=1):
    return openscrub.Detection(t, t, (24, 16, 56, 48), "face", "synthetic",
                               .95, dense=True, track=track, poly=())


def install_capture(monkeypatch, cap):
    monkeypatch.setattr(openscrub.cv2, "VideoCapture", lambda _: cap)
    converted = []
    cvt_color = cv2.cvtColor

    def convert(frame, code):
        converted.append(int(frame[0, 0, 0]))
        return cvt_color(frame, code)

    monkeypatch.setattr(openscrub.cv2, "cvtColor", convert)
    return converted


def test_prefix_and_gap_avoid_retrieval_without_changing_frames(monkeypatch):
    cap = Capture()
    converted = install_capture(monkeypatch, cap)
    dets = [detection(6), detection(12, 2)]
    assert openscrub.smooth_dense_tracks(dets, 10, "synthetic") == (0, 0, .5)
    needed = list(range(16, 63)) + list(range(76, 121))
    assert converted == needed
    assert cap.reads == needed
    assert cap.grabs == list(range(16)) + list(range(63, 76))
    assert [(d.t_start, d.t_end, d.cbox, d.track, d.poly) for d in dets] == [
        (5.75, 6.25, (24, 16, 56, 48), 1, ()),
        (11.75, 12.25, (24, 16, 56, 48), 2, ())]
    assert cap.releases == 1


def test_overlapping_all_needed_spans_reuse_cached_frames(monkeypatch):
    cap = Capture()
    converted = install_capture(monkeypatch, cap)
    dets = [detection(2), detection(2, 2), detection(4, 3)]
    assert openscrub.smooth_dense_tracks(dets, 10, "synthetic") == (0, 0, .75)
    assert converted == list(range(41))
    assert cap.reads == list(range(41))
    assert cap.grabs == []
    assert cap.releases == 1


@pytest.mark.parametrize("kwargs,grabs,reads,converted", [
    ({"frames": 10}, list(range(11)), [], []),
    ({"fail_grab": 7}, list(range(8)), [], []),
    ({"fail_read": 20}, list(range(16)), list(range(16, 21)), list(range(16, 20))),
    ({"frames": 20}, list(range(16)), list(range(16, 21)), list(range(16, 20))),
])
def test_eof_or_failed_advance_stops_without_later_mislabeled_frames(
        monkeypatch, kwargs, grabs, reads, converted):
    cap = Capture(**kwargs)
    seen = install_capture(monkeypatch, cap)
    dets = [detection(6), detection(12, 2)]
    assert openscrub.smooth_dense_tracks(dets, 10, "synthetic") == (0, 0, .5)
    assert (cap.grabs, cap.reads, seen) == (grabs, reads, converted)
    assert cap.releases == 1


@pytest.mark.parametrize("cancel_after,advances", [(0, 0), (1, 90), (91, 180)])
def test_cancellation_in_prefix_keeps_checkpoints_and_releases(
        monkeypatch, cancel_after, advances):
    cap = Capture(frames=500)
    install_capture(monkeypatch, cap)

    class Cancel(openscrub.Callbacks):
        def cancelled(self):
            return cap.pos >= cancel_after

    with pytest.raises(openscrub.PipelineCancelled):
        openscrub.smooth_dense_tracks([detection(30)], 10, "synthetic", cb=Cancel())
    assert cap.pos == advances
    assert cap.reads == []
    assert cap.releases == 1


@pytest.mark.parametrize("failure", ["isOpened", "get", "read", "grab", "convert", "matching", "progress", "final_progress"])
def test_decoder_released_when_processing_raises(monkeypatch, failure):
    cap = Capture()
    install_capture(monkeypatch, cap)

    def broken(*args, **kwargs):
        raise RuntimeError("injected failure")

    cb = openscrub.Callbacks()
    if failure in ("isOpened", "get", "read", "grab"):
        monkeypatch.setattr(cap, failure, broken)
    elif failure == "progress":
        cb.progress = broken
    elif failure == "final_progress":
        cb.progress = lambda stage, done, total: broken() if done == total else None
    elif failure == "convert":
        monkeypatch.setattr(openscrub.cv2, "cvtColor", broken)
    else:
        # Real textured pixels reach the actual template-matching branch.
        rng = np.random.default_rng(8)
        frame = rng.integers(0, 255, (64, 96, 3), dtype=np.uint8)
        monkeypatch.setattr(cap, "read", lambda: (True, frame))
        monkeypatch.setattr(openscrub.cv2, "matchTemplate", broken)
    with pytest.raises(RuntimeError, match="injected failure"):
        openscrub.smooth_dense_tracks([detection(6 if failure == "grab" else 2)],
                                     10, "synthetic", cb=cb)
    assert cap.releases == 1


def test_failed_open_is_released_and_preserves_no_video_behavior(monkeypatch):
    cap = Capture(opened=False)
    install_capture(monkeypatch, cap)
    actual = [detection(6)]
    expected = [detection(6)]
    want = openscrub.smooth_dense_tracks(expected, 10, None)
    assert openscrub.smooth_dense_tracks(actual, 10, "unopenable") == want
    assert [asdict(d) for d in actual] == [asdict(d) for d in expected]
    assert cap.reads == cap.grabs == []
    assert cap.releases == 1


def test_no_tracks_never_opens_decoder(monkeypatch):
    def unexpected(_):
        pytest.fail("no tracks should not open video")
    monkeypatch.setattr(openscrub.cv2, "VideoCapture", unexpected)
    assert openscrub.smooth_dense_tracks([], 10, "synthetic") == (0, 0, 0.0)


def test_marked_video_preserves_matching_and_complete_detections(tmp_path, monkeypatch):
    """Lossless marked pixels catch skipped/duplicated frames and onset changes."""
    import hashlib
    import json

    path = str(tmp_path / "marked.avi")
    rng = np.random.default_rng(111)
    patch = rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"FFV1"), 10, (128, 96))
    assert writer.isOpened()
    try:
        for index in range(130):
            frame = np.full((96, 128, 3), 60, np.uint8)
            frame[:8, :] = index
            if 50 <= index <= 70:
                x = 40 + (index - 50) // 5 * 2
                frame[40:72, x:x + 32] = patch
            writer.write(frame)
    finally:
        writer.release()
    native = cv2.VideoCapture(path)
    assert native.isOpened()

    class Counted:
        def __init__(self):
            self.reads = self.grabs = self.releases = 0

        def __getattr__(self, name):
            return getattr(native, name)

        def read(self):
            self.reads += 1
            return native.read()

        def grab(self):
            self.grabs += 1
            return native.grab()

        def set(self, *args):
            pytest.fail("smoothing must retain sequential access")

        def release(self):
            self.releases += 1
            native.release()

    cap = Counted()
    seen = install_capture(monkeypatch, cap)
    dets = [openscrub.Detection(t, t, (44, 40, 76, 72), "face", "synthetic", .95,
                                dense=True, track=1, poly=()) for t in (6., 6.2, 6.3)]
    assert openscrub.smooth_dense_tracks(dets, 10, path) == (1, 5, 1.25)
    assert seen == list(range(16, 61))
    assert (cap.reads, cap.grabs, cap.releases) == (45, 16, 1)
    # Characterized on the full pre-change module e21ebdf, not recomputed
    # from the optimized implementation: includes every dataclass field.
    rows = json.dumps([asdict(d) for d in dets], sort_keys=True).encode()
    assert hashlib.sha256(rows).hexdigest() == (
        "2c61c2352afd72a6f69ea46398b3947eaf00b80e82609d9148c3368b805ba050")
