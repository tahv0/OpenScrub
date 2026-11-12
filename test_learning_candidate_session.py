"""Training quality rejection retains an inspectable secondary candidate."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

import learning_candidates
import learning_session as ls
import openscrub_web as web
from test_learning_candidates import candidate_job, proposal_model_bytes, VERSION
from test_learning_session import _seed
from test_plate_quad_editor import plate_job


def complete_candidate(versions):
    folder = Path(versions) / VERSION
    folder.mkdir(parents=True)
    (folder / 'model.onnx').write_bytes(proposal_model_bytes())
    (folder / 'weights.pt').write_bytes(b'synthetic training checkpoint')
    meta = {'schema': 1, 'status': 'candidate', 'version': VERSION,
            'created_utc': '2026-11-11T12:00:00+00:00',
            'artifacts': {name: ls.sha256(folder / name) for name in ('model.onnx', 'weights.pt')}}
    (folder / 'manifest.json').write_text(json.dumps(meta), encoding='utf-8')
    return folder, meta


def rejection_type():
    assert hasattr(ls, 'CoverageRejected'), 'Quality rejection must be distinct from operational failure'
    assert issubclass(ls.CoverageRejected, ValueError)
    return ls.CoverageRejected


class EmptyModel:
    def __init__(self, *args, **kwargs):
        pass

    def predict(self, image):
        return None, 0.

    def predict_proposal(self, image, box):
        return self.predict(image)


class TightModel:
    def __init__(self, *args):
        pass

    def predict(self, image):
        mask = np.zeros(image.shape[:2], np.uint8)
        mask[10:23, 8:25] = 1
        return mask, .99


def test_real_mask_quality_rejection_is_typed_and_explains_retained_candidate(tmp_path):
    _, folder = candidate_job(tmp_path)
    with pytest.raises(rejection_type()) as caught:
        ls.calibrate(EmptyModel(), folder.parent.parent / 'dataset')
    assert 'tighter coverage' in str(caught.value)
    assert 'candidate' in str(caught.value).lower()
    assert 'secondary' in str(caught.value).lower()
    assert 'review' in str(caught.value).lower()


def test_valid_mask_calibration_remains_accepted(tmp_path):
    _, folder = candidate_job(tmp_path)
    assessment = ls.calibrate(TightModel(), folder.parent.parent / 'dataset')
    assert assessment['held_out_positive'] == assessment['accepted'] == 4
    assert assessment['excess_pixels_removed'] > 0
    assert assessment['minimum_known_coverage'] >= .995


@pytest.mark.parametrize('damage', [
    'missing_manifest', 'missing_image', 'invalid_json', 'invalid_label',
    'empty_label', 'nan_label', 'nan_baseline', 'nan_score', 'nan_mask',
])
def test_corrupt_calibration_inputs_remain_operational_failures(tmp_path, damage):
    _, folder = candidate_job(tmp_path)
    dataset = folder.parent.parent / 'dataset'
    model = EmptyModel()
    if damage == 'missing_manifest':
        (dataset / 'manifest.jsonl').unlink()
    elif damage == 'missing_image':
        (dataset / 'images/val/sample-0.png').unlink()
    elif damage == 'invalid_json':
        (dataset / 'manifest.jsonl').write_text('{')
    elif damage == 'invalid_label':
        (dataset / 'labels/val/sample-0.txt').write_text('0 not-a-number')
    elif damage == 'empty_label':
        (dataset / 'labels/val/sample-0.txt').write_text('')
    elif damage == 'nan_label':
        (dataset / 'labels/val/sample-0.txt').write_text('0 nan .3 .75 .3 .75 .7 .25 .7')
    elif damage == 'nan_baseline':
        rows = [json.loads(line) for line in (dataset / 'manifest.jsonl').read_text().splitlines()]
        rows[0]['baseline_box'][0] = float('nan')
        (dataset / 'manifest.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
    elif damage == 'nan_score':
        model.predict = lambda image: (None, float('nan'))
    else:
        model.predict = lambda image: (np.full(image.shape[:2], float('nan')), .9)
    with pytest.raises(Exception) as caught:
        ls.calibrate(model, dataset)
    assert not isinstance(caught.value, rejection_type()), 'Corruption must not advertise a quality-only rejection'


def test_rejected_mask_assessment_is_persisted_without_scan_or_report_change(plate_job, monkeypatch):
    job, _, path, _ = _seed(plate_job)
    before = path.read_bytes()
    made = []
    def train(dataset, versions, *args):
        result = complete_candidate(versions)
        made.append(result[0])
        return result
    def reject(*args):
        raise rejection_type()('Candidate undercovers known plate pixels')
    monkeypatch.setattr(ls, 'run_training', train)
    with pytest.raises(rejection_type(), match='undercovers'):
        ls.run_session(job, lambda i: web._read_exact_frame(job['video'], i),
                       lambda *a: pytest.fail('Quality rejection must not start a rescan'),
                       lambda *a: pytest.fail('Quality rejection must not publish a report'),
                       refiner=EmptyModel, calibration=reject)
    assert path.read_bytes() == before
    records = learning_candidates.list_candidates(job['dir'])
    assert len(records) == 1 and records[0]['assessment'] is None
    assert records[0]['mask_assessment']['status'] == 'failed'
    assert 'undercovers' in records[0]['mask_assessment']['message']
    assert (made[0] / 'model.onnx').exists() and (made[0] / 'weights.pt').exists()
    assert not (Path(job['dir']) / 'learning/active.json').exists()


@pytest.mark.parametrize('outcome', ['no_proposals', 'no_refinements'])
def test_post_rescan_quality_outcome_retains_candidate_and_previous_review(plate_job, monkeypatch, outcome):
    job, original, path, _ = _seed(plate_job)
    before = path.read_bytes()
    monkeypatch.setattr(ls, 'run_training', lambda dataset, versions, *args: complete_candidate(versions))
    calls = []
    def scan(*args):
        calls.append('scan')
        fresh = deepcopy(original)
        if outcome == 'no_proposals':
            fresh['detections'] = []
        return fresh
    with pytest.raises(rejection_type()) as caught:
        ls.run_session(job, lambda i: web._read_exact_frame(job['video'], i), scan,
                       lambda *a: pytest.fail('No usable output must not replace previous review'),
                       refiner=EmptyModel, calibration=lambda *a: {'threshold': .5})
    assert calls == ['scan']
    assert ('no proposals' if outcome == 'no_proposals' else 'no usable refinements') in str(caught.value)
    assert path.read_bytes() == before
    candidate = learning_candidates.list_candidates(job['dir'])[0]
    assert candidate['mask_assessment']['status'] == 'failed'
    assert candidate['assessment'] is None


def test_successful_mask_calibration_records_pass_without_certifying_verification(plate_job, monkeypatch, tmp_path):
    job, original, path, _ = _seed(plate_job)
    _, validation_candidate = candidate_job(tmp_path)
    def train(dataset, versions, *args):
        shutil.copytree(validation_candidate.parent.parent / 'dataset', dataset, dirs_exist_ok=True)
        return complete_candidate(versions)
    monkeypatch.setattr(ls, 'run_training', train)
    def refined(video, doc, model, *args, **kwargs):
        return deepcopy(doc), {'model_calls': 1, 'refined': 1}
    monkeypatch.setattr(ls.vl, 'refine_report', refined)
    result = ls.run_session(job, lambda i: web._read_exact_frame(job['video'], i),
                            lambda *a: deepcopy(original), lambda doc: ls.atomic_json(path, doc),
                            refiner=TightModel)
    assert result['learning']['active']['model']
    assert result['learning']['validation']['accepted'] == 4
    candidate = learning_candidates.list_candidates(job['dir'])[0]
    assert candidate['mask_assessment']['status'] == 'passed'
    assert candidate['assessment'] is None


def test_operational_calibration_failure_does_not_claim_a_mask_quality_outcome(plate_job, monkeypatch):
    job, _, path, _ = _seed(plate_job)
    before = path.read_bytes()
    monkeypatch.setattr(ls, 'run_training', lambda dataset, versions, *args: complete_candidate(versions))
    def broken(*args):
        raise ValueError('Unreadable validation crop')
    with pytest.raises(ValueError, match='Unreadable') as caught:
        ls.run_session(job, lambda i: web._read_exact_frame(job['video'], i),
                       lambda *a: pytest.fail('Invalid inputs must not start a rescan'),
                       lambda *a: pytest.fail('Invalid inputs must not publish'),
                       refiner=EmptyModel, calibration=broken)
    assert not isinstance(caught.value, rejection_type())
    assert path.read_bytes() == before
    assert learning_candidates.list_candidates(job['dir'])[0]['mask_assessment'] is None


@pytest.mark.parametrize('damage', ['missing_manifest', 'changed_model'])
def test_damaged_candidate_is_an_operational_error_not_a_retained_quality_result(plate_job, monkeypatch, damage):
    job, _, path, _ = _seed(plate_job)
    before = path.read_bytes()
    def train(dataset, versions, *args):
        folder, meta = complete_candidate(versions)
        if damage == 'missing_manifest':
            (folder / 'manifest.json').unlink()
        else:
            (folder / 'model.onnx').write_bytes(b'corrupt model')
        return folder, meta
    def reject(*args):
        raise rejection_type()('The trained mask failed its quality check')
    monkeypatch.setattr(ls, 'run_training', train)
    with pytest.raises(ValueError) as caught:
        ls.run_session(job, lambda i: web._read_exact_frame(job['video'], i),
                       lambda *a: pytest.fail('Damaged model must not scan'),
                       lambda *a: pytest.fail('Damaged model must not publish'),
                       refiner=EmptyModel, calibration=reject)
    assert not isinstance(caught.value, rejection_type())
    assert path.read_bytes() == before


def test_worker_exposes_retained_candidate_without_marking_training_as_an_error(plate_job, monkeypatch):
    client, jid, _, _ = plate_job
    job, _, path, _ = _seed(plate_job)
    before = path.read_bytes()
    job.update(phase='learning', learning_previous_phase='review', error='previous error')
    # The worker now saves a named secondary model, so keep that durable
    # library isolated alongside this test's source job.
    monkeypatch.setattr(web, 'JOBS_DIR', str(Path(job['dir']).parent))
    monkeypatch.setattr(ls, 'preflight', lambda: {'ready': True, 'problems': []})
    monkeypatch.setattr(ls, 'run_training', lambda dataset, versions, *args: complete_candidate(versions))
    monkeypatch.setattr(ls.vl, 'CropRefiner', EmptyModel)
    monkeypatch.setattr(web.openscrub, 'run_scan', lambda *a: pytest.fail('Rejected mask must not rescan'))
    web.perform_learning(job)
    assert job['phase'] == 'review' and job['error'] is None
    assert path.read_bytes() == before
    status = client.get('/api/jobs/%s/learning' % jid).get_json()['status']
    assert status['stage'] == 'candidate_ready'
    assert 'candidate' in status['message'] and 'secondary' in status['message']
    records = learning_candidates.list_candidates(job['dir'])
    assert len(records) == 1 and records[0]['mask_assessment']['status'] == 'failed'
    assert records[0]['assessment']['status'] == 'review_only'
    model_id = job['learning']['model_id']
    saved = web.learned_models.list_models(web.learned_models_root())
    assert len(saved) == 1 and saved[0]['id'] == model_id
    assert saved[0]['kind'] == 'openscrub-plate-verifier'
