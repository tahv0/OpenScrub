"""Portable plate-mask models: real files, ZIP boundaries, and CPU ONNX inference."""
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import io
import json
import re
import shutil
import stat
import struct
import warnings
import zipfile

import numpy as np
import pytest


FIELDS = {
    'schema', 'kind', 'contract', 'id', 'name', 'description', 'created_at',
    'model_sha256', 'model_size', 'input_size', 'threshold', 'validation',
}
VALIDATION = {
    'threshold': .75, 'held_out_positive': 8, 'accepted': 6,
    'excess_pixels_removed': 120, 'minimum_known_coverage': .995,
}


def models():
    assert importlib.util.find_spec('learned_models'), 'Reusable learned model library is missing'
    return importlib.import_module('learned_models')


def onnx_bytes(shape=(1, 3, 32, 32), input_type=None, bad_outputs=False):
    # Real, deterministic single-class YOLO-seg graph; no mocked inference.
    from onnx import TensorProto, helper, numpy_helper
    input_type = TensorProto.FLOAT if input_type is None else input_type
    head = np.zeros((1, 37, 1), np.float32)
    head[0, :5, 0] = [16, 16, 24, 12, .95]
    head[0, 5, 0] = 1
    proto = np.zeros((1, 32, 8, 8), np.float32)
    proto[0, 0, 2:6, 1:7] = 10
    if bad_outputs:
        head = np.zeros((1, 6, 100), np.float32)
    graph = helper.make_graph([
        helper.make_node('Constant', [], ['output0'], value=numpy_helper.from_array(head)),
        helper.make_node('Constant', [], ['output1'], value=numpy_helper.from_array(proto)),
    ], 'portable plate fixture',
        [helper.make_tensor_value_info('images', input_type, list(shape))],
        [helper.make_tensor_value_info('output0', TensorProto.FLOAT, list(head.shape)),
         helper.make_tensor_value_info('output1', TensorProto.FLOAT, list(proto.shape))])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=9)
    return model.SerializeToString()


def model_bytes():
    return onnx_bytes()


def library():
    return models()


def accepted_job(tmp_path):
    job = tmp_path / 'original-video-job'
    version = job / 'learning' / 'passes' / 'accepted' / 'versions' / 'v1'
    version.mkdir(parents=True)
    payload = onnx_bytes()
    model = version / 'model.onnx'
    model.write_bytes(payload)
    (version / 'weights.pt').write_bytes(b'never export training checkpoints')
    report = {
        'video': '/private/camera/front-door.mp4',
        'provenance': {'input_sha256': 'a' * 64},
        'detections': [{'category': 'plate', 'verified_label': 'plate', 'frame_index': 17}],
        'learning': {
            'active': {'model': str(model), 'weights': str(version / 'weights.pt'),
                       'pass_id': 'accepted', 'training_groups': ['private-group']},
            'model_sha256': hashlib.sha256(payload).hexdigest(),
            'validation': dict(VALIDATION, warning='Original calibration only'),
            'previous_report': str(job / 'learning' / 'before-report.json'),
        },
    }
    (job / 'report.json').write_text(json.dumps(report), encoding='utf-8')
    (job / 'learning' / 'feedback.json').write_text('{"private_annotations": true}')
    return job


@pytest.fixture
def accepted(tmp_path):
    job = accepted_job(tmp_path)
    report = json.loads((job / 'report.json').read_text(encoding='utf-8'))
    from pathlib import Path
    model = Path(report['learning']['active']['model'])
    return job, report, model, model.read_bytes()


def write_report(job, report):
    (job / 'report.json').write_text(json.dumps(report), encoding='utf-8')


def archive(manifest, payload, entries=None):
    target = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr('manifest.json', json.dumps(manifest))
            zipped.writestr('model.onnx', payload)
            for name, value in entries or []:
                zipped.writestr(name, value)
    return target.getvalue()


def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        return json.loads(zipped.read('manifest.json')), zipped.read('model.onnx')


def assert_unpublished(root):
    assert not root.exists() or not list(root.iterdir()), 'Failed operations must leave no partial models'


