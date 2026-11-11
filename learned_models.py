"""Portable, explicitly selected plate-mask refiners.

Only the accepted artifact named by a job's committed report may be saved.
Portable archives contain an ONNX graph and a small, whitelisted manifest;
calibration metadata describes the original training checks, not new videos.
"""
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone
import functools
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import threading
import unicodedata
import uuid
import zipfile

import numpy as np


class ModelError(ValueError):
    """A model, manifest, archive, or snapshot is unavailable or invalid."""


_MANIFEST_LIMIT = 64 * 1024
MAX_MODEL_BYTES = 256 * 1024 * 1024
_MODEL_LIMIT = MAX_MODEL_BYTES
_ARCHIVE_LIMIT = MAX_MODEL_BYTES + 1024 * 1024
_FIELDS = {
    'schema', 'kind', 'contract', 'id', 'name', 'description', 'created_at',
    'model_sha256', 'model_size', 'input_size', 'threshold', 'validation',
}
_VALIDATION_FIELDS = {
    'threshold', 'held_out_positive', 'accepted', 'excess_pixels_removed',
    'minimum_known_coverage',
}
_KIND = 'openscrub-plate-mask-refiner'
_ID = re.compile(r'[0-9a-f]{32}')
_HASH = re.compile(r'[0-9a-f]{64}')
# Only successful validation metadata lives here, never model bytes or sessions.
_VALIDATED_ONNX = OrderedDict()
_VALIDATION_CACHE_LIMIT = 16
_VALIDATION_CACHE_LOCK = threading.Lock()


def _boundary(function):
    """Keep failures actionable without leaking low-level runtime exceptions."""
    @functools.wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ModelError:
            raise
        except OSError as error:
            raise ModelError('Model files are missing, unreadable, or could not be saved') from error
        except Exception as error:
            raise ModelError('Model operation failed: ' + str(error)) from error
    return guarded


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ModelError('Invalid model identifier')
    return value


def _text(value, label, maximum, required=False):
    if not isinstance(value, str):
        raise ModelError(label + ' must be text')
    if len(value) > maximum or any(unicodedata.category(c) == 'Cc' for c in value):
        raise ModelError(label + ' is too long or contains control characters')
    if required and not value.strip():
        raise ModelError(label + ' must not be empty')
    return value.strip() if required else value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ModelError(label + ' must be a finite number')
    return value


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ModelError(label + ' is outside its supported integer range')
    return value


def _threshold(value):
    value = _number(value, 'Model threshold')
    if not 0 < value <= 1:
        raise ModelError('Model threshold must be in (0, 1]')
    return value


def _validation(value, allow_warning=False):
    if not isinstance(value, dict):
        raise ModelError('Accepted calibration validation is missing')
    optional = {'margin_fraction'}
    if allow_warning:
        # Reports may have explanatory text, but calibrated geometry must travel
        # with the model so inference does not silently drop its outward margin.
        value = {key: value[key] for key in _VALIDATION_FIELDS | optional if key in value}
    if not _VALIDATION_FIELDS <= set(value) or set(value) - (_VALIDATION_FIELDS | optional):
        raise ModelError('Unsupported calibration validation fields')
    result = dict(value)
    result['threshold'] = _threshold(result['threshold'])
    if 'margin_fraction' in result:
        margin = _number(result['margin_fraction'], 'Calibrated mask margin')
        if not 0 <= margin <= .05:
            raise ModelError('Calibrated mask margin must be between 0 and 0.05')
    held_out = _integer(result['held_out_positive'], 'Held-out positive count', 4, 2**53)
    _integer(result['accepted'], 'Accepted positive count', 1, held_out)
    _integer(result['excess_pixels_removed'], 'Removed excess pixels', 1, 2**53)
    coverage = _number(result['minimum_known_coverage'], 'Minimum known coverage')
    if not .995 <= coverage <= 1:
        raise ModelError('Calibration did not meet minimum known plate coverage')
    return result


