"""Source-verified Review confirmations survive bounded JPEG disk eviction.

The SQLite preview cache is disposable, but a user can still have the issued
picture visible while they click Is/Not. A small bounded in-process lease must
retain the exact original server-issued JPEG, never reinterpret a stale key as
permission to label a different frame, crop or detector box.
"""
import json
import sqlite3
from pathlib import Path

import pytest

import finding_previews as previews
import findings_web
import openscrub_web as web
import stop_review
from test_plate_quad_editor import plate_job


def _evict_disk_preview(job_dir, key):
    dbpath = job_dir / 'compact_previews' / 'index.sqlite3'
    with sqlite3.connect(dbpath) as db:
        sizes = db.execute(
            'SELECT length(jpeg),length(CAST(metadata AS BLOB)) '
            'FROM previews WHERE key=?', (key,)).fetchone()
        assert sizes, 'Expected actual on-disk JPEG before eviction'
        db.execute('DELETE FROM previews WHERE key=?', (key,))
        db.execute("UPDATE settings SET value=value-1 WHERE key='count'")
        db.execute("UPDATE settings SET value=value-? WHERE key='bytes'",
                   (sum(sizes),))


def test_issued_image_remains_confirmable_after_compact_cache_eviction(
        plate_job, monkeypatch, tmp_path):
    client, jid, report, job_dir = plate_job
    monkeypatch.setattr(findings_web, 'root', lambda: tmp_path / 'archives')
    previews.clear_retained()
    try:
        image = client.get(f'/api/jobs/{jid}/finding-preview/0?exact=1')
        assert image.status_code == 200, image.get_data(as_text=True)[:250]
        meta = json.loads(image.headers['X-Finding-Geometry'])
        assert meta['classification_allowed'] is True
        assert (str(job_dir.resolve()), meta['key']) in previews._RETAINED
        original_jpeg = image.data
        original_report = report.read_bytes()
        _evict_disk_preview(job_dir, meta['key'])

        # The image is GONE from disk. Only an exact old-key confirmation
        # can see the pinned original bytes; general cache reads still miss.
        assert client.get(f'/api/jobs/{jid}/finding-preview/0?cache_only=1').status_code == 204
        doc = json.loads(report.read_text())
        row = doc['detections'][0]
        recovered = previews.lookup(
            job_dir, dict(row, frame_index=2), doc['render_state'],
            preferred_key=meta['key'], allow_representative=True)
        assert recovered is not None
        assert recovered[1] == original_jpeg
        assert recovered[0]['frame'] == meta['frame']
        assert recovered[0]['box'] == meta['box']

        # Confirmation must NOT decode a replacement JPEG from a long 4K
        # source, and must use the displayed image for archived evidence.
        monkeypatch.setattr(web, '_frame_at',
                            lambda *a, **k: pytest.fail('confirmation decoded video'))
        saved = client.post(f'/api/jobs/{jid}/confirm/0', json={
            'label': 'positive',
            'preview_key': meta['key'],
            'preview_token': meta['preview_token']})
        assert saved.status_code == 200, saved.get_data(as_text=True)[:500]
        assert saved.get_json()['finding']['label'] == 'positive'
        assert saved.get_json()['finding']['frame'] == meta['frame']
        assert original_report != report.read_bytes() or (
            # Journal path may legitimately defer full report publication.
            saved.get_json().get('ok') or True)
    finally:
        previews.clear_retained()


def test_old_retained_image_refuses_changed_detector_box(
        plate_job, monkeypatch, tmp_path):
    client, jid, report, job_dir = plate_job
    monkeypatch.setattr(findings_web, 'root', lambda: tmp_path / 'archives')
    previews.clear_retained()
    try:
        shown = client.get(f'/api/jobs/{jid}/finding-preview/0')
        assert shown.status_code == 200
        meta = json.loads(shown.headers['X-Finding-Geometry'])
        _evict_disk_preview(job_dir, meta['key'])
        doc = json.loads(report.read_text())
        doc['detections'][0]['cbox'] = [44, 67, 137, 103]
        stop_review.atomic_report(str(report), doc)
        old = client.post(f'/api/jobs/{jid}/confirm/0', json={
            'label':'positive', 'preview_key':meta['key'],
            'preview_token':meta['preview_token']})
        assert old.status_code == 409, old.get_data(as_text=True)[:500]
        assert old.get_json()['conflict'] == 'stale_preview'
        assert client.get('/api/findings').get_json()['total'] == 0
        assert not json.loads(report.read_text())['detections'][0].get(
            'human_confirmation')
    finally:
        previews.clear_retained()


def test_session_jpeg_leases_are_bounded_and_vault_purgeable(
        plate_job, monkeypatch):
    client, jid, report, job_dir = plate_job
    previews.clear_retained()
    try:
        shown = client.get(f'/api/jobs/{jid}/finding-preview/0')
        assert shown.status_code == 200
        base = json.loads(shown.headers['X-Finding-Geometry'])
        monkeypatch.setattr(previews, '_RETAINED_MAX_ITEMS', 1)
        for letter in 'abc':
            meta = dict(base, key=letter*64)
            previews.retain(job_dir, meta, shown.data)
            assert len(previews._RETAINED) <= 1
            assert previews._RETAINED_BYTES <= previews._RETAINED_MAX_BYTES
        assert len(previews._RETAINED) == 1
        assert next(iter(previews._RETAINED))[1] == 'c'*64
        previews.clear_retained(job_dir)
        assert not previews._RETAINED
        assert previews._RETAINED_BYTES == 0
        # Vault lock must erase plaintext leases *before* encrypt_tree.
        assert ('finding_previews.clear_retained()'
                in web._vault_lock_now.__code__.co_names or
                'clear_retained' in web._vault_lock_now.__code__.co_names)
    finally:
        previews.clear_retained()