def test_save_names_only_the_report_accepted_model_and_strips_private_data(tmp_path, accepted):
    lm = models()
    job, report, model, payload = accepted
    # An arbitrary newer candidate must not supersede the report's accepted artifact.
    candidate = job / 'learning' / 'passes' / 'newest-candidate'
    candidate.mkdir()
    (candidate / 'model.onnx').write_bytes(b'unaccepted training output')
    before = (job / 'report.json').read_bytes()
    root = tmp_path / 'models'
    manifest = lm.save_model(root, job, 'Front entrance', 'Rain and evening light')
    assert set(manifest) == FIELDS
    assert manifest['schema'] == 1 and manifest['contract'] == 1
    assert manifest['kind'] == 'openscrub-plate-mask-refiner'
    assert re.fullmatch('[0-9a-f]{32}', manifest['id'])
    assert manifest['name'] == 'Front entrance'
    assert manifest['description'] == 'Rain and evening light'
    assert manifest['input_size'] == 32
    assert manifest['threshold'] == .75
    assert manifest['validation'] == VALIDATION
    assert manifest['model_size'] == len(payload)
    assert manifest['model_sha256'] == hashlib.sha256(payload).hexdigest()
    assert isinstance(manifest['created_at'], str) and manifest['created_at']
    saved = root / manifest['id']
    assert {p.name for p in saved.iterdir()} == {'model.onnx', 'manifest.json'}
    assert (saved / 'model.onnx').read_bytes() == payload
    assert json.loads((saved / 'manifest.json').read_text()) == manifest
    assert (job / 'report.json').read_bytes() == before
    assert not (job / 'plate_model').exists(), 'Saving must never activate a model on a job'
    assert lm.list_models(root) == [manifest]


@pytest.mark.parametrize('mutation', [
    'no_learning', 'no_active', 'no_hash', 'wrong_hash', 'no_validation',
    'no_accepted', 'too_few_held_out', 'no_improvement', 'undercoverage',
])
def test_save_refuses_unaccepted_or_unverified_candidates(tmp_path, accepted, mutation):
    lm = models()
    job, report, model, payload = accepted
    if mutation == 'no_learning':
        report.pop('learning')
    elif mutation == 'no_active':
        report['learning'].pop('active')
    elif mutation == 'no_hash':
        report['learning'].pop('model_sha256')
    elif mutation == 'wrong_hash':
        report['learning']['model_sha256'] = '0' * 64
    elif mutation == 'no_validation':
        report['learning'].pop('validation')
    else:
        field, value = {
            'no_accepted': ('accepted', 0), 'too_few_held_out': ('held_out_positive', 3),
            'no_improvement': ('excess_pixels_removed', 0),
            'undercoverage': ('minimum_known_coverage', .9),
        }[mutation]
        report['learning']['validation'][field] = value
    write_report(job, report)
    root = tmp_path / 'models'
    with pytest.raises(lm.ModelError):
        lm.save_model(root, job, 'Rejected candidate')
    assert_unpublished(root)


@pytest.mark.parametrize('name,description', [
    ('', ''), ('   ', ''), ('a' * 81, ''), ('valid', 'a' * 501),
    (None, ''), (123, ''), ('valid', None), ('valid', []),
    ('bad\nname', ''), ('bad\x00name', ''), ('valid', 'bad\x7fdescription'),
])
def test_save_rejects_invalid_display_metadata(tmp_path, accepted, name, description):
    lm = models()
    root = tmp_path / 'models'
    with pytest.raises(lm.ModelError):
        lm.save_model(root, accepted[0], name, description)
    assert_unpublished(root)


def test_export_import_is_independent_of_video_and_machine_paths(tmp_path, accepted):
    lm = models()
    job, report, model, payload = accepted
    origin = tmp_path / 'machine-a' / 'jobs' / 'learned_plate_models'
    saved = lm.save_model(origin, job, 'Driveway', 'Original camera calibration')
    exported = lm.export_model(origin, saved['id'])
    with zipfile.ZipFile(io.BytesIO(exported)) as zipped:
        assert zipped.namelist().count('manifest.json') == 1
        assert set(zipped.namelist()) == {'manifest.json', 'model.onnx'}
    manifest, exported_payload = unpack(exported)
    assert exported_payload == payload
    text = json.dumps(manifest)
    assert '/private/' not in text and str(job) not in text
    for forbidden in ('source_sha256', 'input_sha256', 'training_groups', 'detections',
                      'annotations', 'frames', 'weights.pt', 'previous_report'):
        assert forbidden not in text
    # The source job and original machine are entirely absent when importing.
    shutil.rmtree(job)
    shutil.rmtree(origin.parent.parent)
    destination = tmp_path / 'machine-b' / 'elsewhere'
    imported = lm.import_model(destination, io.BytesIO(exported), name='Garage')
    assert imported['id'] != saved['id']
    assert imported['name'] == 'Garage'
    assert imported['description'] == 'Original camera calibration'
    assert imported['model_sha256'] == saved['model_sha256']
    assert imported['validation'] == VALIDATION
    assert {p.name for p in (destination / imported['id']).iterdir()} == {'manifest.json', 'model.onnx'}
    unrelated = tmp_path / 'another-video'
    unrelated.mkdir()
    (unrelated / 'report.json').write_text('{"provenance":{"input_sha256":"' + 'b' * 64 + '"},"detections":[]}')
    before = (unrelated / 'report.json').read_bytes()
    lm.snapshot_model(destination, imported['id'], unrelated)
    snap, copied = lm.load_snapshot(unrelated)
    assert copied == payload and snap['name'] == 'Garage'
    assert (unrelated / 'report.json').read_bytes() == before
    assert sorted(p.name for p in unrelated.iterdir()) == ['plate_model', 'report.json']


