"""Secondary verification uses proposal scores and never invents human labels."""
from copy import deepcopy
import importlib
import importlib.util
import json

import cv2
import numpy as np
import pytest

import video_learning as vl


def verifier():
    assert importlib.util.find_spec('plate_verifier'), 'Secondary plate verifier is missing'
    return importlib.import_module('plate_verifier')


def brightness_onnx_bytes():
    """Real CPU graph: bright crop=.9 plate score, dark crop=.1 plate score."""
    from onnx import TensorProto, helper, numpy_helper
    head = np.zeros((1, 37, 1), np.float32)
    head[0, :4, 0] = [16, 16, 16, 8]
    head[0, 5, 0] = 1
    selector = np.zeros_like(head)
    selector[0, 4, 0] = 1
    values = {'base': head, 'selector': selector,
              'proto': np.ones((1, 32, 8, 8), np.float32),
              'half': np.array(.5, np.float32), 'scale': np.array(.8, np.float32),
              'offset': np.array(.1, np.float32)}
    nodes = [helper.make_node('Constant', [], [key], value=numpy_helper.from_array(value))
             for key, value in values.items()]
    nodes += [helper.make_node('ReduceMean', ['images'], ['mean'], axes=[0, 1, 2, 3], keepdims=0),
              helper.make_node('Greater', ['mean', 'half'], ['bright']),
              helper.make_node('Cast', ['bright'], ['number'], to=TensorProto.FLOAT),
              helper.make_node('Mul', ['number', 'scale'], ['scaled']),
              helper.make_node('Add', ['scaled', 'offset'], ['score']),
              helper.make_node('Mul', ['score', 'selector'], ['selected']),
              helper.make_node('Add', ['base', 'selected'], ['head'])]
    graph = helper.make_graph(nodes, 'brightness verifier',
        [helper.make_tensor_value_info('images', TensorProto.FLOAT, [1, 3, 32, 32])],
        [helper.make_tensor_value_info('head', TensorProto.FLOAT, [1, 37, 1]),
         helper.make_tensor_value_info('proto', TensorProto.FLOAT, [1, 32, 8, 8])])
    return helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=9).SerializeToString()


