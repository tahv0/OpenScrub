"""Direct-corner autosave: track semantics and retry-safe local samples."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import openscrub_web as web
from test_plate_quad_editor import plate_job


def add_track(plate_job):
    client, jid, path, folder = plate_job
    doc = json.loads(path.read_text())
    member = deepcopy(doc['detections'][0])
    member.update(cbox=[70, 60, 160, 100], last_seen=.4)
    other = deepcopy(member)
    other['track'] = 99
    doc['detections'] += [member, other]
    path.write_text(json.dumps(doc))
    return client, '/api/jobs/%s/plate_quad/0' % jid, path, folder


def test_autosave_applies_track_and_verifies_only_seed(plate_job):
    client, endpoint, path, folder = add_track(plate_job)
    meta = client.get(endpoint).get_json()
    points = [[54, 77], [126, 74], [129, 91], [52, 94]]
    response = client.post(endpoint, json=dict(points=points, preview_token=meta['preview_token'],
                          autosave=True, edit_id='gesture-1'))
    assert response.status_code == 200, response.get_json()
    rows = json.loads(path.read_text())['detections']
    assert rows[0]['plate_quad'] == rows[1].get('plate_quad')
    assert not rows[2].get('plate_quad')
    assert rows[0]['verified_label'] == 'plate'
    assert not rows[1].get('verified_label')
    assert response.get_json()['applied'] == 2


def test_autosave_retry_is_idempotent_and_latest_sample_replaces_old(plate_job, monkeypatch):
    client, jid, path, folder = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('warm autosave decoded video'))
    first = dict(points=[[54, 77], [126, 74], [129, 91], [52, 94]],
                 preview_token=meta['preview_token'], autosave=True, edit_id='gesture-1')
    response = client.post(endpoint, json=first)
    assert response.status_code == 200
    meta = response.get_json()['preview']
    retry = client.post(endpoint, json=first)  # old token, lost response
    assert retry.status_code == 200, retry.get_json()
    second = dict(points=[[56, 78], [126, 74], [129, 91], [52, 94]],
                  preview_token=meta['preview_token'], autosave=True, edit_id='gesture-2')
    assert client.post(endpoint, json=second).status_code == 200
    entries = [json.loads(s) for s in (folder/'plate_annotations/annotations.jsonl').read_text().splitlines()]
    assert len(entries) == 1
    assert len(list((folder/'plate_annotations').glob('*.jpg'))) == 1
    assert entries[0]['corners'][0] != [0, 0]


def test_autosave_without_real_change_creates_no_sample(plate_job):
    client, jid, path, folder = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    body = dict(points=meta['points'], preview_token=meta['preview_token'], autosave=True, edit_id='no-op')
    response = client.post(endpoint, json=body)
    assert response.status_code == 200
    assert not (folder/'plate_annotations').exists()


def test_autosave_id_cannot_be_reused_for_different_geometry(plate_job):
    client, jid, _, _ = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    body = dict(points=[[54, 77], [126, 74], [129, 91], [52, 94]],
                preview_token=meta['preview_token'], autosave=True, edit_id='one')
    assert client.post(endpoint, json=body).status_code == 200
    body['points'][0] = [57, 78]
    assert client.post(endpoint, json=body).status_code == 409


def test_explicit_legacy_single_frame_save_is_still_supported(plate_job):
    client, endpoint, path, _ = add_track(plate_job)
    response = client.post(endpoint, json=dict(points=[[54, 77], [126, 74], [129, 91], [52, 94]],
                                             apply_track=False))
    assert response.status_code == 200
    assert not json.loads(path.read_text())['detections'][1].get('plate_quad')


def test_direct_card_has_no_edit_mode_or_rotation_controls():
    for old in ['id="qSave"', 'id="qClose"', 'id="qTrack"', 'id="qRotateRight"',
                'id="qRedraw"', '>Edit 4 corners</button>', '.det.editing{']:
        assert old not in web.APP_JS + web.APP_CSS


def test_autosave_js_serializes_writes_preserves_newer_drag_and_retries():
    import shutil
    import subprocess
    if not shutil.which('node'):
        pytest.skip('Node required')
    js = web.APP_JS
    helpers = js[js.index('let QEDIT=null;'):js.index('function initPlateCorners(')]
    harness = r'''
const assert=require('node:assert/strict');
const window={removeEventListener(){},addEventListener(){}};
const document={getElementById(){return null}};
let VLBL={},CUR="test",requests=[],resolve,reject;
let timers=[];
function setTimeout(fn,ms){timers.push({fn,ms});return timers.length;}
function clearTimeout(){}
function reviewRequest(url,options){
 requests.push({url,body:JSON.parse(options.body)});
 return new Promise((ok,no)=>{resolve=ok;reject=no;});
}
''' + helpers + r'''
function state(i){const points=[[20,20],[80,20],[80,60],[20,60]];
 return {i,job:'test',meta:{points:plateCopy(points),crop:[0,0,100,100],preview_token:'old-'+i,track:i},
  img:{},points:plateCopy(points),saved:plateCopy(points),version:0,dirty:false,pending:null,
  status:{textContent:'',scrollIntoView(){}},retry:{hidden:true},draw(){},readyAt:0,failures:0};
}
function move(s,x){const before=plateCopy(s.points);s.points[0][0]=x;commitPlateGesture(s,before);s.readyAt=0;}
function ack(s,request,token){return {data:{preview:{...s.meta,preview_token:token,points:request.body.points}}};}
(async()=>{
 const a=state(0),b=state(1);PLATE_EDITS.set(0,a);PLATE_EDITS.set(1,b);
 move(a,23);move(a,25);assert.equal(requests.length,0,'debounce must not POST each movement');
 const first=pumpPlateSaves();assert.equal(requests.length,1);assert.equal(requests[0].body.points[0][0],25);
 move(a,27);move(b,24);pumpPlateSaves();assert.equal(requests.length,1,'overlapping report writes');
 VLBL[0]='not_plate';resolve(ack(a,requests[0],'new-a'));await first;
 assert.equal(a.points[0][0],27,'old response overwrote latest drag');assert.ok(a.dirty);
 assert.equal(VLBL[0],'not_plate','autosave overwrote a newer review decision');
 const latest=pumpPlateSaves();assert.equal(requests[1].body.preview_token,'new-a');
 resolve(ack(a,requests[1],'newer-a'));await latest;assert.ok(!a.dirty);
 const next=pumpPlateSaves();assert.equal(requests[2].body.apply_track,true);
 reject(new Error('lost response'));await next;
 assert.ok(b.dirty&&b.pending&&b.error);assert.equal(b.retry.hidden,false);
 assert.equal(await flushPlateSaves(),false,'navigation discarded a failed draft');
 const id=requests[2].body.edit_id;await retryPlateSave(b);const retry=pumpPlateSaves();
 assert.equal(requests[3].body.edit_id,id,'uncertain write needs same idempotency key');
 resolve(ack(b,requests[3],'new-b'));await retry;
 assert.equal(await flushPlateSaves(),true);
 // An older response also must not erase a drag that has not yet been released.
 move(a,28);const inflight=pumpPlateSaves();
 a.drag={id:1,before:plateCopy(a.points)};a.points[0][0]=29;
 resolve(ack(a,requests[4],'last'));await inflight;
 assert.equal(a.points[0][0],29);assert.equal(await flushPlateSaves(),false);
 a.drag=null;
 // Busy decoder has bounded retries/backoff, not a request storm.
 move(b,26);
 for(let n=0;n<4;n++){b.readyAt=0;const busy=pumpPlateSaves();reject(Object.assign(new Error('busy'),{status:503}));await busy;}
 assert.ok(b.error&&b.dirty);assert.ok(requests.length<12);
 console.log('autosave queue, latest-wins, labels, retries, navigation and backoff OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout+result.stderr


def test_autosave_retry_refuses_replaced_source(plate_job):
    import os
    client, jid, path, _ = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    body = dict(points=[[54, 77], [126, 74], [129, 91], [52, 94]],
                preview_token=meta['preview_token'], autosave=True, edit_id='same-id')
    assert client.post(endpoint, json=body).status_code == 200
    source = web.JOBS[jid]['video']
    stat = os.stat(source)
    os.utime(source, ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000000))
    assert client.post(endpoint, json=body).status_code == 409
