"""Bounded read-only research: real pinned renderer, encoder and web worker.

Only observation proxies and labelled task-local I/O failure/gates are injected.
No renderer, publisher, geometry function or worker is replaced by a model.
"""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
from unittest.mock import patch

ROOT = Path('/tmp/openscrub-render-failure-20261117')
PIN = ROOT / 'pinned'
sys.path.insert(0, str(PIN))
import openscrub as engine
import openscrub_web as web
from openscrub_internal import reports

RESULT = {'pin': '12919c96c6f7558136b50d7b4d85e5e6b62f1971',
          'modules': {}, 'cases': []}
for module in (engine, web, reports):
    p = Path(module.__file__)
    assert p.is_relative_to(PIN)
    RESULT['modules'][str(p.relative_to(PIN))] = hashlib.sha256(p.read_bytes()).hexdigest()

def file_state(path):
    p = Path(path)
    return {'exists': p.exists(), 'size': p.stat().st_size if p.exists() else None,
            'sha256': hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None}

class Observation:
    def __init__(self):
        self.children, self.caps, self.temps = [], [], []
        self.real_popen = subprocess.Popen
        self.real_cap = engine.cv2.VideoCapture
        self.real_temp = engine.tempfile.TemporaryFile
    def popen(self, *args, **kwargs):
        p = self.real_popen(*args, **kwargs)
        self.children.append(p)
        return p
    def cap(self, *args, **kwargs):
        c = self.real_cap(*args, **kwargs)
        self.caps.append(c)
        return c
    def temp(self, *args, **kwargs):
        t = self.real_temp(*args, **kwargs)
        self.temps.append(t)
        return t
    def snapshot(self):
        # Do not poll(): waitpid polling itself could reap a previously
        # unreaped child. returncode records production wait; /proc is separate.
        children = []
        for p in self.children:
            status = Path('/proc') / str(p.pid) / 'status'
            state = None
            if status.exists():
                state = next(x for x in status.read_text().splitlines() if x.startswith('State:'))
            children.append({'pid': p.pid, 'args': p.args, 'returncode': p.returncode,
                             'proc_state': state,
                             'stdin_closed': p.stdin.closed if p.stdin else None,
                             'stdout_closed': p.stdout.closed if p.stdout else None})
        return {'children': children,
                'captures_open': [c.isOpened() for c in self.caps],
                'stderr_temps_closed': [t.closed for t in self.temps]}
    @contextlib.contextmanager
    def installed(self):
        with patch.object(subprocess, 'Popen', self.popen), \
             patch.object(engine.cv2, 'VideoCapture', self.cap), \
             patch.object(engine.tempfile, 'TemporaryFile', self.temp):
            yield
    def cleanup(self):
        # Harness cleanup is unconditional and explicitly NOT product behavior.
        for c in self.caps:
            c.release()
        for p in self.children:
            if p.returncode is None:
                try:
                    p.terminate()
                except ProcessLookupError:
                    pass
            for stream in (p.stdin, p.stdout, p.stderr):
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except (BrokenPipeError, OSError):
                        pass
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=3)
        for t in self.temps:
            t.close()

def fixture(path, color):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i',
                    'color=c=%s:s=64x64:r=10' % color, '-frames:v', '8',
                    '-c:v', 'mpeg4', '-an', str(path)], check=True, timeout=15)

ROOT.mkdir(exist_ok=True)
fixture(ROOT / 'input.mp4', 'blue')
fixture(ROOT / 'previous.mp4', 'green')