def dataset(tmp_path, positives=(204, 230, 255, 220), negatives=(0, 25)):
    root = tmp_path / 'dataset'
    root.mkdir()
    records = []
    for label, levels in [('positive', positives), ('negative', negatives)]:
        for index, level in enumerate(levels):
            name = '%s-%d.png' % (label, index)
            assert cv2.imwrite(str(root / name), np.full((20, 20, 3), level, np.uint8))
            records.append(dict(image=name, label=label, split='val', baseline_box=[.25, .25, .75, .75]))
    (root / 'manifest.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
    return root


class ScoreModel:
    def predict_proposal(self, image, box):
        assert np.allclose(box, [5, 5, 15, 15])
        return None, float(image[0, 0, 0]) / 255


def assessment(status='validated'):
    return dict(schema=1, status=status, threshold=.5,
                held_out_positive=4, held_out_negative=2,
                retained_positive=4, rejected_positive=0, rejected_negative=2,
                reason='Held-out proposal score assessment')


def video_report(tmp_path, rows, frames=5, timeline=3):
    path = tmp_path / 'video.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (80, 60))
    assert writer.isOpened()
    for _ in range(frames):
        writer.write(np.zeros((60, 80, 3), np.uint8))
    writer.release()
    doc = dict(provenance={}, render_state=dict(fps=10., cum=[[0, 0]] * timeline), detections=rows)
    return path, doc


def row(frame=1, **kwargs):
    result = dict(category='plate', frame_index=frame, t_start=frame / 10, cbox=[20, 20, 50, 40],
                  enabled=True, track=frame)
    result.update(kwargs)
    return result


def test_assessment_separates_both_labels_without_mask_shrink_requirement(tmp_path):
    pv = verifier()
    progress = []
    result = pv.assess(ScoreModel(), dataset(tmp_path), progress=lambda *p: progress.append(p))
    assert result['status'] == 'validated'
    assert .1 < result['threshold'] < .8, 'Keep a margin below the lowest observed plate score'
    assert result['held_out_positive'] == result['retained_positive'] == 4
    assert result['held_out_negative'] == result['rejected_negative'] == 2
    assert result['rejected_positive'] == 0
    assert progress[-1] == (6, 6)
    assert pv.validate_assessment(result) == result


@pytest.mark.parametrize('positives,negatives', [((0, 230, 255, 220), (0, 25)),
    ((200, 210, 220), (0, 25)), ((200, 210, 220, 230), (0,)),
    ((100, 110, 120, 130), (240, 250))])
def test_missing_positive_insufficient_and_inseparable_scores_allow_review_only(tmp_path, positives, negatives):
    result = verifier().assess(ScoreModel(), dataset(tmp_path, positives, negatives))
    assert result['status'] == 'review_only'
    assert result['held_out_positive'] == len(positives)
    assert result['held_out_negative'] == len(negatives)
    assert result['retained_positive'] + result['rejected_positive'] == len(positives)


@pytest.mark.parametrize('change', [dict(rejected_positive=1), dict(held_out_positive=3, retained_positive=3),
    dict(held_out_negative=1, rejected_negative=1), dict(rejected_negative=0), dict(threshold=float('nan')),
    dict(threshold=0), dict(retained_positive=True), dict(schema=True), dict(reason=[]), dict(extra='bad')])
def test_filtering_metadata_cannot_claim_unobserved_acceptance(change):
    value = assessment()
    value.update(change)
    with pytest.raises(ValueError):
        verifier().validate_assessment(value)


def test_real_cpu_proposal_scores_include_low_confidence_and_keep_legacy_predict():
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    assert callable(getattr(model, 'predict_proposal', None)), 'Proposal-associated prediction is missing'
    low_mask, low = model.predict_proposal(np.zeros((32, 32, 3), np.uint8), [8, 8, 24, 24])
    high_mask, high = model.predict_proposal(np.full((32, 32, 3), 255, np.uint8), [8, 8, 24, 24])
    assert low == pytest.approx(.1) and high == pytest.approx(.9)
    assert high_mask is not None
    legacy, score = model.predict(np.full((32, 32, 3), 255, np.uint8))
    assert legacy is not None and score == pytest.approx(.9)


def test_neighbor_prediction_cannot_confirm_proposal_and_association_handles_letterbox():
    from onnx import TensorProto, helper, numpy_helper
    pred = np.zeros((1, 37, 2), np.float32)
    # In a 64x32 image letterboxed to 32x32, original y=16 becomes net y=16.
    pred[0, :5, 0] = [8, 16, 6, 6, .12]
    pred[0, :5, 1] = [25, 16, 6, 6, .99]
    pred[0, 5, :] = 1
    proto = np.ones((1, 32, 8, 8), np.float32)
    graph = helper.make_graph([
        helper.make_node('Constant', [], ['head'], value=numpy_helper.from_array(pred)),
        helper.make_node('Constant', [], ['proto'], value=numpy_helper.from_array(proto))], 'nearby plate',
        [helper.make_tensor_value_info('images', TensorProto.FLOAT, [1, 3, 32, 32])],
        [helper.make_tensor_value_info('head', TensorProto.FLOAT, [1, 37, 2]),
         helper.make_tensor_value_info('proto', TensorProto.FLOAT, [1, 32, 8, 8])])
    payload = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=9).SerializeToString()
    model = vl.CropRefiner(payload, providers=['CPUExecutionProvider'])
    assert callable(getattr(model, 'predict_proposal', None)), 'Proposal-associated prediction is missing'
    image = np.zeros((32, 64, 3), np.uint8)
    _, score = model.predict_proposal(image, [8, 8, 24, 24])
    assert score == pytest.approx(.12)
    _, absent = model.predict_proposal(image, [28, 0, 32, 5])
    assert absent == 0


@pytest.mark.parametrize('mode,suppressed,decision', [('review', 0, 'suggest_not_plate'), ('filter', 1, 'suppress')])
def test_review_suggests_filter_suppresses_and_preserves_original_input(tmp_path, mode, suppressed, decision):
    path, doc = video_report(tmp_path, [row()])
    before = deepcopy(doc)
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    out, stats = verifier().review_report(path, doc, model, assessment(), mode)
    result = out['detections'][0]
    assert doc == before
    assert result['enabled'] is (mode == 'review')
    assert 'verified_label' not in result
    assert result['plate_verification']['decision'] == decision
    assert result['plate_verification']['previous_enabled'] is True
    assert result['plate_verification']['applied'] is (mode == 'filter')
    assert stats['decoded_frames'] == 3 and stats['model_calls'] == stats['checked'] == 1
    assert stats['suppressed'] == suppressed and stats['suggested'] == 1


def test_unvalidated_filter_and_unknown_modes_fail_before_changing_report(tmp_path):
    path, doc = video_report(tmp_path, [row()])
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    for gate, mode in [(assessment('review_only'), 'filter'), (assessment(), 'primary')]:
        with pytest.raises(ValueError):
            verifier().review_report(path, doc, model, gate, mode)


def test_human_labels_manual_keeps_and_manual_categories_are_preserved(tmp_path):
    rows = [row(0, verified_label='plate'), row(1, enabled=False, verified_label='not_plate'),
            row(2, enabled=False), row(2, category='manual')]
    path, doc = video_report(tmp_path, rows)
    before = deepcopy(rows)
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    out, stats = verifier().review_report(path, doc, model, assessment(), 'filter')
    assert [r['enabled'] for r in out['detections']] == [True, False, False, True]
    for old, new in zip(before, out['detections']):
        for key, value in old.items():
            assert new[key] == value
    assert stats['human_preserved'] == 3 and stats['model_calls'] == 0


