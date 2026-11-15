"""Ensure slow Review confirmation stage telemetry identifies a real bottleneck.

Stage accounting cannot make an acknowledged Is/Not save ambiguous. It is
metadata-only, with no source pixels or user labels in the metric payload.
"""
import json

import findings_web
import openscrub_web as web
from test_review_browser import review_server


def test_journal_confirmation_emits_bounded_stage_times(review_server, monkeypatch):
    url, report = review_server
    received = []
    monkeypatch.setattr(findings_web, '_CONFIRM_SLOW_TRACE_SECONDS', 0)
    monkeypatch.setattr(
        web.diagnostics, 'event',
        lambda name, *args, **fields: received.append((name, fields))
    )

    with web.app.test_client() as client:
        preview = client.get('/api/jobs/inline-fixture/finding-preview/0')
        assert preview.status_code == 200
        meta = json.loads(preview.headers['X-Finding-Geometry'])
        result = client.post('/api/jobs/inline-fixture/confirm/0',
                             json=dict(label='positive', preview_key=meta['key'],
                                       preview_token=meta['preview_token']))
        assert result.status_code == 200, result.get_data(as_text=True)
    traces = [data for name, data in received
              if name == 'review_confirmation_stages_slow']
    assert len(traces) == 1
    trace = traces[0]
    assert trace['mode'] == 'journal'
    assert trace['request_id']
    assert trace['total_ms'] >= 0
    assert 'report_mb' not in trace  # No disk or private source telemetry
    for key in ('load_preview_report_ms', 'source_identity_check_ms',
                'preview_ms', 'archive_ms', 'journal_commit_ms', 'member_count_ms'):
        assert key in trace and trace[key] >= 0
    assert json.loads(report.read_text())['detections'][0].get(
        'human_confirmation') is None, 'The journal keeps the report snapshot unchanged'


def test_full_report_confirmation_reports_snapshot_and_fsync_stage(review_server, monkeypatch):
    url, report = review_server
    received = []
    monkeypatch.setattr(findings_web, '_CONFIRM_SLOW_TRACE_SECONDS', 0)
    # Force the existing legitimate fallback without altering persistent
    # semantics: an unindexed/section-locked report requires a full snapshot.
    monkeypatch.setattr(findings_web, '_journal_doc', lambda job: None)
    monkeypatch.setattr(
        web.diagnostics, 'event',
        lambda name, *args, **fields: received.append((name, fields))
    )
    with web.app.test_client() as client:
        preview = client.get('/api/jobs/inline-fixture/finding-preview/1')
        assert preview.status_code == 200
        meta = json.loads(preview.headers['X-Finding-Geometry'])
        result = client.post('/api/jobs/inline-fixture/confirm/1',
                             json=dict(label='negative', preview_key=meta['key'],
                                       preview_token=meta['preview_token']))
        assert result.status_code == 200, result.get_data(as_text=True)
    traces = [data for name, data in received
              if name == 'review_confirmation_stages_slow']
    assert len(traces) == 1
    trace = traces[0]
    assert trace['mode'] == 'full_report'
    for key in ('publish_journal_ms', 'load_full_report_ms', 'preview_ms',
                'propagate_group_ms', 'section_guard_ms', 'archive_ms',
                'save_full_report_ms', 'member_count_ms'):
        assert key in trace and trace[key] >= 0
    assert json.loads(report.read_text())['detections'][1]['verified_label'] == 'not_plate'


def test_telemetry_failure_cannot_change_confirmed_save_receipt(review_server, monkeypatch):
    monkeypatch.setattr(findings_web, '_CONFIRM_SLOW_TRACE_SECONDS', 0)
    def broken_logger(*args, **kwargs):
        raise OSError('Synthetic telemetry backend failure')
    monkeypatch.setattr(web.diagnostics, 'event', broken_logger)
    with web.app.test_client() as client:
        preview = client.get('/api/jobs/inline-fixture/finding-preview/2')
        assert preview.status_code == 200
        meta = json.loads(preview.headers['X-Finding-Geometry'])
        result = client.post('/api/jobs/inline-fixture/confirm/2',
                             json=dict(label='positive', preview_key=meta['key'],
                                       preview_token=meta['preview_token']))
        assert result.status_code == 200, result.get_data(as_text=True)
        assert result.get_json()['finding']['label'] == 'positive'
