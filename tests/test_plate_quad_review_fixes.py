"""Regression tests for box edits and source-guard publication fences."""
import json
import os

import cv2
import numpy as np
import pytest

import openscrub
from openscrub_internal.render_delivery import _RenderDelivery
from test_job_lifecycle import store
from test_exact_samples import exact, sample, precondition, post, raw
from test_plate_quad_render import saved_plate, render
from test_report_roundtrip import Quiet


def plate_pc(store):
    inspected = sample(store, 1.0)
    pc = precondition(inspected)
    pc['quad_context_eq'] = inspected['boxes'][0]['quad_context_eq']
    pc['quad_baseline'] = inspected['boxes'][0]['quad_baseline']
    return pc


def test_strict_box_change_retires_quad_and_lost_ack_is_idempotent(exact, tmp_path):
    path = saved_plate(exact)
    pc = plate_pc(exact)
    edits = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': [0, 0, 15, 15]}}
    result = post(exact, **edits)
    assert result.status_code == 200, result.get_data(as_text=True)
    row = raw(exact)['detections'][0]
    assert row['cbox'] == [0, 0, 15, 15]
    assert 'manual_plate_quad' not in row
    assert result.json['geometry_rows']['0']['manual_plate_quad'] is None
    assert result.json['geometry_rows']['0']['quad_baseline'] is None
    before = exact.path.read_bytes(), exact.path.stat().st_mtime_ns
    replay = post(exact, **edits)
    assert replay.status_code == 200, replay.get_data(as_text=True)
    assert replay.json['geometry_rows']['0']['manual_plate_quad'] is None
    assert (exact.path.read_bytes(), exact.path.stat().st_mtime_ns) == before
    frames = render(exact, path, tmp_path)
    assert frames[5][8, 8].mean() < 20
    assert frames[5][20, 30].mean() > 150
    assert frames[4][8, 8].mean() < 20


def test_legacy_strict_box_change_requires_quad_witness_before_any_mutation(exact):
    saved_plate(exact)
    inspected = sample(exact, 1.0)
    pc = precondition(inspected)
    before = exact.path.read_bytes()
    result = post(exact, geometry_preconditions={'0': pc},
                  box_overrides={'0': [0, 0, 15, 15]}, enabled={'1': True})
    assert result.status_code == 409
    assert exact.path.read_bytes() == before


def test_unconditional_box_change_retires_only_a_valid_quad(exact):
    saved_plate(exact)
    result = post(exact, box_overrides={'0': [0, 0, 15, 15]})
    assert result.status_code == 200
    assert 'manual_plate_quad' not in raw(exact)['detections'][0]


@pytest.mark.parametrize('edit', ['noop_box', 'time', 'choice', 'opaque', 'null', 'aliases_restore_box'])
def test_unrelated_or_opaque_values_survive(exact, edit):
    saved_plate(exact)
    doc = raw(exact)
    if edit == 'opaque': doc['detections'][0]['manual_plate_quad'] = {'version': 9, 'opaque': ['preserve']}
    if edit == 'null': doc['detections'][0]['manual_plate_quad'] = None
    exact.path.write_text(json.dumps(doc))
    before = raw(exact)['detections'][0]['manual_plate_quad']
    if edit == 'noop_box': edits = {'box_overrides': {'0': [5., 5., 55., 35.]}}
    elif edit == 'time': edits = {'time_overrides': {'0': [.1, 1.9]}}
    elif edit == 'choice': edits = {'enabled': {'0': False}}
    elif edit == 'aliases_restore_box': edits = {'box_overrides': {'0': [0, 0, 15, 15], '00': [5, 5, 55, 35]}}
    else: edits = {'box_overrides': {'0': [0, 0, 15, 15]}}
    assert post(exact, **edits).status_code == 200
    assert raw(exact)['detections'][0]['manual_plate_quad'] == before


def test_strict_box_and_new_quad_ack_full_value_and_replay(exact):
    saved_plate(exact)
    pc = plate_pc(exact)
    edits = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': [0, 0, 15, 15]},
             'manual_plate_quads': {'0': {'points': [[2, 2], [12, 2], [12, 12], [2, 12]]}}}
    result = post(exact, **edits)
    assert result.status_code == 200, result.get_data(as_text=True)
    saved = raw(exact)['detections'][0]['manual_plate_quad']
    assert saved['points'] == [[2/64, 2/48], [12/64, 2/48], [12/64, 12/48], [2/64, 12/48]]
    assert result.json['geometry_rows']['0']['manual_plate_quad'] == saved
    before = exact.path.read_bytes(), exact.path.stat().st_mtime_ns
    assert post(exact, **edits).status_code == 200
    assert (exact.path.read_bytes(), exact.path.stat().st_mtime_ns) == before


