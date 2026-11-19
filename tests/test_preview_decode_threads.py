"""Preview decoder selection and backwards-compatible fallback."""
import math
import sys
from unittest.mock import Mock

import pytest

import openscrub_web as web


@pytest.fixture(autouse=True)
def restore_threads(monkeypatch):
    # main() assigns these before the test stops startup; restore even when
    # the embedding process had already configured either value.
    monkeypatch.setattr(web, "TOKEN", web.TOKEN)
    monkeypatch.setitem(web.app.config, "MAX_CONTENT_LENGTH",
                        web.app.config["MAX_CONTENT_LENGTH"])
    previous = web.app.config.pop("PREVIEW_DECODE_THREADS", None)
    yield
    if previous is None:
        web.app.config.pop("PREVIEW_DECODE_THREADS", None)
    else:
        web.app.config["PREVIEW_DECODE_THREADS"] = previous


class Capture:
    def __init__(self, opened=True, count=2, error=None):
        self.opened, self.count, self.error = opened, count, error
        self.releases = 0

    def isOpened(self):
        if self.error == "opened":
            raise RuntimeError("unexpected")
        return self.opened

    def get(self, prop):
        assert prop == web.cv2.CAP_PROP_N_THREADS
        if self.error:
            raise self.error
        return self.count

    def release(self):
        self.releases += 1


def configure(monkeypatch, candidate=None, failure=None):
    monkeypatch.setattr(web.cv2, "CAP_PROP_N_THREADS", 70, raising=False)
    monkeypatch.setattr(web.cv2, "CAP_FFMPEG", 1900, raising=False)
    legacy = Capture()
    calls = []

    def open_capture(*args):
        calls.append(args)
        if len(args) == 1:
            return legacy
        if failure:
            raise failure
        return candidate

    monkeypatch.setattr(web.cv2, "VideoCapture", open_capture)
    web.app.config["PREVIEW_DECODE_THREADS"] = 2
    return calls, legacy


@pytest.mark.parametrize("configured", [False, True], ids=["absent", "zero"])
def test_default_uses_only_original_constructor_without_probe(monkeypatch, configured):
    sentinel = object()
    constructor = Mock(return_value=sentinel)

    class NoCapabilityProbes:
        VideoCapture = constructor

        def __getattr__(self, name):
            if name in ("CAP_PROP_N_THREADS", "CAP_FFMPEG"):
                raise AssertionError("unexpected capability lookup: " + name)
            raise AttributeError(name)

    monkeypatch.setattr(web, "cv2", NoCapabilityProbes())
    if configured:
        web.app.config["PREVIEW_DECODE_THREADS"] = 0
    assert web._open_preview_capture("movie.mp4") is sentinel
    constructor.assert_called_once_with("movie.mp4")


def test_matching_open_capture_transfers_ownership(monkeypatch):
    candidate = Capture(count=2)
    calls, _ = configure(monkeypatch, candidate)
    assert web._open_preview_capture("movie.mp4") is candidate
    assert calls == [("movie.mp4", 1900, [70, 2])]
    assert candidate.releases == 0


@pytest.mark.parametrize("missing", ["CAP_PROP_N_THREADS", "CAP_FFMPEG"])
def test_missing_capability_falls_back_once(monkeypatch, missing):
    calls, legacy = configure(monkeypatch)
    monkeypatch.delattr(web.cv2, missing, raising=False)
    assert web._open_preview_capture("movie.mp4") is legacy
    assert calls == [("movie.mp4",)]


@pytest.mark.parametrize("failure", [TypeError("legacy"), web.cv2.error("unsupported")])
def test_constructor_compatibility_falls_back_once(monkeypatch, failure):
    calls, legacy = configure(monkeypatch, failure=failure)
    assert web._open_preview_capture("movie.mp4") is legacy
    assert calls == [("movie.mp4", 1900, [70, 2]), ("movie.mp4",)]


@pytest.mark.parametrize("candidate", [Capture(opened=False), Capture(count=0),
                                       Capture(count=1), Capture(count=math.nan),
                                       Capture(error=web.cv2.error("unsupported"))])
def test_rejected_candidate_is_released_then_falls_back_once(monkeypatch, candidate):
    calls, legacy = configure(monkeypatch, candidate)
    assert web._open_preview_capture("movie.mp4") is legacy
    assert candidate.releases == 1
    assert calls == [("movie.mp4", 1900, [70, 2]), ("movie.mp4",)]


def test_unexpected_failure_releases_and_propagates(monkeypatch):
    candidate = Capture(error="opened")
    calls, _ = configure(monkeypatch, candidate)
    with pytest.raises(RuntimeError, match="unexpected"):
        web._open_preview_capture("movie.mp4")
    assert candidate.releases == 1
    assert calls == [("movie.mp4", 1900, [70, 2])]