def test_import_path_and_default_name_are_supported(tmp_path, accepted):
    lm = models()
    source = tmp_path / 'source'
    saved = lm.save_model(source, accepted[0], 'Patio')
    path = tmp_path / 'portable.zip'
    path.write_bytes(lm.export_model(source, saved['id']))
    imported = lm.import_model(tmp_path / 'destination', path)
    assert imported['name'] == 'Patio'
    assert imported['id'] != saved['id']


def test_same_display_name_does_not_overwrite_an_existing_model(tmp_path, accepted):
    lm = models()
    root = tmp_path / 'models'
    first = lm.save_model(root, accepted[0], 'Entrance')
    second = lm.save_model(root, accepted[0], 'Entrance')
    assert first['id'] != second['id']
    assert {m['id'] for m in lm.list_models(root)} == {first['id'], second['id']}


@pytest.mark.parametrize('entry', ['../escape', '/absolute', 'nested/model.onnx',
                                   'weights.pt', 'feedback.json', 'model.onnx', 'manifest.json'])
def test_import_rejects_extra_unsafe_and_duplicate_entries(tmp_path, accepted, entry):
    lm = models()
    source = tmp_path / 'source'
    saved = lm.save_model(source, accepted[0], 'Entrance')
    root = tmp_path / 'destination'
    invalid = archive(saved, accepted[3], [(entry, b'forbidden')])
    with pytest.raises(lm.ModelError):
        lm.import_model(root, io.BytesIO(invalid))
    assert_unpublished(root)
    assert not (tmp_path / 'escape').exists()


def test_import_rejects_archive_symlink_entry(tmp_path, accepted):
    lm = models()
    source = tmp_path / 'source'
    saved = lm.save_model(source, accepted[0], 'Entrance')
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as zipped:
        zipped.writestr('manifest.json', json.dumps(saved))
        link = zipfile.ZipInfo('model.onnx')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipped.writestr(link, '/etc/private-model')
    root = tmp_path / 'destination'
    with pytest.raises(lm.ModelError):
        lm.import_model(root, io.BytesIO(target.getvalue()))
    assert_unpublished(root)


@pytest.mark.parametrize('damage', ['not_zip', 'missing_model', 'missing_manifest',
                                    'oversized_manifest', 'oversized_model', 'encrypted'])
def test_import_rejects_broken_and_oversized_archives(tmp_path, accepted, damage):
    lm = models()
    source = tmp_path / 'source'
    saved = lm.save_model(source, accepted[0], 'Entrance')
    payload = accepted[3]
    data = archive(saved, payload)
    if damage == 'not_zip':
        data = b'not a zip archive'
    elif damage in ('missing_model', 'missing_manifest', 'oversized_manifest'):
        target = io.BytesIO()
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            if damage != 'missing_manifest':
                zipped.writestr('manifest.json', ' ' * 65537 if damage == 'oversized_manifest' else json.dumps(saved))
            if damage != 'missing_model':
                zipped.writestr('model.onnx', payload)
        data = target.getvalue()
    else:
        # Patch actual ZIP metadata to exercise pre-read limits/flags with tiny fixtures.
        data = bytearray(data)
        offset = 0
        while True:
            offset = data.find(b'PK\x01\x02', offset)
            if offset < 0:
                break
            name_len, extra_len, comment_len = struct.unpack_from('<HHH', data, offset + 28)
            name = bytes(data[offset + 46:offset + 46 + name_len])
            if name == b'model.onnx':
                if damage == 'oversized_model':
                    struct.pack_into('<I', data, offset + 24, 256 * 1024 * 1024 + 1)
                else:
                    flags = struct.unpack_from('<H', data, offset + 8)[0]
                    struct.pack_into('<H', data, offset + 8, flags | 1)
                    local = struct.unpack_from('<I', data, offset + 42)[0]
                    flags = struct.unpack_from('<H', data, local + 6)[0]
                    struct.pack_into('<H', data, local + 6, flags | 1)
                break
            offset += 46 + name_len + extra_len + comment_len
        data = bytes(data)
    root = tmp_path / 'destination'
    with pytest.raises(lm.ModelError):
        lm.import_model(root, io.BytesIO(data))
    assert_unpublished(root)


