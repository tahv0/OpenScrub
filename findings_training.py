"""Explicit named verifier training from durable, revision-frozen human examples.

Portable model folders remain ONNX + manifest only. Locally produced checkpoint
and corpus lineage live beside the model library, never in exported packages.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import unicodedata
import uuid

import cv2
import numpy as np

import learned_models as models
import learning_candidates as candidates
import learning_session as session


def default_name(video_names, now=None):
    names = sorted({str(name).strip() for name in video_names if str(name).strip()})
    title = names[0] if len(names) == 1 else 'Confirmed findings'
    title = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in title)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    suffix = moment.astimezone(timezone.utc).strftime(' — %Y-%m-%d %H:%M:%S UTC')
    return title[:80-len(suffix)].rstrip() + suffix


def _lineage_root(model_root):
    return models._no_links(Path(model_root).parent / 'learned_model_training')


def _local_metadata(model_root, model_id):
    model_id = models._identifier(model_id)
    manifest = models._manifest(models._json(models._read_file(
        Path(model_root) / model_id / 'manifest.json', models._MANIFEST_LIMIT)))
    folder = _lineage_root(model_root) / model_id
    if not folder.exists():
        raise models.ModelError('This model has no trusted local training checkpoint. Choose the configured base checkpoint or a locally trained model; imported ONNX models are inference-only.')
    folder = models._directory(folder)
    info = models._json(models._read_file(folder / 'training.json', models._MANIFEST_LIMIT))
    if (not isinstance(info, dict) or info.get('schema') != 1 or info.get('model_id') != model_id or manifest['id'] != model_id
            or info.get('model_sha256') != manifest['model_sha256']
            or type(info.get('example_count')) is not int or info['example_count'] < 1
            or type(info.get('checkpoint_size')) is not int or info['checkpoint_size'] < 1
            or type(info.get('lineage_size')) is not int or info['lineage_size'] < 1
            or not isinstance(info.get('lineage_sha256'), str)
            or not models._HASH.fullmatch(info['lineage_sha256'])):
        raise models.ModelError('Invalid local training checkpoint metadata')
    for name, size in (('weights.pt', info['checkpoint_size']), ('lineage.json', info['lineage_size'])):
        path = models._no_links(folder / name)
        if not path.is_file() or path.stat().st_size != size:
            raise models.ModelError('The local training checkpoint or frozen corpus is missing or modified')
    return folder, info


def resolve_parent(model_root, model_id=None):
    """Resolve only configured trusted weights or hash-bound local training data."""
    if model_id is None:
        weights = os.environ.get('OPENSCRUB_TRAIN_WEIGHTS', '')
        if not weights or not models._no_links(weights).is_file() or Path(weights).suffix != '.pt':
            raise models.ModelError('Configure a trusted local .pt base checkpoint before training')
        return {'weights': str(models._no_links(weights)), 'lineage': None, 'folder': None,
                'parent_model_id': None}
    model_id = models._identifier(model_id)
    manifest, _ = models._load_directory(Path(model_root) / model_id)
    folder, summary = _local_metadata(model_root, model_id)
    try:
        payload = models._read_file(folder / 'lineage.json', 32 * 1024 * 1024)
        if hashlib.sha256(payload).hexdigest() != summary['lineage_sha256']:
            raise ValueError('lineage hash mismatch')
        lineage = models._json(payload)
        if (not isinstance(lineage, dict) or lineage.get('schema') != 1 or lineage.get('model_id') != model_id
                or lineage.get('model_sha256') != manifest['model_sha256']
                or not isinstance(lineage.get('samples'), dict)
                or not isinstance(lineage.get('training_groups'), list)
                or any(not isinstance(g, str) for g in lineage['training_groups'])):
            raise ValueError('invalid lineage binding')
        weights = models._no_links(folder / 'weights.pt')
        if candidates._hash_file(weights) != lineage['checkpoint_sha256']:
            raise ValueError('checkpoint hash mismatch')
        for sid, sample in lineage['samples'].items():
            if not isinstance(sid, str) or not models._HASH.fullmatch(sid):
                raise ValueError('invalid frozen example identity')
            image = Path(sample['image'])
            if image.is_absolute() or len(image.parts) != 2 or image.parts[0] != 'images':
                raise ValueError('invalid corpus image')
            if candidates._hash_file(folder / image) != sample['image_sha256']:
                raise ValueError('corpus image hash mismatch')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise models.ModelError('The local training checkpoint or frozen corpus cannot be verified: ' + str(error)) from error
    return {'weights': str(weights), 'lineage': lineage, 'folder': folder,
            'parent_model_id': model_id}


def training_corpus_summary(model_root, model_id):
    """Read-only counts for a locally retained parent, without opening images.

    A model is eligible only if its detached lineage receipt is bound to the
    published model manifest. Full checkpoint/image integrity is deliberately
    checked at training time by resolve_parent; this view is NOT a claim that
    unreviewed tracker predictions are trusted or that all files were rehashed.
    """
    folder, info = _local_metadata(model_root, model_id)
    payload = models._read_file(folder / 'lineage.json', 32 * 1024 * 1024)
    if hashlib.sha256(payload).hexdigest() != info['lineage_sha256']:
        raise models.ModelError('The saved model training lineage changed')
    lineage = models._json(payload)
    samples = lineage.get('samples') if isinstance(lineage, dict) else None
    if (not isinstance(lineage, dict) or lineage.get('schema') != 1
            or lineage.get('model_id') != model_id
            or lineage.get('model_sha256') != info['model_sha256']
            or not isinstance(samples, dict)
            or len(samples) != info['example_count']):
        raise models.ModelError('Invalid saved model training corpus metadata')
    counts = {'positive': 0, 'negative': 0}
    confirmed_quads = 0
    videos = set()
    for sid, sample in samples.items():
        if (not isinstance(sid, str) or not models._HASH.fullmatch(sid)
                or not isinstance(sample, dict)
                or not isinstance(sample.get('label'), str)
                or sample.get('label') not in counts):
            raise models.ModelError('Invalid saved model training example metadata')
        source = sample.get('source')
        if not isinstance(source, dict) or not isinstance(source.get('video_id'), str):
            raise models.ModelError('Invalid saved model training example provenance')
        counts[sample['label']] += 1
        confirmed_quads += int(sample.get('label') == 'positive' and
                               sample.get('quality') == 'human_quad')
        videos.add(source['video_id'])
    return {
        'model_id': model_id,
        'total': len(samples),
        'positive': counts['positive'],
        'negative': counts['negative'],
        'human_quads': confirmed_quads,
        'source_videos': len(videos),
        'parent_model_id': lineage.get('parent_model_id'),
        'status': 'retained_snapshot',
    }


def training_info(model_root, model_id):
    try:
        _, info = _local_metadata(model_root, model_id)
        return {'trainable': True, 'reason': 'Local checkpoint available; integrity is checked before training',
                'parent_model_id': info.get('parent_model_id'),
                'example_count': info['example_count']}
    except (OSError, ValueError) as error:
        return {'trainable': False, 'reason': str(error)}


def _geometry(record):
    crop = record['crop']; box = np.asarray(crop['box'], dtype=float)
    scale = np.array([crop['scale_x'], crop['scale_y']], dtype=float)
    size = np.array([crop['width'], crop['height']], dtype=float)
    baseline = np.asarray(record['box'], dtype=float)
    if (box.shape != (4,) or baseline.shape != (4,) or not np.isfinite(box).all()
            or not np.isfinite(baseline).all() or not np.isfinite(scale).all()
            or (scale <= 0).any() or not np.isfinite(size).all() or (size <= 0).any()):
        raise models.ModelError('Invalid confirmed crop coordinate transform')
    # Use a single direct crop-span division. The former
    # (point - origin) / scale / image_size could round a valid right/bottom
    # crop edge to 1.0000000000000002 and break held-out evaluation.
    crop_span = box[2:] - box[:2]
    if (crop_span <= 0).any():
        raise models.ModelError('Invalid confirmed crop coordinate transform')
    baseline = ((baseline.reshape(2, 2) - box[:2]) / crop_span).reshape(-1)
    # Do not silently accept genuinely outside-crop detector proposals.
    if ((baseline < -1e-6).any() or (baseline > 1.000001).any() or
            baseline[2] <= baseline[0] or baseline[3] <= baseline[1]):
        raise models.ModelError('Confirmed plate geometry falls outside its stored crop')
    baseline = np.clip(baseline, 0, 1)
    points = record.get('points') if record.get('shape_confirmed') else None
    quality = 'human_quad' if points is not None else 'human_region'
    if points is None:
        x1, y1, x2, y2 = baseline
        points = [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
    else:
        points = (np.asarray(points, dtype=float) - box[:2]) / scale / size
    points = np.asarray(points, dtype=float)
    if (points.shape != (4,2) or not np.isfinite(points).all()
            or (points < -1e-5).any() or (points > 1.00001).any()
            or baseline[2] <= baseline[0] or baseline[3] <= baseline[1]):
        raise models.ModelError('Confirmed plate geometry falls outside its stored crop')
    return np.clip(points, 0, 1).tolist(), baseline.tolist(), quality


def _freeze(stage, selected, parent):
    """Copy selected revisions and inherited evidence before any training starts."""
    corpus = session.private_dir(stage / 'corpus')
    images = session.private_dir(corpus / 'images')
    samples = {}
    selected_identities = {(r['video_id'], r['id']) for r in selected}
    if parent['lineage']:
        for sid, sample in parent['lineage']['samples'].items():
            provenance = sample.get('source') or {}
            if (provenance.get('video_id'), provenance.get('id')) in selected_identities:
                continue
            sample = deepcopy(sample)
            shutil.copyfile(models._no_links(parent['folder'] / sample['image']), images / (sid + '.jpg'))
            sample['image'] = 'images/' + sid + '.jpg'
            samples[sid] = sample
    for record in selected:
        if record.get('explicit') is not True or record.get('category') != 'plate' or record.get('label') not in ('positive', 'negative'):
            raise models.ModelError('Training requires explicit confirmed plate examples')
        sid = hashlib.sha256((record['video_id'] + ':' + record['id']).encode()).hexdigest()
        source = models._no_links(record['image_path'])
        digest = candidates._hash_file(source, models.MAX_MODEL_BYTES)
        if digest != record['image']['sha256']:
            raise models.ModelError('Confirmed example image changed before freezing')
        points, baseline, quality = _geometry(record)
        destination = images / (sid + '.jpg')
        shutil.copyfile(source, destination)
        if candidates._hash_file(destination) != digest:
            raise models.ModelError('Confirmed example changed while freezing')
        provenance = {k: deepcopy(v) for k,v in record.items() if k != 'image_path'}
        samples[sid] = {'image': 'images/' + sid + '.jpg', 'image_sha256': digest,
            'label': record['label'], 'quality': quality if record['label'] == 'positive' else 'human_hard_negative',
            'points': points, 'baseline_box': baseline, 'frame': record['frame'],
            'group': record['video_id'] + ':' + record['id'], 'source': provenance}
    if not samples:
        raise models.ModelError('Select at least one explicit confirmed plate example')
    session.atomic_json(corpus / 'examples.json', {'schema': 1, 'samples': samples})
    return corpus, samples


def _reconcile(findings_root, selected, parent):
    """Current archive corrections govern reused evidence, without erasing exposure.

    A missing archive record leaves its detached parent snapshot usable. A known
    tombstone explicitly excludes that example from the new training corpus.
    The parent weights and exposure history still reflect the earlier training.
    """
    import confirmed_findings
    if not parent['lineage']:
        return selected, parent, {'revoked_ids': [], 'refreshed_ids': []}
    samples = parent['lineage']['samples']
    known = {s['source']['id']: s for s in samples.values()
             if isinstance(s.get('source', {}).get('id'), str)
             and models._HASH.fullmatch(s['source']['id'])}
    state = confirmed_findings.training_revisions(findings_root, list(known))
    revoked = set(state['revoked_ids'])
    if revoked.intersection(r['id'] for r in selected):
        raise models.ModelError('A selected confirmed example was revoked before freezing; refresh your selection')
    selected_by_id = {(r['video_id'], r['id']): r for r in selected if r['id'] not in revoked}
    refreshed = []
    for record in state['active']:
        previous = known[record['id']]['source'].get('revision') or 0
        if record['revision'] > previous:
            key = (record['video_id'], record['id'])
            current = selected_by_id.get(key)
            if current is not None and current['revision'] != record['revision']:
                raise models.ModelError('A selected confirmed example changed revision before freezing; refresh your selection')
            if current is None:
                selected_by_id[key] = record
            refreshed.append(record['id'])
    filtered = {sid: sample for sid,sample in samples.items()
                if sample['source']['id'] not in revoked}
    parent = dict(parent, lineage=dict(parent['lineage'], samples=filtered))
    return list(selected_by_id.values()), parent, {'revoked_ids': sorted(revoked),
                                                  'refreshed_ids': sorted(refreshed)}


def _signatures(corpus, samples):
    signatures = {}
    for sid, sample in samples.items():
        image = cv2.imread(str(corpus / sample['image']))
        if image is None or min(image.shape[:2]) < 8:
            raise models.ModelError('Unreadable or too-small frozen training example')
        signatures[sid] = {'group': sample['group'], 'image_sha256': sample['image_sha256'],
                           'dhash': '%016x' % session._feedback_dhash(image)}
    return signatures


def _exposed_groups(signatures, inherited):
    """Never validate pixels resembling an earlier trained revision/tombstone."""
    buckets = {}; digests = set()
    blocks = ((0,22), (22,21), (43,21))
    if not isinstance(inherited, list):
        raise models.ModelError('Invalid parent visual exposure history')
    for record in inherited:
        try:
            digest = record['image_sha256']; text = record['dhash']
            if (not isinstance(digest, str) or not models._HASH.fullmatch(digest)
                    or not isinstance(text, str) or len(text) != 16
                    or not isinstance(record['group'], str)):
                raise ValueError('invalid visual signature')
            signature = int(text, 16)
        except (KeyError, TypeError, ValueError) as error:
            raise models.ModelError('Invalid parent visual exposure history') from error
        digests.add(digest)
        for shift,width in blocks:
            buckets.setdefault((shift, (signature >> shift) & ((1 << width)-1)), set()).add(signature)
    exposed = set()
    for record in signatures.values():
        signature = int(record['dhash'], 16)
        possible = set()
        for shift,width in blocks:
            possible.update(buckets.get((shift, (signature >> shift) & ((1 << width)-1)), ()))
        if record['image_sha256'] in digests or any((signature ^ old).bit_count() <= 2 for old in possible):
            exposed.add(record['group'])
    return exposed


def _accumulate_exposure(inherited, signatures, groups):
    records = {(s['group'],s['image_sha256'],s['dhash']): s for s in inherited}
    records.update({(s['group'],s['image_sha256'],s['dhash']): s
                    for s in signatures.values() if s['group'] in groups})
    return [deepcopy(records[key]) for key in sorted(records)]


def _retain(model_root, manifest, candidate, corpus, samples, groups, history, parent_id, exposure):
    root = models._directory(_lineage_root(model_root), create=True)
    pending = root / ('.pending-' + uuid.uuid4().hex)
    try:
        session.private_dir(pending)
        shutil.copytree(corpus / 'images', pending / 'images')
        for sample in samples.values():
            if candidates._hash_file(pending / sample['image']) != sample['image_sha256']:
                raise models.ModelError('Frozen training corpus changed before publication')
        shutil.copyfile(candidate['folder'] / 'weights.pt', pending / 'weights.pt')
        checkpoint = candidates._hash_file(pending / 'weights.pt')
        if checkpoint != candidate['artifacts']['weights.pt']:
            raise models.ModelError('Candidate checkpoint changed while preserving lineage')
        lineage = {'schema': 1, 'model_id': manifest['id'], 'name': manifest['name'],
            'model_sha256': manifest['model_sha256'], 'checkpoint_sha256': checkpoint,
            'parent_model_id': parent_id, 'samples': samples,
            'training_groups': sorted(groups), 'split_history': history,
            'training_exposure': exposure}
        session.atomic_json(pending / 'lineage.json', lineage)
        session.atomic_json(pending / 'training.json', {'schema': 1, 'model_id': manifest['id'],
            'model_sha256': manifest['model_sha256'], 'parent_model_id': parent_id,
            'example_count': len(samples), 'checkpoint_size': (pending / 'weights.pt').stat().st_size,
            'lineage_size': (pending / 'lineage.json').stat().st_size,
            'lineage_sha256': candidates._hash_file(pending / 'lineage.json')})
        # fsync image/checkpoint bytes before exposing a durable publication.
        for path in pending.rglob('*'):
            if path.is_file():
                with path.open('rb') as stream: os.fsync(stream.fileno())
        os.rename(pending, root / manifest['id'])
    finally:
        if pending.exists(): shutil.rmtree(pending)


def session_parent(job, doc, prior):
    """Bind an accepted legacy pass to its detached locally saved checkpoint."""
    model_id = prior.get('model_id') or (doc.get('learning') or {}).get('library_model_id')
    if not model_id:
        return None
    if not job.get('model_root'):
        raise models.ModelError('The previous learning pass needs its local model checkpoint library')
    parent = resolve_parent(job['model_root'], model_id)
    if parent['lineage']['model_sha256'] != (doc.get('learning') or {}).get('model_sha256'):
        raise models.ModelError('Previous learning model and local checkpoint lineage do not agree')
    return parent


def publish_session_candidate(job, stage, folder, feedback, groups, name, parent=None):
    """Legacy mask sessions opt into automatic named saving via job.model_root.

    The root is server-owned job configuration, never a request-supplied path.
    Synthetic injection-only trainers without retained version metadata remain
    supported and do not create fictitious library models.
    """
    if not job.get('model_root') or not (Path(folder) / 'manifest.json').is_file():
        return None
    lineage = parent['lineage'] if parent else {}
    groups = set(groups) | set(lineage.get('training_groups', []))
    candidate_id = Path(stage).name + ':' + Path(folder).name
    assessment = candidates.evaluate(job['dir'], candidate_id, cancelled=job['cancel'].is_set)
    corpus = session.private_dir(Path(stage) / 'corpus')
    images = session.private_dir(corpus / 'images')
    samples = {}
    for old_id, item in feedback['samples'].items():
        sample = deepcopy(item)
        sample['source'] = deepcopy(item.get('archive_source')) or {'id': old_id, 'revision': None,
            'video_id': feedback['source_sha256'], 'frame': item['frame'],
            'label': item['label'], 'explicit': True, 'category': 'plate'}
        identity = (sample['source']['video_id'] + ':' + sample['source']['id']) if item.get('archive_source') else old_id
        sid = hashlib.sha256(identity.encode()).hexdigest()
        source = models._no_links(Path(job['dir']) / 'learning' / item['image'])
        if candidates._hash_file(source) != sample['image_sha256']:
            raise models.ModelError('Saved human example changed before publication')
        shutil.copyfile(source, images / (sid + '.jpg'))
        sample['image'] = 'images/' + sid + '.jpg'
        samples[sid] = sample
    split = session._load(Path(stage) / 'dataset' / 'split-groups.json')['groups']
    exposure = _accumulate_exposure(lineage.get('training_exposure', []), _signatures(corpus, samples), groups)
    history = deepcopy(lineage.get('split_history', []))
    history.append({'run_id': Path(stage).name, 'groups': split,
                    'examples': {sid:s['source'].get('revision') for sid,s in samples.items()}})
    manifest = models.save_candidate(job['model_root'], job['dir'], candidate_id, name,
        publication_hook=lambda manifest,candidate: _retain(job['model_root'], manifest,
            candidate, corpus, samples, groups, history,
            parent['parent_model_id'] if parent else None, exposure))
    session.update_learning(job, model_id=manifest['id'], assessment=assessment)
    session.atomic_json(Path(stage) / 'library-model.json', {'model_id': manifest['id'], 'name': name})
    return manifest


def session_feedback(job, doc, store, group_for):
    """Plan compact archive imports for Train & rescan, using clicked seeds only.

    The archive's current revision governs supervision. Report labels are output
    constraints and may be stale or propagated; they never replace archive truth.
    Actual crop copying belongs to the collector's existing transaction cleanup.
    """
    import confirmed_findings
    rows = doc['detections']
    managed = {i for i,r in enumerate(rows) if r.get('confirmed_finding_id')
               or r.get('human_confirmation') or r.get('human_region_confirmed')}
    seeds = {r['confirmed_finding_id']: (i,r) for i,r in enumerate(rows)
             if r.get('confirmed_finding_id')
             and not (r.get('human_confirmation') or {}).get('propagated')}
    blocked = {r['confirmed_finding_id'] for r in rows if r.get('confirmed_finding_id')
               and (r.get('human_confirmation') or {}).get('propagated')} - set(seeds)
    prior = {s['archive_id']: s for s in store['samples'].values() if s.get('archive_id')}
    registry = deepcopy(store.get('confirmed_seed_refs', {}))
    for identity, sample in prior.items():
        registry.setdefault(identity, {'group': sample['group']})
    for identity, (i,row) in seeds.items():
        registry.setdefault(identity, {'group': group_for(i,row)})
    store['confirmed_seed_refs'] = registry
    archived_groups = {reference['group'] for reference in registry.values()}
    managed.update(i for i,row in enumerate(rows) if group_for(i,row) in archived_groups)
    identities = set(registry) - blocked
    if identities and not job.get('model_root'):
        raise models.ModelError('Confirmed findings storage is unavailable for this training job')
    covered = {group_for(i, rows[i]) for i in managed}
    # Remove stale archive snapshots and earlier legacy samples from a group
    # now governed by an explicit archive seed (including a revoked seed).
    store['samples'] = {sid:s for sid,s in store['samples'].items()
                        if not s.get('archive_id') and s['group'] not in covered}
    if not identities:
        return managed, []
    archive = Path(job['model_root']).parent / 'confirmed_findings'
    state = confirmed_findings.training_revisions(archive, sorted(identities))
    plans = []
    for entry in state['active']:
        if entry['category'] != 'plate' or entry['explicit'] is not True:
            continue
        if entry['video']['variant_sha256'] != doc['provenance']['input_sha256']:
            raise models.ModelError('Confirmed training example belongs to a different scanned source')
        if entry['label'] == 'positive' and (not entry.get('shape_confirmed') or not entry.get('points')):
            raise models.ModelError('Train & rescan requires manually confirmed plate corners. Confirm the corners, or train a named checker from this positive example instead.')
        points, baseline, quality = _geometry(entry)
        old = prior.get(entry['id'])
        group = old['group'] if old is not None else registry[entry['id']]['group']
        filename = 'samples/archive-%s-r%d-%s.jpg' % (entry['id'], entry['revision'], entry['image']['sha256'][:12])
        sample = {'image': filename, 'image_sha256': entry['image']['sha256'],
            'label': entry['label'], 'quality': quality if entry['label'] == 'positive' else 'human_hard_negative',
            'points': points if entry['label'] == 'positive' else None,
            'frame': entry['frame'], 'box': entry['box'], 'group': group,
            'baseline_box': baseline, 'archive_id': entry['id'], 'archive_revision': entry['revision'],
            'archive_source': {k:deepcopy(v) for k,v in entry.items() if k != 'image_path'}}
        plans.append(('archive-' + entry['id'], sample, models._no_links(entry['image_path'])))
    return managed, plans


def _run_metadata(name, expected_revisions=None):
    """Keep run metadata compact even with thousands of confirmed findings.

    The full revision set is still pinned in training_job.json and in the
    frozen corpus/examples.json, so no evidence is lost by hashing it here.
    """
    result = {'schema': 1, 'name': name}
    if expected_revisions is not None:
        encoded = json.dumps(sorted(expected_revisions.items()), separators=(',', ':')).encode('utf-8')
        result['selected_revisions_count'] = len(expected_revisions)
        result['selected_revisions_sha256'] = hashlib.sha256(encoded).hexdigest()
    return result


def run(job, findings_root, model_root, settings, log=None, train=None):
    import confirmed_findings
    log = log or (lambda message: None)
    if settings.get('license_accepted') is not True:
        raise models.ModelError('Local training license acknowledgment is required')
    selected = confirmed_findings.training_snapshot(findings_root,
        ids=settings.get('example_ids'), video_ids=settings.get('video_ids'), category='plate')
    name = models._text(settings.get('name') or default_name(
        [item['video']['name'] for item in selected]), 'Model name', 80, required=True)
    session.update_learning(job, 'collecting', 'Freezing confirmed examples', name=name)
    stage = session.private_dir(Path(job['dir']) / 'learning' / 'passes' / ('pass-' + uuid.uuid4().hex[:12]))
    expected = settings.get('expected_revisions')
    if expected is not None:
        if (not isinstance(expected, dict) or any(not isinstance(k, str) or type(v) is not int or v < 1
                                                  for k,v in expected.items())):
            raise models.ModelError('Expected example revisions must map selected IDs to positive revision numbers')
        current = {record['id']: record['revision'] for record in selected}
        if current != expected:
            raise models.ModelError('Selected confirmed examples changed revision or were revoked after queuing; refresh your selection before training')
    run_metadata = _run_metadata(name, expected)
    session.atomic_json(stage / 'run.json', run_metadata)
    parent = resolve_parent(model_root, settings.get('parent_model_id'))
    selected, parent, reconciliation = _reconcile(findings_root, selected, parent)
    corpus, samples = _freeze(stage, selected, parent)
    lineage = parent['lineage'] or {}
    groups = set(lineage.get('training_groups', []))
    signatures = _signatures(corpus, samples)
    inherited_exposure = lineage.get('training_exposure', [])
    groups.update(_exposed_groups(signatures, inherited_exposure))
    session.export_dataset(corpus, {'samples': samples}, stage / 'dataset', training_groups=groups)
    splits = session._load(stage / 'dataset' / 'split-groups.json')['groups']
    groups.update(group for group, split in splits.items() if split == 'train')
    exposure = _accumulate_exposure(inherited_exposure, signatures, groups)
    history = deepcopy(lineage.get('split_history', []))
    history.append({'run_id': stage.name, 'groups': splits,
                    'examples': {sid: s['source'].get('revision') for sid,s in samples.items()},
                    'archive_reconciliation': reconciliation})
    if job['cancel'].is_set(): raise InterruptedError('Training cancelled')
    session.update_learning(job, 'training', 'Training the named plate checker', name=name)
    folder, meta = (train or session.run_training)(stage / 'dataset', stage / 'versions',
        parent['weights'], job, dict(settings, verifier_training=True))
    candidate_id = stage.name + ':' + Path(folder).name
    session.atomic_json(stage / 'run.json', dict(run_metadata, candidate_id=candidate_id))
    # This path intentionally trains a checker, including confirmed bounding
    # regions. A separate mask gate has not accepted this candidate.
    message = ('Confirmed bounding-region supervision is verifier-only; mask tightening has not been accepted.'
        if any(s['quality'] == 'human_region' for s in samples.values()) else
        'Verifier training does not run the mask-tightening acceptance gate.')
    candidates.record_mask_assessment(job['dir'], folder, 'failed', message)
    session.update_learning(job, 'checking', 'Assessing positive and negative held-out examples')
    assessment = candidates.evaluate(job['dir'], candidate_id, cancelled=job['cancel'].is_set,
        progress=lambda done,total: session.update_learning(job, done=done,total=total,unit='checks'))
    if job['cancel'].is_set(): raise InterruptedError('Training cancelled')
    manifest = models.save_candidate(model_root, job['dir'], candidate_id, name,
        publication_hook=lambda manifest,candidate: _retain(model_root, manifest, candidate,
            corpus, samples, groups, history, parent['parent_model_id'], exposure))
    result = {'status': 'complete', 'candidate_id': candidate_id, 'model_id': manifest['id'],
              'name': name, 'assessment': assessment, 'model': manifest,
              'training_info': training_info(model_root, manifest['id'])}
    session.atomic_json(stage / 'result.json', result)
    session.update_learning(job, 'complete', 'Named plate checker saved', name=name, model_id=manifest['id'])
    log('Saved named plate checker: ' + name)
    return result


def finalize_retained(job, model_root, log=None):
    """Finish an already-trained named checker without starting CUDA training.

    Only a failed named-model job with an exact published candidate, its frozen
    checked training corpus and the original selected revisions is eligible.
    All model/dataset hashes and the held-out checker gate are re-evaluated.
    This does not read source videos or collect new training examples.
    """
    if job.get('kind') != 'model_training' or job.get('phase') not in ('error', 'learning'):
        raise models.ModelError('Only a failed named-model job can finalize its saved candidate')
    settings = job.get('learning_request')
    if not isinstance(settings, dict) or settings.get('license_accepted') is not True:
        raise models.ModelError('Missing original named-model training request')
    expected = settings.get('expected_revisions')
    if (not isinstance(expected, dict) or not expected or
            any(not isinstance(i, str) or type(v) is not int or v < 1
                for i, v in expected.items())):
        raise models.ModelError('Cannot recover without the original selected revision snapshot')
    root = models._directory(Path(job['dir']) / 'learning' / 'passes')
    completed = []
    for stage in root.iterdir():
        if not stage.is_dir() or not candidates._PASS.fullmatch(stage.name):
            continue
        runpath = stage / 'run.json'
        if not runpath.is_file():
            continue
        run = models._json(models._read_file(runpath, candidates._RUN_METADATA_LIMIT))
        candidate_id = run.get('candidate_id')
        if (isinstance(candidate_id, str) and
                candidate_id.startswith(stage.name + ':')):
            completed.append((stage, run, candidate_id))
    if len(completed) != 1:
        raise models.ModelError('Expected exactly one completed retained training candidate for this failed job')
    stage, run, candidate_id = completed[0]
    name = models._text(settings.get('name'), 'Training name', 80, required=True)
    if run.get('name') != name:
        raise models.ModelError('Retained candidate belongs to another training request')
    if 'expected_revisions' in run and run['expected_revisions'] != expected:
        raise models.ModelError('Retained run revision snapshot differs from the original request')
    if 'selected_revisions_sha256' in run:
        receipt = _run_metadata(name, expected)
        if (run.get('selected_revisions_count') != receipt['selected_revisions_count']
                or run['selected_revisions_sha256'] != receipt['selected_revisions_sha256']):
            raise models.ModelError('Retained run selection fingerprint changed')
    candidate = candidates.load_candidate(job['dir'], candidate_id)
    if candidate['folder'].parent.parent != stage:
        raise models.ModelError('Retained candidate does not belong to this training pass')

    result_path = stage / 'result.json'
    if result_path.is_file():
        result = models._json(models._read_file(result_path, 1024 * 1024))
        if (result.get('candidate_id') != candidate_id or
                result.get('status') != 'complete' or
                not isinstance(result.get('model_id'), str)):
            raise models.ModelError('Retained model result does not match this candidate')
        manifest, _ = models._load_directory(Path(model_root) / result['model_id'])
        if manifest['model_sha256'] != candidate['model_sha256'] or not training_info(model_root, manifest['id'])['trainable']:
            raise models.ModelError('Previously published model or its local training state failed verification')
        return result

    corpus = models._directory(stage / 'corpus')
    frozen = models._json(models._read_file(corpus / 'examples.json', models.MAX_MODEL_BYTES))
    samples = frozen.get('samples')
    if (frozen.get('schema') != 1 or not isinstance(samples, dict) or not samples):
        raise models.ModelError('Frozen example snapshot is missing or invalid')
    revisions = {}
    for sid, sample in samples.items():
        if not isinstance(sid, str) or not models._HASH.fullmatch(sid) or not isinstance(sample, dict):
            raise models.ModelError('Invalid retained example identity')
        if sample.get('image') != 'images/' + sid + '.jpg':
            raise models.ModelError('Retained example image path does not match its identity')
        source = sample.get('source')
        if not isinstance(source, dict):
            raise models.ModelError('Retained example lacks confirmed provenance')
        if source.get('id') in expected:
            if (source.get('revision') != expected[source['id']]
                    or source.get('category') != 'plate'
                    or source.get('explicit') is not True):
                raise models.ModelError('Retained confirmed example revision no longer matches the queued request')
            revisions[source['id']] = source['revision']
    if revisions != expected:
        raise models.ModelError('Retained training set does not contain every originally selected revision')

    splits_doc = models._json(models._read_file(stage / 'dataset' / 'split-groups.json', 32 * 1024 * 1024))
    splits = splits_doc.get('groups')
    if (splits_doc.get('schema') != 1 or not isinstance(splits, dict)
            or set(splits) != {sample.get('group') for sample in samples.values()}
            or any(split not in ('train', 'val') for split in splits.values())):
        raise models.ModelError('Frozen training/validation group split is inconsistent')
    manifest_bytes = models._read_file(stage / 'dataset' / 'manifest.jsonl', candidates._DATASET_MANIFEST_LIMIT)
    for line in manifest_bytes.splitlines():
        row = models._json(line)
        image = row.get('image')
        if not isinstance(image, str):
            raise models.ModelError('Invalid recovered training image reference')
        sid = PurePosixPath(image).stem
        if (sid not in samples or row.get('job') != samples[sid].get('group')
                or row.get('label') != samples[sid].get('label')
                or row.get('split') != splits[row['job']]):
            raise models.ModelError('Retained dataset no longer matches its frozen examples')

    parent = resolve_parent(model_root, settings.get('parent_model_id'))
    lineage = parent['lineage'] or {}
    signatures = _signatures(corpus, samples)
    inherited = lineage.get('training_exposure', [])
    groups = set(lineage.get('training_groups', []))
    groups.update(_exposed_groups(signatures, inherited))
    groups.update(group for group, split in splits.items() if split == 'train')
    exposure = _accumulate_exposure(inherited, signatures, groups)
    history = deepcopy(lineage.get('split_history', []))
    history.append({'run_id': stage.name, 'groups': splits,
                    'examples': {sid: s['source'].get('revision') for sid,s in samples.items()},
                    'archive_reconciliation': {'recovered_from_frozen_corpus': True}})

    cancelled = job['cancel'].is_set
    if cancelled():
        raise InterruptedError('Model finalization cancelled; candidate retained')
    session.update_learning(job, 'checking', 'Validating saved candidate without training again', name=name)
    candidates.record_mask_assessment(job['dir'], candidate['folder'], 'failed',
        'Named verifier training; no mask-tightening acceptance claim')
    assessment = candidates.evaluate(job['dir'], candidate_id, cancelled=cancelled,
        progress=lambda done,total: session.update_learning(job, done=done,total=total,unit='checks'))
    if cancelled():
        raise InterruptedError('Model finalization cancelled; candidate retained')
    manifest = models.save_candidate(model_root, job['dir'], candidate_id, name,
        publication_hook=lambda manifest, checked: _retain(model_root, manifest, checked,
            corpus, samples, groups, history, parent['parent_model_id'], exposure))
    result = {'status': 'complete', 'candidate_id': candidate_id, 'model_id': manifest['id'],
              'name': name, 'assessment': assessment, 'model': manifest,
              'training_info': training_info(model_root, manifest['id'])}
    session.atomic_json(result_path, result)
    session.update_learning(job, 'complete', 'Saved existing named plate checker', name=name, model_id=manifest['id'])
    (log or (lambda message: None))('Finalized saved candidate without retraining: ' + name)
    return result