def test_model_only_suppression_is_reversible_and_never_becomes_a_human_keep(tmp_path):
    path, doc = video_report(tmp_path, [row()])
    doc['provenance']['input_sha256'] = 'a' * 64
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    first, _ = verifier().review_report(path, doc, model, assessment(), 'filter')
    constraints = vl.capture_constraints(first)
    assert not constraints['anchors'] and not constraints['negative_paths']
    second, _ = verifier().review_report(path, first, model, assessment(), 'review')
    assert second['detections'][0]['enabled'] is True
    assert second['detections'][0]['plate_verification']['applied'] is False
    # An explicit later human label remains authoritative despite stale machine metadata.
    first['detections'][0]['verified_label'] = 'not_plate'
    third, _ = verifier().review_report(path, first, model, assessment(), 'review')
    assert third['detections'][0]['enabled'] is False
    assert vl.capture_constraints(third)['anchors'][0]['label'] == 'not_plate'


def test_explicit_human_blur_override_survives_constraints_and_checker(tmp_path):
    path, doc = video_report(tmp_path, [row(plate_verification_override=True)])
    doc['provenance']['input_sha256'] = 'a' * 64
    constraints = vl.capture_constraints(doc)
    assert len(constraints['anchors']) == 1
    fresh = deepcopy(doc)
    fresh['detections'][0].pop('plate_verification_override')
    fresh['detections'][0].update(enabled=False, plate_verification=dict(
        applied=True, decision='suppress', previous_enabled=True))
    applied = vl.apply_constraints(fresh, constraints)
    assert applied['detections'][0]['enabled'] is True
    assert applied['detections'][0]['plate_verification_override'] is True
    assert 'plate_verification' not in applied['detections'][0]
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    result, stats = verifier().review_report(path, applied, model, assessment(), 'filter')
    assert result['detections'][0]['enabled'] is True
    assert stats['human_preserved'] == 1 and stats['model_calls'] == 0


def test_human_negative_constraints_remove_stale_machine_suppression(tmp_path):
    source = dict(provenance={'input_sha256': 'a' * 64},
        render_state=dict(fps=10., cum=[[0, 0]] * 3),
        detections=[row(enabled=False, verified_label='not_plate')])
    constraints = vl.capture_constraints(source)
    fresh = deepcopy(source)
    fresh['detections'][0].pop('verified_label')
    fresh['detections'][0].update(enabled=False, plate_verification=dict(
        applied=True, decision='suppress', previous_enabled=True))
    applied = vl.apply_constraints(fresh, constraints)
    assert 'plate_verification' not in applied['detections'][0]
    assert applied['detections'][0]['verified_label'] == 'not_plate'


def test_cancel_and_decoder_shortfall_do_not_publish_partial_changes(tmp_path):
    path, doc = video_report(tmp_path, [row()], frames=2, timeline=3)
    before = deepcopy(doc)
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    with pytest.raises(InterruptedError):
        verifier().review_report(path, doc, model, assessment(), cancelled=lambda: True)
    with pytest.raises(ValueError, match='timeline'):
        verifier().review_report(path, doc, model, assessment())
    assert doc == before


def test_assessment_cancellation_on_last_progress_is_not_published(tmp_path):
    stop = []
    def progress(done, total):
        if done == total:
            stop.append(True)
    with pytest.raises(InterruptedError):
        verifier().assess(ScoreModel(), dataset(tmp_path), cancelled=lambda: bool(stop), progress=progress)


def test_out_of_timeline_proposal_is_an_error_instead_of_silently_unchecked(tmp_path):
    path, doc = video_report(tmp_path, [row(4)], frames=5, timeline=3)
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    with pytest.raises(ValueError, match='timeline'):
        verifier().review_report(path, doc, model, assessment())


def test_section_pass_only_changes_rows_inside_bounds_and_checks_identity(tmp_path):
    path, doc = video_report(tmp_path, [row(0), row(1), row(2)], frames=5, timeline=5)
    import hashlib
    doc['provenance']['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    doc['source_identity'] = dict(input_sha256=doc['provenance']['input_sha256'], total_frames=5)
    model = vl.CropRefiner(brightness_onnx_bytes(), providers=['CPUExecutionProvider'])
    result, stats = verifier().review_report(path, doc, model, assessment(), 'filter', frame_range=(1, 2))
    assert [r['enabled'] for r in result['detections']] == [True, False, True]
    assert stats['decoded_frames'] == 1
    doc['source_identity']['input_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='source'):
        verifier().review_report(path, doc, model, assessment(), frame_range=(1, 2))