def test_stale_strict_box_cannot_retire_newer_quad_or_change_choices(exact):
    saved_plate(exact)
    pc = plate_pc(exact)
    doc = raw(exact)
    doc['detections'][0]['text'] = 'new context'
    exact.path.write_text(json.dumps(doc))
    before = exact.path.read_bytes()
    result = post(exact, geometry_preconditions={'0': pc},
                  box_overrides={'0': [0, 0, 15, 15]}, enabled={'1': True})
    assert result.status_code == 409
    assert exact.path.read_bytes() == before


@pytest.mark.parametrize('boundary', ['context', 'prepared', 'video_commit', 'report_commit'])
def test_source_guard_rechecked_through_final_publication(exact, tmp_path, monkeypatch, boundary):
    path = saved_plate(exact)
    output = tmp_path / 'out.mp4'
    output.write_bytes(b'previous-output')
    old_report = exact.path.read_bytes()
    replacement = tmp_path / 'replacement.avi'
    writer = cv2.VideoWriter(str(replacement), cv2.VideoWriter_fourcc(*'MJPG'), 5, (64, 48))
    assert writer.isOpened()
    for _ in range(10): writer.write(np.full((48, 64, 3), 210, dtype=np.uint8))
    writer.release()
    original_replace = os.replace
    if boundary == 'context':
        original = openscrub._quad_render_context
        def changed(*args):
            original_replace(replacement, path)
            return original(*args)
        monkeypatch.setattr(openscrub, '_quad_render_context', changed)
    elif boundary == 'prepared':
        original = _RenderDelivery.prepare_rollback
        def changed(self):
            original(self)
            original_replace(replacement, path)
        monkeypatch.setattr(_RenderDelivery, 'prepare_rollback', changed)
    else:
        swapped = []
        def changed(source, destination):
            original_replace(source, destination)
            target = output if boundary == 'video_commit' else exact.path
            if str(destination) == str(target) and not swapped:
                swapped.append(True)
                original_replace(replacement, path)
        monkeypatch.setattr(os, 'replace', changed)
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0'])
    with pytest.raises(RuntimeError, match='quad input changed'):
        openscrub.run_pipeline(args, Quiet())
    assert output.read_bytes() == b'previous-output'
    assert exact.path.read_bytes() == old_report


def test_independent_choice_survives_identical_box_retry(exact):
    saved_plate(exact)
    pc = plate_pc(exact)
    edits = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': [0, 0, 15, 15]}}
    assert post(exact, **edits).status_code == 200
    assert post(exact, enabled={'0': False, '1': True}).status_code == 200
    before = exact.path.read_bytes(), exact.path.stat().st_mtime_ns
    assert post(exact, **edits).status_code == 200
    assert (exact.path.read_bytes(), exact.path.stat().st_mtime_ns) == before
    assert raw(exact)['detections'][0]['enabled'] is False
    assert raw(exact)['detections'][1]['enabled'] is True


def test_retired_quad_retry_rejects_changed_nonquad_context(exact):
    saved_plate(exact)
    pc = plate_pc(exact)
    edits = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': [0, 0, 15, 15]}}
    assert post(exact, **edits).status_code == 200
    doc = raw(exact)
    doc['detections'][0]['future'] = {'revision': 2}
    exact.path.write_text(json.dumps(doc))
    before = exact.path.read_bytes()
    assert post(exact, **edits).status_code == 409
    assert exact.path.read_bytes() == before


@pytest.mark.parametrize('quad', [{'version': 9, 'opaque': [1, {'x': 2}]}, None])
def test_strict_box_ack_preserves_and_returns_opaque_raw_quad(exact, quad):
    saved_plate(exact)
    doc = raw(exact)
    doc['detections'][0]['manual_plate_quad'] = quad
    exact.path.write_text(json.dumps(doc))
    pc = plate_pc(exact)
    edits = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': [0, 0, 15, 15]}}
    result = post(exact, **edits)
    assert result.status_code == 200
    assert result.json['geometry_rows']['0']['manual_plate_quad'] == quad
    assert raw(exact)['detections'][0]['manual_plate_quad'] == quad
    before = exact.path.read_bytes(), exact.path.stat().st_mtime_ns
    assert post(exact, **edits).status_code == 200
    assert (exact.path.read_bytes(), exact.path.stat().st_mtime_ns) == before


def test_changed_quad_between_sample_and_box_save_conflicts_atomically(exact):
    saved_plate(exact)
    pc = plate_pc(exact)
    doc = raw(exact)
    doc['detections'][0]['manual_plate_quad']['points'][0][0] += .01
    exact.path.write_text(json.dumps(doc))
    before = exact.path.read_bytes()
    result = post(exact, geometry_preconditions={'0': pc}, box_overrides={'0': [0, 0, 15, 15]},
                  enabled={'1': True})
    assert result.status_code == 409
    assert exact.path.read_bytes() == before


