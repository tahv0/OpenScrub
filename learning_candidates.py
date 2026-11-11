"""Discover and assess retained training artifacts without activating masks.

Candidate identities name exact server-owned training versions. Listing reads
small metadata only; actions recheck artifact hashes and path confinement.
Secondary and mask assessments remain independent, and never edit job reports.
"""
from datetime import datetime, timezone
import functools
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

import learned_models as models


_PASS = re.compile(r'pass-[0-9a-f]{12}')
_VERSION = re.compile(r'v[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}')
_HASH = re.compile(r'[0-9a-f]{64}')
_ASSESSMENT = 'secondary_assessment.json'
_MASK_ASSESSMENT = 'mask_assessment.json'
_DATASET_MANIFEST_LIMIT = 16 * 1024 * 1024


def _action(function):
    @functools.wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (models.ModelError, InterruptedError):
            raise
        except OSError as error:
            raise models.ModelError('Candidate files are missing, unreadable, or could not be saved') from error
        except (ValueError, TypeError, KeyError) as error:
            raise models.ModelError('Invalid candidate metadata: ' + str(error)) from error
    return guarded


def _parts(candidate_id):
    if not isinstance(candidate_id, str) or candidate_id.count(':') != 1:
        raise models.ModelError('Invalid candidate identifier')
    pass_id, version = candidate_id.split(':')
    if not _PASS.fullmatch(pass_id) or not _VERSION.fullmatch(version):
        raise models.ModelError('Invalid candidate identifier')
    return pass_id, version


def _cancel(cancelled):
    if cancelled and cancelled():
        raise InterruptedError('Candidate check cancelled; previous review retained')


