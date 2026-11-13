"""Explicit, bounded local OCR discovery; proposals never confirm examples.

The web request freezes report writers only long enough to record a cheap file
identity and queue the work. The worker then reads and hashes that stable report
snapshot, owns one sequential CPU decoder, and publishes only after
source/report revalidation. Neither thumbnail reads nor ordinary review
decisions invoke this module's OCR search.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import cv2
from flask import abort, jsonify, request

import finding_previews as previews
import learning_session
import plate_text_hints as hints
import stop_review
import video_learning
import video_sections


_web = None
NOTE = 'Sampled candidate search; not complete redaction. Review every proposal before rendering.'
_ERROR = ('Known plate text search stopped; previous review retained. '
          'Check local OCR availability and the source video timeline before retrying.')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _path(job):
    return Path(job['dir']) / 'report.json'


def _report_identity(job):
    path = _path(job)
    stat = path.stat()
    return (str(path), stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def _cancel(job):
    if job['cancel'].is_set() or job['stop'].is_set():
        raise InterruptedError


def _intervals(job, doc):
    """Respect real scan coverage, checkpoint prefix and section ownership."""
    intervals = video_sections._coverage_intervals(doc)
    limit = job.get('options', {}).get('section_context')
    if limit is None:
        limit = job.get('options', {}).get('section_range')
    if limit is not None:
        if (not isinstance(limit, (tuple, list)) or len(limit) != 2 or
                any(type(x) is not int for x in limit) or not 0 <= limit[0] < limit[1]):
            raise ValueError('Invalid section bounds')
        intervals = [(max(a, limit[0]), min(b, limit[1])) for a, b in intervals]
    return [(a, b) for a, b in intervals if b > a]


def _samples(intervals, fps, maximum):
    """One-second spatial samples with endpoints, evenly bounded in memory."""
    step = max(1, int(round(fps)))
    lengths = [(b-a-1)//step+1 + int((b-a-1) % step != 0) for a, b in intervals]
    total = sum(lengths)
    count = min(total, maximum)
    if not count:
        return []
    ranks = {0} if count == 1 else {round(i*(total-1)/(count-1)) for i in range(count)}
    frames, cursor = [], 0
    for (a, b), size in zip(intervals, lengths):
        for rank in sorted(ranks):
            if cursor <= rank < cursor+size:
                frames.append(min(b-1, a+(rank-cursor)*step))
        cursor += size
    return frames


def _visible(row, frame, fps):
    if row.get('category') != 'plate' or row.get('zone_dropped'):
        return False
    exact = row.get('frame_index', -1)
    if exact >= 0:
        return exact == frame
    if row.get('owned_start_frame', -1) >= 0 and frame < row['owned_start_frame']:
        return False
    if row.get('owned_end_frame', -1) >= 0 and frame >= row['owned_end_frame']:
        return False
    return float(row['t_start'])-.01 <= frame/fps <= float(row['t_end'])+.01


def _box(value, width, height):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError('Invalid OCR region')
    values = [float(x) for x in value]
    if not all(math.isfinite(x) for x in values):
        raise ValueError('Invalid OCR region')
    a,b,c,d = values
    # Clipping source boundaries is safe; a degenerate/outside region is not.
    values = [max(0., a), max(0., b), min(float(width), c), min(float(height), d)]
    if values[2] <= values[0] or values[3] <= values[1]:
        raise ValueError('Invalid OCR region')
    return values


def _evidence(proposal):
    """Copy an explicit schema; local sensitive evidence never enters logs."""
    value = {'method': 'known_plate_text', 'review_status': 'unreviewed',
             'confidence_is_detector_probability': False,
             'protection': 'entire_candidate'}
    for key in ('observed_text', 'matched_target', 'matched_text'):
        text = proposal.get(key)
        if isinstance(text, str):
            value[key] = ''.join(c for c in text[:128] if 32 <= ord(c) < 127)
    if proposal.get('match_kind') in ('exact', 'partial'):
        value['match_kind'] = proposal['match_kind']
    for key in ('match_strength', 'target_coverage', 'ocr_confidence'):
        score = proposal.get(key)
        if type(score) in (float, int) and math.isfinite(score):
            value[key] = max(0., min(1., float(score)))
    orientation = proposal.get('orientation') or {}
    if isinstance(orientation, dict):
        value['orientation'] = dict(rotation=orientation.get('rotation')
            if orientation.get('rotation') in (0,90,180,270) else 0,
            mirrored=orientation.get('mirrored') is True)
    provenance = proposal.get('provenance') or {}
    if isinstance(provenance, dict):
        # Strings from OCR adapters may include filenames/errors. Keep only
        # bounded known enum values and the explicit geometry caveat.
        value['boundary_requires_review'] = provenance.get('boundary_requires_review') is True
        if provenance.get('candidate') in ('provided_region','plate_contour','text_contour','full_frame_text'):
            value['candidate'] = provenance['candidate']
    return value


def _editor_crop(box, points, width, height):
    # The isolated OCR process must not import the web server or its model
    # state merely to compute the exact same source-coordinate preview crop.
    if _web is not None:
        return _web._plate_editor_crop(box, points, width, height)
    xs = [float(box[0]), float(box[2])] + [float(pt[0]) for pt in points]
    ys = [float(box[1]), float(box[3])] + [float(pt[1]) for pt in points]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (xmin+xmax)/2., (ymin+ymax)/2.
    radius = max(38., .5*math.hypot(xmax-xmin, ymax-ymin)
                 + max(28., .15*(xmax-xmin)))
    crop = [max(0, math.floor(cx-radius)), max(0, math.floor(cy-radius)),
            min(width, math.ceil(cx+radius)), min(height, math.ceil(cy+radius))]
    if crop[2] <= crop[0] or crop[3] <= crop[1]:
        raise ValueError('Plate is outside the video frame')
    return crop


def _cache(job, doc, row, frame, pixels):
    rs = doc['render_state']
    height, width = pixels.shape[:2]
    box = video_learning._screen_box(row, rs, frame)
    quad = row.get('plate_quad') or [[0,0],[1,0],[1,1],[0,1]]
    points = [[box[0]+x*(box[2]-box[0]), box[1]+y*(box[3]-box[1])] for x,y in quad]
    # Reuse the review editor's source-coordinate rotation envelope.
    crop = _editor_crop(box, points, width, height)
    x1,y1,x2,y2 = crop
    meta = dict(width=width, height=height, crop=crop, box=box, points=points,
                frame=frame, fps=float(rs['fps']))
    previews.store(job['dir'], row, rs, meta, pixels[y1:y2,x1:x2])


def _merge(job, doc, frame, pixels, proposals, stats):
    rs, fps = doc['render_state'], float(doc['render_state']['fps'])
    height, width = pixels.shape[:2]
    ox, oy = map(float, rs['cum'][frame])
    for proposal in proposals[:12]:
        _cancel(job)
        if not isinstance(proposal, dict):
            continue
        # Text-only OCR corners are never a safe permission to expose the
        # unmatched part of a known number. Use the enclosing protection box.
        box = _box(proposal.get('protection_box') or proposal.get('source_box'), width, height)
        source = _box(proposal.get('source_box') or box, width, height)
        box = [min(box[0],source[0]),min(box[1],source[1]),
               max(box[2],source[2]),max(box[3],source[3])]
        evidence = _evidence(proposal)
        matches = [(i,row) for i,row in enumerate(doc['detections'])
                   if _visible(row, frame, fps)
                   and video_learning._iou(video_learning._screen_box(row,rs,frame), box) >= .5]
        if matches:
            row_index, row = max(matches, key=lambda item: video_learning._iou(
                video_learning._screen_box(item[1],rs,frame),box))
            # OCR evidence is independent of every existing human/output
            # choice. Never replace a correction, classification or polygon.
            row['plate_text_evidence'] = evidence
            # A subprocess publishes only sparse OCR changes. The main web
            # process merges them into the authoritative report under its own
            # edit lock; the child never writes report.json.
            if ('_ocr_updates' in doc and
                    row_index < doc.get('_ocr_original_count', 0)):
                doc['_ocr_updates'][str(row_index)] = evidence
            stats['matched_existing'] += 1
            # Only exact-index rows can use this frame as their exact preview.
            if (video_learning._frame(row,rs) == frame and
                    previews._requested(row,rs)[0] == frame):
                _cache(job,doc,row,frame,pixels)
            continue
        row = dict(t_start=frame/fps, t_end=frame/fps, last_seen=frame/fps,
                   frame_index=frame, cbox=[box[0]-ox,box[1]-oy,box[2]-ox,box[3]-oy],
                   aoff=[ox,oy], category='plate', text='Known-text plate candidate',
                   confidence=0., track=-1, dense=True, enabled=True,
                   verified_label='', mask_pad=-1, fallback_reason='known_text_candidate',
                   plate_text_evidence=evidence)
        # No poly/plate_quad/human_region_confirmed: narrow mode must use the
        # entire candidate fallback until a person chooses its safe boundary.
        _cache(job,doc,row,frame,pixels)
        doc['detections'].append(row)
        stats['added'] += 1


def _scan(job, doc, settings, stats):
    rs = doc['render_state']
    fps = float(rs['fps'])
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('Invalid source FPS')
    frames = _samples(_intervals(job,doc),fps,settings['max_frames'])
    if not frames:
        raise ValueError('No scanned frames to search')
    stats['sampled_frames'] = frames
    cap = cv2.VideoCapture(str(job['video']))
    try:
        if not cap.isOpened() or not math.isclose(float(cap.get(cv2.CAP_PROP_FPS)),fps,
                                                rel_tol=1e-4,abs_tol=.001):
            raise ValueError('Source timeline differs')
        expected = (doc.get('source_identity') or {}).get('total_frames')
        expected = expected or (doc.get('stop_review') or {}).get('total_frames')
        if expected is not None and int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) != expected:
            raise ValueError('Source length differs')
        index, done = 0, 0
        targets = set(frames)
        # A single sequential decoder keeps source indices exact even where
        # backend random seeking cannot honor a requested source frame.
        while index <= frames[-1]:
            _cancel(job)
            ok, pixels = cap.read()
            if not ok:
                raise ValueError('Source ended before the scanned timeline')
            stats['decoded_frames'] += 1
            if index in targets:
                identity = doc.get('source_identity') or {}
                if (identity.get('width') not in (None,pixels.shape[1]) or
                        identity.get('height') not in (None,pixels.shape[0])):
                    raise ValueError('Source dimensions differ')
                regions = []
                for row in doc['detections']:
                    if _visible(row,index,fps):
                        box = video_learning._screen_box(row,rs,index)
                        region = {'source_box': box}
                        if row.get('plate_quad'):
                            region['plate_quad'] = [[box[0]+x*(box[2]-box[0]),box[1]+y*(box[3]-box[1])]
                                                     for x,y in row['plate_quad']]
                        regions.append(region)
                proposals = hints.search_frame(pixels,settings['plate_texts'],regions=regions,
                    cancelled=lambda: job['cancel'].is_set() or job['stop'].is_set())
                _cancel(job)
                _merge(job,doc,index,pixels,proposals,stats)
                done += 1
                _progress(job,stats,done,len(frames),index)
            index += 1
    finally:
        cap.release()


def _progress(job, stats, done, total, frame):
    public = dict(state='running', note=NOTE, done=done,total=total,
                  added=stats['added'],matched_existing=stats['matched_existing'],source_frame=frame)
    job['plate_text_search'] = public
    callback = job.get('_ocr_progress')
    if callback is not None:
        callback(public)
    learning_session.update_learning(job,'plate_text_search','Searching known plate text',
                                     done=done,total=total,unit='frames',source_frame=frame)


def perform(job):
    """Worker entry point for action ``plate_text``; publication is atomic."""
    settings = job.get('plate_text_request') or {}
    previous = settings.get('previous_phase','review')
    stats = dict(added=0,matched_existing=0,decoded_frames=0,sampled_frames=[])
    try:
        _cancel(job)
        expected_identity = tuple(settings.get('report_identity') or ())
        if not expected_identity or _report_identity(job) != expected_identity:
            raise ValueError('Review changed before search')
        before = _path(job).read_bytes()
        if _report_identity(job) != expected_identity:
            raise ValueError('Review changed while loading search snapshot')
        report_sha256 = _digest(before)
        original = json.loads(before)
        fingerprint = learning_session.verify_source(job,original)
        for metadata in (original.get('source_identity'),original.get('stop_review')):
            if metadata and metadata.get('input_sha256') not in (None,fingerprint):
                raise ValueError('Source metadata differs')
        if original.get('stop_review'):
            stop_review.validate_resume(original,fingerprint)
        doc = deepcopy(original)
        _scan(job,doc,settings,stats)
        _cancel(job)
        status = dict(state='completed',note=NOTE,done=len(stats['sampled_frames']),
                      total=len(stats['sampled_frames']),hint_count=len(settings['plate_texts']),
                      **stats)
        doc['plate_text_search'] = status
        if stats['added']:
            doc['render_required'] = True
        with _web._REVIEW_EDIT_LOCK, _web._REVIEW_WORK_LOCK:
            _cancel(job)
            if _digest(_path(job).read_bytes()) != report_sha256:
                raise ValueError('Review changed during search')
            if learning_session.verify_source(job,doc) != fingerprint:
                raise ValueError('Source changed before publication')
            if _web._SECTIONS.whole_job_error(job):
                raise ValueError('Approved section changed during search')
            _web._SECTIONS.guard_edits(job,original,doc)
            stop_review.atomic_report(str(_path(job)),doc)
        job.update(phase='paused' if previous=='paused' else 'review',error=None,
                   plate_text_search=status)
        if stats['added']:
            job['output'] = None
        learning_session.update_learning(job,'plate_text_complete',NOTE,
            done=status['done'],total=status['total'],unit='frames')
    except InterruptedError:
        message = 'Known plate text search cancelled; previous review retained.'
        job.update(phase=previous,error=None,plate_text_search=dict(state='cancelled',note=NOTE,message=message),
                   learning=dict(stage='cancelled',message=message))
    except Exception:
        # An OCR adapter's exception can contain the number, raw OCR text,
        # subprocess arguments or local paths. Never log/echo that exception.
        job.update(phase=previous,error=_ERROR,plate_text_search=dict(state='failed',note=NOTE,message=_ERROR),
                   learning=dict(stage='failed',message=_ERROR))
    finally:
        job.pop('plate_text_request',None)
        job['cancel'].clear()
        job['stop'].clear()
        job['eta'] = None


def install(app, web):
    global _web
    _web = web

    @app.route('/api/jobs/<jid>/plate-text-search',methods=['GET','POST'])
    def plate_text_search(jid):
        job = web.JOBS.get(jid) or abort(404)
        if request.method == 'GET':
            status = job.get('plate_text_search')
            if status is None:
                status = web._load_job_report(job).get('plate_text_search')
            return jsonify(status=status,note=NOTE)
        payload = request.get_json(silent=True)
        if not isinstance(payload,dict):
            return jsonify(error='Supply a JSON object with known plate text.'),400
        try:
            targets = hints.normalize_hints(payload.get('plate_texts'))
            maximum = payload.get('max_frames',120)
            if type(maximum) is not int or not 1 <= maximum <= 600:
                raise ValueError('Use an integer max_frames between 1 and 600.')
        except ValueError as error:
            # normalize_hints validation messages must contain no raw text.
            return jsonify(error=str(error)),400
        if not web._REVIEW_EDIT_LOCK.acquire(blocking=False):
            return jsonify(error='Another review edit is saving. Retry shortly.'),503
        try:
            with web.JOBS_LOCK:
                if job['phase'] not in ('review','paused','done'):
                    return jsonify(error='Pause or finish scanning before searching known plate text.'),409
                if job.get('trackbg',{}).get('state') == 'running':
                    return jsonify(error='Finish object tracking before searching known plate text.'),409
                protected = web._SECTIONS.whole_job_error(job)
                if protected:
                    return jsonify(error=protected),409
                try:
                    report_identity = _report_identity(job)
                except OSError:
                    return jsonify(error='No valid scanned source timeline is available to search.'),409
                job['plate_text_request'] = dict(plate_texts=targets,max_frames=maximum,
                    previous_phase=job['phase'],report_identity=report_identity)
                job['cancel'].clear()
                job['stop'].clear()
                job.update(phase='learning',error=None,
                    plate_text_search=dict(state='queued',hint_count=len(targets),note=NOTE))
                learning_session.update_learning(job,'plate_text_search','Searching known plate text')
        finally:
            web._REVIEW_EDIT_LOCK.release()
        web.WORK_Q.put((jid,'plate_text'))
        return jsonify(ok=True,status=job['plate_text_search'],note=NOTE)
