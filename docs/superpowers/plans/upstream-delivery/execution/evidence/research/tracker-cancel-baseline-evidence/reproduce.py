#!/usr/bin/env python3
"""Bounded read-only P10C evidence. Run with env-opencv4.sh, from anywhere."""
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import tempfile
import threading
from contextlib import ExitStack
from unittest.mock import patch

PIN = '12919c96c6f7558136b50d7b4d85e5e6b62f1971'
EXPORT = Path('/tmp/openscrub-tracker-cancel-20261117/pinned')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPORT))
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
import cv2
import numpy as np
import openscrub as engine
import openscrub_web as web
from openscrub_internal import lifetimes, reports
for module in (engine, web, lifetimes, reports):
    assert Path(module.__file__).resolve().is_relative_to(EXPORT), module.__file__
cv2.setNumThreads(1)
REAL_CAPTURE = cv2.VideoCapture
REAL_GRAB = engine._grab_frame
REAL_MATCH = cv2.matchTemplate
downloads = []

def deny_fetch(*args, **kwargs):
    downloads.append(args[0])
    raise RuntimeError('P10C evidence: model downloads forbidden')

def make_video(path, lost=False):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (96,96))
    assert writer.isOpened()
    rng = np.random.default_rng(621)
    background = rng.integers(5, 40, (96,96,3), dtype=np.uint8)
    texture = rng.integers(30, 255, (32,32,3), dtype=np.uint8)
    try:
        for i in range(31):
            frame = background.copy()
            if not lost or i == 14:
                frame[32:64,32:64] = texture
            # Frame identity marker lives outside the target/search template.
            cv2.putText(frame, str(i), (2,12), cv2.FONT_HERSHEY_SIMPLEX, .35,
                        (255,255,255), 1)
            writer.write(frame)
    finally:
        writer.release()

class Probe:
    def __init__(self, event=None, trigger=None, gate=None, owner=None):
        self.event = event or threading.Event()
        self.trigger, self.gate, self.owner = trigger, gate, owner
        self.count = dict(grabs=0, reads=0, matches=0, hold_appends=0, callback_polls=0)
        self.after = dict(grabs=0, reads=0, matches=0, hold_appends=0)
        self.grab_times = []
        self.cancel_snapshot = None
        self.logs, self.captures = [], []
        self.entered = threading.Event()
        self.factory_returns = []

    def mark_cancel(self):
        self.event.set()
        if self.cancel_snapshot is None:
            self.cancel_snapshot = dict(self.count)

    def record(self, name):
        self.count[name] += 1
        if self.event.is_set() and name in self.after:
            self.after[name] += 1

    def log(self, message):
        self.logs.append(message)
        if self.trigger == 'hold_log' and 'LOST the object' in message:
            self.mark_cancel()

    def cancelled(self):
        self.record('callback_polls')
        return self.event.is_set()

    def grab(self, *args):
        self.record('grabs')
        self.grab_times.append(args[1])
        return REAL_GRAB(*args)

    def match(self, *args, **kwargs):
        self.record('matches')
        result = REAL_MATCH(*args, **kwargs)
        if self.count['matches'] == 1:
            if self.trigger == 'match_return':
                self.mark_cancel()
            if self.gate is not None:
                self.entered.set()
                assert self.gate.wait(8), 'bounded matching boundary not resumed'
        return result

    def capture(self, *args, **kwargs):
        probe = self
        class Capture:
            def __init__(self):
                self.real = REAL_CAPTURE(*args, **kwargs)
                self.releases = 0
                self.owner_at_release = []
            def __getattr__(self, name):
                return getattr(self.real, name)
            def read(self):
                probe.record('reads')
                return self.real.read()
            def release(self):
                self.releases += 1
                self.owner_at_release.append(probe.owner() if probe.owner else None)
                self.real.release()
        capture = Capture()
        self.captures.append(capture)
        return capture

    def trace(self, frame, event, arg):
        if event == 'line' and frame.f_code.co_name == '_hold_rest':
            # Count the actual unchanged append statement, not a reimplementation.
            if frame.f_lineno == HOLD_APPEND:
                if self.trigger == 'hold_append2' and self.count['hold_appends'] == 1:
                    self.mark_cancel()
                self.record('hold_appends')
        return self.trace

    def hooks(self, stack):
        stack.enter_context(patch.object(engine.cv2, 'VideoCapture', self.capture))
        stack.enter_context(patch.object(engine, '_grab_frame', self.grab))
        stack.enter_context(patch.object(engine.cv2, 'matchTemplate', self.match))
        original_factory = engine._vittrack_factory
        def factory(log):
            value = original_factory(log)
            self.factory_returns.append(value is None)
            return value
        stack.enter_context(patch.object(engine, '_vittrack_factory', factory))

    def cleanup(self):
        for capture in self.captures:
            capture.real.release()  # diagnostic safety net, outside measured count

    def result(self, output, exception=None):
        return dict(counts=self.count, after_cancel=self.after,
                    cancellation_snapshot=self.cancel_snapshot,
                    event_set=self.event.is_set(), output=output, exception=exception,
                    logs=self.logs, grab_times=self.grab_times,
                    natural_factory_returned_none=self.factory_returns,
                    captures=[dict(releases=c.releases, open=c.real.isOpened(),
                                   owner_at_release=c.owner_at_release)
                              for c in self.captures])

