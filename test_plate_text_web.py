"""Transactional known-text discovery against real small CPU video sources."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import cv2
from flask import Flask
import numpy as np
import pytest

import confirmed_findings
import finding_previews
import openscrub_web as web
import plate_text_web as search
import stop_review


@pytest.fixture
def search_job(tmp_path,monkeypatch):
    root = tmp_path/'jobs'
    root.mkdir()
    monkeypatch.setattr(web,'JOBS_DIR',str(root))
    monkeypatch.setattr(web,'JOBS',{})
    monkeypatch.setattr(web,'vault_locked',lambda: False)
    video = tmp_path/'synthetic.mp4'
    writer = cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(96,64))
    assert writer.isOpened()
    for index in range(12):
        writer.write(np.full((64,96,3),20*index,np.uint8))
    writer.release()
    job = web.new_job(str(video),{'categories':'plate'},video.name)
    job['phase'] = 'review'
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    doc = dict(provenance=dict(input=str(video),input_sha256=sha),
        render_state=dict(fps=10.,cum=[[i,2*i] for i in range(12)],bands=[[0,0]]*12),
        source_identity=dict(input_sha256=sha,fps=10.,total_frames=12,width=96,height=64),
        detections=[])
    path = Path(job['dir'])/'report.json'
    path.write_text(json.dumps(doc))
    queued = []
    monkeypatch.setattr(web.WORK_Q,'put',queued.append)
    app = Flask('known_text_tests')
    search.install(app,web)
    return app.test_client(),job,video,path,queued


def proposal(partial=False):
    return dict(source_box=[24,20,70,44],protection_box=[24,20,70,44],
        text_box=[45,22,60,36],plate_quad=[[24,20],[70,20],[70,44],[24,44]],
        observed_text='BC123' if partial else 'ABC123',matched_target='ABC123',
        matched_text='BC123' if partial else 'ABC123',match_kind='partial' if partial else 'exact',
        match_strength=.4 if partial else 1.,target_coverage=5/6 if partial else 1.,
        ocr_confidence=.97,orientation=dict(rotation=180,mirrored=True),
        provenance=dict(method='known_plate_text',candidate='provided_region',
                        boundary_requires_review=False))


def queue(client,job,**payload):
    return client.post('/api/jobs/%s/plate-text-search'%job['id'],
                       json=dict(plate_texts='abc 123',**payload))


def run_search(fixture,monkeypatch,reader=None,**payload):
    client,job,*_ = fixture
    monkeypatch.setattr(search.hints,'search_frame',reader or (lambda *a,**k:[proposal()]))
    response = queue(client,job,**payload)
    assert response.status_code == 200,response.get_data(as_text=True)
    search.perform(job)
    assert job['error'] is None,job['error']


def test_exact_indices_source_coordinates_cached_jpegs_and_explicit_archive(search_job,monkeypatch):
    client,job,_,path,queued = search_job
    calls = []
    def reader(frame,targets,regions=None,cancelled=None):
        calls.append((float(frame.mean()),targets,regions))
        return [proposal()]
    original = search.cv2.VideoCapture
    opens = []
    def capture(*args):
        opens.append(args)
        return original(*args)
    monkeypatch.setattr(search.cv2,'VideoCapture',capture)
    run_search(search_job,monkeypatch,reader)
    assert queued == [(job['id'],'plate_text')]
    assert len(opens) == 1
    doc = json.loads(path.read_text())
    assert doc['plate_text_search']['sampled_frames'] == [0,10,11]
    assert [row['frame_index'] for row in doc['detections']] == [0,10,11]
    assert [round(mean/20) for mean,_,_ in calls] == [0,10,11]
    assert all(targets == ['ABC123'] for _,targets,_ in calls)
    assert doc['provenance']['input_sha256'] == hashlib.sha256(search_job[2].read_bytes()).hexdigest()
    assert doc['detections'][1]['cbox'] == [14.,0.,60.,24.]
    assert doc['detections'][1]['aoff'] == [10.,20.]
    for row in doc['detections']:
        assert row['verified_label'] == '' and row['enabled']
        assert not row.get('human_region_confirmed') and not row.get('human_confirmation')
        assert row['confidence'] == 0 and row['plate_text_evidence']['review_status']=='unreviewed'
        meta,jpeg = finding_previews.lookup(job['dir'],row,doc['render_state'])
        assert meta['frame'] == row['frame_index'] and meta['box'] == [24.,20.,70.,44.]
        assert cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR) is not None
    assert confirmed_findings.list_findings(Path(web.JOBS_DIR)/'confirmed_findings')['total'] == 0
    assert job['phase'] == 'review' and doc['render_required']
    status = client.get('/api/jobs/%s/plate-text-search'%job['id']).get_json()
    assert status['status']['state'] == 'completed'
    assert 'not complete redaction' in status['note']
    assert 'ABC123' not in json.dumps(status)


def test_partial_candidate_keeps_full_number_fallback(search_job,monkeypatch):
    run_search(search_job,monkeypatch,lambda *a,**k:[proposal(True)],max_frames=1)
    doc = json.loads(search_job[3].read_text())
    row = doc['detections'][0]
    assert row['cbox'] == [24.,20.,70.,44.]
    assert row['plate_text_evidence']['match_kind'] == 'partial'
    assert not row.get('poly') and not row.get('plate_quad')
    assert row['fallback_reason'] == 'known_text_candidate' and row['mask_pad'] == -1
    import openscrub
    detections,_,_ = openscrub.load_report(search_job[3])
    assert detections[0].cbox == (24.,20.,70.,44.) and not detections[0].poly


def test_existing_human_geometry_and_output_choices_are_preserved(search_job,monkeypatch):
    _,job,_,path,_ = search_job
    doc = json.loads(path.read_text())
    human = dict(category='plate',text='human',cbox=[24,20,70,44],aoff=[0,0],
        t_start=0.,t_end=0.,last_seen=0.,frame_index=0,confidence=.2,track=5,dense=True,
        enabled=False,verified_label='not_plate',output_choice_explicit=True,
        human_region_confirmed=True,plate_quad=[[.1,.1],[.9,.1],[.9,.9],[.1,.9]],
        human_confirmation=dict(label='negative',source='explicit'),
        poly=[[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]])
    doc['detections'] = [deepcopy(human)]
    path.write_text(json.dumps(doc))
    seen = []
    def reader(*a,**k):
        seen.extend(k['regions'])
        return [proposal()]
    run_search(search_job,monkeypatch,reader,max_frames=1)
    after = json.loads(path.read_text())['detections']
    assert len(after) == 1
    for key,value in human.items():
        assert after[0][key] == value
    assert after[0]['plate_text_evidence']['matched_target']=='ABC123'
    assert seen[0]['source_box'] == [24.,20.,70.,44.]
    assert seen[0]['plate_quad'][0] == [28.6,22.4]


def test_repeated_search_updates_evidence_without_duplicate_rows(search_job,monkeypatch):
    run_search(search_job,monkeypatch,max_frames=1)
    run_search(search_job,monkeypatch,lambda *a,**k:[proposal(True)],max_frames=1)
    doc = json.loads(search_job[3].read_text())
    assert len(doc['detections']) == 1
    assert doc['detections'][0]['plate_text_evidence']['match_kind'] == 'partial'
    assert doc['plate_text_search']['added'] == 0


def test_cancellation_keeps_report_byte_identical(search_job,monkeypatch):
    client,job,_,path,_ = search_job
    before = path.read_bytes()
    def reader(*a,**k):
        job['cancel'].set()
        return [proposal()]
    monkeypatch.setattr(search.hints,'search_frame',reader)
    assert queue(client,job).status_code == 200
    search.perform(job)
    assert path.read_bytes() == before
    assert job['phase']=='review' and job['plate_text_search']['state']=='cancelled'
    assert not job['cancel'].is_set() and 'plate_text_request' not in job


def test_source_change_is_refused_without_report_or_sensitive_diagnostic(search_job,monkeypatch):
    client,job,video,path,_ = search_job
    before = path.read_bytes()
    monkeypatch.setattr(search.hints,'search_frame',lambda *a,**k: pytest.fail('Changed source cannot reach OCR'))
    assert queue(client,job).status_code == 200
    video.write_bytes(video.read_bytes()+b'synthetic change')
    search.perform(job)
    assert path.read_bytes() == before and job['plate_text_search']['state']=='failed'
    assert 'ABC123' not in job['error'] and str(video) not in job['error']


def test_report_changed_during_search_is_not_overwritten(search_job,monkeypatch):
    client,job,_,path,_ = search_job
    changed = None
    def reader(*a,**k):
        nonlocal changed
        doc = json.loads(path.read_text())
        doc['human_note'] = 'preserve this newer edit'
        path.write_text(json.dumps(doc))
        changed = path.read_bytes()
        return [proposal()]
    monkeypatch.setattr(search.hints,'search_frame',reader)
    assert queue(client,job,max_frames=1).status_code == 200
    search.perform(job)
    assert path.read_bytes() == changed and job['plate_text_search']['state']=='failed'


def test_source_changed_during_search_is_not_published(search_job,monkeypatch):
    client,job,video,path,_ = search_job
    before = path.read_bytes()
    def reader(*a,**k):
        video.write_bytes(video.read_bytes()+b'source changed while decoding')
        return [proposal()]
    monkeypatch.setattr(search.hints,'search_frame',reader)
    assert queue(client,job,max_frames=1).status_code == 200
    search.perform(job)
    assert path.read_bytes()==before and job['plate_text_search']['state']=='failed'


def test_request_pins_report_snapshot_before_worker_starts(search_job,monkeypatch):
    client,job,_,path,_ = search_job
    monkeypatch.setattr(search.hints,'search_frame',lambda *a,**k: pytest.fail('Changed review cannot reach OCR'))
    assert queue(client,job,max_frames=1).status_code == 200
    doc = json.loads(path.read_text())
    doc['human_note'] = 'new review'
    path.write_text(json.dumps(doc))
    before = path.read_bytes()
    search.perform(job)
    assert path.read_bytes()==before and job['plate_text_search']['state']=='failed'


def test_paused_section_intersects_actual_scanned_prefix(search_job,monkeypatch):
    _,job,_,path,_ = search_job
    doc = stop_review.with_checkpoint(json.loads(path.read_text()),8,12,{})
    job.update(phase='paused',options={'section_context':[5,12]})
    path.write_text(json.dumps(doc))
    run_search(search_job,monkeypatch)
    doc = json.loads(path.read_text())
    assert doc['plate_text_search']['sampled_frames'] == [5,7]
    assert all(5 <= row['frame_index'] < 8 for row in doc['detections'])
    assert job['phase'] == 'paused' and doc['stop_review']['next_frame'] == 8


def test_scan_window_gaps_are_never_searched(search_job,monkeypatch):
    _,job,_,path,_ = search_job
    doc = json.loads(path.read_text())
    doc['provenance']['settings'] = {'detect_windows':'0.2-0.4,0.8-1.0'}
    path.write_text(json.dumps(doc))
    # detect_windows are absolute seconds in the canonical coverage helper.
    run_search(search_job,monkeypatch)
    doc = json.loads(path.read_text())
    assert doc['plate_text_search']['sampled_frames'] == [2,3,8,9]


@pytest.mark.parametrize('maximum',[True,False,None,0,601,-1,2.5,'10',[],{}])
def test_max_frames_requires_bounded_integer(search_job,maximum):
    client,job,_,path,queued = search_job
    before = path.read_bytes()
    assert queue(client,job,max_frames=maximum).status_code == 400
    assert job['phase']=='review' and not queued and path.read_bytes()==before


@pytest.mark.parametrize('targets',[None,'',[],True,123,['ABC123',5],'A1','X'*17])
def test_hint_types_and_sizes_are_checked_before_queue(search_job,targets):
    client,job,_,path,queued = search_job
    before = path.read_bytes()
    response = client.post('/api/jobs/%s/plate-text-search'%job['id'],json={'plate_texts':targets})
    assert response.status_code == 400
    assert job['phase']=='review' and not queued and path.read_bytes()==before


@pytest.mark.parametrize('phase',['scanning','learning','rendering'])
def test_active_work_is_not_interrupted(search_job,phase):
    client,job,*_ = search_job
    job['phase'] = phase
    assert queue(client,job).status_code == 409


def test_tracking_and_approved_sections_are_guarded(search_job,monkeypatch):
    client,job,_,path,queued = search_job
    job['trackbg'] = dict(state='running')
    assert queue(client,job).status_code == 409
    job.pop('trackbg')
    monkeypatch.setattr(web._SECTIONS,'whole_job_error',lambda job:'Approved section is locked.')
    assert queue(client,job).status_code == 409
    assert not queued


def test_section_guard_rechecked_before_publication(search_job,monkeypatch):
    client,job,_,path,_ = search_job
    before = path.read_bytes()
    def reader(*a,**k):
        monkeypatch.setattr(web._SECTIONS,'guard_edits',lambda *a: (_ for _ in ()).throw(ValueError('locked')))
        return [proposal()]
    monkeypatch.setattr(search.hints,'search_frame',reader)
    assert queue(client,job,max_frames=1).status_code==200
    search.perform(job)
    assert path.read_bytes()==before and job['plate_text_search']['state']=='failed'


def test_ocr_exception_cannot_echo_sensitive_text(search_job,monkeypatch):
    client,job,_,path,_ = search_job
    before = path.read_bytes()
    def reader(*a,**k):
        raise RuntimeError('secret OCR ABC123 /private/path')
    monkeypatch.setattr(search.hints,'search_frame',reader)
    assert queue(client,job,max_frames=1).status_code == 200
    search.perform(job)
    assert path.read_bytes()==before
    assert 'ABC123' not in json.dumps(job['learning'])+job['error']


def test_spatial_sampling_has_bound_and_endpoints_without_full_timeline_allocation():
    selected = search._samples([(100,1_000_000_000)],30.,120)
    assert len(selected)==120 and selected[0]==100 and selected[-1]==999_999_999
    assert selected==sorted(set(selected))