def _manifest(value):
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ModelError('Unsupported model manifest fields')
    if type(value['schema']) is not int or value['schema'] != 1:
        raise ModelError('Unsupported model manifest schema')
    if type(value['contract']) is not int or value['contract'] != 1 or value['kind'] != _KIND:
        raise ModelError('Unsupported plate-mask model contract or kind')
    _identifier(value['id'])
    _text(value['name'], 'Model name', 80, required=True)
    _text(value['description'], 'Model description', 500)
    created = value['created_at']
    if not isinstance(created, str) or len(created) > 64:
        raise ModelError('Invalid model creation time')
    try:
        timestamp = datetime.fromisoformat(created.replace('Z', '+00:00'))
    except ValueError as error:
        raise ModelError('Invalid model creation time') from error
    if timestamp.tzinfo is None:
        raise ModelError('Model creation time must include a time zone')
    if not isinstance(value['model_sha256'], str) or not _HASH.fullmatch(value['model_sha256']):
        raise ModelError('Invalid model SHA-256')
    _integer(value['model_size'], 'Model size', 1, _MODEL_LIMIT)
    _integer(value['input_size'], 'Model input size', 1, 2048)
    _threshold(value['threshold'])
    checked = _validation(value['validation'])
    if value['threshold'] != checked['threshold']:
        raise ModelError('Model and calibration thresholds do not agree')
    # JSON round trip provides a detached nested object to every caller.
    return json.loads(json.dumps(value, allow_nan=False))


def _absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def _no_links(path):
    """Check every existing path component before following any filesystem path."""
    path = _absolute(path)
    for component in reversed((path, *path.parents)):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ModelError('Symbolic links are not permitted for model files')
    return path


def _directory(path, create=False):
    path = _no_links(path)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        _no_links(path)
    if not path.is_dir():
        raise ModelError('A required model directory is missing or is not a directory')
    return path


