"""Web adapter for explicit confirmed examples and compact image review."""
from copy import deepcopy
from functools import wraps
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time

import cv2
import numpy as np
from flask import Response, abort, jsonify, request

import confirmed_findings as library
import finding_previews as previews
import findings_training as training
import learning_session
import stop_review
import video_learning


RESERVED = {'learned_plate_models', 'confirmed_findings', 'learned_model_training'}
_LEGACY_TIMING_NOTE = ('This legacy variable-frame-rate picture uses an approximate timestamp. '
    'Output and draft area edits remain available. Rescan with frame-rate normalization '
    'before saving confirmed training examples.')
_web = None


def root():
    return Path(_web.JOBS_DIR) / 'confirmed_findings'


def _guard(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except library.ConflictError as error:
            return jsonify(error=str(error),current_archive=getattr(error,'current_archive',None)), 409
        except (KeyError, FileNotFoundError):
            return jsonify(error='This saved finding is no longer available.'), 404
        except ValueError as error:
            return jsonify(error=str(error)), 400
    return wrapped


def _body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        abort(400, description='Supply a JSON object.')
    return value


def _job(jid, edit=False):
    job = _web.JOBS.get(jid) or abort(404)
    if edit and job['phase'] not in ('review', 'paused', 'done'):
        abort(409, description='Pause or finish scanning before saving review decisions.')
    return job


def _token(doc, row, frame, sample_key=None):
    value = [doc.get('compact_preview_source',doc.get('provenance', {}).get('input_sha256')), frame,
             sample_key, row['category'], row['cbox'], row.get('plate_quad') or [],
             doc['render_state']['cum'][frame], doc.get('preview_revision')]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _cold_frame(job,doc,row,frame):
    """Bind a cold crop to verified bytes once per source file identity."""
    if not _web._REVIEW_WORK_LOCK.acquire(blocking=False):
        abort(503,description='Another preview is decoding. Retry shortly.')
    try:
        if _web.vault_locked():
            abort(423)
        identity = _web._video_identity(job['video'])
        expected = (doc.get('provenance') or {}).get('input_sha256') or (doc.get('source_identity') or {}).get('input_sha256')
        signature = (identity,expected)
        verified = job.get('_finding_source_verified')
        if not verified or verified['signature'] != signature:
            actual = learning_session.sha256(job['video'])
            if expected and actual != expected:
                raise library.ConflictError('The source video changed. Rescan it before creating new previews or examples.')
            verified = dict(signature=signature,sha256=actual)
            job['_finding_source_verified'] = verified
        rs = doc['render_state']
        info = _web._review_probe(job['video'],identity)
        if not math.isclose(float(rs['fps']),info['fps'],rel_tol=1e-4,abs_tol=.001):
            raise library.ConflictError('The source frame rate differs from the saved review timeline. Rescan before creating new previews.')
        source_identity = doc.get('source_identity') or {}
        if any(source_identity.get(key) not in (None,info[key]) for key in ('width','height')):
            raise library.ConflictError('The source dimensions differ from the saved review timeline. Rescan before creating new previews.')
        approximate = row.get('frame_index',-1) < 0 and not info['cfr']
        source = dict(sha256=verified['sha256'],timing='timestamp' if approximate else 'frame')
        if approximate:
            # Preserve the legacy review timestamp, without pretending that
            # timestamp seeking established an exact source frame for training.
            tref = min(max(float(row.get('last_seen',row['t_start'])),float(row['t_start'])),float(row['t_end']))
            source['requested_time'] = tref
            pixels = _web._frame_at(job,tref,rs,None)
        else:
            pixels = _web._frame_at(job,frame/float(rs['fps']),rs,frame)
        if _web._video_identity(job['video']) != identity:
            job.pop('_finding_source_verified',None)
            raise library.ConflictError('The source changed while reading this preview. Retry with the original video.')
        return pixels,source
    finally:
        _web._REVIEW_WORK_LOCK.release()


def preview(job, index, doc=None, cache_only=False):
    """Return source geometry and compact pixels; a warm read never opens video."""
    doc = doc if doc is not None else _web._load_preview_report(job)
    if not 0 <= index < len(doc.get('detections', [])):
        abort(404)
    row, rs = doc['detections'][index], doc['render_state']
    frame = video_learning._frame(row, rs)
    if row.get('frame_index',-1) < 0:
        tref = min(max(float(row.get('last_seen',row['t_start'])),float(row['t_start'])),float(row['t_end']))
        position = tref*float(rs['fps'])
        if 0 <= position < len(rs['cum']):
            # A valid final legacy timestamp may round to the exclusive end.
            # Keep its coordinate lookup on the last available timeline entry.
            frame = min(round(position),len(rs['cum'])-1)
    if not 0 <= frame < len(rs['cum']):
        abort(400, description='Finding is outside the scanned timeline.')
    # Match the canonical report frame even when a legacy fractional timestamp
    # would be rounded differently by the generic cache's time-based lookup.
    cache_row = dict(row,frame_index=frame)
    cached = _web._serialize_review_read(previews.lookup)(job['dir'], cache_row, rs)
    if cached is None and int(row.get('track', -1)) >= 0:
        cached = _web._serialize_review_read(previews.lookup)(
            job['dir'], cache_row, rs, allow_representative=True)
    if cached is None and cache_only:
        return None
    box = list(map(float, video_learning._screen_box(row, rs, frame)))
    q = row.get('plate_quad') or ((0., 0.), (1., 0.), (1., 1.), (0., 1.))
    points = [[box[0]+x*(box[2]-box[0]), box[1]+y*(box[3]-box[1])] for x,y in q]
    if cached is None:
        # Legacy jobs may need one bounded CPU decode. All subsequent thumbnail,
        # confirmation and area-editor requests share this compact cache.
        pixels, source = _cold_frame(job,doc,row,frame)
        if pixels is None:
            abort(404, description='Source frame is unavailable and has no saved preview.')
        h,w = pixels.shape[:2]
        crop = _web._plate_editor_crop(box, points, w, h)
        x1,y1,x2,y2 = crop
        meta = dict(width=w, height=h, crop=crop, box=box, points=points,
                    frame=frame, t=frame/float(rs['fps']), fps=float(rs['fps']),
                    source=source,
                    track=row.get('track', -1))
        cached = _web._serialize_review_read(previews.store)(
            job['dir'], cache_row, rs, meta, pixels[y1:y2,x1:x2])
    meta, jpeg = cached
    source = meta.get('source') or {}
    exact = source.get('timing') != 'timestamp'
    representative = meta.get('match') == 'representative'
    shown_frame = int(meta['frame']) if representative else frame
    shown_box = list(map(float, meta['box'])) if representative else box
    shown_points = meta.get('points') if representative else points
    shown_t = float(meta.get('t', shown_frame/float(rs['fps'])))
    sample_key = meta.get('key')
    meta = dict(meta, i=index, frame=shown_frame,
                frame_index=shown_frame if exact else -1,
                t=shown_t if exact else source['requested_time'], box=shown_box,
                points=shown_points, track=row.get('track', -1), compact=True,
                exact_frame=exact, classification_allowed=exact,
                classification_note=None if exact else _LEGACY_TIMING_NOTE,
                requested_frame=frame,
                preview_token=_token(doc, row, shown_frame, sample_key))
    if not exact:
        meta['match'] = 'timestamp'
    source_row = dict(row, plate_quad=[])
    meta['source_token'] = _token(doc, source_row, shown_frame, sample_key)
    return doc, row, meta, jpeg


def _video(job, doc, meta):
    if meta.get('exact_frame') is False:
        raise library.ConflictError(_LEGACY_TIMING_NOTE)
    p = doc.get('provenance') or {}
    source = p.get('input_sha256')
    if not source:
        # Old reports only: verify once on explicit confirmation, never listing.
        # Existing open thumbnails must keep their source token when this old
        # report first acquires its verified content hash.
        doc.setdefault('compact_preview_source',None)
        source = (meta.get('source') or {}).get('sha256') or learning_session.verify_source(job, doc)
        doc.setdefault('provenance', {})['input_sha256'] = source
    identity = doc.setdefault('source_identity', {})
    identity.update(input_sha256=source, width=meta['width'], height=meta['height'])
    return dict(sha256=p.get('original_input_sha256') or source, variant_sha256=source,
                name=Path(job.get('name') or p.get('original_input') or p.get('input') or 'Video').name,
                fps=float(doc['render_state']['fps']), width=meta['width'], height=meta['height'],
                total_frames=int(identity.get('total_frames') or len(doc['render_state']['cum'])))


def _shape(points, meta):
    try:
        value = np.asarray(points, dtype=float)
    except (ValueError,TypeError) as error:
        raise ValueError('Select four finite corner points.') from error
    if value.shape != (4,2) or not np.isfinite(value).all():
        raise ValueError('Select four finite corner points.')
    crop = meta['crop']
    if (np.any(value[:,0] < crop[0]) or np.any(value[:,0] > crop[2]) or
            np.any(value[:,1] < crop[1]) or np.any(value[:,1] > crop[3])):
        raise ValueError('Keep the corners inside the saved picture. Open the source view for a wider area.')
    contour = value.astype(np.float32).reshape(-1,1,2)
    if not cv2.isContourConvex(contour) or cv2.contourArea(contour) < 8:
        raise ValueError('Corners must form a convex region of at least eight source pixels.')
    return value.tolist()


def _archived(job, doc, row, meta, jpeg, label, expected_revision=None):
    value = dict(category=row['category'], label=label, frame=meta['frame'],
                 box=meta['box'], crop=meta['crop'], job_id=job['id'], explicit=True,
                 shape_confirmed=bool(row.get('human_region_confirmed')),
                 points=meta['points'] if row.get('human_region_confirmed') else None)
    current = row.get('confirmed_finding_id')
    if current:
        value['id'] = current
        value['expected_revision'] = (expected_revision if expected_revision is not None
                                     else row.get('confirmed_finding_revision'))
    elif expected_revision is not None:
        value['expected_revision'] = expected_revision
    try:
        return library.record(root(), _video(job, doc, meta), value, jpeg)
    except library.ConflictError as error:
        # The archive may already be durable when a report write or its HTTP
        # acknowledgment failed. A matching current value is a safe receipt;
        # a different newer human decision must still raise a conflict.
        if current:
            state = library.revision_state(root(),current)
            latest = library.get_finding(root(), current) if not state['revoked'] else None
            if latest and all(latest.get(key) == value.get(key)
                   for key in ('label', 'points', 'shape_confirmed')):
                return latest
            error.current_archive = state
        raise


def _members(doc, index):
    row = doc['detections'][index]
    tid = row.get('track', -1)
    person = row.get('person', -1)
    return [(i,d) for i,d in enumerate(doc['detections'])
            if i == index or (d['category'] == row['category'] and
                (d.get('person', -1) == person if person >= 0 else tid >= 0 and d.get('track', -1) == tid))]


def _guard_section(job, before, after):
    if before.get('video_sections') or (job.get('section') or {}).get('role') == 'export':
        _web._SECTIONS.guard_edits(job, before, after)


def confirm(job, index, payload):
    label = payload.get('label')
    if label not in ('positive', 'negative') or type(label) is not str:
        raise ValueError('Choose Is a … or Not a … to store a confirmed example.')
    before, _, meta, jpeg = preview(job, index)
    if meta.get('classification_allowed') is False:
        raise library.ConflictError(_LEGACY_TIMING_NOTE)
    doc = deepcopy(before)
    row = doc['detections'][index]
    if payload.get('preview_token') not in (None, meta['preview_token']):
        abort(409, description='The finding changed. Reload its picture.')
    if payload.get('points') is not None:
        meta['points'] = _shape(payload['points'], meta)
        box = meta['box']
        row['plate_quad'] = [[(x-box[0])/(box[2]-box[0]),(y-box[1])/(box[3]-box[1])]
                             for x,y in meta['points']]
        row['human_region_confirmed'] = True
    for i, member in _members(doc, index):
        _web._human_plate_override(member)
        member['enabled'] = label == 'positive'
        member['output_choice_explicit'] = True
        member['human_confirmation'] = dict(label=label, category=row['category'],
                                            source='explicit', propagated=i != index)
        if row['category'] == 'plate':
            member['verified_label'] = 'plate' if label == 'positive' else 'not_plate'
            if payload.get('points') is not None:
                member['plate_quad'] = row['plate_quad']
    _guard_section(job, before, doc)
    # Archive first. A failed report write is retryable/idempotent; never tell
    # the UI the example is saved if its JPEG/metadata transaction failed.
    entry = _archived(job, doc, row, meta, jpeg, label, payload.get('expected_revision'))
    row['confirmed_finding_id'] = entry['id']
    row['confirmed_finding_revision'] = entry['revision']
    row['human_confirmation'].update(id=entry['id'], revision=entry['revision'])
    doc['render_required'] = True
    stop_review.atomic_report(str(Path(job['dir'])/'report.json'), doc)
    meta['preview_token'] = _token(doc,row,meta['frame'],meta.get('key'))
    return dict(ok=True, finding=entry, applied=len(_members(doc,index)),
                label=row.get('verified_label',''), preview=meta)


def region(job, index, payload):
    before, _, meta, jpeg = preview(job, index)
    doc = deepcopy(before)
    row = doc['detections'][index]
    if row['category'] != 'plate':
        raise ValueError('Four-corner area editing currently applies to plate findings.')
    points = _shape(payload.get('points'), meta)
    box = meta['box']
    quad = [[round((x-box[0])/(box[2]-box[0]),6),round((y-box[1])/(box[3]-box[1]),6)] for x,y in points]
    members = _members(doc,index)
    edit_id = payload.get('edit_id') if payload.get('autosave') is True else None
    if payload.get('autosave') is True and (not isinstance(edit_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',edit_id)):
        raise ValueError('Autosave requires a valid edit identifier.')
    confirmed = row.get('human_confirmation') or {}
    receipt = row.get('compact_edit_receipt') or {}
    if edit_id and receipt.get('id') == edit_id:
        if (receipt.get('source') != meta['source_token'] or row.get('plate_quad') != quad
                or receipt.get('token') != payload.get('preview_token')):
            raise library.ConflictError('Edit identifier belongs to different corners.')
        return dict(ok=True,applied=len(members),verified_samples_added=0,preview=meta,
                    verified_label=row.get('verified_label',''),
                    classification_required=not bool(confirmed.get('label')))
    if payload.get('preview_token') not in (None, meta['preview_token']):
        raise library.ConflictError('This finding changed. Reload its picture before saving.')
    for _, member in members:
        _web._human_plate_override(member)
        member['plate_quad'] = quad
        member.pop('compact_edit_receipt',None)
    row['human_region_confirmed'] = True
    meta['points'] = points
    _guard_section(job,before,doc)
    entry = None
    if row.get('confirmed_finding_id') and confirmed.get('label') in ('positive','negative') and not confirmed.get('propagated'):
        entry = _archived(job,doc,row,meta,jpeg,confirmed['label'])
        row['confirmed_finding_revision'] = entry['revision']
        row['human_confirmation']['revision'] = entry['revision']
    if edit_id:
        row['compact_edit_receipt'] = dict(id=edit_id,source=meta['source_token'],token=payload.get('preview_token'))
    doc['render_required'] = True
    stop_review.atomic_report(str(Path(job['dir'])/'report.json'),doc)
    meta['preview_token'] = _token(doc,row,meta['frame'])
    return dict(ok=True, applied=len(members), verified_samples_added=0,
                finding=entry, preview=meta, verified_label=row.get('verified_label',''),
                classification_required=not bool(confirmed.get('label')))


def _state(job):
    keep = ('id','name','kind','phase','created','error','learning','training_result','learning_request')
    learning_session.atomic_json(Path(job['dir'])/'training_job.json',
                                 {k:job[k] for k in keep if k in job})


def perform_training(job):
    cb = _web.WebCallbacks(job)
    try:
        result = training.run(job,root(),_web.learned_models_root(),job['learning_request'],cb.log)
        job.update(phase='model_ready',progress=1.,error=None,training_result=result)
        cb.log('Saved named model: '+result['name'])
    except InterruptedError:
        job.update(phase='cancelled',error=None)
        cb.log('Model training cancelled; previous models and confirmed examples kept.')
    except Exception as error:
        _web.diagnostics.exception('confirmed_findings_training_failed',job)
        job.update(phase='error',error=str(error))
        cb.log('Model training stopped: '+str(error))
    finally:
        _state(job)


def recover_training(jid, jdir):
    path = Path(jdir)/'training_job.json'
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    if data.get('id') != jid or data.get('kind') != 'model_training':
        return None
    job = dict(data, dir=str(jdir), video='',options={},progress=0.,size=0,
               output=None,eta=None,log=[],cancel=threading.Event(),stop=threading.Event(),stats={})
    if job.get('phase') in ('queued','learning'):
        job.update(phase='error',error='Training was interrupted. Confirmed examples and saved models are kept; start a new training run.')
    return job


def install(app, web):
    global _web
    _web = web

    @app.get('/api/findings')
    @_guard
    @web._serialize_review_read
    def findings_list():
        return jsonify(library.list_findings(root(),video_id=request.args.get('video_id') or None,
            category=request.args.get('category') or None,label=request.args.get('label') or None,
            offset=int(request.args.get('offset',0)),limit=int(request.args.get('limit',60))))

    @app.route('/api/findings/<identity>',methods=['GET','POST','DELETE'])
    @_guard
    @web._serialize_review_edit
    def finding_detail(identity):
        if request.method == 'GET':
            return jsonify(finding=library.get_finding(root(),identity))
        value = _body()
        if request.method == 'DELETE':
            library.forget(root(),identity,expected_revision=value.get('expected_revision'))
            return jsonify(ok=True)
        return jsonify(finding=library.update_finding(root(),identity,
            label=value.get('label'),points=value.get('points'),expected_revision=value.get('expected_revision')))

    @app.get('/api/findings/<identity>/image')
    @_guard
    @web._serialize_review_read
    def finding_image(identity):
        # Read the bounded JPEG before releasing the vault gate; no file handle
        # may remain open while encryption replaces the archive's files.
        return Response(library.image_path(root(),identity).read_bytes(),mimetype='image/jpeg',
                        headers={'Cache-Control':'no-store'})

    @app.get('/api/jobs/<jid>/finding-preview/<int:index>')
    @_guard
    def finding_preview(jid,index):
        result = preview(_job(jid),index,cache_only=request.args.get('cache_only')=='1')
        if result is None:
            return Response(status=204,headers={'Cache-Control':'no-store'})
        _,_,meta,jpeg = result
        response = Response(jpeg,mimetype='image/jpeg',headers={'Cache-Control':'no-store'})
        response.headers['X-Finding-Geometry'] = json.dumps(meta,separators=(',',':'))
        response.headers['X-Plate-Geometry'] = response.headers['X-Finding-Geometry']
        return response

    @app.post('/api/jobs/<jid>/confirm/<int:index>')
    @_guard
    @web._serialize_review_edit
    def finding_confirm(jid,index):
        return jsonify(confirm(_job(jid,True),index,_body()))

    @app.post('/api/jobs/<jid>/finding-region/<int:index>')
    @_guard
    @web._serialize_review_edit
    def finding_region(jid,index):
        return jsonify(region(_job(jid,True),index,_body()))

    @app.get('/api/jobs/<jid>/review-queue')
    @_guard
    @web._serialize_review_read
    def finding_queue(jid):
        job = _job(jid)
        data = previews.pending(job['dir'],offset=int(request.args.get('offset',0)),limit=60)
        data['phase'] = job['phase']
        return jsonify(data)

    @app.get('/api/jobs/<jid>/review-queue/<key>/image')
    @_guard
    @web._serialize_review_read
    def finding_queue_image(jid,key):
        result = previews.image(_job(jid)['dir'],key)
        if result is None:
            abort(404)
        return Response(result[1],mimetype='image/jpeg',headers={'Cache-Control':'no-store'})

    @app.post('/api/findings/train')
    @_guard
    @web._serialize_review_edit
    def findings_train():
        value = _body()
        if value.get('license_accepted') is not True:
            raise ValueError('Acknowledge the existing training framework terms before training.')
        if not (isinstance(value.get('example_ids'),list) and value['example_ids']):
            raise ValueError('Select the confirmed plate examples to train.')
        selected = library.training_snapshot(root(),ids=value.get('example_ids'),
                                             video_ids=value.get('video_ids'),category='plate')
        if not selected:
            raise ValueError('Select confirmed plate examples to train.')
        if {item['id'] for item in selected} != set(value['example_ids']):
            raise library.ConflictError('Some selected examples changed or were forgotten. Reload the library before training.')
        parent = training.resolve_parent(web.learned_models_root(),value.get('parent_model_id'))
        ready = learning_session.preflight(weights=parent['weights'])
        if not ready['ready']:
            return jsonify(error='; '.join(ready['problems'])),409
        name = value.get('name') or training.default_name([item['video']['name'] for item in selected])
        if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 or ord(c)==127 for c in name):
            raise ValueError('Use a model name between 1 and 80 characters.')
        settings = {key:value[key] for key in ('example_ids','video_ids','parent_model_id') if key in value}
        settings.update(name=name.strip(),license_accepted=True,epochs=40,batch=8)
        # Resolve/filter now and persist the explicit selected identities. The
        # worker freezes their revisions/pixels before invoking the trainer.
        settings['example_ids'] = [item['id'] for item in selected]
        settings['expected_revisions'] = {item['id']:item['revision'] for item in selected}
        job = web.new_job('',{},name.strip())
        job.update(kind='model_training',phase='learning',learning_request=settings,
                   learning={'stage':'queued','message':'Named model training queued'})
        _state(job)
        web.WORK_Q.put((job['id'],'learn_examples'))
        return jsonify(id=job['id'],name=job['name'])