@pytest.mark.parametrize('field,value', [
    ('schema', 2), ('schema', True), ('kind', 'torch-checkpoint'), ('contract', 2),
    ('threshold', 0), ('threshold', 1.1), ('threshold', '0.75'), ('threshold', float('nan')),
    ('model_size', -1), ('model_size', True), ('model_sha256', '0' * 64),
    ('input_size', 64), ('name', ''), ('description', []),
    ('source_sha256', 'a' * 64), ('annotations', []),
])
def test_import_rejects_unsupported_manifest_fields_and_values(tmp_path, accepted, field, value):
    lm = models()
    source = tmp_path / 'source'
    manifest = lm.save_model(source, accepted[0], 'Entrance')
    manifest[field] = value
    root = tmp_path / 'destination'
    with pytest.raises(lm.ModelError):
        lm.import_model(root, io.BytesIO(archive(manifest, accepted[3])))
    assert_unpublished(root)


@pytest.mark.parametrize('damage', ['bytes', 'batch', 'channels', 'dynamic', 'rectangle',
                                   'large', 'input_type', 'outputs'])
def test_import_checks_real_onnx_contract_even_with_matching_hash(tmp_path, accepted, damage):
    lm = models()
    source = tmp_path / 'source'
    manifest = lm.save_model(source, accepted[0], 'Entrance')
    if damage == 'bytes':
        payload = b'not an ONNX model'
    elif damage == 'outputs':
        payload = onnx_bytes(bad_outputs=True)
    elif damage == 'input_type':
        from onnx import TensorProto
        payload = onnx_bytes(input_type=TensorProto.UINT8)
    else:
        shape = {
            'batch': (2, 3, 32, 32), 'channels': (1, 1, 32, 32),
            'dynamic': (1, 3, 'height', 'width'), 'rectangle': (1, 3, 32, 64),
            'large': (1, 3, 4096, 4096),
        }[damage]
        payload = onnx_bytes(shape=shape)
        if damage == 'large':
            manifest['input_size'] = 4096
    manifest['model_sha256'] = hashlib.sha256(payload).hexdigest()
    manifest['model_size'] = len(payload)
    root = tmp_path / 'destination'
    with pytest.raises(lm.ModelError):
        lm.import_model(root, io.BytesIO(archive(manifest, payload)))
    assert_unpublished(root)


def test_save_rejects_invalid_onnx_even_when_report_hash_matches(tmp_path, accepted):
    lm = models()
    job, report, model, payload = accepted
    model.write_bytes(b'not ONNX')
    report['learning']['model_sha256'] = hashlib.sha256(b'not ONNX').hexdigest()
    write_report(job, report)
    root = tmp_path / 'models'
    with pytest.raises(lm.ModelError):
        lm.save_model(root, job, 'Invalid')
    assert_unpublished(root)


@pytest.mark.parametrize('location', ['outside_learning', 'model_link', 'parent_link', 'report_link'])
def test_save_rejects_escaped_paths_and_symlinks(tmp_path, accepted, location):
    lm = models()
    job, report, model, payload = accepted
    if location == 'outside_learning':
        outside = tmp_path / 'outside.onnx'
        outside.write_bytes(payload)
        report['learning']['active']['model'] = str(outside)
        write_report(job, report)
    elif location == 'model_link':
        outside = tmp_path / 'outside.onnx'
        outside.write_bytes(payload)
        model.unlink()
        model.symlink_to(outside)
    elif location == 'parent_link':
        linked = job / 'learning' / 'linked'
        linked.symlink_to(model.parent, target_is_directory=True)
        report['learning']['active']['model'] = str(linked / 'model.onnx')
        write_report(job, report)
    else:
        outside = tmp_path / 'outside-report.json'
        (job / 'report.json').rename(outside)
        (job / 'report.json').symlink_to(outside)
    root = tmp_path / 'models'
    with pytest.raises(lm.ModelError):
        lm.save_model(root, job, 'Unsafe')
    assert_unpublished(root)


