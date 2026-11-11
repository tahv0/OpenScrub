"""Named, offline training and local checkpoint lineage from confirmed crops."""
from datetime import datetime, timezone
import importlib
import json
import hashlib
from pathlib import Path
import threading

import cv2
import numpy as np
import pytest


def module():
    try:
        return importlib.import_module('findings_training')
    except ModuleNotFoundError:
        pytest.fail('Named confirmed-findings training is not implemented')


def test_default_name_is_utc_bounded_and_handles_multiple_sources():
    ft = module()
    now = datetime(2026, 11, 12, 9, 8, 7, tzinfo=timezone.utc)
    assert ft.default_name(['Road.mp4'], now) == 'Road.mp4 — 2026-11-12 09:08:07 UTC'
    assert ft.default_name(['A.mp4', 'B.mp4'], now).startswith('Confirmed findings — ')
    assert len(ft.default_name(['a' * 100], now)) <= 80
    assert '\n' not in ft.default_name(['bad\nname'], now)


def test_imported_inference_only_parent_requires_explicit_different_parent(tmp_path):
    from test_learning_candidates import candidate_job, CANDIDATE_ID
    import learning_candidates as lc
    import learned_models as lm
    job, _ = candidate_job(tmp_path)
    lc.evaluate(job, CANDIDATE_ID)
    saved = lm.save_candidate(tmp_path / 'models', job, CANDIDATE_ID, 'Imported checker')
    ft = module()
    info = ft.training_info(tmp_path / 'models', saved['id'])
    assert info['trainable'] is False
    assert 'checkpoint' in info['reason'].lower()
    with pytest.raises(ValueError, match='checkpoint'):
        ft.resolve_parent(tmp_path / 'models', saved['id'])


