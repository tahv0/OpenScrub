"""Retained training candidates remain distinct from accepted mask models."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest

import learned_models


PASS_ID = 'pass-123456789abc'
VERSION = 'v20261111T120000Z-abcdef12'
CANDIDATE_ID = PASS_ID + ':' + VERSION


def candidates():
    assert importlib.util.find_spec('learning_candidates'), 'Retained candidate support is missing'
    return importlib.import_module('learning_candidates')


def proposal_model_bytes(separable=True):
    """Actual ONNX: centered plate score is image brightness, or a constant."""
    from onnx import TensorProto, helper, numpy_helper
    head = np.zeros((1, 37, 1), np.float32)
    head[0, :4, 0] = [16, 16, 24, 12]
    head[0, 5, 0] = 1
    selector = np.zeros_like(head)
    selector[0, 4, 0] = 1
    proto = np.zeros((1, 32, 8, 8), np.float32)
    proto[0, 0, 2:6, 1:7] = 10
    nodes = [
        helper.make_node('Constant', [], ['head'], value=numpy_helper.from_array(head)),
        helper.make_node('Constant', [], ['selector'], value=numpy_helper.from_array(selector)),
        helper.make_node('Constant', [], ['output1'], value=numpy_helper.from_array(proto)),
    ]
    if separable:
        nodes.append(helper.make_node('ReduceMean', ['images'], ['score'], keepdims=0))
    else:
        nodes.append(helper.make_node('Constant', [], ['score'],
                                      value=numpy_helper.from_array(np.array(.9, np.float32))))
    nodes.extend([
        helper.make_node('Mul', ['selector', 'score'], ['scored']),
        helper.make_node('Add', ['head', 'scored'], ['output0']),
    ])
    graph = helper.make_graph(nodes, 'synthetic retained candidate',
        [helper.make_tensor_value_info('images', TensorProto.FLOAT, [1, 3, 32, 32])],
        [helper.make_tensor_value_info('output0', TensorProto.FLOAT, [1, 37, 1]),
         helper.make_tensor_value_info('output1', TensorProto.FLOAT, [1, 32, 8, 8])])
    return helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)],
                             ir_version=9).SerializeToString()


def candidate_job(tmp_path, *, separable=True):
    job = tmp_path / 'retained-job'
    stage = job / 'learning' / 'passes' / PASS_ID
    folder = stage / 'versions' / VERSION
    folder.mkdir(parents=True)
    payload = proposal_model_bytes(separable)
    weights = b'synthetic checkpoint; must never be deserialized'
    (folder / 'model.onnx').write_bytes(payload)
    (folder / 'weights.pt').write_bytes(weights)
    manifest = {
        'schema': 1, 'status': 'candidate', 'version': VERSION,
        'created_utc': '2026-11-11T12:00:00+00:00',
        'artifacts': {'model.onnx': hashlib.sha256(payload).hexdigest(),
                      'weights.pt': hashlib.sha256(weights).hexdigest()},
        'validation': {'mask_map50': .8, 'mask_map': .6},
    }
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    dataset = stage / 'dataset'
    (dataset / 'images' / 'val').mkdir(parents=True)
    (dataset / 'labels' / 'val').mkdir(parents=True)
    rows = []
    for index in range(6):
        positive = index < 4
        name = 'sample-%d' % index
        image = np.full((32, 32, 3), 255 if positive else 0, np.uint8)
        assert cv2.imwrite(str(dataset / 'images' / 'val' / (name + '.png')), image)
        (dataset / 'labels' / 'val' / (name + '.txt')).write_text(
            '0 .25 .3 .75 .3 .75 .7 .25 .7\n' if positive else '', encoding='utf-8')
        rows.append({'image': 'images/val/' + name + '.png', 'split': 'val',
                     'label': 'positive' if positive else 'negative',
                     'baseline_box': [.125, .25, .875, .75]})
    (dataset / 'manifest.jsonl').write_text(
        ''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    (job / 'report.json').write_text(json.dumps({
        'provenance': {'input': '/synthetic/original.mp4', 'input_sha256': 'a' * 64},
        'detections': [{'enabled': False, 'verified_label': 'not_plate'}],
    }), encoding='utf-8')
    return job, folder


def test_historical_candidates_list_without_model_execution_or_activation(tmp_path, monkeypatch):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    before = (job / 'report.json').read_bytes()
    import onnxruntime as ort
    monkeypatch.setattr(ort, 'InferenceSession', lambda *a, **k: pytest.fail('Listing executed ONNX'))
    listed = lc.list_candidates(job)
    assert len(listed) == 1
    descriptor = listed[0]
    assert set(descriptor) == {'id', 'name', 'version', 'created_at', 'model_sha256',
                                'assessment', 'mask_assessment'}
    assert descriptor['id'] == CANDIDATE_ID
    assert descriptor['version'] == VERSION
    assert descriptor['assessment'] is None and descriptor['mask_assessment'] is None
    assert descriptor['model_sha256'] == hashlib.sha256((folder / 'model.onnx').read_bytes()).hexdigest()
    assert str(job) not in json.dumps(listed)
    assert (job / 'report.json').read_bytes() == before
    assert not (job / 'learning' / 'active.json').exists()


def test_empty_or_incomplete_candidate_trees_are_not_activated(tmp_path):
    lc = candidates()
    job = tmp_path / 'job'
    job.mkdir()
    assert lc.list_candidates(job) == []
    partial = job / 'learning' / 'passes' / PASS_ID / 'versions' / VERSION
    partial.mkdir(parents=True)
    (partial / 'model.onnx').write_bytes(b'incomplete training')
    assert lc.list_candidates(job) == []


def test_loading_candidate_verifies_artifacts_and_returns_bounded_internal_paths(tmp_path):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    candidate = lc.load_candidate(job, CANDIDATE_ID)
    assert candidate['id'] == CANDIDATE_ID
    assert Path(candidate['folder']) == folder
    assert Path(candidate['model_path']) == folder / 'model.onnx'
    assert Path(candidate['dataset']) == folder.parent.parent / 'dataset'
    assert candidate['model_sha256'] == hashlib.sha256((folder / 'model.onnx').read_bytes()).hexdigest()


@pytest.mark.parametrize('candidate_id', ['../outside', '/tmp/model.onnx',
    PASS_ID + ':../../other', PASS_ID + '/' + VERSION, CANDIDATE_ID + ':extra',
    'pass-not-a-real-id:' + VERSION, None, 42])
def test_candidate_identifiers_cannot_select_arbitrary_paths(tmp_path, candidate_id):
    lc = candidates()
    job, _ = candidate_job(tmp_path)
    with pytest.raises(ValueError):
        lc.load_candidate(job, candidate_id)


@pytest.mark.parametrize('artifact', ['model.onnx', 'weights.pt'])
def test_corrupt_or_linked_candidate_artifacts_are_refused(tmp_path, artifact):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    path = folder / artifact
    original = path.read_bytes()
    path.write_bytes(original + b'changed')
    with pytest.raises(ValueError, match='hash|SHA|integrity|modified'):
        lc.load_candidate(job, CANDIDATE_ID)
    outside = tmp_path / ('outside-' + artifact)
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        lc.load_candidate(job, CANDIDATE_ID)


def test_real_evaluation_reuses_retained_model_and_persists_independent_assessment(tmp_path):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    before = (job / 'report.json').read_bytes()
    lc.record_mask_assessment(job, folder, 'failed', 'No tighter masks without plate-pixel loss')
    notices = []
    assessment = lc.evaluate(job, CANDIDATE_ID, progress=lambda done, total: notices.append((done, total)))
    assert assessment['status'] == 'validated'
    assert assessment['held_out_positive'] == assessment['retained_positive'] == 4
    assert assessment['held_out_negative'] == assessment['rejected_negative'] == 2
    assert assessment['rejected_positive'] == 0
    assert notices and notices[-1] == (6, 6)
    current = lc.list_candidates(job)[0]
    assert current['assessment'] == assessment
    assert current['mask_assessment']['status'] == 'failed'
    assert 'No tighter' in current['mask_assessment']['message']
    assert (job / 'report.json').read_bytes() == before
    assert not (job / 'learning' / 'active.json').exists()
    assert (folder / 'weights.pt').read_bytes().startswith(b'synthetic checkpoint')


def test_unseparated_candidate_keeps_honest_review_only_result(tmp_path):
    lc = candidates()
    job, _ = candidate_job(tmp_path, separable=False)
    assessment = lc.evaluate(job, CANDIDATE_ID)
    assert assessment['status'] == 'review_only'
    assert assessment['rejected_negative'] == 0
    assert lc.load_candidate(job, CANDIDATE_ID)['assessment'] == assessment


def test_cancelled_candidate_evaluation_does_not_publish_an_assessment(tmp_path):
    lc = candidates()
    job, _ = candidate_job(tmp_path)
    before = (job / 'report.json').read_bytes()
    with pytest.raises(InterruptedError):
        lc.evaluate(job, CANDIDATE_ID, cancelled=lambda: True)
    assert lc.list_candidates(job)[0]['assessment'] is None
    assert (job / 'report.json').read_bytes() == before


def test_modified_dataset_during_evaluation_does_not_certify_filtering(tmp_path, monkeypatch):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    import plate_verifier
    original = plate_verifier.assess
    def changed(model, dataset, **kwargs):
        result = original(model, dataset, **kwargs)
        image = Path(dataset) / 'images' / 'val' / 'sample-0.png'
        image.write_bytes(image.read_bytes() + b'changed during evaluation')
        return result
    monkeypatch.setattr(plate_verifier, 'assess', changed)
    with pytest.raises(ValueError, match='changed'):
        lc.evaluate(job, CANDIDATE_ID)
    assert lc.list_candidates(job)[0]['assessment'] is None


def test_candidate_assessment_never_follows_replaced_model_bytes(tmp_path):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    lc.evaluate(job, CANDIDATE_ID)
    payload = proposal_model_bytes(separable=False)
    (folder / 'model.onnx').write_bytes(payload)
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['artifacts']['model.onnx'] = hashlib.sha256(payload).hexdigest()
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    assert lc.load_candidate(job, CANDIDATE_ID)['assessment'] is None
    with pytest.raises(ValueError, match='assessment|evaluat'):
        learned_models.save_candidate(tmp_path / 'models', job, CANDIDATE_ID, 'Stale check')


def test_candidate_dataset_paths_and_symlinks_cannot_escape(tmp_path):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    dataset = folder.parent.parent / 'dataset'
    manifest = dataset / 'manifest.jsonl'
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    rows[0]['image'] = '../../outside.png'
    manifest.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    with pytest.raises(ValueError):
        lc.evaluate(job, CANDIDATE_ID)
    shutil.rmtree(dataset)
    outside = tmp_path / 'outside-dataset'
    outside.mkdir()
    dataset.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        lc.load_candidate(job, CANDIDATE_ID)


def test_mask_assessment_records_only_exact_verified_candidate(tmp_path):
    lc = candidates()
    job, folder = candidate_job(tmp_path)
    lc.record_mask_assessment(job, folder, 'passed', 'Mask gate passed')
    row = lc.list_candidates(job)[0]
    assert row['mask_assessment']['status'] == 'passed'
    assert row['assessment'] is None
    with pytest.raises(ValueError):
        lc.record_mask_assessment(job, tmp_path, 'passed', 'Wrong location')
    with pytest.raises(ValueError):
        lc.record_mask_assessment(job, folder, 'accepted_for_everything', 'Unknown meaning')