def test_snapshot_survives_model_and_original_job_deletion(tmp_path, accepted):
    lm = models()
    root = tmp_path / 'models'
    saved = lm.save_model(root, accepted[0], 'Entrance')
    job = tmp_path / 'new-video-job'
    job.mkdir()
    copied = lm.snapshot_model(root, saved['id'], job)
    assert copied['id'] == saved['id']
    assert {p.name for p in (job / 'plate_model').iterdir()} == {'model.onnx', 'manifest.json'}
    lm.delete_model(root, saved['id'])
    shutil.rmtree(accepted[0])
    assert lm.list_models(root) == []
    manifest, payload = lm.load_snapshot(job)
    assert manifest == copied and payload == accepted[3]
    # This invokes the actual CPU model; the snapshot is an independent artifact.
    import video_learning
    refiner = video_learning.CropRefiner(payload, providers=['CPUExecutionProvider'])
    mask, score = refiner.predict(np.zeros((20, 40, 3), np.uint8))
    assert mask is not None and mask.shape == (20, 40) and mask.any()
    assert score == pytest.approx(.95)


def test_snapshot_is_a_copy_and_cannot_be_overwritten(tmp_path, accepted):
    lm = models()
    root = tmp_path / 'models'
    first = lm.save_model(root, accepted[0], 'First')
    second = lm.save_model(root, accepted[0], 'Second')
    job = tmp_path / 'new-video-job'
    job.mkdir()
    lm.snapshot_model(root, first['id'], job)
    before = (job / 'plate_model' / 'manifest.json').read_bytes()
    with pytest.raises(lm.ModelError):
        lm.snapshot_model(root, second['id'], job)
    assert (job / 'plate_model' / 'manifest.json').read_bytes() == before
    (root / first['id'] / 'model.onnx').write_bytes(b'corrupt original')
    manifest, payload = lm.load_snapshot(job)
    assert manifest['name'] == 'First' and payload == accepted[3]


@pytest.mark.parametrize('damage', ['missing_model', 'corrupt_model', 'missing_manifest', 'corrupt_manifest', 'model_link'])
def test_snapshot_load_fails_clearly_for_missing_corrupt_or_linked_files(tmp_path, accepted, damage):
    lm = models()
    root = tmp_path / 'models'
    saved = lm.save_model(root, accepted[0], 'Entrance')
    job = tmp_path / 'new-video-job'
    job.mkdir()
    lm.snapshot_model(root, saved['id'], job)
    folder = job / 'plate_model'
    target = folder / ('manifest.json' if 'manifest' in damage else 'model.onnx')
    if damage.startswith('missing'):
        target.unlink()
    elif damage == 'model_link':
        target.unlink()
        target.symlink_to(accepted[2])
    else:
        target.write_bytes(b'corrupt')
    with pytest.raises(lm.ModelError):
        lm.load_snapshot(job)


@pytest.mark.parametrize('operation', ['export', 'snapshot', 'list'])
def test_corrupt_library_model_is_never_silently_usable(tmp_path, accepted, operation):
    lm = models()
    root = tmp_path / 'models'
    saved = lm.save_model(root, accepted[0], 'Entrance')
    (root / saved['id'] / 'model.onnx').write_bytes(b'corrupt')
    with pytest.raises(lm.ModelError):
        if operation == 'export':
            lm.export_model(root, saved['id'])
        elif operation == 'snapshot':
            job = tmp_path / 'another-job'
            job.mkdir()
            lm.snapshot_model(root, saved['id'], job)
        else:
            lm.list_models(root)


@pytest.mark.parametrize('model_id', ['../outside', '/absolute', '', 'g' * 32, 'a' * 31])
def test_model_identifiers_cannot_escape_the_library(tmp_path, model_id):
    lm = models()
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'keep.txt'
    sentinel.write_text('keep')
    root = tmp_path / 'models'
    root.mkdir()
    for operation in (lm.export_model, lm.delete_model):
        with pytest.raises(lm.ModelError):
            operation(root, model_id)
    assert sentinel.read_text() == 'keep'


def test_library_directory_symlink_is_rejected_without_touching_target(tmp_path, accepted):
    lm = models()
    root = tmp_path / 'models'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'keep.txt').write_text('keep')
    model_id = 'a' * 32
    (root / model_id).symlink_to(outside, target_is_directory=True)
    with pytest.raises(lm.ModelError):
        lm.export_model(root, model_id)
    with pytest.raises(lm.ModelError):
        lm.delete_model(root, model_id)
    assert (outside / 'keep.txt').read_text() == 'keep'


def test_missing_library_is_empty_but_missing_model_and_snapshot_fail(tmp_path):
    lm = models()
    root = tmp_path / 'not-created'
    assert lm.list_models(root) == []
    with pytest.raises(lm.ModelError):
        lm.export_model(root, 'a' * 32)
    with pytest.raises(lm.ModelError):
        lm.load_snapshot(tmp_path / 'unconfigured-job')
