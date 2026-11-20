"""Explicit optional settings enter through the actual scan job boundary."""

import json

import pytest

import openscrub_web as web
from test_scan_options import intake


@pytest.mark.parametrize('kind', ['upload', 'server-path'])
@pytest.mark.parametrize('policy', ['manual_review', 'blur_candidates'])
def test_optional_settings_reach_scan_but_report_is_canonical_on_rerender(intake, kind, policy):
    _, post, _, _, _ = intake
    options = {'uncertain_policy': policy, 'plate_threshold': .1, 'plate_auto_cutoff': .8}
    response = post(kind, json.dumps(options))
    assert response.status_code == 200
    job = web.JOBS[response.json['jobs'][0]]
    assert job['options'] == options
    scan_args = web.build_args(job)
    assert (scan_args.uncertain_policy, scan_args.plate_threshold,
            scan_args.plate_auto_cutoff) == (policy, .1, .8)
    render_args = web.build_args(job, for_render=True)
    assert render_args.uncertain_policy is None
    assert render_args.from_report.endswith('report.json')


@pytest.mark.parametrize('kind', ['upload', 'server-path'])
@pytest.mark.parametrize('override', [
    {'plate_auto_cutoff': None}, {'plate_threshold': .04}, {'plate_threshold': .9},
    {'plate_auto_cutoff': .96}, {'plate_threshold': float('nan')},
    {'plate_auto_cutoff': float('inf')}, {'plate_auto_cutoff': 10**1000},
    {'plate_threshold': True}, {'uncertain_policy': 'unknown'},
    {'uncertain_policy': ['manual_review']},
])
def test_invalid_optional_settings_are_rejected_before_queue_and_files(intake, kind, override):
    _, post, _, _, jobs_dir = intake
    options = {'uncertain_policy': 'manual_review', 'plate_threshold': .1,
               'plate_auto_cutoff': .8, **override}
    response = post(kind, json.dumps(options))
    assert response.status_code == 400
    assert response.is_json
    assert web.JOBS == {}
    assert web.WORK_Q.empty()
    assert list(jobs_dir.iterdir()) == []


def test_absent_and_off_options_keep_ordinary_settings(intake):
    _, post, _, _, _ = intake
    arguments = []
    for options in ({}, {'uncertain_policy': 'off'}):
        response = post('server-path', json.dumps(options))
        assert response.status_code == 200
        args = web.build_args(web.JOBS[response.json['jobs'][0]])
        settings = web.openscrub._settings_dict(args)
        assert 'uncertain_policy' not in settings
        assert 'plate_auto_cutoff' not in settings
        arguments.append((args.plate_threshold, args.uncertain_policy, args.plate_auto_cutoff))
    assert arguments == [(.35, None, None), (.35, None, None)]