def setup(name):
    case = ROOT / name
    case.mkdir(exist_ok=True)
    src, dst, rpt = case / 'input.mp4', case / 'output.mp4', case / 'report.json'
    shutil.copyfile(ROOT / 'input.mp4', src)
    shutil.copyfile(ROOT / 'previous.mp4', dst)
    doc = {'provenance': {'input': str(src), 'output': str(dst),
                          'output_sha256': file_state(dst)['sha256'],
                          'settings': {'future_setting': 'keep'}},
           'render_state': {'fps': 10, 'cum': [[0, 0]] * 8, 'bands': [[0, 0]] * 8},
           'detections': [dict(t_start=0, t_end=.7, cbox=[8, 8, 24, 24],
                               category='manual', text='synthetic', confidence=1,
                               aoff=[0, 0], last_seen=0, enabled=True,
                               dense=True, track=1)],
           'future_document': {'keep': True}}
    rpt.write_text(json.dumps(doc))
    return case, src, dst, rpt, doc

def direct(name, modify, hdr=False, cancelled=False):
    case, src, dst, rpt, doc = setup(name)
    args = engine.build_parser().parse_args([str(src), '--encoder', 'x264',
                                           '-o', str(dst), '--report', str(rpt)])
    args.mode, args.pad = 'box', 0
    if hdr:
        # Real HDR-render algorithm/10-bit ffmpeg branch; source is deliberately
        # SDR synthetic media, so this is resource evidence, NOT HDR fidelity.
        args.hdr_source, args.hdr_encoder, args.hdr_tags = str(src), 'libx265', {}
    dets, rs, _ = engine._decode_report(doc)
    state = dict(detections=dets, fps=10, cum=copy.deepcopy(rs['cum']),
                 bands=copy.deepcopy(rs['bands']), stats={}, source_report=doc)
    modify(args, state)
    cb = engine.Callbacks()
    cb.log = lambda message: None
    if cancelled:
        cb.cancelled = lambda: True
    obs = Observation()
    out = {'name': name, 'entry': 'actual run_render',
           'before': {'video': file_state(dst), 'report': file_state(rpt)},
           'job': None, 'operation': None}
    exc = None
    try:
        with obs.installed():
            try:
                engine.run_render(args, state, cb)
                out['result'] = 'success'
            except BaseException as e:
                exc = e  # Keep traceback/handles alive for the resource snapshot.
                out['exception'] = {'type': type(e).__name__, 'message': str(e)}
            out['production_terminal'] = obs.snapshot()
            out['after'] = {'video': file_state(dst), 'report': file_state(rpt)}
            out['partial_paths'] = [p.name for p in case.iterdir()
                                    if p.name.startswith('.report-') or 'noaudio' in p.name]
    finally:
        obs.cleanup()
        out['after_resource_cleanup_files'] = {'video': file_state(dst), 'report': file_state(rpt)}
        out['harness_removed_partial_paths'] = []
        if exc is not None and file_state(dst) != out['before']['video'] and dst.exists():
            # Only the case-owned changed failure output is a partial; keep
            # its exact bytes/hash above before removing it.
            dst.unlink()
            out['harness_removed_partial_paths'].append(str(dst))
        out['after_harness_cleanup'] = obs.snapshot()
        out['after_harness_cleanup_files'] = {'video': file_state(dst), 'report': file_state(rpt)}
        exc = None
    RESULT['cases'].append(out)

def early(args, state):
    args.coverage = 'concealed'
    state['detections'][0].cbox = (float('nan'), 8, 24, 24)

def translated(args, state):
    # Six actual frame writes precede nonfinite translation on frame 7.
    state['cum'][6] = [float('inf'), 0]

def source_nan(args, state):
    state['detections'][0].cbox = (float('nan'), 8, 24, 24)

direct('pre_encoder_concealed_source_nan', early)
direct('default_source_nan', source_nan)
direct('sdr_mid_render_nonfinite_translation', translated)
direct('hdr_mid_render_nonfinite_translation', translated, hdr=True)
direct('direct_checkpoint_cancel', lambda *a: None, cancelled=True)