def test_custom_render_publisher_cannot_bypass_guard(exact, tmp_path):
    path = saved_plate(exact)
    output = tmp_path / 'out.mp4'
    output.write_bytes(b'previous-output')
    old_report = exact.path.read_bytes()
    replacement = tmp_path / 'replacement.avi'
    replacement.write_bytes(path.read_bytes())
    class Publish(Quiet):
        def publish_render(self, delivery, summary):
            os.replace(replacement, path)
            delivery.commit()
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0'])
    with pytest.raises(RuntimeError, match='quad input changed'):
        openscrub.run_pipeline(args, Publish())
    assert output.read_bytes() == b'previous-output'
    assert exact.path.read_bytes() == old_report


def test_unguarded_legacy_render_keeps_existing_publication_behavior(exact, tmp_path, monkeypatch):
    path = saved_plate(exact)
    doc = raw(exact)
    del doc['detections'][0]['manual_plate_quad']
    exact.path.write_text(json.dumps(doc))
    replacement = tmp_path / 'replacement.avi'
    replacement.write_bytes(path.read_bytes())
    original = openscrub._quad_render_context
    def changed(*args):
        os.replace(replacement, path)
        return original(*args)
    monkeypatch.setattr(openscrub, '_quad_render_context', changed)
    frames = render(exact, path, tmp_path)
    assert frames[5][10, 10].mean() < 20


def test_noop_stale_box_retry_does_not_remove_identical_reauthored_quad(exact):
    saved_plate(exact)
    pc = plate_pc(exact)
    stale = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': [0, 0, 15, 15]}}
    replacement = dict(stale, manual_plate_quads={'0': {'points': [[20, 15], [40, 15], [40, 25], [20, 25]]}})
    assert post(exact, **replacement).status_code == 200
    retained = raw(exact)['detections'][0]['manual_plate_quad']
    before = exact.path.read_bytes(), exact.path.stat().st_mtime_ns
    replay = post(exact, **stale)
    assert replay.status_code == 200
    assert replay.json['geometry_rows']['0']['manual_plate_quad'] == retained
    assert (exact.path.read_bytes(), exact.path.stat().st_mtime_ns) == before


def test_legacy_box_override_can_repair_an_unrelated_invalid_old_box(exact):
    doc = raw(exact)
    doc['detections'][0]['cbox'] = None
    exact.path.write_text(json.dumps(doc))
    result = post(exact, box_overrides={'0': [1, 2, 8, 9]})
    assert result.status_code == 200
    assert raw(exact)['detections'][0]['cbox'] == [1, 2, 8, 9]


def test_context_alone_cannot_authorize_retirement_of_valid_quad(exact):
    saved_plate(exact)
    pc = plate_pc(exact)
    del pc['quad_baseline']
    before = exact.path.read_bytes()
    result = post(exact, geometry_preconditions={'0': pc}, box_overrides={'0': [0, 0, 15, 15]},
                  enabled={'1': True})
    assert result.status_code == 409
    assert exact.path.read_bytes() == before


def test_opaque_quad_removed_by_another_edit_cannot_be_misidentified_as_retry(exact):
    saved_plate(exact)
    doc = raw(exact)
    doc['detections'][0]['manual_plate_quad'] = {'version': 99, 'keep': 'opaque'}
    exact.path.write_text(json.dumps(doc))
    pc = plate_pc(exact)
    doc = raw(exact)
    del doc['detections'][0]['manual_plate_quad']
    doc['detections'][0]['cbox'] = [0, 0, 15, 15]
    exact.path.write_text(json.dumps(doc))
    before = exact.path.read_bytes()
    result = post(exact, geometry_preconditions={'0': pc}, box_overrides={'0': [0, 0, 15, 15]})
    assert result.status_code == 409
    assert exact.path.read_bytes() == before


def test_opaque_quad_baseline_survives_javascript_json_roundtrip(exact):
    import subprocess
    saved_plate(exact)
    pc = plate_pc(exact)
    new_corners = {'geometry_preconditions': {'0': pc},
                   'manual_plate_quads': {'0': {'points': [[0, 0], [64, 0], [64, 48], [0, 48]]}}}
    assert post(exact, **new_corners).status_code == 200
    sampled = sample(exact, 1.0)
    pc = precondition(sampled)
    pc['quad_context_eq'] = sampled['boxes'][0]['quad_context_eq']
    pc['quad_baseline'] = sampled['boxes'][0]['quad_baseline']
    assert isinstance(pc['quad_baseline'], str)
    assert json.loads(pc['quad_baseline'])['points'][0] == [0., 0.]
    roundtrip = subprocess.check_output(['node', '-e',
        'process.stdout.write(JSON.stringify(JSON.parse(process.argv[1])))', json.dumps(pc)], text=True)
    edits = {'geometry_preconditions': {'0': json.loads(roundtrip)},
             'box_overrides': {'0': [0, 0, 15, 15]}}
    assert post(exact, **edits).status_code == 200
    before = exact.path.read_bytes(), exact.path.stat().st_mtime_ns
    assert post(exact, **edits).status_code == 200
    assert (exact.path.read_bytes(), exact.path.stat().st_mtime_ns) == before