def _read_file(path, limit):
    path = _no_links(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ModelError('Expected a regular model file')
        if metadata.st_size > limit:
            raise ModelError('Model file exceeds its size limit')
        return _read_stream(stream, limit)


def _read_stream(stream, limit):
    chunks = []
    total = 0
    while True:
        chunk = stream.read(min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ModelError('Model archive entry exceeds its size limit')
        chunks.append(chunk)
    return b''.join(chunks)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelError('Duplicate JSON manifest key: ' + key)
        result[key] = value
    return result


def _json(payload):
    return json.loads(payload.decode('utf-8'), object_pairs_hook=_object_pairs)


def _validate_onnx(payload):
    """Reuse only successful digest metadata; changed bytes always get checked."""
    digest = hashlib.sha256(payload).hexdigest()
    with _VALIDATION_CACHE_LOCK:
        cached = _VALIDATED_ONNX.get(digest)
        if cached is not None:
            _VALIDATED_ONNX.move_to_end(digest)
            return cached
    size = _validate_onnx_uncached(payload)
    with _VALIDATION_CACHE_LOCK:
        _VALIDATED_ONNX[digest] = size
        _VALIDATED_ONNX.move_to_end(digest)
        while len(_VALIDATED_ONNX) > _VALIDATION_CACHE_LIMIT:
            _VALIDATED_ONNX.popitem(last=False)
    return size


def _validate_onnx_uncached(payload):
    """Validate real inference from bytes; external ONNX data cannot read a path."""
    import onnxruntime as ort
    from video_learning import decode_segment

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.log_severity_level = 3
    try:
        session = ort.InferenceSession(payload, sess_options=options,
                                       providers=['CPUExecutionProvider'])
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].type != 'tensor(float)':
            raise ModelError('Expected one float32 RGB segmentation input')
        dimensions = inputs[0].shape
        if (len(dimensions) != 4 or dimensions[0] != 1 or dimensions[1] != 3
                or type(dimensions[2]) is not int or dimensions[2] != dimensions[3]
                or not 0 < dimensions[2] <= 2048):
            raise ModelError('Expected fixed batch-one RGB input with square size at most 2048')
        size = dimensions[2]
        outputs = session.run(None, {inputs[0].name: np.zeros((1, 3, size, size), np.float32)})
        if (len(outputs) != 2 or sorted(array.ndim for array in outputs) != [3, 4]
                or any(not all(array.shape) or not np.issubdtype(array.dtype, np.floating)
                       for array in outputs)):
            raise ModelError('Unsupported segmentation output layout')
        mask, score = decode_segment(outputs, (size, size, 3), size, 1., 0, 0)
        if not math.isfinite(score) or (mask is not None and mask.shape != (size, size)):
            raise ModelError('Invalid segmentation prediction')
        return size
    except ModelError:
        raise
    except Exception as error:
        raise ModelError('Invalid or unsupported ONNX segmentation model') from error


def _verify(manifest, payload):
    manifest = _manifest(manifest)
    if len(payload) != manifest['model_size']:
        raise ModelError('Model byte size does not agree with the manifest')
    if hashlib.sha256(payload).hexdigest() != manifest['model_sha256']:
        raise ModelError('Model SHA-256 does not agree with the manifest')
    if _validate_onnx(payload) != manifest['input_size']:
        raise ModelError('ONNX input size does not agree with the manifest')
    return manifest


def _load_directory(folder):
    folder = _directory(folder)
    if {path.name for path in folder.iterdir()} != {'manifest.json', 'model.onnx'}:
        raise ModelError('Model directory must contain exactly manifest.json and model.onnx')
    manifest = _json(_read_file(folder / 'manifest.json', _MANIFEST_LIMIT))
    payload = _read_file(folder / 'model.onnx', _MODEL_LIMIT)
    return _verify(manifest, payload), payload


def _write_file(path, payload):
    with open(path, 'xb') as stream:
        os.chmod(path, 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _publish(parent, name, manifest, payload):
    """Publish both files together; unsuccessful publication leaves no partial copy."""
    parent = _directory(parent, create=True)
    target = parent / name
    if target.exists() or target.is_symlink():
        raise ModelError('A model snapshot or library entry already exists')
    pending = Path(tempfile.mkdtemp(prefix='.model-pending-', dir=parent))
    try:
        encoded = json.dumps(manifest, ensure_ascii=False, allow_nan=False,
                             separators=(',', ':')).encode('utf-8')
        if len(encoded) > _MANIFEST_LIMIT:
            raise ModelError('Model manifest exceeds its size limit')
        _write_file(pending / 'model.onnx', payload)
        _write_file(pending / 'manifest.json', encoded)
        # Existing published directories are nonempty, so rename cannot replace them.
        # The second check also prevents replacing an existing empty snapshot.
        if target.exists() or target.is_symlink():
            raise ModelError('A model snapshot or library entry already exists')
        os.rename(pending, target)
    finally:
        if pending.exists():
            shutil.rmtree(pending)


@_boundary
def list_models(root):
    root = _no_links(root)
    if not root.exists():
        return []
    root = _directory(root)
    results = []
    for folder in sorted(root.iterdir(), key=lambda path: path.name):
        # Concurrent atomic publications are deliberately invisible until complete.
        if folder.name.startswith('.model-pending-'):
            continue
        _identifier(folder.name)
        manifest, _ = _load_directory(folder)
        if manifest['id'] != folder.name:
            raise ModelError('Model directory and manifest identifiers differ')
        results.append(manifest)
    return results


@_boundary
def save_model(root, job_dir, name, description=''):
    name = _text(name, 'Model name', 80, required=True)
    description = _text(description, 'Model description', 500)
    job = _directory(job_dir)
    # The committed report is authoritative. Never infer acceptance from files,
    # modification times, active.json, or the presence of a training checkpoint.
    report = _json(_read_file(job / 'report.json', _MODEL_LIMIT))
    learning = report.get('learning')
    if not isinstance(learning, dict):
        raise ModelError('The job has no accepted learned model')
    active = learning.get('active')
    if not isinstance(active, dict) or not isinstance(active.get('model'), str):
        raise ModelError('The job report does not name an accepted model')
    validation = _validation(learning.get('validation'), allow_warning=True)
    raw_path = Path(active['model'])
    model_path = _absolute(raw_path if raw_path.is_absolute() else job / raw_path)
    learning_dir = _directory(job / 'learning')
    try:
        model_path.relative_to(learning_dir)
    except ValueError as error:
        raise ModelError('Accepted model must be inside the job learning directory') from error
    if model_path.suffix.lower() != '.onnx':
        raise ModelError('Accepted model must be an ONNX artifact')
    payload = _read_file(model_path, _MODEL_LIMIT)
    digest = hashlib.sha256(payload).hexdigest()
    if learning.get('model_sha256') != digest:
        raise ModelError('Accepted report model hash does not agree with the artifact')
    size = _validate_onnx(payload)
    manifest = _manifest({
        'schema': 1, 'kind': _KIND, 'contract': 1, 'id': uuid.uuid4().hex,
        'name': name, 'description': description,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'model_sha256': digest, 'model_size': len(payload), 'input_size': size,
        'threshold': validation['threshold'], 'validation': validation,
    })
    _publish(root, manifest['id'], manifest, payload)
    return manifest


class _SeekableArchiveReader:
    """Supply ZipFile's seekable interface for Python 3.10 uploaded temp files."""
    def __init__(self, source):
        self._source = source

    def read(self, size=-1):
        return self._source.read(size)

    def seek(self, offset, whence=os.SEEK_SET):
        return self._source.seek(offset, whence)

    def tell(self):
        return self._source.tell()

    def seekable(self):
        return True


def _check_archive_stream(stream):
    # Bound the archive itself before ZipFile reads its central directory.
    stream.seek(0, os.SEEK_END)
    length = stream.tell()
    if length > _ARCHIVE_LIMIT:
        raise ModelError('Model archive exceeds its size limit')
    stream.seek(0)
    return _SeekableArchiveReader(stream)


@contextmanager
def _archive_source(archive):
    if isinstance(archive, (str, bytes, os.PathLike)):
        path = _no_links(archive)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                             | getattr(os, 'O_BINARY', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ModelError('Model archive must be a regular file')
            yield _check_archive_stream(stream)
    else:
        if not all(callable(getattr(archive, method, None)) for method in ('read', 'seek', 'tell')):
            raise ModelError('Model archive must be a seekable binary stream')
        seekable = getattr(archive, 'seekable', None)
        if callable(seekable) and not seekable():
            raise ModelError('Model archive must be a seekable binary stream')
        yield _check_archive_stream(archive)


@_boundary
def import_model(root, archive, name=None):
    if name is not None:
        name = _text(name, 'Model name', 80, required=True)
    with _archive_source(archive) as source:
        with zipfile.ZipFile(source, 'r') as zipped:
            entries = zipped.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != 2 or set(names) != {'manifest.json', 'model.onnx'}:
                raise ModelError('Model archive must contain exactly manifest.json and model.onnx')
            by_name = {entry.filename: entry for entry in entries}
            for entry in entries:
                limit = _MANIFEST_LIMIT if entry.filename == 'manifest.json' else _MODEL_LIMIT
                mode = entry.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if (entry.is_dir() or file_type not in (0, stat.S_IFREG)
                        or entry.flag_bits & 1):
                    raise ModelError('Archive links, special files, and encrypted entries are not supported')
                if not 0 < entry.file_size <= limit:
                    raise ModelError('Model archive entry exceeds its size limit or is empty')
            with zipped.open(by_name['manifest.json']) as stream:
                manifest = _json(_read_stream(stream, _MANIFEST_LIMIT))
            # Reject unsupported metadata before spending time loading an ONNX graph.
            _manifest(manifest)
            with zipped.open(by_name['model.onnx']) as stream:
                payload = _read_stream(stream, _MODEL_LIMIT)
    manifest = _verify(manifest, payload)
    manifest['id'] = uuid.uuid4().hex
    if name is not None:
        manifest['name'] = name
    _publish(root, manifest['id'], manifest, payload)
    return manifest


@_boundary
def export_model(root, model_id):
    model_id = _identifier(model_id)
    root = _directory(root)
    manifest, payload = _load_directory(root / model_id)
    if manifest['id'] != model_id:
        raise ModelError('Model directory and manifest identifiers differ')
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False,
                                                   allow_nan=False).encode('utf-8'))
        zipped.writestr('model.onnx', payload)
    return target.getvalue()


@_boundary
def delete_model(root, model_id):
    model_id = _identifier(model_id)
    root = _directory(root)
    folder = _directory(root / model_id)
    # A damaged artifact can still be deliberately deleted, but links are rejected.
    for path in folder.rglob('*'):
        _no_links(path)
    shutil.rmtree(folder)


@_boundary
def snapshot_model(root, model_id, job_dir):
    model_id = _identifier(model_id)
    root = _directory(root)
    manifest, payload = _load_directory(root / model_id)
    if manifest['id'] != model_id:
        raise ModelError('Model directory and manifest identifiers differ')
    _publish(job_dir, 'plate_model', manifest, payload)
    return manifest


@_boundary
def load_snapshot(job_dir):
    job = _directory(job_dir)
    return _load_directory(job / 'plate_model')
