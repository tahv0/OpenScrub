"""Checkpoint intake requires its original options to survive restart."""
import io
import json
import os
from pathlib import Path
import stat
import threading
from types import SimpleNamespace

import pytest

import openscrub_web as web
from test_scan_options import intake
from test_job_lifecycle import finish, request, start_call, store


OPTIONS = {'checkpoint_review': True, 'categories': 'none', 'use_zones': False,
           'custom_option': {'unchanged': [1, None]}}


@pytest.mark.parametrize('kind', ['upload', 'server-path'])
@pytest.mark.parametrize('fault', ['mkdir', 'write', 'file_sync', 'rename', 'job_dir_sync', 'jobs_dir_sync'])
def test_checkpoint_options_io_failure_refuses_intake_and_queue(intake, monkeypatch, kind, fault):
    client, post, video, source, jobs_dir = intake
    body = json.dumps(OPTIONS)
    original_encode, original_sync, original_replace = json.JSONEncoder.iterencode, os.fsync, os.replace
    def encode(encoder, value, *args, **kwargs):
        if (fault == 'write' and encoder.indent == 1 and isinstance(value, dict)
                and value.get('checkpoint_review') is True):
            raise OSError('synthetic options write failure')
        return original_encode(encoder, value, *args, **kwargs)
    def sync(fd):
        info = os.fstat(fd)
        root = jobs_dir.stat()
        is_root = (info.st_dev, info.st_ino) == (root.st_dev, root.st_ino)
        if ((fault == 'file_sync' and stat.S_ISREG(info.st_mode))
                or (fault == 'job_dir_sync' and stat.S_ISDIR(info.st_mode) and not is_root)
                or (fault == 'jobs_dir_sync' and stat.S_ISDIR(info.st_mode) and is_root)):
            raise OSError('synthetic options durability failure')
        return original_sync(fd)
    def replace(source_path, target):
        if fault == 'rename' and Path(target).name == web.OPTIONS_FILE:
            raise OSError('synthetic options replacement failure')
        return original_replace(source_path, target)
    original_mkdir = os.mkdir
    def mkdir(path, *args, **kwargs):
        if fault == 'mkdir' and Path(path).parent == jobs_dir:
            raise OSError('synthetic job directory failure')
        return original_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(json.JSONEncoder, 'iterencode', encode)
    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'replace', replace)
    monkeypatch.setattr(os, 'mkdir', mkdir)
    response = post(kind, body)
    assert response.status_code == 507
    assert response.is_json and 'checkpoint' in response.get_json()['error'].lower()
    assert not web.JOBS and web.WORK_Q.empty() and web.WORK_Q.unfinished_tasks == 0
    assert list(jobs_dir.iterdir()) == []
    assert video.read_bytes() == source
    assert web.FILES.count == 0


def test_checkpoint_options_are_synced_before_queue_admission(intake, monkeypatch):
    client, post, video, source, jobs_dir = intake
    seen = []
    original_sync, original_replace, original_put = os.fsync, os.replace, web.WORK_Q.put
    def sync(fd):
        info = os.fstat(fd)
        root = jobs_dir.stat()
        is_root = (info.st_dev, info.st_ino) == (root.st_dev, root.st_ino)
        if stat.S_ISREG(info.st_mode):
            seen.append('file')
        elif stat.S_ISDIR(info.st_mode) and not is_root:
            seen.append('job_directory')
        elif stat.S_ISDIR(info.st_mode) and is_root:
            seen.append('jobs_directory')
        return original_sync(fd)
    def replace(source_path, target):
        if Path(target).name == web.OPTIONS_FILE:
            assert seen == ['file']
            seen.append('rename')
        return original_replace(source_path, target)
    def put(ticket):
        assert seen == ['file', 'rename', 'job_directory', 'jobs_directory']
        return original_put(ticket)
    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'replace', replace)
    monkeypatch.setattr(web.WORK_Q, 'put', put)
    response = post('upload', json.dumps(OPTIONS))
    assert response.status_code == 200
    jid, = response.get_json()['jobs']
    assert json.loads((jobs_dir / jid / web.OPTIONS_FILE).read_text()) == OPTIONS
    assert seen == ['file', 'rename', 'job_directory', 'jobs_directory']