def test_guarded_same_source_output_is_refused_before_mutating_input(exact):
    path = saved_plate(exact)
    previous = path.read_bytes()
    old_stat = path.stat()
    old_report = exact.path.read_bytes()
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(path), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0'])
    with pytest.raises(RuntimeError, match='quad input'):
        openscrub.run_pipeline(args, Quiet())
    assert path.read_bytes() == previous
    assert (path.stat().st_dev, path.stat().st_ino, path.stat().st_mtime_ns) == (
        old_stat.st_dev, old_stat.st_ino, old_stat.st_mtime_ns)
    assert exact.path.read_bytes() == old_report


@pytest.mark.parametrize('token', ['{}', 'x' * 8193])
def test_invalid_quad_baseline_conflicts_before_any_mutation(exact, token):
    saved_plate(exact)
    pc = plate_pc(exact)
    pc['quad_baseline'] = token
    before = exact.path.read_bytes()
    result = post(exact, geometry_preconditions={'0': pc},
                  box_overrides={'0': [0, 0, 15, 15]}, enabled={'1': True})
    assert result.status_code == 409
    assert exact.path.read_bytes() == before


def test_source_guard_survives_quad_context_downgrade(exact, tmp_path):
    path = saved_plate(exact)
    output = tmp_path / 'out.mp4'
    output.write_bytes(b'previous-output')
    old_report = exact.path.read_bytes()
    replacement = tmp_path / 'replacement.avi'
    replacement.write_bytes(path.read_bytes())
    class Publish(Quiet):
        def publish_render(self, delivery, summary):
            os.replace(replacement, path)
            delivery.commit()
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0', '--coverage', 'box'])
    with pytest.raises(RuntimeError, match='quad input changed'):
        openscrub.run_pipeline(args, Publish())
    assert output.read_bytes() == b'previous-output'
    assert exact.path.read_bytes() == old_report


@pytest.mark.parametrize('alias_kind', ['same_path', 'hardlink', 'symlink'])
def test_guarded_report_source_alias_refused_before_any_stage(exact, tmp_path, alias_kind, monkeypatch):
    source = saved_plate(exact)
    prior_source = source.read_bytes()
    initial = source.stat()
    prior_report = exact.path.read_bytes()
    output = tmp_path / 'redacted.mp4'
    output.write_bytes(b'previous output')
    if alias_kind == 'same_path':
        report = source
    else:
        report = tmp_path / 'source-alias'
        if alias_kind == 'hardlink':
            os.link(source, report)
        else:
            report.symlink_to(source)
        initial = source.stat()  # Creating the hardlink changes ctime.
    entries = []
    real_enter = _RenderDelivery.__enter__
    def track_stage(delivery):
        entries.append(delivery.video_stage)
        return real_enter(delivery)
    monkeypatch.setattr(_RenderDelivery, '__enter__', track_stage)
    args = openscrub.build_parser().parse_args([str(source), '--from-report', str(exact.path),
        '--report', str(report), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0'])
    with pytest.raises(RuntimeError, match='quad input'):
        openscrub.run_pipeline(args, Quiet())
    after = source.stat()
    assert not entries
    assert (after.st_dev, after.st_ino, after.st_mtime_ns) == (
        initial.st_dev, initial.st_ino, initial.st_mtime_ns)
    assert source.read_bytes() == prior_source
    assert output.read_bytes() == b'previous output'
    assert exact.path.read_bytes() == prior_report
    assert not list(tmp_path.glob('.render-*'))
    assert not list(source.parent.glob('.render-*'))
    assert not list(tmp_path.glob('.report-*.tmp'))
    assert not list(source.parent.glob('.report-*.tmp'))


def test_no_quad_report_source_alias_keeps_legacy_publication(exact, tmp_path):
    source = saved_plate(exact)
    doc = raw(exact)
    del doc['detections'][0]['manual_plate_quad']
    exact.path.write_text(json.dumps(doc))
    output = tmp_path / 'redacted.mp4'
    args = openscrub.build_parser().parse_args([str(source), '--from-report', str(exact.path),
        '--report', str(source), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0'])
    openscrub.run_pipeline(args, Quiet())
    assert json.loads(source.read_text())['detections'][0]['category'] == 'plate'
    assert output.is_file() and output.stat().st_size > 0
