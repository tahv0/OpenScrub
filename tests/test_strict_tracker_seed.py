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


@pytest.mark.parametrize('field,value', [('index',True),('index',48),('fps',True),
    ('count',False),('width',63),('canonical_s',.2),('observed_s',.2),
    ('policy','nearby'),('tolerance_s',1/24),('pixels',None)],
    ids=['bool-index','index-overflow','bool-fps','bool-count','dimensions',
         'noncanonical','wrong-observed','wrong-policy','adjacent-tolerance','no-pixels'])
def test_invalid_strict_seed_never_opens_or_resolves(rig, field, value):
    fields = dict(rig.fields); fields[field] = value
    with pytest.raises(exact.ExactError):
        seed = exact.StrictSeed(**fields)
        engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,strict_seed=seed)
    assert rig.captures == [] and rig.initializers == []


@pytest.mark.parametrize('box,reference,start,end', [([True,8,40,40],1/6,.16,.17),
    ([8,8,65,40],1/6,.16,.17),([40,8,8,40],1/6,.16,.17),
    ([8,8,40,40],.2,.16,.21),([8,8,40,40],1/6,.17,.3),
    ([8,8,40,40],1/6,False,.3)],
    ids=['bool-box','outside-box','reversed-box','requested-reference','outside-window','bool-window'])
def test_invalid_strict_inputs_never_open_or_resolve(rig,box,reference,start,end):
    with pytest.raises(exact.ExactError):
        engine.track_manual_region('fixture',box,reference,start,end,strict_seed=rig.seed)
    assert rig.captures == [] and rig.initializers == []


def test_strict_person_miss_fallback_uses_same_supplied_pixels(rig):
    class Detector:
        want_any = False
        def find(self,frame):
            np.testing.assert_array_equal(frame,rig.pixels)
            return []
    result=engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,
        person_det=Detector(),strict_seed=rig.seed)
    assert result[0][0] == 1/6
    assert rig.grabs == [] and [c.index for c in rig.captures] == [4,4]
    assert [c.releases for c in rig.captures] == [1,1]
    for frame in rig.initializers:
        np.testing.assert_array_equal(frame,cv2.resize(rig.pixels,None,fx=.5,fy=.5))



def test_strict_person_prime_error_releases_both_captures(rig,monkeypatch):
    original=exact.read_indexed_capture;calls=[]
    def read(cap,index,**kwargs):
        calls.append(index)
        if len(calls)==2:raise exact.ExactError('person prime retained oracle')
        return original(cap,index,**kwargs)
    monkeypatch.setattr(exact,'read_indexed_capture',read)
    detector=SimpleNamespace(want_any=False,find=lambda frame:pytest.fail('model after failed prime'))
    with pytest.raises(exact.ExactError,match='person prime retained oracle'):
        engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,
            person_det=detector,strict_seed=rig.seed)
    assert calls==[4,4] and rig.grabs==[] and rig.initializers==[]
    assert [c.releases for c in rig.captures]==[1,1] and detector.want_any is False


def test_strict_person_model_error_fallback_keeps_supplied_pixels(rig):
    errors=[]
    def find(frame):
        np.testing.assert_array_equal(frame,rig.pixels)
        error=RuntimeError('person detector retained oracle');errors.append(error);raise error
    detector=SimpleNamespace(want_any=False,find=find)
    result=engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,
        person_det=detector,strict_seed=rig.seed)
    assert result==[(1/6,(8.,8.,40.,40.),1.)] and len(errors)==1
    assert [c.releases for c in rig.captures]==[1,1] and detector.want_any is False
    assert [c.index for c in rig.captures]==[4,4] and rig.grabs==[]
    for frame in rig.initializers:
        np.testing.assert_array_equal(frame,cv2.resize(rig.pixels,None,fx=.5,fy=.5))



def test_strict_person_metadata_error_releases_capture(rig,monkeypatch):
    errors=[]
    def get(cap,prop):
        error=exact.ExactError('metadata retained oracle');errors.append(error);raise error
    monkeypatch.setattr(rig.Capture,'get',get)
    detector=SimpleNamespace(want_any=False,find=lambda frame:[])
    with pytest.raises(exact.ExactError,match='metadata retained oracle'):
        engine._track_person_dense('fixture',[8,8,40,40],1/6,.16,.17,
            detector,lambda m:None,strict_seed=rig.seed)
    assert len(errors)==1 and [c.releases for c in rig.captures]==[1]
    assert detector.want_any is False



def test_strict_native_person_prime_error_never_falls_back(rig,monkeypatch):
    original=exact.read_indexed_capture;calls=[];errors=[]
    def read(cap,index,**kwargs):
        calls.append(index)
        if len(calls)==2:
            error=RuntimeError('native person prime retained oracle');errors.append(error);raise error
        return original(cap,index,**kwargs)
    monkeypatch.setattr(exact,'read_indexed_capture',read)
    detector=SimpleNamespace(want_any=False,find=lambda frame:pytest.fail('detector after prime error'))
    with pytest.raises(exact.ExactError,match='native person prime retained oracle') as caught:
        engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,
            person_det=detector,strict_seed=rig.seed)
    assert caught.value.__cause__ is errors[0]
    assert calls==[4,4] and rig.initializers==[] and rig.grabs==[]
    assert [c.releases for c in rig.captures]==[1,1] and detector.want_any is False



@pytest.mark.parametrize('failure',[engine.PipelineCancelled,KeyboardInterrupt,SystemExit],
    ids=['pipeline-cancel','keyboard-interrupt','system-exit'])
def test_strict_person_prime_preserves_cancellation(rig,monkeypatch,failure):
    original=exact.read_indexed_capture;calls=[]
    def read(cap,index,**kwargs):
        calls.append(index)
        if len(calls)==2:raise failure('prime cancellation oracle')
        return original(cap,index,**kwargs)
    monkeypatch.setattr(exact,'read_indexed_capture',read)
    detector=SimpleNamespace(want_any=False,find=lambda frame:[])
    with pytest.raises(failure,match='prime cancellation oracle'):
        engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,
            person_det=detector,strict_seed=rig.seed)
    assert [c.releases for c in rig.captures]==[1,1]
    assert rig.initializers==[] and rig.grabs==[]



def test_strict_person_constructor_failure_never_falls_back(rig,monkeypatch):
    calls=[];errors=[]
    def capture(video):
        calls.append(video)
        if len(calls)==2:
            error=RuntimeError('person constructor retained oracle');errors.append(error);raise error
        return rig.Capture(video)
    monkeypatch.setattr(engine.cv2,'VideoCapture',capture)
    detector=SimpleNamespace(want_any=False,find=lambda frame:pytest.fail('detector after source failure'))
    with pytest.raises(exact.ExactError,match='person constructor retained oracle') as caught:
        engine.track_manual_region('fixture',[8,8,40,40],1/6,.16,.17,
            person_det=detector,strict_seed=rig.seed)
    assert caught.value.__cause__ is errors[0]
    assert calls==['fixture','fixture']
    assert [c.releases for c in rig.captures]==[1]
    assert rig.initializers==[] and rig.grabs==[] and detector.want_any is False