def examples(tmp_path, count=32):
    result = []
    for index in range(count):
        path = tmp_path / ('crop-%d.jpg' % index)
        image = np.random.default_rng(index).integers(160 if index % 2 else 0,
                    255 if index % 2 else 80, (40, 80, 3), dtype=np.uint8)
        assert cv2.imwrite(str(path), image)
        result.append({'id': 'e%d' % index, 'revision': 1, 'video_id': str(index % 2) * 64,
            'video': {'name': 'road-%d.mp4' % (index % 2)}, 'category': 'plate',
            'label': 'positive' if index % 2 else 'negative', 'explicit': True,
            'frame': index, 'box': [20, 30, 180, 110], 'points': None,
            'shape_confirmed': False,
            'crop': {'box': [0, 0, 200, 140], 'scale_x': 2.5, 'scale_y': 3.5,
                     'width': 80, 'height': 40},
            'image': {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
            'image_path': str(path)})
    return result


def trainer(dataset, versions, weights, job, settings):
    from test_learning_candidates import proposal_model_bytes, VERSION
    assert Path(weights).is_file()
    assert settings['verifier_training'] is True
    folder = versions / VERSION
    folder.mkdir(parents=True)
    (folder / 'model.onnx').write_bytes(proposal_model_bytes())
    (folder / 'weights.pt').write_bytes(b'local trained checkpoint')
    meta = {'schema': 1, 'status': 'candidate', 'version': VERSION,
        'created_utc': '2026-11-12T12:00:00+00:00',
        'artifacts': {n: hashlib.sha256((folder / n).read_bytes()).hexdigest()
                      for n in ('model.onnx', 'weights.pt')}}
    (folder / 'manifest.json').write_text(json.dumps(meta))
    return folder, meta


def make_job(path):
    path.mkdir()
    return {'dir': path, 'cancel': threading.Event(), 'learning': {}, 'log': []}


def test_selected_multivideo_crops_publish_named_checker_without_sources(tmp_path, monkeypatch):
    ft = module()
    import confirmed_findings
    import learned_models as lm
    import learning_candidates as lc
    selected = examples(tmp_path)
    captured = []
    def snapshot(root, ids=None, video_ids=None, category='plate'):
        captured.append((ids, video_ids, category))
        return selected
    monkeypatch.setattr(confirmed_findings, 'training_snapshot', snapshot)
    weights = tmp_path / 'base.pt'; weights.write_bytes(b'trusted local base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(weights))
    job = make_job(tmp_path / 'job')
    result = ft.run(job, tmp_path / 'findings', tmp_path / 'models',
            {'name': 'North roads', 'example_ids': ['chosen-a', 'chosen-b'],
             'video_ids': ['video-a', 'video-b'], 'license_accepted': True}, train=trainer)
    assert captured == [(['chosen-a', 'chosen-b'], ['video-a', 'video-b'], 'plate')]
    assert result['name'] == 'North roads'
    assert result['model']['schema'] == 2
    candidate = lc.load_candidate(job['dir'], result['candidate_id'])
    assert candidate['name'] == 'North roads'
    assert candidate['assessment'] is not None
    assert candidate['mask_assessment']['status'] == 'failed'
    assert 'region' in candidate['mask_assessment']['message'].lower()
    assert {p.name for p in (tmp_path / 'models' / result['model_id']).iterdir()} == {'model.onnx', 'manifest.json'}
    assert ft.training_info(tmp_path / 'models', result['model_id'])['trainable']
    lineage = tmp_path / 'learned_model_training' / result['model_id']
    frozen = json.loads((lineage / 'lineage.json').read_text())
    assert len(frozen['samples']) == len(selected)
    assert all(Path(lineage / s['image']).is_file() for s in frozen['samples'].values())
    before = lm.export_model(tmp_path / 'models', result['model_id'])
    selected[0]['label'] = 'positive'
    assert lm.export_model(tmp_path / 'models', result['model_id']) == before


def test_parent_retains_corpus_and_exposure_after_job_and_original_crop_removal(tmp_path, monkeypatch):
    ft = module()
    import confirmed_findings
    import shutil
    data = examples(tmp_path)
    monkeypatch.setattr(confirmed_findings, 'training_snapshot', lambda *a, **k: data)
    base = tmp_path / 'base.pt'; base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(base))
    first_job = make_job(tmp_path / 'first')
    first = ft.run(first_job, tmp_path / 'findings', tmp_path / 'models',
            {'name': 'First', 'license_accepted': True}, train=trainer)
    parent = ft.resolve_parent(tmp_path / 'models', first['model_id'])
    old_groups = parent['lineage']['training_groups']
    assert old_groups
    trained = next(s for s in parent['lineage']['samples'].values() if s['group'] in old_groups)
    duplicate = dict(trained['source'])
    index = 0
    while True:
        duplicate['id'] = 'new-duplicate-%d' % index
        duplicate_group = duplicate['video_id'] + ':' + duplicate['id']
        if int(hashlib.sha256(duplicate_group.encode()).hexdigest()[:8], 16) / 0xffffffff < .2:
            break
        index += 1
    duplicate['image_path'] = str(parent['folder'] / trained['image'])
    for item in data: Path(item['image_path']).unlink()
    shutil.rmtree(first_job['dir'])
    base.unlink()
    data = [duplicate]
    second = ft.run(make_job(tmp_path / 'second'), tmp_path / 'findings', tmp_path / 'models',
            {'name': 'Second', 'parent_model_id': first['model_id'], 'license_accepted': True}, train=trainer)
    inherited = ft.resolve_parent(tmp_path / 'models', second['model_id'])
    assert len(inherited['lineage']['samples']) == 33
    assert set(old_groups) <= set(inherited['lineage']['training_groups'])
    assert inherited['lineage']['parent_model_id'] == first['model_id']
    assert inherited['lineage']['split_history'][-1]['groups'][duplicate_group] == 'train'
    assert inherited['lineage']['split_history'][:1] == parent['lineage']['split_history']
    Path(inherited['weights']).write_bytes(b'tampered checkpoint')
    assert ft.training_info(tmp_path / 'models', second['model_id'])['trainable'] is False
    with pytest.raises(ValueError, match='checkpoint'):
        ft.resolve_parent(tmp_path / 'models', second['model_id'])


def test_saving_candidate_rejects_dataset_changed_after_independent_assessment(tmp_path):
    from test_learning_candidates import candidate_job, CANDIDATE_ID
    import learned_models as lm
    import learning_candidates as lc
    job, folder = candidate_job(tmp_path)
    lc.evaluate(job, CANDIDATE_ID)
    dataset = folder.parent.parent / 'dataset'
    first_image = next((dataset / 'images' / 'val').iterdir())
    first_image.write_bytes(first_image.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='dataset|assessment'):
        lm.save_candidate(tmp_path / 'models', job, CANDIDATE_ID, 'Stale assessment')


def test_name_is_retained_when_trainer_fails(tmp_path, monkeypatch):
    ft = module()
    import confirmed_findings
    monkeypatch.setattr(confirmed_findings, 'training_snapshot', lambda *a, **k: examples(tmp_path))
    base = tmp_path / 'base.pt'; base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(base))
    job = make_job(tmp_path / 'failed')
    def fail(*a): raise ValueError('GPU failed')
    with pytest.raises(ValueError, match='GPU failed'):
        ft.run(job, tmp_path / 'findings', tmp_path / 'models',
               {'name': 'Remember me', 'license_accepted': True}, train=fail)
    assert job['learning']['name'] == 'Remember me'
    assert json.loads(next(Path(job['dir']).glob('learning/passes/*/run.json')).read_text())['name'] == 'Remember me'


