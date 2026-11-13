"""Drawing plate geometry does not silently create a human training label."""
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import learning_session
import openscrub_web as web
from test_findings_web import findings_job


QUAD = [[.05, .1], [.95, .1], [.95, .9], [.05, .9]]
PAYLOAD = {'box': [24, 24, 70, 40], 't_ref': .4, 't0': .2, 't1': .6,
           'plate_quad': QUAD}


@pytest.fixture
def drawn_job(findings_job, monkeypatch):
    client, job, video, path = findings_job
    doc = json.loads(path.read_text())
    doc['detections'] = []
    path.write_text(json.dumps(doc))

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    # The tracker is the expensive external operation. Keep publication,
    # classification, compact previews, and the training collector real.
    def track(video_path, box, t_ref, t0, t1, cb, person_det):
        assert video_path == job['video'] and person_det is None
        assert (box, t_ref, t0, t1) == ([24., 24., 70., 40.], .4, .2, .6)
        return [(.2, [22, 24, 68, 40], .9),
                (.4, [24, 24, 70, 40], 1.),
                (.6, [26, 24, 72, 40], .9)]

    detector_calls = []

    def detector(*args, **kwargs):
        detector_calls.append((args, kwargs))
        return SimpleNamespace(net=None, ort=None)

    monkeypatch.setattr(web.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(web.openscrub, 'track_manual_region', track)
    monkeypatch.setattr(web.openscrub, 'PersonDetector', detector)
    return client, job, video, path, detector_calls


def test_drawn_plate_stays_a_draft_until_explicit_classification(drawn_job, monkeypatch):
    client, job, _, path, _ = drawn_job
    original_frame_at = web._frame_at
    frame_reads = []

    def counted_frame(*args, **kwargs):
        frame_reads.append(1)
        return original_frame_at(*args, **kwargs)

    monkeypatch.setattr(web, '_frame_at', counted_frame)
    response = client.post(f'/api/jobs/{job["id"]}/track_object',
                           json={**PAYLOAD, 'require_confirmation': True})
    assert response.status_code == 200
    assert job['trackbg'] == {'state': 'done', 'added': 3, 'error': None}
    doc = json.loads(path.read_text())
    rows = doc['detections']
    assert all(row['plate_quad'] == QUAD and row['enabled'] for row in rows)
    assert all(not row.get('verified_label') and not row.get('human_confirmation') for row in rows)
    assert [row.get('human_region_confirmed', False) for row in rows] == [False, True, False]
    assert not (Path(job['dir']) / 'plate_annotations').exists()
    assert frame_reads == [], 'A draft must not reopen the video to write a verified sample'
    assert client.get('/api/findings').get_json()['total'] == 0
    feedback = learning_session.collect_feedback(
        job, doc, read_frame=lambda i: pytest.fail('Draft geometry is not training supervision'))
    assert feedback['samples'] == {}

    # The exact manually drawn seed can become one permanent example only
    # after Is a plate. Propagated tracker guesses are not separate examples.
    response = client.post(f'/api/jobs/{job["id"]}/confirm/1', json={'label': 'positive'})
    assert response.status_code == 200, response.get_data(as_text=True)
    entry = response.get_json()['finding']
    assert entry['label'] == 'positive' and entry['shape_confirmed'] is True
    assert entry['frame'] == 4
    assert client.get('/api/findings').get_json()['total'] == 1
    assert not (Path(job['dir']) / 'plate_annotations').exists()
    job['model_root'] = web.learned_models_root()
    feedback = learning_session.collect_feedback(
        job, web._load_job_report(job),
        read_frame=lambda i: pytest.fail('Confirmed collection uses the stored JPEG'))
    assert len(feedback['samples']) == 1
    assert next(iter(feedback['samples'].values()))['label'] == 'positive'


@pytest.mark.parametrize('require_confirmation', [True, False])
def test_plate_tracking_does_not_construct_an_unused_person_detector(drawn_job, require_confirmation):
    client, job, _, _, detector_calls = drawn_job
    response = client.post(f'/api/jobs/{job["id"]}/track_object',
                           json={**PAYLOAD, 'require_confirmation': require_confirmation})
    assert response.status_code == 200 and job['trackbg']['added'] == 3
    assert detector_calls == [], 'The person detector is never passed to plate tracking'


@pytest.mark.parametrize('flag', [None, False, 'true', 1])
def test_legacy_drawn_plate_requests_keep_the_existing_confirmation_contract(drawn_job, flag):
    client, job, _, path, _ = drawn_job
    payload = dict(PAYLOAD)
    if flag is not None:
        payload['require_confirmation'] = flag
    response = client.post(f'/api/jobs/{job["id"]}/track_object', json=payload)
    assert response.status_code == 200 and job['trackbg']['added'] == 3
    rows = json.loads(path.read_text())['detections']
    assert sum(row.get('verified_label') == 'plate' for row in rows) == 1
    entries = (Path(job['dir']) / 'plate_annotations' / 'annotations.jsonl').read_text().splitlines()
    assert len(entries) == 1 and json.loads(entries[0])['verified_by_user'] is True
    assert client.get('/api/findings').get_json()['total'] == 0


def test_draw_plate_ui_requests_explicit_confirmation():
    if not shutil.which('node'):
        pytest.skip('Node is required for the production drawing handler')
    handler = web.APP_JS[web.APP_JS.index('async function beTrackGo('):
                         web.APP_JS.index('async function beScrub(')]
    source = r"""
const assert=require('node:assert/strict');
const status={style:{}},posts=[];
const document={getElementById(){return status}};
const BE={win:[.2,.6],t:.4},CUR='fixture';
async function fetch(url,options){posts.push({url,body:JSON.parse(options.body)});return {ok:true}};
function setInterval(){return 1};
""" + handler + r"""
(async()=>{
 await beTrackGo([24,24,70,40],[[0,0],[1,0],[1,1],[0,1]]);
 assert.equal(posts[0].body.require_confirmation,true,'Drawing coordinates must not classify a plate');
 await beTrackGo([24,24,70,40]);
 assert.equal(posts[1].body.plate_quad,undefined);
 assert.equal(posts[1].body.require_confirmation,undefined,'Generic object tracking keeps its contract');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run(['node', '-e', source], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
