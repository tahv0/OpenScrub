#!/usr/bin/env python3
"""Actual exported render boundaries, weak observers, real FFmpeg children.

Source env-opencv4.sh; no install/network/model/product changes. All media are
synthetic and task-owned. Full pinned exports must already exist in SCRATCH.
"""
import ast
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace
import weakref

import cv2
import numpy as np

SCRATCH = Path('/tmp/openscrub-hdr-cleanup-20261117')
HERE = Path(__file__).resolve().parent
BASE = 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
DONOR = '08f432b6160d2fc22e51456020df929de6717e16'
TAGS = {'-color_primaries': 'bt2020', '-color_trc': 'smpte2084', '-colorspace': 'bt2020nc'}
POPEN = subprocess.Popen
TEMPFILE = tempfile.TemporaryFile


class ObservedPopen(POPEN):
    def wait(self, *args, **kwargs):
        rc = super().wait(*args, **kwargs)
        if hasattr(self, '_evidence_wait_events'):
            self._evidence_wait_events.append(rc)
        return rc


def fd_state(fd, target):
    try:
        current = os.readlink('/proc/self/fd/' + str(fd))
        return {'open': True, 'same_target': current == target, 'target': current}
    except FileNotFoundError:
        return {'open': False, 'same_target': False}


def process_state(pid):
    try:
        return Path('/proc/' + str(pid) + '/stat').read_text().split(') ')[1].split()[0]
    except FileNotFoundError:
        return 'absent'


class Tracker:
    """Weak observer by default. Optional strong Popen references are explicit."""
    def __init__(self, strong=False):
        self.children = []
        self.files = []
        self.strong = [] if strong else None

    def stream_record(self, stream, name):
        fd = stream.fileno()
        return {'name': name, 'fd': fd,
                'target': os.readlink('/proc/self/fd/' + str(fd)),
                'ref': weakref.ref(stream)}

    def popen(self, *args, **kwargs):
        p = ObservedPopen(*args, **kwargs)
        row = {'pid': p.pid, 'command': p.args, 'ref': weakref.ref(p), 'streams': [], 'wait_returns': []}
        p._evidence_wait_events = row['wait_returns']
        for name in ['stdin', 'stdout', 'stderr']:
            stream = getattr(p, name)
            if stream is not None:
                row['streams'].append(self.stream_record(stream, name))
        self.children.append(row)
        if self.strong is not None:
            self.strong.append(p)
        return p

    def temporary_file(self, *args, **kwargs):
        f = TEMPFILE(*args, **kwargs)
        self.files.append(self.stream_record(f, 'encoder_error_file'))
        return f

    def start(self):
        subprocess.Popen = self.popen
        tempfile.TemporaryFile = self.temporary_file

    def restore(self):
        subprocess.Popen = POPEN
        tempfile.TemporaryFile = TEMPFILE

    def stream_snapshot(self, row):
        f = row['ref']()
        return {k: v for k, v in row.items() if k != 'ref'} | {
            'object_alive': f is not None,
            'closed': None if f is None else f.closed,
            'fd_state': fd_state(row['fd'], row['target'])}

    def snapshot(self):
        rows = []
        for row in self.children:
            p = row['ref']()
            rows.append({'pid': row['pid'], 'command': row['command'],
                         'object_alive': p is not None,
                         'returncode': None if p is None else p.returncode,
                         'wait_returns': list(row['wait_returns']),
                         'proc_state': process_state(row['pid']),
                         'streams': [self.stream_snapshot(s) for s in row['streams']]})
        return {'children': rows, 'temporary_files': [self.stream_snapshot(f) for f in self.files]}

    def cleanup(self):
        actions = []
        for row in self.children:
            p = row['ref']()
            if p is not None:
                if p.poll() is None:
                    p.terminate()
                    actions.append({'pid': p.pid, 'action': 'harness terminate'})
                for name in ['stdin', 'stdout', 'stderr']:
                    stream = getattr(p, name)
                    if stream is not None and not stream.closed:
                        stream.close()
                        actions.append({'pid': p.pid, 'action': 'harness close ' + name})
                try:
                    p.wait(timeout=5)  # harness containment, not product/native deadline
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=5)
                    actions.append({'pid': p.pid, 'action': 'harness kill and reap'})
            else:
                # No live Python owner: only reap any exited orphaned child here.
                try:
                    pid, _ = os.waitpid(row['pid'], os.WNOHANG)
                    if pid:
                        actions.append({'pid': pid, 'action': 'harness reap'})
                except ChildProcessError:
                    pass
        for row in self.files:
            f = row['ref']()
            if f is not None and not f.closed:
                f.close()
                actions.append({'action': 'harness close encoder error file'})
        return actions