def test_training_info_lists_local_parent_without_reading_model_checkpoint_or_images(tmp_path, monkeypatch):
    ft = module()
    import confirmed_findings
    import learning_candidates as lc
    monkeypatch.setattr(confirmed_findings, 'training_snapshot', lambda *a, **k: examples(tmp_path))
    base = tmp_path / 'base.pt'; base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(base))
    result = ft.run(make_job(tmp_path / 'job'), tmp_path / 'findings', tmp_path / 'models',
            {'name': 'Local', 'license_accepted': True}, train=trainer)
    def forbidden(*args, **kwargs): pytest.fail('Listing hashed a training artifact')
    monkeypatch.setattr(lc, '_hash_file', forbidden)
    info = ft.training_info(tmp_path / 'models', result['model_id'])
    assert info['trainable'] is True and info['example_count'] == 32


def test_real_archive_corrections_replace_parent_labels_and_revocation_excludes_retraining(tmp_path, monkeypatch):
    import confirmed_findings as cf
    ft = module()
    source = examples(tmp_path)
    archive = tmp_path / 'archive'
    saved = []
    for index, item in enumerate(source):
        video = dict(sha256=item['video_id'], variant_sha256='a'*64,
            name=item['video']['name'], fps=25., width=200, height=140, total_frames=100)
        finding = dict(category='plate', label=item['label'], explicit=True,
            shape_confirmed=False, points=None, frame=index, box=item['box'],
            crop=item['crop']['box'])
        saved.append(cf.record(archive, video, finding, Path(item['image_path']).read_bytes()))
    base = tmp_path / 'base.pt'; base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(base))
    first = ft.run(make_job(tmp_path / 'first'), archive, tmp_path / 'models',
        {'name': 'Before correction', 'license_accepted': True}, train=trainer)
    changed = cf.update_finding(archive, saved[1]['id'], label='negative', expected_revision=1)
    cf.forget(archive, saved[3]['id'], expected_revision=1)
    # Only a different item was newly selected. Current corrections/revocations
    # still govern the inherited corpus; past train exposure remains recorded.
    second = ft.run(make_job(tmp_path / 'second'), archive, tmp_path / 'models',
        {'name': 'After correction', 'example_ids': [saved[0]['id']],
         'parent_model_id': first['model_id'], 'license_accepted': True}, train=trainer)
    parent = ft.resolve_parent(tmp_path / 'models', second['model_id'])
    corpus = parent['lineage']['samples'].values()
    revised = next(s for s in corpus if s['source']['id'] == changed['id'])
    assert revised['label'] == 'negative' and revised['source']['revision'] == 2
    assert not any(s['source']['id'] == saved[3]['id'] for s in corpus)
    assert len(parent['lineage']['samples']) == 31


def test_changed_frozen_corpus_aborts_named_publication(tmp_path, monkeypatch):
    ft = module()
    import confirmed_findings
    import learned_models as lm
    monkeypatch.setattr(confirmed_findings, 'training_snapshot', lambda *a, **k: examples(tmp_path))
    base = tmp_path / 'base.pt'; base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(base))
    def changed(dataset, *args):
        result = trainer(dataset, *args)
        image = next((dataset.parent / 'corpus' / 'images').iterdir())
        image.write_bytes(image.read_bytes() + b'modified')
        return result
    with pytest.raises(ValueError, match='corpus|example'):
        ft.run(make_job(tmp_path / 'job'), tmp_path / 'findings', tmp_path / 'models',
            {'name': 'Invalid corpus', 'license_accepted': True}, train=changed)
    assert lm.list_models(tmp_path / 'models') == []