def test_ordinary_intake_retains_best_effort_options_write(intake, monkeypatch):
    client, post, video, source, jobs_dir = intake
    original_dump = json.dump
    def fail(value, stream, *args, **kwargs):
        if isinstance(value, dict) and value.get('categories') == 'email':
            raise OSError('synthetic ordinary options failure')
        return original_dump(value, stream, *args, **kwargs)
    monkeypatch.setattr(json, 'dump', fail)
    response = post('upload', json.dumps({'categories': 'email'}))
    assert response.status_code == 200
    assert len(response.get_json()['jobs']) == 1 and web.WORK_Q.qsize() == 1


def test_later_checkpoint_options_failure_does_not_queue_earlier_upload(intake, monkeypatch):
    client, _, video, source, jobs_dir = intake
    body = json.dumps(OPTIONS)
    original_encode = json.JSONEncoder.iterencode
    count = [0]
    def fail_second(encoder, value, *args, **kwargs):
        if encoder.indent == 1 and isinstance(value, dict) and value.get('checkpoint_review') is True:
            count[0] += 1
            if count[0] == 2:
                raise OSError('synthetic second options failure')
        return original_encode(encoder, value, *args, **kwargs)
    monkeypatch.setattr(json.JSONEncoder, 'iterencode', fail_second)
    response = client.post('/api/jobs', data={
        'options': body,
        'video': [(io.BytesIO(source), 'one.avi'), (io.BytesIO(source), 'two.avi')],
    }, content_type='multipart/form-data')
    assert response.status_code == 507
    assert not web.JOBS and web.WORK_Q.empty() and web.WORK_Q.unfinished_tasks == 0
    assert list(jobs_dir.iterdir()) == []
    assert web.FILES.count == 0


def test_later_checkpoint_upload_failure_cleans_all_unadmitted_copies(intake, monkeypatch):
    from werkzeug.datastructures import FileStorage
    client, _, video, source, jobs_dir = intake
    original_save = FileStorage.save
    count = [0]
    def fail_second(upload, destination, *args, **kwargs):
        count[0] += 1
        if count[0] == 2:
            with open(destination, 'wb') as partial:
                partial.write(b'partial upload')
            raise OSError('synthetic second upload write failure')
        return original_save(upload, destination, *args, **kwargs)
    monkeypatch.setattr(FileStorage, 'save', fail_second)
    response = client.post('/api/jobs', data={
        'options': json.dumps(OPTIONS),
        'video': [(io.BytesIO(source), 'one.avi'), (io.BytesIO(source), 'two.avi')],
    }, content_type='multipart/form-data')
    assert response.status_code == 507
    assert not web.JOBS and web.WORK_Q.empty() and web.WORK_Q.unfinished_tasks == 0
    assert list(jobs_dir.iterdir()) == []
    assert web.FILES.count == 0 and video.read_bytes() == source


def test_checkpoint_multi_upload_admits_every_staged_source(intake):
    client, _, video, source, jobs_dir = intake
    response = client.post('/api/jobs', data={
        'options': json.dumps(OPTIONS),
        'video': [(io.BytesIO(source), 'one.avi'), (io.BytesIO(source), 'two.avi')],
    }, content_type='multipart/form-data')
    assert response.status_code == 200
    first, second = response.get_json()['jobs']
    assert first != second and set(web.JOBS) == {first, second}
    assert web.WORK_Q.qsize() == 2
    for jid in (first, second):
        job = web.JOBS[jid]
        assert Path(job['video']).read_bytes() == source
        assert json.loads((jobs_dir / jid / web.OPTIONS_FILE).read_text()) == OPTIONS
    assert video.read_bytes() == source