SOURCE_LINES = (EXPORT/'openscrub.py').read_text().splitlines()
HOLD_APPEND = next(i for i,line in enumerate(SOURCE_LINES, 1)
                   if 'out.append((t2, (cur[0]' in line)

def direct(video, trigger=None, box=(32,32,64,64), person=False, fake_vit=False):
    probe = Probe(trigger=trigger)
    if trigger == 'preset':
        probe.mark_cancel()
    output, exception = None, None
    try:
        with ExitStack() as stack:
            probe.hooks(stack)
            if person:
                def cancelled_person(*args, **kwargs):
                    probe.mark_cancel()
                    raise engine.PipelineCancelled('controlled dense-person cancel boundary')
                stack.enter_context(patch.object(engine, '_track_person_dense', cancelled_person))
            if fake_vit:
                class Vit:
                    def init(self, *args):
                        pass
                stack.enter_context(patch.object(engine, '_vittrack_factory', lambda log: Vit))
            old_trace = sys.gettrace()
            sys.settrace(probe.trace)
            try:
                output = engine.track_manual_region(str(video), box, 1.4, 0, 2.8,
                                                     cb=probe,
                                                     person_det=object() if person else None)
            except Exception as error:
                exception = type(error).__name__ + ': ' + str(error)
            finally:
                sys.settrace(old_trace)
        result = probe.result(output, exception)
        assert len(probe.captures) == 1
        assert all(c.releases == 1 and not c.real.isOpened() for c in probe.captures)
        return result
    finally:
        probe.cleanup()

def request(method, url, **kwargs):
    with web.app.test_client() as client:
        response = getattr(client, method)(url, **kwargs)
        try:
            response.get_data()
            return response.status_code, response.get_json(silent=True)
        finally:
            response.close()

def actual_web(root, video):
    gate = threading.Event()
    threads = []
    with ExitStack() as stack:
        for name, value in dict(_data_root=lambda: str(root), JOBS_DIR=str(root/'jobs'),
                                JOBS={}, WORK_Q=queue.Queue(),
                                WORKER={'current': None, 'thread': None}, VAULT={'key':None},
                                TOKEN=None, MODEL_SELECT_PATH=str(root/'model_select.json')).items():
            stack.enter_context(patch.object(web, name, value))
        stack.enter_context(patch.object(web, 'FILES', type(web.FILES)(web.VAULT_LOCK)))
        job = web.new_job('', {}, 'synthetic.avi')
        source = Path(job['dir'])/'input.avi'
        shutil.copyfile(video, source)
        job.update(video=str(source), phase='review')
        report = Path(job['dir'])/'report.json'
        report.write_text(json.dumps(dict(provenance={'input':str(source)}, detections=[],
                                         render_state={'fps':10,'cum':[[0,0]]*31})))
        original_report = report.read_bytes()
        probe = Probe(event=job['cancel'], gate=gate, owner=lambda: web.FILES.count)
        probe.hooks(stack)
        # Deliberately remove unrelated person model construction; ordinary tracker is real.
        stack.enter_context(patch.object(engine, 'PersonDetector', lambda *a,**k: None))
        start = web._start_owned_thread
        def remember(*args):
            thread = start(*args)
            threads.append(thread)
            return thread
        stack.enter_context(patch.object(web, '_start_owned_thread', remember))
        result = {}
        try:
            result['start'] = request('post', '/api/jobs/'+job['id']+'/track_object',
                                      json=dict(box=[32,32,64,64],t_ref=1.4,t0=0,t1=2.8))
            assert result['start'][0] == 200
            assert probe.entered.wait(8)
            # Admission installs a fresh real operation Event. Probe observes that same Event.
            probe.event = job['cancel']
            result['cancel'] = request('post', '/api/jobs/'+job['id']+'/cancel')
            assert probe.event.is_set()
            probe.cancel_snapshot = dict(probe.count)
            result['owners_while_cancelled'] = web.FILES.count
            result['status_while_cancelled'] = request('get', '/api/jobs/'+job['id']+'/track_status')
            result['delete_while_cancelled'] = request('delete', '/api/jobs/'+job['id'])[0]
        finally:
            gate.set()
            for thread in threads:
                thread.join(8)
                assert not thread.is_alive(), 'synthetic tracker worker leaked'
            assert all(c.releases == 1 and not c.real.isOpened() for c in probe.captures)
            probe.cleanup()
        result['probe'] = probe.result(None)
        result['report_unchanged'] = report.read_bytes() == original_report
        result['owners_after'] = web.FILES.count
        result['work_after'] = web.FILES.initialize(job).work
        result['tracker_lease_released'] = web.FILES.initialize(job).tracker.released
        result['worker_threads_alive'] = sum(t.is_alive() for t in threads)
        assert result['report_unchanged'] and result['owners_after'] == 0
        assert result['work_after'] == 0 and result['tracker_lease_released']
        result['delete_after'] = request('delete', '/api/jobs/'+job['id'])[0]
        assert result['delete_while_cancelled'] == 409 and result['delete_after'] == 200
        assert all(c.releases == 1 and c.owner_at_release[0] > 0 for c in probe.captures)
        return result

