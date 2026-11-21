"""Review thumbnails reuse one parsed report.json per file identity."""
import json
import os

import openscrub_web as web

from test_exact_samples import exact  # noqa: F401
from test_job_lifecycle import store, request  # noqa: F401


def _count_report_parses(monkeypatch):
    calls = []
    real = web.json.load

    def load(fp, *args, **kwargs):
        if os.path.basename(getattr(fp, 'name', '')) == 'report.json':
            calls.append(fp.name)
        return real(fp, *args, **kwargs)

    monkeypatch.setattr(web.json, 'load', load)
    return calls


def _version(exact):
    response = request('get', exact.url + '/detections')
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.json['thumbnail_version']


def test_thumbnails_parse_report_once_per_identity(exact, monkeypatch):
    web._forget_report_parses()
    calls = _count_report_parses(monkeypatch)
    version = _version(exact)
    for index in (0, 1, 0, 1):
        for kind in ('thumb', 'detframe'):
            response = request('get', '%s/%s/%d?v=%s' % (exact.url, kind, index, version))
            assert response.status_code == 200, response.get_data(as_text=True)
    assert len(calls) == 1


def test_replaced_report_is_parsed_again(exact, monkeypatch):
    web._forget_report_parses()
    calls = _count_report_parses(monkeypatch)
    _version(exact)
    doc = json.loads(exact.path.read_text())
    doc['detections'][1]['text'] = 'replaced'
    staged = exact.path.with_name('report.staged')
    staged.write_text(json.dumps(doc))
    os.replace(staged, exact.path)
    response = request('get', exact.url + '/detections')
    assert response.status_code == 200
    assert [row['text'] for row in response.json['detections']][1] == 'replaced'
    assert len(calls) == 2


def test_cached_report_is_not_mutated_by_review_reads(exact):
    web._forget_report_parses()
    version = _version(exact)
    for index in (0, 1):
        assert request('get', '%s/thumb/%d?v=%s' % (exact.url, index, version)).status_code == 200
    (stamp, doc), = web._REPORT_PARSES.values()
    assert doc == json.loads(exact.path.read_text())


def test_store_transition_forgets_parsed_reports(exact):
    _version(exact)
    assert web._REPORT_PARSES
    web._evict_thumbnails_for_store_transition()
    assert not web._REPORT_PARSES


def test_plate_policy_review_reads_leave_cached_report_untouched(exact):
    from test_optional_plate_review import optional_report
    optional_report(exact)
    web._forget_report_parses()
    version = _version(exact)
    for index in range(4):
        request('get', '%s/thumb/%d?v=%s' % (exact.url, index, version))
    assert _version(exact) == version
    (stamp, doc), = web._REPORT_PARSES.values()
    assert doc == json.loads(exact.path.read_text())


def test_deleting_a_job_forgets_its_parsed_report(exact):
    _version(exact)
    assert web._REPORT_PARSES
    assert request('delete', exact.url).status_code == 200
    assert not web._REPORT_PARSES


def test_idle_parsed_report_expires(exact):
    import time
    web._forget_report_parses()
    _version(exact)
    web._expire_idle_report_parses()
    assert web._REPORT_PARSES  # just used
    web._expire_idle_report_parses(time.monotonic() + web._REPORT_PARSE_IDLE_S)
    assert not web._REPORT_PARSES