def worker_case(name, cancel=False):
    case, src, dst, rpt, doc = setup(name)
    entered, release = threading.Event(), threading.Event()
    obs = Observation()
    original_replace = reports.os.replace
    original_hash = engine.sha256_file
    root = case / 'store'
    root.mkdir(exist_ok=True)
    # Task-owned isolated registry, queue, vault-state and lifetime domain.
    patches = [patch.object(web, '_data_root', lambda: str(root)),
               patch.object(web, 'JOBS_DIR', str(root / 'jobs')),
               patch.object(web, 'JOBS', {}), patch.object(web, 'WORK_Q', queue.Queue()),
               patch.object(web, 'WORKER', {'current': None, 'thread': None}),
               patch.object(web, 'VAULT', {'key': None}),
               patch.object(web, 'FILES', type(web.FILES)(web.VAULT_LOCK)),
               patch.object(web, 'TOKEN', None)]
    def replace(source, target):
        if Path(target) == rpt:
            raise OSError('research-injected final report replace failure')
        return original_replace(source, target)
    def sha(path, *a, **kw):
        value = original_hash(path, *a, **kw)
        if Path(path) == dst:
            entered.set()
            assert release.wait(8), 'research gate not released'
        return value
    out = {'name': name, 'entry': 'enqueue -> ordinary worker -> run_pipeline(from_report) -> run_render',
           'injection': 'gate after actual output hashing' if cancel else 'task report os.replace raises OSError',
           'before': {'video': file_state(dst), 'report': file_state(rpt)}}
    thread = None
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        # New job directory is moved to the task case; no product directory used.
        (root / 'jobs').mkdir(exist_ok=True)
        job = web.new_job(str(src), {'encoder': 'x264', 'mode': 'box', 'pad': 0}, 'synthetic.mp4')
        job.update(dir=str(case), video=str(src), phase='done', output=str(dst))
        files = web.FILES.initialize(job)
        def ownership():
            return {'phase': job['phase'], 'error': job['error'],
                    'output': job['output'], 'files_count': files.count,
                    'files_work': files.work, 'global_files_count': web.FILES.count,
                    'active': files.active is not None,
                    'operation_present': files.operation is not None,
                    'active_operation_current': bool(files.active and files.active.operation is files.operation),
                    'active_released': files.active.released if files.active else None,
                    'active_source': files.active.source if files.active else None,
                    'queue_count': len(files.queued), 'worker_current': web.WORKER['current']}
        try:
            stack.enter_context(obs.installed())
            stack.enter_context(patch.object(engine, 'sha256_file', sha) if cancel
                                else patch.object(reports.os, 'replace', replace))
            web.enqueue(job, 'render')
            out['queued'] = ownership()
            web.WORK_Q.put(None)
            thread = threading.Thread(target=web.worker)
            thread.start()
            if cancel:
                assert entered.wait(8), 'actual hashing boundary not reached'
                out['at_hash_gate'] = {'ownership': ownership(),
                                       'video': file_state(dst), 'report': file_state(rpt),
                                       'resources': obs.snapshot()}
                with web.app.test_client() as client:
                    response = client.post('/api/jobs/%s/cancel' % job['id'])
                    out['cancel_http_status'] = response.status_code
                    response.close()
                out['after_cancel_ack'] = ownership()
                release.set()
            thread.join(10)
            assert not thread.is_alive(), 'worker failed to terminate'
            out['job_terminal'] = ownership()
            out['production_terminal'] = obs.snapshot()
            out['after'] = {'video': file_state(dst), 'report': file_state(rpt)}
            out['logs'] = job['log']
            out['partial_paths'] = [p.name for p in case.iterdir()
                                    if p.name.startswith('.report-') or 'noaudio' in p.name]
        finally:
            release.set()
            if thread:
                thread.join(10)
            obs.cleanup()
            out['after_harness_cleanup'] = obs.snapshot()
            assert thread is None or not thread.is_alive()
    RESULT['cases'].append(out)

worker_case('worker_final_report_replace_failure')
worker_case('worker_cancel_after_video_before_report_ack', cancel=True)

RESULT['fixtures'] = {n: file_state(ROOT / n) for n in ('input.mp4', 'previous.mp4')}
print(json.dumps(RESULT, indent=2))
