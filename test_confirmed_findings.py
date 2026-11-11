"""Durable human evidence: identity, transactions, and image-only reuse."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

import confirmed_findings as cf


def jpeg(width=180, height=90):
    a = np.zeros((height, width, 3), np.uint8)
    a[:, :, 1] = 110
    ok, encoded = cv2.imencode('.jpg', a)
    assert ok
    return encoded.tobytes()


def video(**changes):
    value = dict(sha256='a' * 64, variant_sha256='b' * 64, name='copied/video.mp4',
                 fps=25., width=1920, height=1080, total_frames=100)
    value.update(changes)
    return value


def finding(**changes):
    value = dict(category='plate', label='positive', frame=10,
                 box=[100, 100, 280, 190], points=None,
                 crop=[80, 80, 300, 210], job_id='job-one', explicit=True,
                 shape_confirmed=False)
    value.update(changes)
    return value


def save(root, **changes):
    return cf.record(root, video(), finding(**changes), jpeg())


def report(**identity):
    source = dict(input_sha256='b' * 64, fps=25., total_frames=100,
                  width=1920, height=1080)
    source.update(identity)
    return dict(provenance=dict(original_input_sha256='a' * 64,
                                input_sha256=source['input_sha256']),
                source_identity=source,
                render_state=dict(fps=source['fps'], cum=[[0., 0.]] * 100),
                detections=[dict(category='plate', frame_index=10,
                                 t_start=.4, t_end=.5, cbox=[100, 100, 280, 190],
                                 enabled=True, track=99)])


@pytest.mark.parametrize('change', [dict(explicit=False), dict(explicit=1),
    dict(label='plate'), dict(label='keep'), dict(label=''),
    dict(points=[[100,100],[280,100],[280,190],[100,190]])])
def test_only_explicit_classification_enters_library(tmp_path, change):
    with pytest.raises(ValueError):
        save(tmp_path, **change)
    assert cf.list_findings(tmp_path)['total'] == 0


def test_content_identity_survives_copies_jobs_and_caller_mutation(tmp_path):
    f, v = finding(), video()
    first = cf.record(tmp_path, v, f, jpeg())
    v['name'] = '/other/copied.mp4'
    f['job_id'] = 'different-job'
    second = cf.record(tmp_path, v, f, jpeg())
    assert first['id'] == second['id']
    assert second['revision'] == 1
    assert second['video_id'] == 'a' * 64
    assert second['video']['name'] == 'video.mp4'
    assert second['time'] == .4
    f['box'][0] = 999
    first['box'][0] = 888
    assert cf.get_finding(tmp_path, second['id'])['box'][0] == 100
    assert cf.list_findings(tmp_path)['total'] == 1
    assert '/other' not in json.dumps(second)


def test_compact_jpeg_has_source_transform_and_survives_restart(tmp_path):
    saved = cf.record(tmp_path, video(), finding(), jpeg(1500, 1000))
    path = cf.image_path(tmp_path, saved['id'])
    decoded = cv2.imread(str(path))
    assert max(decoded.shape[:2]) <= 640
    assert path.read_bytes()[:2] == b'\xff\xd8'
    assert saved['image']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert saved['crop']['box'] == [80, 80, 300, 210]
    assert saved['crop']['scale_x'] == pytest.approx(220 / decoded.shape[1])
    assert saved['crop']['scale_y'] == pytest.approx(130 / decoded.shape[0])
    assert cf.get_finding(Path(str(tmp_path)), saved['id']) == saved
    assert str(tmp_path) not in json.dumps(saved)


@pytest.mark.parametrize('v,f', [
    (video(sha256='../../bad'), finding()),
    (video(variant_sha256='x'*64), finding()),
    (video(fps=float('nan')), finding()),
    (video(total_frames=1), finding()),
    (video(), finding(frame=-1)), (video(), finding(frame=1.5)),
    (video(), finding(box=[100,100,80,190])),
    (video(), finding(box=[100,100,2000,190])),
    (video(), finding(crop=[110,110,200,180])),
    (video(), finding(points=[[70,70],[280,100],[280,190],[100,190]], shape_confirmed=True)),
    (video(), finding(points=[[100,100],[100,100],[280,190],[100,190]], shape_confirmed=True)),
])
def test_invalid_identity_or_geometry_cannot_be_persisted(tmp_path, v, f):
    with pytest.raises(ValueError):
        cf.record(tmp_path, v, f, jpeg())
    assert cf.list_findings(tmp_path)['total'] == 0


def test_bad_image_is_not_acknowledged_or_listed(tmp_path):
    with pytest.raises(ValueError):
        cf.record(tmp_path, video(), finding(), b'not a JPEG')
    assert cf.list_findings(tmp_path)['total'] == 0


def test_correction_revision_and_frozen_training_values(tmp_path):
    first = save(tmp_path)
    frozen = cf.training_snapshot(tmp_path, ids=[first['id']])
    quad = [[100,100],[280,100],[280,190],[100,190]]
    changed = cf.update_finding(tmp_path, first['id'], label='negative', points=quad,
                                expected_revision=1)
    assert changed['revision'] == 2
    assert changed['label'] == 'negative'
    assert changed['points'] == quad and changed['shape_confirmed'] is True
    assert frozen[0]['label'] == 'positive' and frozen[0]['revision'] == 1
    assert frozen[0]['points'] is None
    assert Path(frozen[0]['image_path']).read_bytes()
    with pytest.raises(cf.ConflictError):
        cf.update_finding(tmp_path, first['id'], label='positive', expected_revision=1)
    with pytest.raises(cf.ConflictError):
        save(tmp_path)
    assert cf.get_finding(tmp_path, first['id'])['label'] == 'negative'


def test_forgetting_revokes_training_and_blocks_stale_job_resurrection(tmp_path):
    first = save(tmp_path)
    frozen = cf.training_snapshot(tmp_path)
    cf.forget(tmp_path, first['id'], expected_revision=1)
    assert cf.list_findings(tmp_path)['items'] == []
    assert cf.training_snapshot(tmp_path) == []
    with pytest.raises(KeyError):
        cf.get_finding(tmp_path, first['id'])
    with pytest.raises(cf.ConflictError):
        save(tmp_path)
    assert Path(frozen[0]['image_path']).exists()
    with pytest.raises(cf.ConflictError):
        cf.forget(tmp_path, first['id'], expected_revision=1)


def test_snapshot_filters_and_verifies_immutable_asset(tmp_path):
    a = save(tmp_path)
    b = cf.record(tmp_path, video(sha256='c'*64), finding(label='negative'), jpeg())
    cf.record(tmp_path, video(), finding(category='face'), jpeg())
    assert [i['id'] for i in cf.training_snapshot(tmp_path, video_ids=['c'*64])] == [b['id']]
    assert cf.training_snapshot(tmp_path, ids=[]) == []
    assert len(cf.training_snapshot(tmp_path)) == 2
    assert cf.list_findings(tmp_path, category='plate', label='negative')['total'] == 1
    listed = cf.list_findings(tmp_path, offset=1, limit=1)
    assert len(listed['items']) == 1 and listed['total'] == 3
    assert len(listed['videos']) == 2
    cf.image_path(tmp_path, a['id']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='image'):
        cf.training_snapshot(tmp_path, ids=[a['id']])


def test_concurrent_writers_cannot_overwrite_each_others_decisions(tmp_path):
    first = save(tmp_path)
    def change(label):
        try:
            return cf.update_finding(tmp_path, first['id'], label=label,
                                     expected_revision=1)
        except cf.ConflictError:
            return None
    # Two real mutations (shape and label) against a single revision.
    def shape():
        try:
            return cf.update_finding(tmp_path, first['id'],
                points=[[101,101],[279,101],[279,189],[101,189]], expected_revision=1)
        except cf.ConflictError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda fn: fn(), [lambda: change('negative'), shape]))
    assert sum(v is not None for v in outcomes) == 1
    assert cf.get_finding(tmp_path, first['id'])['revision'] == 2


def test_replay_requires_exact_source_variant_timeline_and_unique_region(tmp_path):
    first = save(tmp_path, label='negative')
    original = report()
    restored, stats = cf.apply_to_report(tmp_path, original)
    row = restored['detections'][0]
    assert row['verified_label'] == 'not_plate'
    assert row['human_confirmation']['label'] == 'negative'
    assert row['confirmed_finding_id'] == first['id']
    assert stats['applied'] == 1
    assert 'verified_label' not in original['detections'][0]
    for doc in [report(fps=30.), report(total_frames=101),
                report(input_sha256='c'*64), report(width=1280)]:
        result, stats = cf.apply_to_report(tmp_path, doc)
        assert stats['applied'] == 0
        assert 'verified_label' not in result['detections'][0]
    wrong_source = report()
    wrong_source['provenance']['original_input_sha256'] = 'c'*64
    assert cf.apply_to_report(tmp_path, wrong_source)[1]['applied'] == 0
    ambiguous = report()
    ambiguous['detections'] *= 2
    assert cf.apply_to_report(tmp_path, ambiguous)[1]['applied'] == 0


def test_replay_preserves_later_human_choices_and_ignores_neighboring_boxes(tmp_path):
    save(tmp_path, label='negative')
    for changes in [dict(verified_label='plate'), dict(plate_verification_override=True),
                    dict(human_confirmation={'label':'positive'}),
                    dict(cbox=[101,100,281,190])]:
        doc = report()
        doc['detections'][0].update(changes)
        assert cf.apply_to_report(tmp_path, doc)[0] == doc


def test_replay_never_opens_video_and_replaces_older_archive_revision(tmp_path, monkeypatch):
    first = save(tmp_path)
    doc, _ = cf.apply_to_report(tmp_path, report())
    cf.update_finding(tmp_path, first['id'], label='negative', expected_revision=1)
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *a, **k: pytest.fail('video opened'))
    cf.list_findings(tmp_path)
    cf.training_snapshot(tmp_path)
    restored, stats = cf.apply_to_report(tmp_path, doc)
    assert restored['detections'][0]['verified_label'] == 'not_plate'
    assert stats['applied'] == 1


def test_failed_image_publication_has_no_save_receipt_or_partial_entry(tmp_path, monkeypatch):
    original_replace = cf.os.replace
    def fail_image(source, target):
        if str(target).endswith('.jpg'):
            raise OSError('simulated disk failure')
        return original_replace(source, target)
    monkeypatch.setattr(cf.os, 'replace', fail_image)
    with pytest.raises(OSError, match='disk failure'):
        save(tmp_path)
    assert cf.list_findings(tmp_path)['total'] == 0
    assert cf.training_snapshot(tmp_path) == []


def test_idempotent_receipt_requires_its_existing_image_to_be_intact(tmp_path):
    first = save(tmp_path)
    cf.image_path(tmp_path, first['id']).unlink()
    with pytest.raises(ValueError, match='image'):
        save(tmp_path)


def test_revocation_removes_only_prior_replay_human_evidence(tmp_path):
    first = save(tmp_path)
    doc, _ = cf.apply_to_report(tmp_path, report())
    cf.forget(tmp_path, first['id'], expected_revision=1)
    result, stats = cf.apply_to_report(tmp_path, doc)
    assert result['detections'][0].get('verified_label', '') == ''
    assert not result['detections'][0].get('human_confirmation')
    assert not result['detections'][0].get('confirmed_finding_id')
    assert result['detections'][0]['enabled'] is True
    assert stats['revoked'] == 1
    # A later direct human choice is independent and must survive forgetting.
    doc['detections'][0]['verified_label'] = 'not_plate'
    assert cf.apply_to_report(tmp_path, doc)[0] == doc


def test_replay_preserves_later_local_label_even_if_old_replay_marker_remains(tmp_path):
    first = save(tmp_path)
    doc, _ = cf.apply_to_report(tmp_path, report())
    doc['detections'][0]['verified_label'] = 'not_plate'
    cf.update_finding(tmp_path, first['id'],
                      points=[[101,101],[279,101],[279,189],[101,189]], expected_revision=1)
    assert cf.apply_to_report(tmp_path, doc)[0] == doc


def test_shape_edit_outside_original_box_but_inside_crop_is_supported(tmp_path):
    first = save(tmp_path)
    quad = [[90,90],[290,90],[290,200],[90,200]]
    result = cf.update_finding(tmp_path, first['id'], points=quad, expected_revision=1)
    assert result['box'] == [100,100,280,190]
    assert result['points'] == quad


def test_different_scanned_variant_keeps_source_association_without_replay(tmp_path):
    first = save(tmp_path)
    second = cf.record(tmp_path, video(variant_sha256='d'*64), finding(), jpeg())
    assert second['id'] != first['id']
    assert second['video_id'] == first['video_id']
    assert len(cf.list_findings(tmp_path)['videos']) == 1
    cf.forget(tmp_path, first['id'], expected_revision=1)
    assert cf.apply_to_report(tmp_path, report())[1]['applied'] == 0


def test_public_records_never_expose_job_or_video_absolute_paths(tmp_path):
    saved = cf.record(tmp_path, video(name=r'C:\private\movie.mp4'),
                      finding(job_id='/private/jobs/job-three'), jpeg())
    assert saved['video']['name'] == 'movie.mp4'
    assert saved['job_id'] == 'job-three'
    for public in [saved, cf.get_finding(tmp_path, saved['id']),
                   cf.list_findings(tmp_path)['items'][0]]:
        assert '/private' not in json.dumps(public)
        assert 'C:' not in json.dumps(public)


def test_durability_failure_does_not_commit_metadata(tmp_path, monkeypatch):
    original_sync = cf._sync_dir
    def fail_durability(path):
        if Path(path).name == 'images':
            raise OSError('image directory fsync failed')
        original_sync(path)
    monkeypatch.setattr(cf, '_sync_dir', fail_durability)
    with pytest.raises(OSError, match='fsync'):
        save(tmp_path)
    assert cf.list_findings(tmp_path)['total'] == 0


def test_training_revisions_distinguishes_current_revoked_and_absent_parent_ids(tmp_path):
    active = save(tmp_path)
    forgotten = save(tmp_path, frame=11)
    missing = 'e' * 64
    cf.update_finding(tmp_path, active['id'], label='negative', expected_revision=1)
    cf.forget(tmp_path, forgotten['id'], expected_revision=1)
    result = cf.training_revisions(tmp_path, [active['id'], forgotten['id'], missing])
    assert result['revoked_ids'] == [forgotten['id']]
    assert result['missing_ids'] == [missing]
    assert len(result['active']) == 1
    snapshot = result['active'][0]
    assert snapshot['id'] == active['id']
    assert snapshot['revision'] == 2 and snapshot['label'] == 'negative'
    assert snapshot['explicit'] is True
    assert Path(snapshot['image_path']).read_bytes()
    assert snapshot == cf.training_snapshot(tmp_path, ids=[active['id']])[0]
    # Returned current values remain detached when a later correction commits.
    cf.update_finding(tmp_path, active['id'], label='positive', expected_revision=2)
    assert snapshot['revision'] == 2 and snapshot['label'] == 'negative'
    assert cf.training_revisions(tmp_path, []) == dict(active=[], revoked_ids=[], missing_ids=[])


def test_training_revisions_verifies_active_images_but_not_revoked_assets(tmp_path):
    active = save(tmp_path)
    forgotten = save(tmp_path, frame=11)
    cf.forget(tmp_path, forgotten['id'], expected_revision=1)
    cf.image_path(tmp_path, active['id']).write_bytes(b'tampered')
    # Both entries intentionally share a content-addressed asset. Revoked rows
    # must still be reported as revoked even when their old JPEG is damaged.
    assert cf.training_revisions(tmp_path, [forgotten['id']])['revoked_ids'] == [forgotten['id']]
    with pytest.raises(ValueError, match='image'):
        cf.training_revisions(tmp_path, [active['id']])


def test_replay_restores_label_output_and_revocation_restores_original_policy(tmp_path):
    saved = save(tmp_path, label='negative')
    doc, stats = cf.apply_to_report(tmp_path, report())
    assert stats['applied'] == 1
    assert doc['detections'][0]['enabled'] is False
    cf.forget(tmp_path,saved['id'],expected_revision=1)
    restored,_ = cf.apply_to_report(tmp_path,doc)
    assert restored['detections'][0]['enabled'] is True
    assert not restored['detections'][0].get('output_choice_explicit')


def test_replay_positive_overrides_machine_filter_but_preserves_explicit_output(tmp_path):
    save(tmp_path)
    doc=report();doc['detections'][0]['enabled']=False
    doc['detections'][0]['plate_verification']={'applied':True,'decision':'suppress'}
    restored,_=cf.apply_to_report(tmp_path,doc)
    assert restored['detections'][0]['enabled'] is True
    doc['detections'][0]['output_choice_explicit']=True
    unchanged,_=cf.apply_to_report(tmp_path,doc)
    assert unchanged==doc


def test_windows_directory_durability_does_not_require_posix_descriptor(tmp_path,monkeypatch):
    class WindowsOS:
        name='nt'
        def open(self,*args,**kwargs):
            pytest.fail('Windows CRT cannot open a directory for POSIX fsync')
    monkeypatch.setattr(cf,'os',WindowsOS())
    cf._sync_dir(tmp_path)
