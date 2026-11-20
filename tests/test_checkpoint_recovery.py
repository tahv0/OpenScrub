"""Restart outcomes after a real process dies during report replacement."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import openscrub_web as web
from openscrub_internal import checkpoint_media
from test_checkpoint_web_worker import checkpoint_web
from test_job_lifecycle import store
from test_report_transactions import join, run_worker


def localize_input(store):
    target = store.path.parent / 'input.mp4'
    shutil.copyfile(store.job['video'], target)
    (store.path.parent / 'input.avi').unlink(missing_ok=True)
    store.job['video'] = str(target)


def stop_after_seven(store):
    real_read = checkpoint_media.FrameStream.read
    def read(stream):
        frame = real_read(stream)
        if frame is not None and stream.next_frame == 7:
            web.FILES.initialize(store.job).active.checkpoint_stop.set()
        return frame
    return read


def make_paused(store, monkeypatch):
    real_read = checkpoint_media.FrameStream.read
    monkeypatch.setattr(checkpoint_media.FrameStream, 'read', stop_after_seven(store))
    try:
        web.enqueue(store.job, 'scan')
        join(run_worker())
    finally:
        monkeypatch.setattr(checkpoint_media.FrameStream, 'read', real_read)
    assert store.job['phase'] == 'paused', store.job['error']


def crash_during_replace(store, action, timing, stop):
    payload = {'root': str(store.root), 'jobs': str(store.jobs),
               'jid': store.job['id'], 'action': action, 'timing': timing, 'stop': stop}
    child = subprocess.run([sys.executable, '-B', __file__, json.dumps(payload)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
    assert child.returncode == 73, child.stderr.decode(errors='replace')


def crash_child(payload):
    web.JOBS_DIR = payload['jobs']
    web._data_root = lambda: payload['root']
    web._rehydrate_jobs()
    job = web.JOBS[payload['jid']]
    store = SimpleNamespace(job=job, path=Path(job['dir']) / 'report.json')
    real_replace = os.replace
    def replace(source, destination):
        if os.path.abspath(destination) == str(store.path):
            if payload['timing'] == 'before':
                os._exit(73)
            real_replace(source, destination)
            os._exit(73)
        return real_replace(source, destination)
    os.replace = replace
    if payload['stop']:
        checkpoint_media.FrameStream.read = stop_after_seven(store)
    web.enqueue(job, payload['action'])
    join(run_worker())
    raise RuntimeError('worker did not reach report replacement: %s / %s / %s' %
                       (job.get('phase'), job.get('error'), job['log'].snapshot()))


@pytest.mark.skipif(os.name != 'posix', reason='checkpoint publication requires POSIX')
@pytest.mark.parametrize('action,timing,stop,phase', [
    ('scan', 'before', False, 'error'),
    ('scan', 'after', True, 'paused'),
    ('scan', 'after', False, 'review'),
    ('resume', 'before', False, 'paused'),
    ('resume', 'after', False, 'review'),
])
def test_restart_resolves_recorded_report_outcome(checkpoint_web, monkeypatch,
                                                  action, timing, stop, phase):
    store, output = checkpoint_web
    localize_input(store)
    if action == 'resume':
        make_paused(store, monkeypatch)
    previous = store.path.read_bytes() if store.path.exists() else None
    crash_during_replace(store, action, timing, stop)
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    assert marker.is_file()
    marker_bytes = marker.read_bytes()
    proof = json.loads(marker_bytes)
    assert len(marker_bytes) < 1024
    assert set(proof) == {'version', 'kind', 'old', 'new'} and proof['version'] == 2
    assert str(store.path).encode() not in marker_bytes
    assert str(store.job['video']).encode() not in marker_bytes
    observed = store.path.read_bytes() if store.path.exists() else None
    if timing == 'before':
        assert observed == previous
    else:
        assert observed is not None and observed != previous
    web.JOBS.clear()
    web._rehydrate_jobs()
    recovered = web.JOBS[store.job['id']]
    assert recovered['phase'] == phase
    assert not web.FILES.initialize(recovered).recovery_required
    assert recovered['output'] is None
    assert not marker.exists()
    assert output.read_bytes() == b'older output must remain intact'
    if observed is not None:
        assert store.path.read_bytes() == observed


@pytest.mark.skipif(os.name != 'posix', reason='checkpoint publication requires POSIX')
@pytest.mark.parametrize('damage', ['report_mismatch', 'legacy', 'malformed',
                                    'marker_symlink', 'report_symlink', 'directory_symlink'])
def test_restart_fences_unprovable_report_outcomes(checkpoint_web, damage):
    store, output = checkpoint_web
    localize_input(store)
    crash_during_replace(store, 'scan', 'after', True)
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    if damage == 'report_mismatch':
        with store.path.open('ab') as stream:
            stream.write(b' ')
    elif damage == 'legacy':
        marker.write_text('{"version":1,"kind":"checkpoint-publication"}\n')
    elif damage == 'malformed':
        marker.write_text('{')
    elif damage == 'marker_symlink':
        target = store.path.parent / 'marker-copy'
        target.write_bytes(marker.read_bytes())
        marker.unlink()
        marker.symlink_to(target)
    elif damage == 'report_symlink':
        target = store.path.parent / 'report-copy'
        target.write_bytes(store.path.read_bytes())
        store.path.unlink()
        store.path.symlink_to(target)
    else:
        target = store.root / 'moved-job'
        store.path.parent.rename(target)
        store.path.parent.symlink_to(target, target_is_directory=True)
    web.JOBS.clear()
    web._rehydrate_jobs()
    recovered = web.JOBS[store.job['id']]
    assert recovered['phase'] == 'error' and recovered['output'] is None
    assert web.FILES.initialize(recovered).recovery_required
    assert os.path.lexists(marker)
    assert output.read_bytes() == b'older output must remain intact'


@pytest.mark.skipif(os.name != 'posix', reason='checkpoint publication requires POSIX')
def test_restart_rejects_structurally_invalid_new_report_even_with_matching_digest(checkpoint_web):
    store, _ = checkpoint_web
    localize_input(store)
    crash_during_replace(store, 'scan', 'after', True)
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    proof = json.loads(marker.read_bytes())
    doc = json.loads(store.path.read_bytes())
    doc['stop_review']['next_frame'] = doc['stop_review']['total_frames']
    bad = json.dumps(doc).encode()
    store.path.write_bytes(bad)
    proof['new']['sha256'] = hashlib.sha256(bad).hexdigest()
    proof['new']['size'] = len(bad)
    marker.write_text(json.dumps(proof))
    web.JOBS.clear()
    web._rehydrate_jobs()
    recovered = web.JOBS[store.job['id']]
    assert recovered['phase'] == 'error' and recovered['output'] is None
    assert web.FILES.initialize(recovered).recovery_required
    assert marker.exists()


@pytest.mark.skipif(os.name != 'posix', reason='checkpoint publication requires POSIX')
def test_recovery_syncs_report_and_directory_before_clearing_marker(checkpoint_web, monkeypatch):
    store, _ = checkpoint_web
    localize_input(store)
    crash_during_replace(store, 'scan', 'after', True)
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    real_sync, real_unlink = os.fsync, os.unlink
    observed = []
    report_inode, directory_inode = store.path.stat().st_ino, store.path.parent.stat().st_ino
    def sync(fd):
        inode = os.fstat(fd).st_ino
        if inode == report_inode:
            observed.append('report')
        elif inode == directory_inode:
            observed.append('directory')
        return real_sync(fd)
    def unlink(path, *args, **kwargs):
        if os.fspath(path) == str(marker):
            assert 'report' in observed and 'directory' in observed
            observed.append('unlink')
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'unlink', unlink)
    web.JOBS.clear()
    web._rehydrate_jobs()
    assert web.JOBS[store.job['id']]['phase'] == 'paused'
    assert observed[-2:] == ['unlink', 'directory']


@pytest.mark.parametrize('changed', ['stage', 'old', 'appeared',
                                     'stage_during_invalidation', 'old_during_invalidation'])
def test_publication_rejects_replacement_after_evidence_is_recorded(checkpoint_web, monkeypatch, changed):
    store, _ = checkpoint_web
    localize_input(store)
    old = changed.startswith('old')
    if old:
        make_paused(store, monkeypatch)
    before = store.path.read_bytes() if store.path.exists() else None
    actual_publish = web._publish_checkpoint_locked
    def replace_after_proof(job, owner, generation, operation, staged, path, doc, **kwargs):
        def change_file():
            target = Path(staged if changed.startswith('stage') else path)
            replacement = target.parent / '.external-replacement'
            replacement.write_bytes(target.read_bytes() if target.exists() else b'external report')
            os.replace(replacement, target)
        if changed.endswith('_during_invalidation'):
            invalidate = web.thumbs.invalidate_locked
            def change_after_invalidation(*args, **kw):
                invalidate(*args, **kw)
                change_file()
            with monkeypatch.context() as scoped:
                scoped.setattr(web.thumbs, 'invalidate_locked', change_after_invalidation)
                return actual_publish(job, owner, generation, operation, staged, path, doc, **kwargs)
        change_file()
        return actual_publish(job, owner, generation, operation, staged, path, doc, **kwargs)
    monkeypatch.setattr(web, '_publish_checkpoint_locked', replace_after_proof)
    web.enqueue(store.job, 'resume' if old else 'scan')
    join(run_worker())
    assert store.job['phase'] == 'error'
    if changed == 'appeared':
        assert store.path.read_bytes() == b'external report'
    elif before is None:
        assert not store.path.exists()
    else:
        assert store.path.read_bytes() == before
    assert not (store.path.parent / web._CHECKPOINT_RECOVERY_NAME).exists()


if __name__ == '__main__':
    crash_child(json.loads(sys.argv[1]))
