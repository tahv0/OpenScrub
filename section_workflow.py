"""Attached video-section jobs and immutable approved revisions.

The parent report is the commit record. Candidates share source media, but never
write the parent's report until the reviewer accepts their selected interval.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import time
import uuid

import cv2
from flask import abort, jsonify, request

import stop_review
import video_learning
import video_sections


class Sections:
    def __init__(self, web):
        self.web = web

    def read(self, job, verify=False):
        doc = self.web._load_job_report(job)
        if verify or not doc.get('source_identity'):
            cap = cv2.VideoCapture(job['video'])
            try:
                fps = float(cap.get(cv2.CAP_PROP_FPS))
                count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            finally:
                cap.release()
            if not count or not math.isclose(fps, float(doc['render_state']['fps']), rel_tol=1e-5):
                raise video_sections.SectionError('Source video timeline changed; section operation refused.')
            expected = doc.get('provenance', {}).get('input_sha256')
            fingerprint = expected if expected and not verify else self.web.openscrub.sha256_file(job['video'])
            if expected and expected != fingerprint:
                raise video_sections.SectionError('Source video changed; section operation refused.')
            doc.setdefault('provenance', {})['input_sha256'] = fingerprint
            doc['source_identity'] = dict(input_sha256=fingerprint, fps=fps, total_frames=count)
            original = doc['provenance'].get('original_input')
            if verify and original and Path(original).resolve() != Path(job['video']).resolve():
                if not Path(original).is_file():
                    raise video_sections.SectionError('Original video is unavailable; relink it before section work.')
                original_sha = self.web.openscrub.sha256_file(original)
                known = doc['provenance'].get('original_input_sha256')
                if known and known != original_sha:
                    raise video_sections.SectionError('Original video changed; section operation refused.')
                doc['provenance']['original_input_sha256'] = original_sha
        return doc

    @staticmethod
    def items(doc):
        return doc.get('video_sections', {}).get('items', [])

    def item(self, doc, sid):
        return next((s for s in self.items(doc) if s['id'] == sid), None) or abort(404)

    def publish(self, job, doc):
        # A section approval is a full-report boundary. Incorporate any
        # separately committed human corrections before replacing the report.
        self.web._review_journal_snapshot(job)
        meta = doc.setdefault('video_sections', {'schema': 1, 'items': [], 'revision': 0})
        meta['revision'] = meta.get('revision', 0) + 1
        stop_review.atomic_report(Path(job['dir'])/'report.json', doc)
        job['sections_revision'] = meta['revision']

    def busy(self, job):
        if job['phase'] not in ('review', 'paused', 'done', 'error', 'cancelled'):
            abort(409, description='Wait for the current operation before changing sections.')
        if job.get('trackbg', {}).get('state') == 'running':
            abort(409, description='Finish object tracking before changing sections.')

    def whole_job_error(self, job):
        if (job.get('section') or {}).get('role') == 'export':
            return 'This job exports an approved snapshot. Render the saved section to retry; create a candidate to edit or train.'
        try:
            if any(s.get('approved') for s in self.items(self.web._load_job_report(job))):
                return 'This video has approved sections. Rescan or train a section candidate to preserve them.'
        except FileNotFoundError:
            pass
        return None

    def guard_edits(self, job, before, after):
        """Reject edits to locked intervals while allowing unrelated changes."""
        if (job.get('section') or {}).get('role') == 'export':
            abort(409, description='This export uses an approved snapshot. Open a section candidate to edit it.')
        for item in self.items(before):
            if not item.get('approved'):
                continue
            a, b = item['start_frame'], item['end_frame']
            old = video_sections.slice_report(before, a, b)
            new = video_sections.slice_report(after, a, b)
            if any(old.get(k) != new.get(k) for k in ('detections', 'audio_redactions')):
                abort(409, description='This edit changes an approved section. Open a section candidate to revise it.')

    def locked_overlap(self, doc, start, end):
        return any(s.get('approved') and start < s['end_frame'] and end > s['start_frame']
                   for s in self.items(doc))

    def deletion_error(self, job):
        for other in list(self.web.JOBS.values()):
            if other['id'] != job['id'] and (other.get('section') or {}).get('parent_id') == job['id']:
                return 'This source is used by section jobs. Delete those jobs first to keep their source available.'
        # A child can outlive a damaged report or a failed recovery. Its durable
        # source relationship still protects the parent from deletion.
        for link in Path(self.web.JOBS_DIR).glob('*/section-job.json'):
            if link.parent.name == job['id']:
                continue
            try:
                saved = json.loads(link.read_text(encoding='utf-8'))
                parent = saved.get('section', {}).get('parent_id')
            except (OSError, ValueError, AttributeError):
                continue
            if parent == job['id']:
                return 'This source is used by section jobs. Delete those jobs first to keep their source available.'
        return None

    @staticmethod
    def payload():
        data = request.get_json(silent=True)
        if data is None and not request.data:
            return {}
        if not isinstance(data, dict):
            raise video_sections.SectionError('Supply section settings as a JSON object.')
        return data

    def recover(self, job, doc=None):
        link = Path(job['dir'])/'section-job.json'
        if link.is_file():
            saved = json.loads(link.read_text(encoding='utf-8'))
            job['section'] = saved['section']
            job['options'] = saved['options']
            job['name'] = saved['name']
        if doc:
            job['sections_revision'] = doc.get('video_sections', {}).get('revision', 0)

    def restore_interrupted(self, jid, folder):
        link = folder/'section-job.json'
        if not link.is_file():
            return None
        saved = json.loads(link.read_text(encoding='utf-8'))
        if not Path(saved['video']).is_file():
            return None
        import threading
        return dict(id=jid, dir=str(folder), video=saved['video'], name=saved['name'],
                    options=saved['options'], section=saved['section'], phase='error',
                    progress=0., error='Section work was interrupted. The approved result is retained.',
                    log=['Recovered interrupted section job; approved parent unchanged.'],
                    output=None, created=folder.stat().st_mtime, stats={},
                    cancel=threading.Event(), stop=threading.Event())

    def persist_link(self, job):
        stop_review.atomic_report(Path(job['dir'])/'section-job.json',
            {k: job[k] for k in ('video', 'name', 'options', 'section')})

    def options(self, parent, doc, section, model_id, model_mode=None):
        if model_mode is not None and model_mode not in ('refine', 'review', 'filter'):
            raise video_sections.SectionError('Choose a valid learned plate model mode.')
        result = deepcopy(parent['options'])
        # A newly selected checker defaults to suggestions, even if the parent
        # used filtering. new_job validates and durably stores the model's mode.
        result.pop('learned_plate_model_mode', None)
        if model_id and model_mode is not None:
            result['learned_plate_model_mode'] = model_mode
        ident = video_sections.identity(doc)
        a, b = section['start_frame'], section['end_frame']
        # Context is read-only. Only the owned interval is published/approved.
        overlap = max(1, math.ceil(ident['fps'] * 2.5))
        lo, hi = max(0, a-overlap), min(ident['total_frames'], b+overlap)
        duration_frames = ident['total_frames']
        windows = deepcopy(doc['provenance'].get('windows') or result.get('windows') or [])
        if windows:
            windows = [dict(w, t0=max(float(w.get('t0', 0)), lo/duration_frames),
                               t1=min(float(w.get('t1', 1)), hi/duration_frames)) for w in windows]
            windows = [w for w in windows if w['t1'] > w['t0']]
            if not windows:
                raise video_sections.SectionError('Selected section does not intersect the configured detection windows.')
        else:
            windows = [{'t0':lo/duration_frames, 't1':hi/duration_frames}]
        result.update(windows=windows, detect_windows_frac='', skip_start=0, skip_end=0,
                      section_range=[a,b], section_context=[lo,hi], clip_frac='',
                      skip_review=False, learned_plate_model=model_id)
        return result

    def finish_scan(self, job, doc):
        relation = job.get('section')
        if not relation or relation.get('role') != 'candidate':
            return doc
        base = json.loads((Path(job['dir'])/'section-before.json').read_text(encoding='utf-8'))
        doc['source_identity'] = deepcopy(base['source_identity'])
        for key in ('original_input', 'original_input_sha256', 'vfr_normalized', 'hdr_tonemapped', 'hdr_output'):
            if key in base['provenance']:
                doc['provenance'][key] = deepcopy(base['provenance'][key])
        a, b = relation['start_frame'], relation['end_frame']
        # Restrict source-bound decisions before applying them to a partial scan.
        previous = video_sections.slice_report(base, a, b)
        constraints = video_learning.capture_constraints(previous)
        constraints['manual'] = []
        doc = video_learning.apply_constraints(doc, constraints)
        doc = video_sections.carry_manual(previous, doc, a, b)
        return video_sections.slice_report(doc, a, b)

    def register(self, app):
        web = self.web

        @app.errorhandler(video_sections.SectionError)
        def section_error(error):
            return jsonify(error=str(error)), 400

        @app.route('/api/jobs/<jid>/sections', methods=['GET', 'POST'])
        def sections(jid):
            job = web.JOBS.get(jid) or abort(404)
            with web._REVIEW_EDIT_LOCK:
                if web.vault_locked(): abort(423)
                if job.get('section'):
                    return jsonify(section_job=job['section'], items=[])
                self.busy(job)
                doc = self.read(job)
                if request.method == 'GET':
                    return jsonify(items=self.items(doc), identity=doc['source_identity'],
                                   revision=doc.get('video_sections', {}).get('revision', 0))
                data = self.payload()
                start, end = video_sections.bounds(doc, data.get('start'), data.get('end'))
                if any(start < s['end_frame'] and end > s['start_frame'] for s in self.items(doc)):
                    raise video_sections.SectionError('Sections cannot overlap. Select a separate interval.')
                item = dict(id=uuid.uuid4().hex[:12], name=str(data.get('name') or 'Section')[:120],
                            start_frame=start, end_frame=end, approved=None, candidate_id=None)
                doc.setdefault('video_sections', {'schema':1, 'items':[]})['items'].append(item)
                self.publish(job, doc)
                return jsonify(section=item), 201

        @app.route('/api/jobs/<jid>/sections/<sid>/rescan', methods=['POST'])
        def rescan_section(jid, sid):
            job = web.JOBS.get(jid) or abort(404)
            with web._REVIEW_EDIT_LOCK:
                if web.vault_locked(): abort(423)
                self.busy(job)
                doc = self.read(job, verify=True)
                section = self.item(doc, sid)
                try:
                    video_sections.covered(doc, section['start_frame'], section['end_frame'])
                except video_sections.SectionError as error:
                    abort(409, description='Resume the original scan before rescanning this section. ' + str(error))
                current = web.JOBS.get(section.get('candidate_id'))
                if current and current['phase'] in ('queued','scanning','learning','rendering'):
                    abort(409, description='This section already has work in progress.')
                payload = self.payload()
                model_id = payload.get('model_id', '')
                if not isinstance(model_id, str):
                    raise video_sections.SectionError('Choose a valid model.')
                options = self.options(job, doc, section, model_id,
                                       payload.get('learned_plate_model_mode'))
                child = web.new_job(job['video'], options, job['name']+' — '+section['name'])
                child['section'] = dict(parent_id=jid, section_id=sid, role='candidate',
                    start_frame=section['start_frame'], end_frame=section['end_frame'],
                    base_revision=(section.get('approved') or {}).get('revision',0))
                stop_review.atomic_report(Path(child['dir'])/'section-before.json', doc)
                self.persist_link(child)
                section['candidate_id'] = child['id']
                self.publish(job, doc)
                web.WORK_Q.put((child['id'],'scan'))
                return jsonify(job_id=child['id']), 202

        @app.route('/api/jobs/<jid>/sections/<sid>/approve', methods=['POST'])
        def approve_section(jid, sid):
            job = web.JOBS.get(jid) or abort(404)
            with web._REVIEW_EDIT_LOCK:
                if web.vault_locked(): abort(423)
                self.busy(job)
                doc = self.read(job, verify=True)
                section = self.item(doc, sid)
                a,b = section['start_frame'],section['end_frame']
                candidate_id = self.payload().get('candidate_id')
                if candidate_id is not None and not isinstance(candidate_id, str):
                    raise video_sections.SectionError('Choose a valid section candidate.')
                candidate = web.JOBS.get(candidate_id) if candidate_id else None
                if candidate_id:
                    if (not candidate or candidate_id != section.get('candidate_id') or
                        candidate.get('section',{}).get('parent_id') != jid or
                        candidate.get('section',{}).get('section_id') != sid or
                        candidate['phase'] not in ('review','done')):
                        abort(409, description='Review the current successful section candidate before approving it.')
                    if candidate['section']['base_revision'] != (section.get('approved') or {}).get('revision',0):
                        abort(409, description='The approved section changed since this candidate was created.')
                    self.busy(candidate)
                    fresh = self.read(candidate, verify=True)
                    if fresh.get('stop_review'):
                        abort(409, description='Finish scanning this section before approval.')
                    merged = video_sections.replace_range(doc, fresh, a,b)
                    options = deepcopy(candidate['options'])
                else:
                    try: video_sections.covered(doc,a,b)
                    except video_sections.SectionError as error: abort(409, description=str(error))
                    merged = deepcopy(doc)
                    fresh = doc
                    options = deepcopy(job['options'])
                # Use parent metadata; a candidate never owns its neighbours.
                merged['video_sections'] = deepcopy(doc['video_sections'])
                section = self.item(merged,sid)
                revision = (section.get('approved') or {}).get('revision',0)+1
                relative = Path('sections')/sid/('revision-%d-%s.json'%(revision,uuid.uuid4().hex[:8]))
                snapshot = video_sections.slice_report(merged,a,b)
                snapshot.pop('video_sections',None)
                snapshot['section_export_options'] = options
                (Path(job['dir'])/relative).parent.mkdir(parents=True,exist_ok=True)
                stop_review.atomic_report(Path(job['dir'])/relative,snapshot)
                if section.get('approved'):
                    section.setdefault('history',[]).append(section['approved'])
                section['approved'] = dict(revision=revision, report=relative.as_posix(),
                    approved_at=time.time(), model=(fresh.get('verification') or {}).get('name') or
                    (fresh.get('refinement') or {}).get('name') or
                    (fresh.get('learning') or {}).get('version') or 'Original masks')
                section['candidate_id'] = None
                if candidate:
                    merged['render_required'] = True
                    merged['preview_revision'] = uuid.uuid4().hex
                self.publish(job,merged)
                if candidate:
                    job['output']=None
                    web._invalidate_review_previews(job)
                    job.pop('refinement',None)
                    job.pop('learning',None)
                    job.pop('verification',None)
                    if job['phase']=='done': job['phase']='review'
                return jsonify(section=section)

        @app.route('/api/jobs/<jid>/sections/<sid>/export', methods=['POST'])
        def export_section(jid,sid):
            job=web.JOBS.get(jid) or abort(404)
            with web._REVIEW_EDIT_LOCK:
                if web.vault_locked(): abort(423)
                self.busy(job)
                doc=self.read(job,verify=True)
                section=self.item(doc,sid)
                if not section.get('approved'): abort(409,description='Approve this section before exporting it.')
                root=Path(job['dir']).resolve()
                path=(root/section['approved']['report']).resolve()
                if root not in path.parents: abort(400)
                approved=json.loads(path.read_text(encoding='utf-8'))
                options=deepcopy(approved.pop('section_export_options',job['options']))
                # Rendering saved geometry never reloads a newer learned model.
                options.pop('learned_plate_model_mode', None)
                options.update(learned_plate_model='',section_range=[section['start_frame'],section['end_frame']],
                               clip_frac='',preview_mode=False,skip_review=False)
                child=web.new_job(job['video'],options,job['name']+' — '+section['name'])
                child['section']=dict(parent_id=jid,section_id=sid,role='export',
                    start_frame=section['start_frame'],end_frame=section['end_frame'],
                    approved_revision=section['approved']['revision'])
                self.persist_link(child)
                stop_review.atomic_report(Path(child['dir'])/'report.json',approved)
                child['phase']='queued_render'
                section['export_id']=child['id']
                self.publish(job,doc)
                web.WORK_Q.put((child['id'],'render'))
                return jsonify(job_id=child['id']),202