def command(args):
    p = subprocess.run(args, capture_output=True, timeout=30)
    commands.append({'argv': args, 'returncode': p.returncode,
                     'stderr': p.stderr.decode(errors='replace')[-3000:]})
    if p.returncode:
        raise RuntimeError(commands[-1])
    return p.stdout


def metadata(path):
    return json.loads(command(['ffprobe', '-v', 'error', '-count_frames',
        '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,pix_fmt,width,height,nb_frames,nb_read_frames,color_transfer,color_primaries,color_space',
        '-of', 'json', str(path)]))


def load(label):
    path = SCRATCH / label / 'openscrub.py'
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('hdr_cleanup_' + label, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    source = path.read_text()
    return mod, {'path': str(path), 'module_name': spec.name,
                 'render_hdr_code_filename': mod.render_hdr.__code__.co_filename,
                 'run_render_code_filename': mod.run_render.__code__.co_filename,
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                 'ranges': {n.name: [n.lineno, n.end_lineno] for n in ast.parse(source).body
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and
                 n.name in ['render_hdr', 'run_render', 'Callbacks', 'PipelineCancelled']}}


def exercise(mod, label, kind, strong=False):
    name = label + '-' + kind + ('-diagnostic-strong' if strong else '-weak-observer')
    dst = SCRATCH / (name + '.mp4')
    if kind == 'io-error':
        dst = SCRATCH / 'missing-parent' / (name + '.mp4')
        assert not dst.parent.exists()
    cb_calls = []
    tracker = Tracker(strong)
    captured_frames = []
    write_line = next(n.lineno for n in ast.walk(ast.parse(Path(mod.__file__).read_text()))
                      if isinstance(n, ast.Expr) and ast.unparse(n).startswith('enc.stdin.write('))
    previous_trace = sys.gettrace()
    def trace(frame, event, arg):
        if frame.f_code is mod.render_hdr.__code__:
            if event == 'line' and frame.f_lineno == write_line:
                captured_frames.append(frame.f_locals['buf'].tobytes())
            return trace
        return None
    class CB(mod.Callbacks):
        def log(self, message):
            cb_calls.append(['log', message])
        def progress(self, *args):
            cb_calls.append(['progress', *args])
        def cancelled(self):
            cb_calls.append(['cancelled', kind == 'cancel'])
            if kind == 'encoder-exit':
                enc = next(r for r in tracker.children if 'pipe:0' in r['command'])
                os.kill(enc['pid'], signal.SIGKILL)
                cb_calls.append(['injection', 'SIGKILL actual encoder before first frame write', enc['pid']])
                deadline = time.monotonic() + 5  # harness injection only
                while os.waitid(os.P_PID, enc['pid'], os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
                    if time.monotonic() > deadline:
                        raise RuntimeError('harness SIGKILL observation deadline')
                    time.sleep(0.001)
                cb_calls.append(['injection confirmed', 'encoder exited, not reaped by harness'])
            return kind == 'cancel'
    args = SimpleNamespace(video=str(SCRATCH / 'synthetic-hdr.mp4'), output=str(dst),
        preview=False, hdr_source=str(SCRATCH / 'synthetic-hdr.mp4'),
        hdr_encoder='libx265', hdr_tags=TAGS, pad=0, mode='box', report=None)
    state = {'detections': [], 'cum': [(0, 0)] * 3, 'bands': [(0, 0)] * 3,
             'fps': 3.0, 'stats': {'synthetic': True}}
    held_errors = []
    row = {'name': name, 'kind': kind, 'strong_diagnostic_popen_references': strong,
           'boundary': 'actual run_render -> actual render_hdr', 'dst': str(dst)}
    tracker.start()
    sys.settrace(trace)
    try:
        try:
            row['return'] = mod.run_render(args, state, CB())
            row['status'] = 'success'
        except Exception as exc:
            row['status'] = type(exc).__name__
            row['message'] = str(exc)
            row['traceback'] = traceback.format_exc()
            held_errors.append(exc)
        row['at_return_or_held_traceback'] = tracker.snapshot()
        held_errors.clear()
        gc.collect()
        row['after_releasing_exception_and_gc'] = tracker.snapshot()
        row['output_exists'] = dst.exists()
        row['output_bytes'] = dst.stat().st_size if dst.exists() else None
    finally:
        sys.settrace(previous_trace)
        row['encoder_write_attempt_frames'] = len(captured_frames)
        if kind == 'success':
            wire = b''.join(captured_frames)
            row['preencode_all_3_frames_equal_source_raw'] = wire == (SCRATCH / 'synthetic.yuv').read_bytes()
            row['preencode_sha256'] = hashlib.sha256(wire).hexdigest()
        row['harness_cleanup_actions'] = tracker.cleanup()
        row['terminal_after_harness_cleanup'] = tracker.snapshot()
        tracker.restore()
        row['callbacks'] = cb_calls
    return row


if __name__ == '__main__':
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    commands = []
    base, bsource = load('baseline')
    donor, dsource = load('donor')
    results = {'baseline': BASE, 'donor': DONOR,
        'source': {'baseline': bsource, 'donor': dsource},
        'python': sys.version, 'opencv': cv2.__version__, 'numpy': np.__version__,
        'imports': {'cv2': cv2.__file__, 'numpy': np.__file__, 'subprocess': subprocess.__file__},
        'tool_paths': {name: shutil.which(name) for name in ['ffmpeg', 'ffprobe']},
        'affinity': sorted(os.sched_getaffinity(0)), 'commands': commands, 'cases': []}
    tools_tracker = Tracker(strong=True)
    tools_tracker.start()
    try:
        results['ffmpeg_version'] = command(['ffmpeg', '-version']).decode().splitlines()[0]
        raw = np.concatenate([np.full(4096, 900, np.uint16),
            np.full(1024, 800, np.uint16), np.full(1024, 300, np.uint16)]).tobytes() * 3
        (SCRATCH / 'synthetic.yuv').write_bytes(raw)
        colors = [a for item in TAGS.items() for a in item]
        command(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', '-s', '64x64', '-r', '3',
            *colors, '-i', str(SCRATCH / 'synthetic.yuv'), '-c:v', 'libx265',
            '-x265-params', 'lossless=1:pools=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc',
            *colors, str(SCRATCH / 'synthetic-hdr.mp4')])
        results['source_metadata'] = metadata(SCRATCH / 'synthetic-hdr.mp4')
        decoded = command(['ffmpeg', '-v', 'error', '-i', str(SCRATCH / 'synthetic-hdr.mp4'),
            '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', 'pipe:1'])
        results['fixture_decoded_all_3_frames_exact'] = decoded == raw
    finally:
        results['fixture_tools_cleanup'] = tools_tracker.cleanup()
        results['fixture_tools_terminal'] = tools_tracker.snapshot()
        tools_tracker.restore()
    for label, mod in [('baseline', base), ('donor', donor)]:
        for kind in ['success', 'cancel', 'io-error', 'encoder-exit']:
            results['cases'].append(exercise(mod, label, kind))
    for kind in ['success', 'cancel']:
        results['cases'].append(exercise(base, 'baseline', kind, strong=True))
    output_tools = Tracker(strong=True)
    output_tools.start()
    try:
        for row in results['cases']:
            if row['status'] == 'success':
                row['metadata'] = metadata(Path(row['dst']))
                data = command(['ffmpeg', '-v', 'error', '-i', row['dst'],
                    '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', 'pipe:1'])
                planes = np.frombuffer(data, np.uint16).reshape(3, 6144)
                row['decoded_frame_count'] = len(planes)
                row['decoded_plane_ranges'] = [[int(p.min()), int(p.max())] for p in
                    [planes[:, :4096], planes[:, 4096:5120], planes[:, 5120:]]]
                row['decoded_plane_max_abs_vs_source'] = [int(np.abs(p.astype(int) - v).max())
                    for p, v in zip([planes[:, :4096], planes[:, 4096:5120], planes[:, 5120:]], [900, 800, 300])]
    finally:
        results['output_tools_cleanup'] = output_tools.cleanup()
        results['output_tools_terminal'] = output_tools.snapshot()
        output_tools.restore()
    (HERE / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({'results': str(HERE / 'results.json'),
                      'outcomes': [[c['name'], c['status']] for c in results['cases']]}))
