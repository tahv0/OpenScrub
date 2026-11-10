"""Use real saved crops and the unchanged trainer's leakage validator."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

import learning_session as ls
from scripts import train_plate_seg as trainer


def old_split(group):
    return 'val' if int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) / 0xffffffff < .2 else 'train'


def groups(split, n=1):
    return [f'group-{i}' for i in range(1000) if old_split(f'group-{i}') == split][:n]


def image_for_hash(value, brightness=128):
    """An 8x9 BGR crop with exactly the requested 64-bit difference hash."""
    rows = []
    for row in range(8):
        values = [brightness]
        for col in range(8):
            bit = (value >> (63 - row * 8 - col)) & 1
            values.append(values[-1] + (4 if bit else -4))
        rows.append(values)
    image = np.repeat(np.asarray(rows, np.uint8)[:, :, None], 3, axis=2)
    assert trainer._dhash(image) == value
    return image


def save(root, specs):
    samples = {}
    for index, (group, signature, label, brightness) in enumerate(specs):
        image = root / f'sample-{index}.png'
        assert cv2.imwrite(str(image), image_for_hash(signature, brightness))
        samples[f's{index:03d}'] = {
            'image': image.name, 'image_sha256': ls.sha256(image),
            'label': label, 'quality': 'human_quad' if label == 'positive' else 'human_hard_negative',
            'points': [[.1, .2], [.8, .2], [.8, .8], [.1, .8]],
            'frame': index, 'group': group, 'baseline_box': [0, 0, 1, 1],
        }
    return {'samples': samples}


def checked_export(root, feedback, name='dataset', **kwargs):
    destination = root / name
    rows = ls.export_dataset(root, feedback, destination, **kwargs)
    # Zero count requirements isolate the independent, UNMODIFIED leakage check.
    trainer.validate_dataset(destination, 0, 0, 0)
    return rows


@pytest.mark.parametrize('distance', [0, 1, 2])
def test_visual_duplicates_across_tracks_export_without_leakage(tmp_path, distance):
    train, val = groups('train')[0], groups('val')[0]
    feedback = save(tmp_path, [(train, 0, 'positive', 128),
                               (val, (1 << distance) - 1, 'positive', 160)])
    assert len({s['image_sha256'] for s in feedback['samples'].values()}) == 2
    rows = checked_export(tmp_path, feedback)
    assert len(rows) == 2 and {r['split'] for r in rows} == {'train'}


def test_near_duplicate_moves_the_whole_track_not_just_one_crop(tmp_path):
    train, val = groups('train')[0], groups('val')[0]
    feedback = save(tmp_path, [(train, 0, 'positive', 128),
                               (val, 3, 'positive', 160),
                               (val, (1 << 64) - 1, 'positive', 128)])
    rows = checked_export(tmp_path, feedback)
    assert len(rows) == 3 and {r['split'] for r in rows} == {'train'}


def test_transitive_similarity_chain_cannot_bridge_the_split(tmp_path):
    v1, v2 = groups('val', 2)
    train = groups('train')[0]
    feedback = save(tmp_path, [(v1, 0, 'positive', 128),
                               (v2, 3, 'positive', 160),
                               (train, 15, 'positive', 128)])
    assert (0 ^ 15).bit_count() > 2
    rows = checked_export(tmp_path, feedback)
    assert len(rows) == 3 and {r['split'] for r in rows} == {'train'}


def test_skipped_exact_duplicate_still_links_both_whole_groups(tmp_path):
    val, train = groups('val')[0], groups('train')[0]
    feedback = save(tmp_path, [(val, 0, 'positive', 128),
                               (train, 0, 'positive', 128),
                               (train, (1 << 64) - 1, 'positive', 128)])
    rows = checked_export(tmp_path, feedback)
    assert len(rows) == 2 and {r['split'] for r in rows} == {'train'}


def test_labels_do_not_exempt_visual_overlap_from_grouping(tmp_path):
    train, val = groups('train')[0], groups('val')[0]
    feedback = save(tmp_path, [(train, 0, 'negative', 128),
                               (val, 3, 'positive', 160)])
    rows = checked_export(tmp_path, feedback)
    assert {r['label'] for r in rows} == {'positive', 'negative'}
    assert {r['split'] for r in rows} == {'train'}


def test_three_bit_difference_stays_independent_and_inputs_unchanged(tmp_path):
    train, val = groups('train')[0], groups('val')[0]
    feedback = save(tmp_path, [(train, 0, 'positive', 128),
                               (val, 7, 'positive', 160)])
    before = deepcopy(feedback)
    bytes_before = {s['image']: (tmp_path / s['image']).read_bytes() for s in feedback['samples'].values()}
    rows = checked_export(tmp_path, feedback)
    assert {r['job']: r['split'] for r in rows} == {train: 'train', val: 'val'}
    assert feedback == before
    assert all((tmp_path / name).read_bytes() == data for name, data in bytes_before.items())
    reordered = {'samples': dict(reversed(list(feedback['samples'].items())))}
    assert checked_export(tmp_path, reordered, 'dataset-two') == rows


def test_validation_only_duplicate_component_stays_held_out(tmp_path):
    v1, v2 = groups('val', 2)
    feedback = save(tmp_path, [(v1, 0, 'positive', 128), (v2, 3, 'positive', 160)])
    assert {r['split'] for r in checked_export(tmp_path, feedback)} == {'val'}


def test_previous_training_group_cannot_reenter_validation_after_bridge_removed(tmp_path):
    val = groups('val')[0]
    feedback = save(tmp_path, [(val, 0, 'positive', 128)])
    rows = checked_export(tmp_path, feedback, training_groups={val})
    assert rows[0]['split'] == 'train'


def test_previous_accepted_manifest_seeds_train_group_history(tmp_path):
    pass_id = 'pass-' + 'a' * 12
    dataset = tmp_path / 'passes' / pass_id / 'dataset'
    dataset.mkdir(parents=True)
    rows = [{'split': 'train', 'job': 'prior-train'}, {'split': 'val', 'job': 'prior-val'}]
    (dataset / 'manifest.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    assert ls._prior_training_groups(tmp_path, {'pass_id': pass_id}) == {'prior-train'}
    assert ls._prior_training_groups(tmp_path, {'pass_id': pass_id, 'training_groups': ['older-train']}) == {'prior-train', 'older-train'}
    assert ls._prior_training_groups(tmp_path, {}) == set()


def test_missing_prior_training_manifest_fails_closed(tmp_path):
    with pytest.raises(ValueError, match='previous.*split|previous.*dataset'):
        ls._prior_training_groups(tmp_path, {'pass_id': 'pass-' + 'a' * 12})


def test_insufficient_distinct_examples_still_rejected(tmp_path):
    train, val = groups('train')[0], groups('val')[0]
    feedback = save(tmp_path, [(train, 0, 'positive', 128), (val, 3, 'positive', 160)])
    ls.export_dataset(tmp_path, feedback, tmp_path / 'dataset')
    with pytest.raises(trainer.DataError, match='val needs at least 1'):
        trainer.validate_dataset(tmp_path / 'dataset', 1, 1, 0)


def test_tampered_source_crop_is_not_exported(tmp_path):
    feedback = save(tmp_path, [(groups('train')[0], 0, 'positive', 128)])
    (tmp_path / 'sample-0.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Saved training image changed'):
        ls.export_dataset(tmp_path, feedback, tmp_path / 'dataset')


@pytest.mark.parametrize('shape', [(8, 9), (72, 128), (125, 227)])
def test_exporter_signature_matches_the_trainer(shape):
    image = np.random.default_rng(91).integers(0, 256, (*shape, 3), dtype=np.uint8)
    assert ls._feedback_dhash(image) == trainer._dhash(image)


def test_default_validation_minima_still_pass_with_independent_groups(tmp_path):
    rng = np.random.default_rng(42)
    specs = []
    for split, positives in [('train', 14), ('val', 5)]:
        for i, group in enumerate(groups(split, positives + 1)):
            signature = int.from_bytes(rng.bytes(8), 'big')
            specs.append((group, signature, 'positive' if i < positives else 'negative', 128))
    train = groups('train')[0]
    val = groups('val')[0]
    # Connect one validation group to an existing training group, leaving four
    # independent held-out positives. Both crops remain in the new snapshot.
    specs.extend([(train, 0, 'positive', 128), (val, 3, 'positive', 160)])
    feedback = save(tmp_path, specs)
    checked_export(tmp_path, feedback)
    report = trainer.validate_dataset(tmp_path / 'dataset')
    assert report['counts']['val']['positive'] == 4
    assert report['samples'] == len(specs)


def test_accepted_session_persists_training_exposure_across_passes(tmp_path, monkeypatch):
    import threading
    group = groups('val')[0]
    root = tmp_path / 'learning'
    root.mkdir()
    duplicate_group = groups('val', 2)[1]
    feedback = save(root, [(group, 0, 'positive', 128), (duplicate_group, 0, 'positive', 128)])
    source = tmp_path / 'video'; source.write_bytes(b'synthetic source fingerprint only')
    sha = ls.sha256(source)
    pass_id = 'pass-' + 'b' * 12
    old_dataset = root / 'passes' / pass_id / 'dataset'
    old_dataset.mkdir(parents=True)
    (old_dataset / 'manifest.jsonl').write_text(json.dumps({'split': 'train', 'job': group}) + '\n')
    doc = {'provenance': {'input_sha256': sha}, 'render_state': {'fps': 30, 'cum': []}, 'detections': [],
           'learning': {'active': {'pass_id': pass_id, 'weights': 'old.pt', 'training_groups': ['absent-older-group']}}}
    (tmp_path / 'report.json').write_text(json.dumps(doc))
    feedback.update(fingerprint='changed', constraints={'source_sha256': sha, 'fps': 30, 'anchors': []})
    monkeypatch.setattr(ls, 'collect_feedback', lambda *a, **k: feedback)
    monkeypatch.setattr(ls.vl, 'refine_report', lambda *a, **k: (deepcopy(doc), {'refined': 1, 'model_calls': 1}))
    def train(dataset, versions, weights, job, settings):
        assert weights == 'old.pt'
        rows = [json.loads(line) for line in (dataset / 'manifest.jsonl').read_text().splitlines()]
        assert rows[0]['split'] == 'train'
        versions.mkdir()
        return versions, {'version': 'synthetic', 'artifacts': {'model.onnx': 'synthetic'}}
    published = []
    job = {'dir': tmp_path, 'video': source, 'cancel': threading.Event(),
           'learning_request': {'license_accepted': True}}
    result = ls.run_session(job, None, lambda path: deepcopy(doc), published.append,
                            train=train, refiner=lambda path: object(),
                            calibration=lambda *a: {'threshold': .8})
    assert len(published) == 1
    assert result['learning']['active']['training_groups'] == sorted([group, duplicate_group, 'absent-older-group'])


@pytest.mark.parametrize('rows', [[], [{'split': 'val', 'job': 'only-val'}]])
def test_empty_previous_training_split_is_not_trusted(tmp_path, rows):
    pass_id = 'pass-' + 'c' * 12
    dataset = tmp_path / 'passes' / pass_id / 'dataset'
    dataset.mkdir(parents=True)
    (dataset / 'manifest.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    with pytest.raises(ValueError, match='previous training split'):
        ls._prior_training_groups(tmp_path, {'pass_id': pass_id})