def test_failed_intake_cleanup_leaves_existing_reaper_marker(intake, monkeypatch):
    client, post, video, source, jobs_dir = intake
    original_reap = web._reap_job_dir
    def fail_sync(_fd):
        raise OSError('synthetic options durability failure')
    monkeypatch.setattr(os, 'fsync', fail_sync)
    monkeypatch.setattr(web, '_reap_job_dir', lambda *args, **kwargs: False)
    response = post('upload', json.dumps(OPTIONS))
    assert response.status_code == 507
    assert not web.JOBS and web.WORK_Q.empty()
    [orphan] = list(jobs_dir.iterdir())
    assert (orphan / web.DELETE_MARKER).is_file()
    monkeypatch.setattr(web, '_reap_job_dir', original_reap)
    web._rehydrate_jobs()
    assert list(jobs_dir.iterdir()) == [] and not web.JOBS


def test_checkpoint_id_collision_does_not_remove_existing_directory(intake, monkeypatch):
    client, post, video, source, jobs_dir = intake
    occupied = jobs_dir / ('a' * 12)
    occupied.mkdir()
    sentinel = occupied / 'existing'
    sentinel.write_bytes(b'keep existing data')
    monkeypatch.setattr(web.uuid, 'uuid4', lambda: SimpleNamespace(hex='a' * 32))
    response = post('upload', json.dumps(OPTIONS))
    assert response.status_code == 507
    assert sentinel.read_bytes() == b'keep existing data'
    assert not web.JOBS and web.WORK_Q.empty()


def test_checkpoint_upload_stages_before_registration_and_keeps_vault_fenced(store, monkeypatch):
    from werkzeug.datastructures import FileStorage
    entered, release = threading.Event(), threading.Event()
    original_save = FileStorage.save
    def save(upload, destination, *args, **kwargs):
        entered.set()
        assert release.wait(8)
        return original_save(upload, destination, *args, **kwargs)
    monkeypatch.setattr(FileStorage, 'save', save)
    call = start_call('post', '/api/jobs', data={
        'options': json.dumps(OPTIONS), 'video': (io.BytesIO(b'synthetic upload'), 'source.mp4')})
    try:
        assert entered.wait(5)
        [staged] = [path for path in store.jobs.iterdir() if path != Path(store.job['dir'])]
        assert json.loads((staged / web.OPTIONS_FILE).read_text()) == OPTIONS
        assert list(web.JOBS) == [store.job['id']]
        assert request('post', '/api/vault/setup', json={'password': 'synthetic-password'}).status_code == 409
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 200
    jid, = response.get_json()['jobs']
    url = '/api/jobs/' + jid
    assert request('post', url + '/cancel').status_code == 200
    assert request('delete', url).status_code == 200


def test_checkpoint_options_sync_holds_vault_before_job_registration(store, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original_sync = os.fsync
    def sync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            entered.set()
            assert release.wait(8)
        return original_sync(fd)
    monkeypatch.setattr(os, 'fsync', sync)
    call = start_call('post', '/api/jobs', data={
        'options': json.dumps(OPTIONS), 'video': (io.BytesIO(b'synthetic upload'), 'source.mp4')})
    try:
        assert entered.wait(5)
        assert list(web.JOBS) == [store.job['id']]
        assert request('post', '/api/vault/setup', json={'password': 'synthetic-password'}).status_code == 409
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 200
    jid, = response.get_json()['jobs']
    assert request('post', '/api/jobs/' + jid + '/cancel').status_code == 200
    assert request('delete', '/api/jobs/' + jid).status_code == 200


def test_checkpoint_options_failure_releases_managed_source_and_vault(store, monkeypatch):
    store.enable()
    source = Path(store.job['video'])
    before = source.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('synthetic checkpoint options failure')
    monkeypatch.setattr(web, '_persist_checkpoint_options', fail)
    response = request('post', '/api/jobs', data={
        'options': json.dumps(OPTIONS), 'server_path': str(source)})
    assert response.status_code == 507
    assert list(web.JOBS) == [store.job['id']] and web.WORK_Q.empty()
    assert list(store.jobs.iterdir()) == [Path(store.job['dir'])]
    assert web.FILES.count == 0 and source.read_bytes() == before
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert source.read_bytes() == before