def _hash_file(path, limit=None, cancelled=None):
    path = models._no_links(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise models.ModelError('Expected a regular candidate file')
        if limit is not None and info.st_size > limit:
            raise models.ModelError('Candidate file exceeds its size limit')
        digest = hashlib.sha256()
        total = 0
        while True:
            _cancel(cancelled)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            total += len(chunk)
            if limit is not None and total > limit:
                raise models.ModelError('Candidate file exceeds its size limit')
            digest.update(chunk)


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise models.ModelError('Invalid candidate creation time')
    timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise models.ModelError('Candidate creation time needs a time zone')
    return value


def _metadata(job_dir, candidate_id):
    pass_id, version = _parts(candidate_id)
    job = models._directory(job_dir)
    stage = models._directory(job / 'learning' / 'passes' / pass_id)
    folder = models._directory(stage / 'versions' / version)
    meta = models._json(models._read_file(folder / 'manifest.json', models._MANIFEST_LIMIT))
    if (not isinstance(meta, dict) or type(meta.get('schema')) is not int or meta['schema'] != 1
            or meta.get('status') != 'candidate' or meta.get('version') != version):
        raise models.ModelError('Invalid retained candidate version metadata')
    artifacts = meta.get('artifacts')
    if (not isinstance(artifacts, dict) or set(artifacts) != {'model.onnx', 'weights.pt'}
            or any(not isinstance(digest, str) or not _HASH.fullmatch(digest)
                   for digest in artifacts.values())):
        raise models.ModelError('Candidate artifact hashes are missing or invalid')
    for name in artifacts:
        path = models._no_links(folder / name)
        if not stat.S_ISREG(path.stat().st_mode):
            raise models.ModelError('Candidate artifacts must be regular files')
    return {
        'id': candidate_id, 'version': version, 'created_at': _timestamp(meta.get('created_utc')),
        'model_sha256': artifacts['model.onnx'], 'artifacts': dict(artifacts),
        'folder': folder, 'model_path': folder / 'model.onnx',
        'dataset': models._no_links(stage / 'dataset'),
    }


def _bound_record(candidate, filename):
    """A stale/corrupt optional result cannot confer evaluation or acceptance."""
    path = candidate['folder'] / filename
    if not os.path.lexists(path):
        return None
    try:
        record = models._json(models._read_file(path, models._MANIFEST_LIMIT))
        if (not isinstance(record, dict) or type(record.get('schema')) is not int
                or record['schema'] != 1 or record.get('candidate_id') != candidate['id']
                or record.get('model_sha256') != candidate['model_sha256']):
            return None
        return record
    except (OSError, ValueError, TypeError):
        return None


def _assessments(candidate):
    candidate['assessment'] = None
    record = _bound_record(candidate, _ASSESSMENT)
    if record is not None:
        try:
            from plate_verifier import validate_assessment
            if (set(record) != {'schema', 'candidate_id', 'model_sha256', 'dataset_sha256',
                                'evaluated_at', 'assessment'}
                    or not isinstance(record['dataset_sha256'], str)
                    or not _HASH.fullmatch(record['dataset_sha256'])):
                raise ValueError('Invalid assessment binding')
            _timestamp(record['evaluated_at'])
            candidate['assessment'] = validate_assessment(record['assessment'])
        except (ValueError, TypeError, KeyError):
            pass
    candidate['mask_assessment'] = None
    record = _bound_record(candidate, _MASK_ASSESSMENT)
    if record is not None:
        try:
            if set(record) != {'schema', 'candidate_id', 'model_sha256', 'assessment'}:
                raise ValueError('Invalid mask assessment binding')
            result = record['assessment']
            if (not isinstance(result, dict) or set(result) != {'status', 'message'}
                    or result['status'] not in ('passed', 'failed')):
                raise ValueError('Invalid mask assessment')
            message = models._text(result['message'], 'Mask assessment message', 2000)
            candidate['mask_assessment'] = {'status': result['status'], 'message': message}
        except (ValueError, TypeError, KeyError):
            pass
    return candidate


def _descriptor(candidate):
    return {key: candidate[key] for key in ('id', 'version', 'created_at', 'model_sha256',
                                           'assessment', 'mask_assessment')}


@_action
def list_candidates(job_dir):
    """List complete version metadata, without hashing/loading model files."""
    job = models._directory(job_dir)
    passes = models._no_links(job / 'learning' / 'passes')
    if not passes.exists():
        return []
    passes = models._directory(passes)
    found = []
    for stage in sorted(passes.iterdir(), key=lambda item: item.name):
        if not _PASS.fullmatch(stage.name):
            continue
        try:
            versions = models._directory(stage / 'versions')
        except (OSError, ValueError):
            continue
        for folder in sorted(versions.iterdir(), key=lambda item: item.name):
            if not _VERSION.fullmatch(folder.name):
                continue
            try:
                candidate = _metadata(job, stage.name + ':' + folder.name)
                found.append(_descriptor(_assessments(candidate)))
            except (OSError, ValueError, TypeError, KeyError):
                continue  # Incomplete/invalid versions are never offered as usable.
    return sorted(found, key=lambda item: (item['created_at'], item['id']), reverse=True)


@_action
def load_candidate(job_dir, candidate_id):
    candidate = _metadata(job_dir, candidate_id)
    for name, expected in candidate['artifacts'].items():
        limit = models.MAX_MODEL_BYTES if name == 'model.onnx' else None
        if _hash_file(candidate['folder'] / name, limit) != expected:
            raise models.ModelError('Candidate artifact hash differs; file is missing or modified')
    return _assessments(candidate)


def _dataset_fingerprint(dataset, cancelled=None):
    dataset = models._directory(dataset)
    payload = models._read_file(dataset / 'manifest.jsonl', _DATASET_MANIFEST_LIMIT)
    digest = hashlib.sha256(payload)
    paths = set()
    for line in payload.decode('utf-8').splitlines():
        _cancel(cancelled)
        if not line.strip():
            continue
        row = models._json(line.encode('utf-8'))
        if not isinstance(row, dict) or row.get('split') not in ('train', 'val'):
            raise models.ModelError('Candidate dataset has an invalid split')
        if row.get('label') not in ('positive', 'negative'):
            raise models.ModelError('Candidate dataset has an invalid label')
        relative = row.get('image')
        if not isinstance(relative, str) or '\\' in relative:
            raise models.ModelError('Candidate dataset has an invalid image path')
        parts = PurePosixPath(relative).parts
        if (len(parts) != 3 or parts[:2] != ('images', row['split'])
                or any(part in ('.', '..') for part in parts)
                or PurePosixPath(relative).suffix.lower() not in ('.png', '.jpg', '.jpeg')):
            raise models.ModelError('Candidate image escapes its dataset split')
        paths.add(relative)
        paths.add('labels/%s/%s.txt' % (row['split'], PurePosixPath(relative).stem))
    for relative in sorted(paths):
        _cancel(cancelled)
        digest.update(relative.encode('utf-8'))
        digest.update(_hash_file(dataset / relative, models.MAX_MODEL_BYTES, cancelled).encode('ascii'))
    return digest.hexdigest()


@_action
def evaluate(job_dir, candidate_id, cancelled=None, progress=None):
    import plate_verifier
    import video_learning

    _cancel(cancelled)
    candidate = load_candidate(job_dir, candidate_id)
    dataset_sha = _dataset_fingerprint(candidate['dataset'], cancelled)
    payload = models._read_file(candidate['model_path'], models.MAX_MODEL_BYTES)
    if hashlib.sha256(payload).hexdigest() != candidate['model_sha256']:
        raise models.ModelError('Candidate model changed before its assessment')
    models._validate_onnx(payload)
    _cancel(cancelled)
    model = video_learning.CropRefiner(payload, providers=['CPUExecutionProvider'])
    assessment = plate_verifier.validate_assessment(plate_verifier.assess(
        model, candidate['dataset'], cancelled=cancelled, progress=progress))
    _cancel(cancelled)
    latest = load_candidate(job_dir, candidate_id)
    if (latest['model_sha256'] != candidate['model_sha256']
            or _dataset_fingerprint(candidate['dataset'], cancelled) != dataset_sha):
        raise models.ModelError('Candidate model or dataset changed during evaluation')
    models._atomic_json(candidate['folder'] / _ASSESSMENT, {
        'schema': 1, 'candidate_id': candidate_id,
        'model_sha256': candidate['model_sha256'], 'dataset_sha256': dataset_sha,
        'evaluated_at': datetime.now(timezone.utc).isoformat(), 'assessment': assessment,
    })
    return assessment


@_action
def record_mask_assessment(job_dir, folder, status, message):
    if status not in ('passed', 'failed'):
        raise models.ModelError('Unknown mask assessment status')
    message = models._text(message, 'Mask assessment message', 2000)
    job = models._directory(job_dir)
    folder = models._directory(folder)
    try:
        parts = folder.relative_to(job / 'learning' / 'passes').parts
    except ValueError as error:
        raise models.ModelError('Mask assessment folder is outside this job') from error
    if len(parts) != 3 or parts[1] != 'versions':
        raise models.ModelError('Mask assessment must name an exact candidate version')
    candidate_id = parts[0] + ':' + parts[2]
    candidate = load_candidate(job, candidate_id)
    assessment = {'status': status, 'message': message}
    models._atomic_json(folder / _MASK_ASSESSMENT, {
        'schema': 1, 'candidate_id': candidate_id, 'model_sha256': candidate['model_sha256'],
        'assessment': assessment,
    })
    return assessment
