"""Actual tracker initializers; deterministic native/model boundaries only."""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import openscrub as engine
from openscrub_internal import exact_samples as exact


@pytest.fixture
def rig(monkeypatch):
    # The supplied pixels, tolerant reread and prime read deliberately differ.
    yy, xx = np.indices((48, 64))
    pixels = np.stack((xx*3, yy*4, (xx+yy)*2), axis=2).astype(np.uint8)
    near = 255-pixels
    prime = np.full_like(pixels, 73)
    captures, grabs, initializers, histograms = [], [], [], []
    class Capture:
        def __init__(self, video):
            self.index, self.releases = 0, 0
            captures.append(self)
        def isOpened(self): return True
        def getBackendName(self): return 'FFMPEG'
        def get(self, prop):
            return {cv2.CAP_PROP_FPS:24, cv2.CAP_PROP_FRAME_COUNT:48,
                    cv2.CAP_PROP_FRAME_WIDTH:64, cv2.CAP_PROP_FRAME_HEIGHT:48,
                    cv2.CAP_PROP_POS_MSEC:self.index/24*1000}.get(prop, 0)
        def set(self, prop, index):
            assert prop == cv2.CAP_PROP_POS_FRAMES
            self.index = index
            return True
        def read(self): return True, prime.copy()
        def release(self): self.releases += 1
    class Tracker:
        def init(self, frame, box): initializers.append(frame.copy())
        def update(self, frame): return False, (0,0,16,16)
        def getTrackingScore(self): return 0
    def grab(cap, time, fps):
        grabs.append(time)
        return near.copy()
    def hist(frame, *args):
        histograms.append(frame.copy())
        return np.ones((16,16), np.float32)
    monkeypatch.setattr(engine.cv2, 'VideoCapture', Capture)
    monkeypatch.setattr(engine, '_grab_frame', grab)
    monkeypatch.setattr(engine, '_vittrack_factory', lambda log: Tracker)
    monkeypatch.setattr(engine, '_crop_hist', hist)
    fields = dict(pixels=pixels, source_selection={'path':'fixture'}, index=4,
                  canonical_s=1/6, observed_s=1/6, fps=24, count=48,
                  width=64, height=48, policy=exact.POLICY, tolerance_s=1e-7)
    seed = getattr(exact, 'StrictSeed', lambda **kw: SimpleNamespace(**kw))(**fields)
    return SimpleNamespace(**locals())


def test_strict_seed_is_capture_free_and_frozen(rig):
    assert hasattr(exact, 'StrictSeed')
    with pytest.raises(FrozenInstanceError): rig.seed.index = 5
    assert not hasattr(rig.seed, 'capture')


def test_strict_person_uses_supplied_pixels(rig):
    detected = []
    class Detector:
        want_any = False
        def find(self, frame):
            detected.append(frame.copy())
            return [(8,8,40,40,.9,(),0)]
    detector = Detector()
    result = engine._track_person_dense('fixture', [8,8,40,40], 1/6,
        .16,.17, detector, lambda m: None, strict_seed=rig.seed)
    assert result[0][0] == 1/6 and len(result) == 1
    assert len(detected) == 1 and len(rig.histograms) == 2
    assert len(rig.initializers) == 2
    for frame in detected+rig.histograms: np.testing.assert_array_equal(frame, rig.pixels)
    for frame in rig.initializers:
        np.testing.assert_array_equal(frame, cv2.resize(rig.pixels, None, fx=.5, fy=.5))
    assert rig.grabs == []
    assert [cap.index for cap in rig.captures] == [4]
    assert [cap.releases for cap in rig.captures] == [1]
    assert detector.want_any is False


def test_strict_vit_uses_supplied_pixels_in_both_directions(rig):
    result = engine.track_manual_region('fixture', [8,8,40,40],1/6,.16,.17,
        strict_seed=rig.seed)
    assert result == [(1/6, (8.,8.,40.,40.),1.)]
    assert len(rig.initializers) == 2
    for frame in rig.initializers:
        np.testing.assert_array_equal(frame, cv2.resize(rig.pixels, None, fx=.5, fy=.5))
    assert rig.grabs == [] and [c.index for c in rig.captures] == [4]
    assert [c.releases for c in rig.captures] == [1]


def test_strict_ncc_template_uses_supplied_pixels(rig, monkeypatch):
    monkeypatch.setattr(engine, '_vittrack_factory', lambda log: None)
    templates = []
    real = cv2.matchTemplate
    def match(image, template, mode):
        templates.append(template.copy())
        return real(image, template, mode)
    monkeypatch.setattr(engine.cv2, 'matchTemplate', match)
    result = engine.track_manual_region('fixture', [8,8,40,40],1/6,1/6,.25,
        strict_seed=rig.seed)
    expected = cv2.GaussianBlur(cv2.resize(cv2.cvtColor(rig.pixels,
        cv2.COLOR_BGR2GRAY), None, fx=.5, fy=.5), (3,3),0)[4:20,4:20]
    assert result[0][0] == 1/6
    assert any(t.shape == expected.shape and np.array_equal(t, expected) for t in templates)
    assert 1/6 not in rig.grabs
    assert [c.index for c in rig.captures] == [4]
    assert [c.releases for c in rig.captures] == [1]


def test_strict_prime_failure_never_enters_nearby_fallback(rig, monkeypatch):
    calls = []
    def fail(*a, **kw):
        calls.append(kw)
        raise exact.ExactError('strict prime oracle')
    monkeypatch.setattr(exact, 'read_indexed_capture', fail)
    class Detector:
        want_any = False
        def find(self, frame): pytest.fail('model before strict prime')
    with pytest.raises(exact.ExactError, match='strict prime oracle'):
        engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,
            person_det=Detector(), strict_seed=rig.seed)
    assert len(calls) == 1 and rig.grabs == [] and rig.initializers == []
    assert all(c.releases == 1 for c in rig.captures)


def test_legacy_tracking_keeps_nearby_behavior(rig):
    result = engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17)
    assert result == [(1/6,(8.,8.,40.,40.),1.)]
    assert rig.grabs == [1/6, 1/6]
    for frame in rig.initializers:
        np.testing.assert_array_equal(frame, cv2.resize(rig.near,None,fx=.5,fy=.5))