def test_old_training_pixels_remain_exposed_after_example_revocation(tmp_path, monkeypatch):
    ft = module()
    import confirmed_findings as cf
    source = examples(tmp_path)
    monkeypatch.setattr(cf, 'training_snapshot', lambda *a, **k: source)
    base = tmp_path / 'base.pt'; base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(base))
    first = ft.run(make_job(tmp_path / 'first'), tmp_path / 'archive', tmp_path / 'models',
        {'name': 'Original', 'license_accepted': True}, train=trainer)
    parent = ft.resolve_parent(tmp_path / 'models', first['model_id'])
    old = next(s for s in parent['lineage']['samples'].values()
               if s['group'] in parent['lineage']['training_groups'])
    # The helper's response represents a known tombstone at the next run.
    monkeypatch.setattr(cf, 'training_revisions', lambda *a, **k:
        {'active': [], 'revoked_ids': [old['source']['id']], 'missing_ids': []})
    source = []
    second = ft.run(make_job(tmp_path / 'second'), tmp_path / 'archive', tmp_path / 'models',
        {'name': 'Removed', 'parent_model_id': first['model_id'], 'license_accepted': True}, train=trainer)
    after_removal = ft.resolve_parent(tmp_path / 'models', second['model_id'])
    assert not any(s['source']['id'] == old['source']['id']
                   for s in after_removal['lineage']['samples'].values())
    duplicate = dict(old['source'])
    index = 0
    while True:
        duplicate['id'] = 'fresh-duplicate-%d' % index
        group = duplicate['video_id'] + ':' + duplicate['id']
        if int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) / 0xffffffff < .2: break
        index += 1
    duplicate['image_path'] = str(parent['folder'] / old['image'])
    source = [duplicate]
    third = ft.run(make_job(tmp_path / 'third'), tmp_path / 'archive', tmp_path / 'models',
        {'name': 'Duplicate', 'parent_model_id': second['model_id'], 'license_accepted': True}, train=trainer)
    final = ft.resolve_parent(tmp_path / 'models', third['model_id'])
    assert final['lineage']['split_history'][-1]['groups'][group] == 'train'


@pytest.mark.parametrize('change', ['correction', 'revocation'])
def test_queued_selected_revision_change_fails_before_training(tmp_path, monkeypatch, change):
    ft = module()
    import confirmed_findings as cf
    source = examples(tmp_path)
    expected = {record['id']: record['revision'] for record in source}
    if change == 'correction':
        source[0]['revision'] = 2
        source[0]['label'] = 'positive'
    else:
        source.pop(0)
    monkeypatch.setattr(cf, 'training_snapshot', lambda *a, **k: source)
    base = tmp_path / 'base.pt'; base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(base))
    def forbidden(*args): pytest.fail('Stale queued selection entered training')
    with pytest.raises(ValueError, match='changed|revoked|revision'):
        ft.run(make_job(tmp_path / 'job'), tmp_path / 'archive', tmp_path / 'models',
            {'name': 'Queued model', 'example_ids': list(expected),
             'expected_revisions': expected, 'license_accepted': True}, train=forbidden)


def test_legacy_auto_publication_preserves_parent_and_removed_pixel_exposure(tmp_path):
    from test_learning_candidates import candidate_job
    import learning_session as ls
    ft=module()
    def publish_fixture(path, name, index, parent=None):
        jobdir,folder=candidate_job(path)
        stage=folder.parent.parent
        image=stage/'dataset'/'images'/'val'/('sample-%d.png'%index)
        feedback={'source_sha256':'a'*64,'samples':{'legacy-seed':{
            'image':str(image.relative_to(jobdir/'learning')),
            'image_sha256':ls.sha256(image),'group':'group-'+name,'frame':index,
            'label':'positive' if index<4 else 'negative',
            'quality':'human_quad' if index<4 else 'human_hard_negative',
            'points':[[.25,.3],[.75,.3],[.75,.7],[.25,.7]],'box':[4,8,28,24],
            'baseline_box':[.125,.25,.875,.75]}}}
        ls.atomic_json(stage/'dataset'/'split-groups.json',{'schema':1,'groups':{'group-'+name:'train'}})
        job={'dir':jobdir,'cancel':threading.Event(),'model_root':tmp_path/'models','learning':{}}
        return ft.publish_session_candidate(job,stage,folder,feedback,{'group-'+name},name,parent=parent)
    first=publish_fixture(tmp_path/'first','First',0)
    parent=ft.resolve_parent(tmp_path/'models',first['id'])
    second=publish_fixture(tmp_path/'second','Second',4,parent)
    child=ft.resolve_parent(tmp_path/'models',second['id'])
    assert child['lineage']['parent_model_id']==first['id']
    assert set(parent['lineage']['training_groups']) <= set(child['lineage']['training_groups'])
    assert all(item in child['lineage']['training_exposure'] for item in parent['lineage']['training_exposure'])
    assert child['lineage']['split_history'][:1]==parent['lineage']['split_history']