def test_legacy_failure_propagates(monkeypatch):
    candidate = Capture(opened=False)
    configure(monkeypatch, candidate)
    def fail(*args):
        if len(args) == 1:
            raise ValueError("legacy failure")
        return candidate
    monkeypatch.setattr(web.cv2, "VideoCapture", fail)
    with pytest.raises(ValueError, match="legacy failure"):
        web._open_preview_capture("movie.mp4")
    assert candidate.releases == 1


@pytest.mark.parametrize("value", [None, "0", "1", "2", "4"])
def test_cli_assigns_threads_before_startup(monkeypatch, value):
    args = ["openscrub-web"] if value is None else ["openscrub-web", "--preview-decode-threads", value]
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(web, "TOKEN", "preconfigured-token")
    monkeypatch.setitem(web.app.config, "MAX_CONTENT_LENGTH", 1234)
    def stop(*args, **kwargs):
        raise RuntimeError("startup stopped")
    monkeypatch.setattr(web.os, "makedirs", stop)
    with pytest.raises(RuntimeError, match="startup stopped"):
        web.main()
    assert web.app.config["PREVIEW_DECODE_THREADS"] == (int(value) if value is not None else 0)


def test_cli_rejects_other_values_before_startup(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["openscrub-web", "--preview-decode-threads", "3"])
    with pytest.raises(SystemExit) as error:
        web.main()
    assert error.value.code == 2


def test_real_consumers_keep_pixels_metadata_and_jpegs(tmp_path, monkeypatch):
    """Exercise the four consumers with a small deterministic video."""
    import hashlib
    import numpy as np

    video = str(tmp_path / "fixture.avi")
    writer = web.cv2.VideoWriter(video, web.cv2.VideoWriter_fourcc(*"MJPG"), 4, (96, 80))
    if not writer.isOpened():
        pytest.skip("MJPG writer unavailable")
    y, x = np.indices((80, 96))
    for i in range(8):
        frame = np.stack(((x * 7 + i * 13) % 256, (y * 9 + i * 17) % 256,
                          ((x + y) * 5 + i * 23) % 256), axis=-1).astype("uint8")
        writer.write(frame)
    writer.release()
    doc = {"render_state": {"fps": 4, "cum": [[0, 0]] * 8},
           "detections": [{"t_start": 0, "t_end": 1.75, "last_seen": 1,
                           "cbox": [30, 25, 65, 55]}]}
    job = {"id": "decoder-test", "video": video, "output": video,
           "dir": str(tmp_path), "log": [], "options": {"skip_review": False}}
    monkeypatch.setitem(web.JOBS, job["id"], job)
    monkeypatch.setattr(web, "build_args", lambda job: None)
    monkeypatch.setattr(web.openscrub, "run_scan", lambda args, cb: {"stats": {}})
    monkeypatch.setattr(web.openscrub, "write_report", lambda *args: None)
    monkeypatch.setattr(web, "_load_job_report", lambda job: doc)
    class InlineThread:
        def __init__(self, target, daemon):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(web.threading, "Thread", InlineThread)
    real_open = web._open_preview_capture
    calls = []

    def recording_open(path):
        calls.append((path, web.app.config["PREVIEW_DECODE_THREADS"]))
        return real_open(path)

    monkeypatch.setattr(web, "_open_preview_capture", recording_open)
    results = []
    for mode in (0, 1, 2, 4):
        web.app.config["PREVIEW_DECODE_THREADS"] = mode
        frames = [web._frame_at(job, t, doc["render_state"]) for t in (0, 1, 1.75)]
        assert calls == [(video, mode)] * 3
        calls.clear()
        assert all(frame is not None for frame in frames)
        pixels = [(hashlib.sha256(frame.tobytes()).hexdigest(),
                   hashlib.sha256(frame[3:44, 5:62].tobytes()).hexdigest()) for frame in frames]
        with web.app.test_client() as client:
            info = client.get('/api/jobs/decoder-test/mediainfo')
            assert calls == [(video, mode)]
            calls.clear()
            previews = []
            for t in (0, 1, 1.75, 2.1):
                previews.append(client.get('/api/jobs/decoder-test/frame_at',
                                           query_string={"t": t, "src": "output"}))
                assert calls == [(video, mode)]
                calls.clear()
        assert info.status_code == 200
        assert all(response.status_code == 200 for response in previews)
        thumb = tmp_path / 'thumb2_0.jpg'
        if thumb.exists():
            thumb.unlink()
        web._run_job(job, 'scan')
        assert calls == [(video, mode)]
        calls.clear()
        assert thumb.exists(), job['log']
        results.append((pixels, info.get_json(), [p.data for p in previews], thumb.read_bytes()))
    assert all(result == results[0] for result in results[1:])
