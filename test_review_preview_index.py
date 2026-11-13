"""Regression tests for large-report thumbnail indexing.

No dependency on a real video for the index unit tests; the HTTP test uses the
existing tiny plate fixture to check editor/preview compatibility.
"""
import json
from pathlib import Path

import pytest

import review_preview_index as index


def sample(tmp_path, count=350):
    path = tmp_path / 'report.json'
    document = dict(
        render_state={'fps': 30.0, 'cum': [[0, 0]] * 600},
        provenance={'input_sha256': 'stable-source'},
        preview_revision='sample',
        detections=[
            {'category': 'plate', 't_start': i / 30., 't_end': (i+1) / 30.,
             'cbox': [i, 2, i+30, 10], 'plate_quad': [],
             'track': i, 'frame_index': i}
            for i in range(count)
        ])
    path.write_text(json.dumps(document))
    return path, document


def test_index_loads_one_finding_without_loading_entire_report(tmp_path, monkeypatch):
    path, doc = sample(tmp_path, 450)
    assert index.load(path) is None
    assert index.prepare(path, doc)
    assert index.prepare(path, doc) is False
    lightweight = index.load(path)
    assert len(lightweight['detections']) == 450
    assert lightweight['detections'][250] == doc['detections'][250]
    assert lightweight['render_state'] == doc['render_state']
    assert lightweight['provenance'] == doc['provenance']
    assert not isinstance(lightweight['detections'], list)

    def no_full_read(*args, **kwargs):
        pytest.fail('Warm indexed reads must not deserialize report.json')
    monkeypatch.setattr(Path, 'read_text', no_full_read)
    for i in (0, 9, 250, 449):
        assert lightweight['detections'][i]['frame_index'] == i


def test_report_replacement_invalidates_index_and_inflight_read(tmp_path):
    path, doc = sample(tmp_path)
    assert index.prepare(path, doc)
    original = index.load(path)
    changed = json.loads(path.read_text())
    changed['detections'][17]['cbox'] = [80, 10, 90, 20]
    alternate = path.with_name('replacement.json')
    alternate.write_text(json.dumps(changed))
    alternate.replace(path)
    assert index.load(path) is None
    with pytest.raises(Exception) as error:
        _ = original['detections'][17]
    assert getattr(error.value, 'code', None) == 409
    assert index.prepare(path, changed)
    assert index.load(path)['detections'][17]['cbox'] == [80, 10, 90, 20]


def test_failed_index_build_preserves_previous_revision(tmp_path, monkeypatch):
    path, doc = sample(tmp_path, 4)
    assert index.prepare(path, doc)
    old = index._index_path(path).read_bytes()
    changed = json.loads(path.read_text())
    changed['detections'][0]['track'] = 900
    path.write_text(json.dumps(changed))

    def reject(*args, **kwargs):
        raise OSError('cannot publish index')
    monkeypatch.setattr(index.os, 'replace', reject)
    with pytest.raises(OSError):
        index.prepare(path, changed)
    assert index._index_path(path).read_bytes() == old
    assert index.load(path) is None
    assert not list(tmp_path.glob('.review-index-*.sqlite3'))


def test_preview_http_uses_lightweight_document_and_edit_uses_full(plate_job, monkeypatch):
    import openscrub_web as web

    client, jid, report, _ = plate_job
    monkeypatch.setattr(web, '_REVIEW_REPORT_MAX_FILE_BYTES', 1)
    web._REVIEW_REPORTS.clear()
    original = web._load_job_report
    reads = []
    def observed(*args, **kwargs):
        reads.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(web, '_load_job_report', observed)

    assert client.get(f'/api/jobs/{jid}/thumb/0?cache_only=1').status_code == 204
    assert len(reads) == 1
    for _ in range(5):
        assert client.get(f'/api/jobs/{jid}/thumb/0?cache_only=1').status_code == 204
    assert len(reads) == 1

    # A writer deliberately rereads a full document rather than trying to
    # deepcopy the read-only SQLite facade.
    response = client.get(f'/api/jobs/{jid}/plate_quad/0')
    assert response.status_code == 200
    meta = response.get_json()
    edited = client.post(f'/api/jobs/{jid}/plate_quad/0',
                         json={'points': meta['points'], 'preview_token': meta['preview_token']})
    assert edited.status_code == 200, edited.get_data(as_text=True)
    assert len(reads) >= 2
