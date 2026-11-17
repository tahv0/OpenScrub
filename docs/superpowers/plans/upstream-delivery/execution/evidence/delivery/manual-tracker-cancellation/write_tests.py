from pathlib import Path
import json
out=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_manual_tracker_cancel.py')
evidence=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/tracker-cancel-baseline-evidence')
baseline=json.loads((evidence/'results.json').read_text())
head='''"""Actual ordinary tracker cancellation, output parity, and Flask ownership.

The two complete 15-sample arrays are retained from the reviewed P10C
baseline at 12919c96; the synthetic marked media uses the same recipe.
Person/Vit doubles below test handoff boundaries, not model inference.
"""
import inspect
import json
import queue
import shutil
import sys
import threading
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
import openscrub as engine
import openscrub_web as web

REAL_CAPTURE = cv2.VideoCapture
REAL_GRAB = engine._grab_frame
REAL_MATCH = cv2.matchTemplate
'''
head+='BASELINE = '+repr({k:baseline['cases'][k+'_complete']['output'] for k in ('steady','lost')})+'\n\n'
source=(evidence/'reproduce.py').read_text()
recipe=source[source.index('def make_video'):source.index('class Probe:')]
probe=source[source.index('class Probe:'):source.index('SOURCE_LINES =')]
probe=probe.replace("if self.count['matches'] == 1:","if self.count['matches'] == self.match_at:")
probe=probe.replace('self.factory_returns = []','self.factory_returns = []\n        self.match_at = 1\n        self.release_entered = threading.Event()\n        self.release_gate = None')
probe=probe.replace('self.real.release()\n        capture',"self.real.release()\n                if probe.release_gate is not None:\n                    probe.release_entered.set()\n                    assert probe.release_gate.wait(8), 'capture cleanup boundary not resumed'\n        capture")
a=probe.index('    def trace(');b=probe.index('    def hooks(',a)
probe=probe[:a]+'''    def trace(self, frame, event, arg):
        if frame.f_code.co_name == '_hold_rest':
            if event == 'line' and frame.f_lineno == HOLD_APPEND:
                self.record('hold_appends')
            elif event == 'line' and frame.f_lineno == HOLD_ADVANCE:
                # This statement is reached only after the real append completed.
                if ((self.trigger == 'hold_append1' and self.count['hold_appends'] == 1)
                        or (self.trigger == 'hold_append14' and self.count['hold_appends'] == 14)):
                    self.mark_cancel()
        return self.trace

'''+probe[b:]
head+=recipe+probe
head+='''# Find real append/advance locations without hard-coding production line numbers.
SOURCE_LINES, SOURCE_START = inspect.getsourcelines(engine.track_manual_region)
HOLD_APPEND = next(SOURCE_START + i for i, line in enumerate(SOURCE_LINES)
                   if 'out.append((t2, (cur[0]' in line)
HOLD_ADVANCE = HOLD_APPEND + 1


@pytest.fixture
def media(tmp_path, monkeypatch):
    models = tmp_path / 'models'
    models.mkdir()
    monkeypatch.setattr(engine, '_model_dir', lambda: str(models))
    def deny_fetch(*args, **kwargs):
        raise RuntimeError('manual cancellation tests prohibit model downloads')
    monkeypatch.setattr(engine, '_fetch_model', deny_fetch)
    steady, lost = tmp_path / 'steady.avi', tmp_path / 'lost.avi'
    make_video(steady)
    make_video(lost, lost=True)
    return steady, lost


@contextmanager
def observed(probe):
    old_trace = sys.gettrace()
    try:
        with ExitStack() as stack:
            probe.hooks(stack)
            sys.settrace(probe.trace)
            yield stack
    finally:
        sys.settrace(old_trace)
        try:
            # Observe the engine's cleanup before the defensive harness cleanup.
            assert all(c.releases == 1 and not c.real.isOpened() for c in probe.captures)
        finally:
            probe.cleanup()


def track(video, probe, **kwargs):
    return engine.track_manual_region(str(video), kwargs.pop('box', (32,32,64,64)),
                                     1.4, 0, 2.8, cb=probe, **kwargs)


@pytest.mark.parametrize('index,name', [(0, 'steady'), (1, 'lost')])
def test_complete_uncancelled_samples_and_none_callback_match_retained_baseline(media, index, name):
    probe = Probe()
    with observed(probe):
        output = track(media[index], probe)
    none_probe = Probe()
    with observed(none_probe):
        without_callback = track(media[index], None)
    assert json.loads(json.dumps(output)) == BASELINE[name]
    assert output == without_callback
    assert len(output) == 15
    assert probe.factory_returns == [True]  # actual offline missing-model fallback
    assert probe.count['matches'] == (42 if index == 0 else 6)
    assert probe.count['hold_appends'] == (0 if index == 0 else 14)


@pytest.mark.parametrize('match_at,grabs,reads', [(1,2,3), (22,9,12)])
def test_ncc_cancels_after_forward_or_backward_completed_match_without_later_grab(media, match_at, grabs, reads):
    probe = Probe(trigger='match_return')
    probe.match_at = match_at
    with observed(probe), pytest.raises(engine.PipelineCancelled) as error:
        track(media[0], probe)
    assert type(error.value) is engine.PipelineCancelled
    assert probe.after == dict(grabs=0, reads=0, matches=2, hold_appends=0)
    assert probe.count['grabs'] == grabs
    assert probe.count['reads'] == reads
    assert probe.count['matches'] == match_at + 2


@pytest.mark.parametrize('trigger,held,matches', [
    ('hold_log',0,3), ('hold_append1',1,3), ('hold_append14',14,6)])
def test_natural_loss_cancels_at_held_coverage_and_final_backward_return(media, trigger, held, matches):
    probe = Probe(trigger=trigger)
    with observed(probe), pytest.raises(engine.PipelineCancelled) as error:
        track(media[1], probe)
    assert type(error.value) is engine.PipelineCancelled
    assert probe.count['hold_appends'] == held
    assert probe.count['matches'] == matches
    assert probe.after == dict(grabs=0, reads=0, matches=0, hold_appends=0)


@pytest.mark.parametrize('kind', ['valid','missing','small'])
def test_precancelled_request_precedes_invalid_input_without_capture(media, kind):
    probe = Probe()
    probe.mark_cancel()
    video = media[0] if kind != 'missing' else media[0].with_name('missing.avi')
    box = (0,0,4,4) if kind == 'small' else (32,32,64,64)
    with observed(probe), pytest.raises(engine.PipelineCancelled) as error:
        track(video, probe, box=box)
    assert type(error.value) is engine.PipelineCancelled
    assert probe.captures == []
    assert probe.count['grabs'] == probe.count['matches'] == 0


@pytest.mark.parametrize('kind', ['missing','small','unreadable','clipped','vit_unreadable'])
def test_uncancelled_unusable_input_keeps_empty_result_and_releases_once(media, kind):
    probe = Probe()
    video = media[0] if kind != 'missing' else media[0].with_name('missing.avi')
    box = (0,0,4,4) if kind == 'small' else (200,200,232,232) if kind == 'clipped' else (32,32,64,64)
    with observed(probe) as stack:
        if kind in ('unreadable', 'vit_unreadable'):
            stack.enter_context(patch.object(engine, '_grab_frame', lambda *a: None))
        if kind == 'vit_unreadable':
            stack.enter_context(patch.object(engine, '_vittrack_factory', lambda log: object()))
        assert track(video, probe, box=box) == []
    assert len(probe.captures) == 1


@pytest.mark.parametrize('mode', ['raise_cancel','return_live','return_empty','return_held'])
def test_person_handoff_observes_cancellation_without_generic_fallback(media, mode):
    probe = Probe()
    def helper(*args, **kwargs):
        probe.mark_cancel()
        if mode == 'raise_cancel':
            raise engine.PipelineCancelled('person boundary')
        return [] if mode == 'return_empty' else [(1.4,(32,32,64,64), 0. if mode == 'return_held' else 1.)]
    with observed(probe) as stack, pytest.raises(engine.PipelineCancelled) as error:
        stack.enter_context(patch.object(engine, '_track_person_dense', helper))
        track(media[0], probe, person_det=object())
    assert type(error.value) is engine.PipelineCancelled
    assert probe.count['grabs'] == probe.count['matches'] == 0
    assert probe.factory_returns == []


def test_ordinary_person_failure_still_falls_back_to_complete_ncc(media):
    probe = Probe()
    def helper(*args, **kwargs):
        raise RuntimeError('ordinary detector failure')
    with observed(probe) as stack:
        stack.enter_context(patch.object(engine, '_track_person_dense', helper))
        output = track(media[0], probe, person_det=object())
    assert json.loads(json.dumps(output)) == BASELINE['steady']


@pytest.mark.parametrize('vit', [False, True])
def test_cancellation_during_model_factory_stops_before_seed(media, vit):
    probe = Probe()
    def factory(log):
        probe.mark_cancel()
        return object() if vit else None
    with observed(probe) as stack, pytest.raises(engine.PipelineCancelled):
        stack.enter_context(patch.object(engine, '_vittrack_factory', factory))
        track(media[0], probe)
    assert probe.count['grabs'] == 0


def test_unexpected_native_match_error_propagates_and_releases_once(media):
    probe = Probe()
    def fail(*args, **kwargs):
        raise ArithmeticError('controlled compute failure')
    with observed(probe) as stack, pytest.raises(ArithmeticError):
        stack.enter_context(patch.object(engine.cv2, 'matchTemplate', fail))
        track(media[0], probe)


def test_vit_final_return_observes_cancellation_from_last_update(media):
    probe = Probe()
    updates = []
    class Vit:
        def init(self, *args):
            pass
        def update(self, frame):
            updates.append(None)
            if len(updates) == 14:
                probe.mark_cancel()
            return True, (16,16,16,16)
        def getTrackingScore(self):
            return 1.
    with observed(probe) as stack, pytest.raises(engine.PipelineCancelled):
        stack.enter_context(patch.object(engine, '_vittrack_factory', lambda log: Vit))
        track(media[0], probe)
    assert len(updates) == 14


def request(method, url, **kwargs):
    with web.app.test_client() as client:
        response = getattr(client, method)(url, **kwargs)
        try:
            response.get_data()
            return response.status_code, response.get_json(silent=True)
        finally:
            response.close()


def test_actual_flask_tracker_cancel_delete_preserves_source_until_capture_cleanup(media, tmp_path):
    gate, release_gate = threading.Event(), threading.Event()
    threads = []
    with ExitStack() as stack:
        root = tmp_path / 'web'
        for name, value in dict(_data_root=lambda: str(root), JOBS_DIR=str(root/'jobs'),
                                JOBS={}, WORK_Q=queue.Queue(),
                                WORKER={'current': None, 'thread': None}, VAULT={'key':None},
                                TOKEN=None, MODEL_SELECT_PATH=str(root/'model_select.json')).items():
            stack.enter_context(patch.object(web, name, value))
        stack.enter_context(patch.object(web, 'FILES', type(web.FILES)(web.VAULT_LOCK)))
        job = web.new_job('', {}, 'synthetic.avi')
        source = Path(job['dir'])/'input.avi'
        shutil.copyfile(media[0], source)
        job.update(video=str(source), phase='review')
        report = Path(job['dir'])/'report.json'
        report.write_text(json.dumps(dict(provenance={'input':str(source)}, detections=[],
                                         render_state={'fps':10,'cum':[[0,0]]*31})))
        original_report = report.read_bytes()
        probe = Probe(gate=gate, owner=lambda: web.FILES.count)
        probe.release_gate = release_gate
        probe.hooks(stack)
        # Avoid unrelated person-model construction; track_manual_region is real.
        stack.enter_context(patch.object(engine, 'PersonDetector', lambda *a,**k: None))
        start = web._start_owned_thread
        def remember(*args):
            thread = start(*args)
            threads.append(thread)
            return thread
        stack.enter_context(patch.object(web, '_start_owned_thread', remember))
        url = '/api/jobs/' + job['id']
        try:
            assert request('post', url+'/track_object', json=dict(box=[32,32,64,64],t_ref=1.4,t0=0,t1=2.8))[0] == 200
            assert probe.entered.wait(8)
            probe.event = job['cancel']  # admitted operation's actual Event
            assert request('post', url+'/cancel')[0] == 200
            assert probe.event.is_set()
            probe.cancel_snapshot = dict(probe.count)
            status, value = request('get', url+'/track_status')
            assert status == 200
            assert value['done'] and value['added'] == 0 and value['error'] == 'cancelled by user'
            assert web.FILES.count == 1 and web.FILES.initialize(job).work == 1
            assert request('delete', url)[0] == 409 and source.exists()
            gate.set()
            assert probe.release_entered.wait(8)
            # Capture really closes while lease is still owned, before cleanup resumes.
            assert len(probe.captures) == 1
            assert probe.captures[0].releases == 1 and not probe.captures[0].real.isOpened()
            assert probe.captures[0].owner_at_release == [1]
            assert web.FILES.count == 1 and web.FILES.initialize(job).work == 1
            assert request('delete', url)[0] == 409 and source.exists()
            assert report.read_bytes() == original_report
        finally:
            gate.set()
            release_gate.set()
            try:
                for thread in threads:
                    thread.join(8)
                assert not any(t.is_alive() for t in threads), 'tracker worker leaked'
                assert all(c.releases == 1 and not c.real.isOpened() for c in probe.captures)
            finally:
                probe.cleanup()
        assert probe.count['matches'] == 3
        assert probe.count['grabs'] == 2 and probe.count['reads'] == 3
        assert probe.after == dict(grabs=0, reads=0, matches=2, hold_appends=0)
        assert report.read_bytes() == original_report
        status, value = request('get', url+'/track_status')
        assert status == 200 and value['error'] == 'cancelled by user' and value['added'] == 0
        assert web.FILES.count == 0 and web.FILES.initialize(job).work == 0
        assert web.FILES.initialize(job).tracker.released
        assert request('delete', url)[0] == 200
        assert not source.exists()
'''
out.write_text(head)