def main():
    results = dict(pin=PIN, imports={m.__name__:m.__file__ for m in (engine,web,lifetimes,reports)},
                   python=sys.version, opencv=cv2.__version__, hold_append_line=HOLD_APPEND,
                   hashes={str(p.relative_to(EXPORT)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [EXPORT/'openscrub.py', EXPORT/'openscrub_web.py',
                                     EXPORT/'openscrub_internal/lifetimes.py']})
    with tempfile.TemporaryDirectory(prefix='p10c-', dir=EXPORT.parent) as temporary:
        root = Path(temporary)
        models = root/'models'
        models.mkdir()
        with patch.object(engine, '_model_dir', lambda: str(models)), \
                patch.object(engine, '_fetch_model', deny_fetch):
            steady, lost = root/'steady.avi', root/'lost.avi'
            make_video(steady)
            make_video(lost, lost=True)
            results['media'] = {p.name:dict(bytes=p.stat().st_size,
                                          sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                                for p in (steady,lost)}
            cases = {}
            cases['steady_complete'] = direct(steady)
            cases['steady_cancel_after_match1'] = direct(steady, 'match_return')
            cases['steady_precancelled'] = direct(steady, 'preset')
            cases['lost_complete'] = direct(lost)
            cases['lost_cancel_at_hold_log'] = direct(lost, 'hold_log')
            cases['lost_cancel_inside_hold'] = direct(lost, 'hold_append2')
            cases['small_complete'] = direct(steady, box=(0,0,4,4))
            cases['small_precancelled'] = direct(steady, 'preset', box=(0,0,4,4))
            cases['missing_complete'] = direct(root/'missing.avi')
            cases['missing_precancelled'] = direct(root/'missing.avi', 'preset')
            cases['person_cancel_exception_controlled'] = direct(steady, person=True)
            cases['vit_precancelled_controlled_factory'] = direct(steady, 'preset', fake_vit=True)
            for name, baseline in [('steady_cancel_after_match1','steady_complete'),
                                   ('steady_precancelled','steady_complete'),
                                   ('lost_cancel_at_hold_log','lost_complete'),
                                   ('lost_cancel_inside_hold','lost_complete')]:
                cases[name]['equals_uncancelled'] = cases[name]['output'] == cases[baseline]['output']
                assert cases[name]['equals_uncancelled']
            results['cases'] = cases
            results['web'] = actual_web(root/'web', steady)
            results['download_attempts_blocked_before_network'] = len(downloads)
        results['synthetic_temporary_directory_removed_on_exit'] = str(root)
    assert not root.exists()
    results['synthetic_directory_exists_after_cleanup'] = root.exists()
    (OUT/'results.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps({name:dict(counts=case['counts'],after=case['after_cancel'],
                                samples=len(case['output'] or []),exception=case['exception'])
                      for name,case in cases.items()},indent=2))
    print(json.dumps({'web':{k:v for k,v in results['web'].items() if k!='probe'},
                      'web_counts':results['web']['probe']['counts'],
                      'web_after_cancel':results['web']['probe']['after_cancel']},indent=2))

if __name__ == '__main__':
    main()
