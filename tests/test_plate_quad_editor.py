"""Plate corner editing exercises the shipped exact editor and transactions."""
import json

import pytest

from test_review_save_failures import EXACT, run_js
from test_plate_quad import plate, quad_edit
from test_exact_samples import exact, post, raw
from test_job_lifecycle import store


PLATE = EXACT + r"""
async function plateDraft(eligibility='verification_required'){
 const m=strictDraft();
 for(const id of ['beQuad','beQuadReset','beQuadStatus'])elements.set(id,el());
 const pending=beScrub(),body=sample();const row=body.boxes[0];
 row.category='plate';row.quad_context_eq='c'.repeat(64);row.quad_baseline=null;
 row.quad_edit_eligibility=eligibility;row.quad_eligibility='none';
 await reply(body);candidates.shift().resolve();await tick();await pending;
 assert(beReady(m.view));return m;
}
function event(m,type,x,y,id=1){m.cv.events[type]({clientX:x,clientY:y,pointerId:id});}
function selectPlate(m){event(m,'pointerdown',100,60);event(m,'pointerup',100,60);assert.equal(BE.sel,0);}
"""


def test_plate_corners_use_current_sample_and_write_pixel_edges():
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);
    assert.equal(typeof beQuadMode,'function','selected plate needs an explicit corner editor');
    beQuadMode();assert(m.view.quadEdit,'corner mode did not bind current view');
    const [x,y]=m.view.quadEdit.points[0];event(m,'pointerdown',x*m.view.transform.sx,y*m.view.transform.sy);
    event(m,'pointermove',(x+12)*m.view.transform.sx,(y+8)*m.view.transform.sy);
    event(m,'pointerup',(x+12)*m.view.transform.sx,(y+8)*m.view.transform.sy);
    assert.deepEqual(BE.quads[0].points[0],[x+12,y+8]);
    const save=saveAndRender(),sent=calls.at(-1).body;
    assert.deepEqual(sent.manual_plate_quads['0'].points,BE.quads[0].points);
    assert.equal(sent.geometry_preconditions['0'].index,4);
    assert.equal(sent.geometry_preconditions['0'].quad_context_eq,'c'.repeat(64));
    """)


def test_plate_ack_returns_whole_written_quad_for_safe_client_reconciliation(plate):
    edits = quad_edit(plate)
    response = post(plate, **edits)
    assert response.status_code == 200
    saved = raw(plate)['detections'][0]['manual_plate_quad']
    ack = response.get_json()['geometry_rows']['0']
    assert ack['manual_plate_quad'] == saved
    assert json.loads(ack['quad_baseline']) == saved


def test_plate_unavailable_and_unverified_saved_geometry_are_honest():
    run_js(PLATE+r"""const m=await plateDraft('unavailable');selectPlate(m);beQuadControls(m.view);
    assert.equal(elements.get('beQuad').disabled,true);beQuadMode();assert(!m.view.quadEdit);
    const row=BE.raw[0];row.quad_edit_eligibility='verification_required';row.quad_eligibility='unverified';
    row.manual_plate_quad={version:1,source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:'opencv-ffmpeg-zero-cfr-v1',timeline_eq:'a'.repeat(64)},
     points:[[.05,.05],[.1,.05],[.1,.1],[.05,.1]]};row.quad_baseline=JSON.stringify(row.manual_plate_quad);
    beQuadControls(m.view);assert(elements.get('beQuadStatus').textContent.includes('not shown'));
    assert(elements.get('beQuadStatus').textContent.includes('verified on Save'));
    beQuadMode();assert.deepEqual(m.view.quadEdit.points[0],[128,76]);
    assert.equal(Object.keys(BE.quads).length,0,'opening corners created an edit');""")


def test_valid_saved_plate_uses_its_inspected_frame_and_reset_is_explicit():
    run_js(PLATE+r"""const m=await plateDraft('ready');selectPlate(m);const row=BE.raw[0];
    row.quad_eligibility='eligible_sdr_frame';row.manual_plate_quad={version:1,
     source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:'opencv-ffmpeg-zero-cfr-v1',timeline_eq:'a'.repeat(64)},
     points:[[.1,.2],[.4,.2],[.4,.4],[.1,.4]]};row.quad_baseline=JSON.stringify(row.manual_plate_quad);
    beQuadMode();assert.deepEqual(m.view.quadEdit.points[0],[64,72]);beQuadReset();
    assert.equal(BE.quads[0],null);assert.equal(m.view.quadEdit,null);
    const p=saveAndRender(),sent=calls.at(-1).body;assert.equal(sent.manual_plate_quads['0'],null);
    assert.equal(sent.geometry_preconditions['0'].quad_context_eq,'c'.repeat(64));""")


def test_quad_invalid_drag_and_resize_cancel_do_not_corrupt_draft():
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();const tr=m.view.transform;
    const start=copyEdit(m.view.quadEdit.points);event(m,'pointerdown',start[0][0]*tr.sx,start[0][1]*tr.sy);
    event(m,'pointermove',start[2][0]*tr.sx,start[2][1]*tr.sy);
    assert.equal(Object.keys(BE.quads).length,0,'crossed corners became a draft');
    event(m,'pointermove',(start[0][0]+10)*tr.sx,(start[0][1]+5)*tr.sy);
    const applied=JSON.stringify(BE.quads);assert(BE.drag);
    m.img.getBoundingClientRect=()=>({width:250,height:140.625});m.view.sync();assert.equal(BE.drag,null);
    event(m,'pointermove',180,120);event(m,'pointerup',180,120);
    assert.equal(JSON.stringify(BE.quads),applied);assert(m.view.quadEdit);""")


def test_quad_cannot_move_between_inspected_frame_families():
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+10)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    const before=JSON.stringify(BE.quads);elements.get('beT').value=.3;const pending=beScrub();
    const data=sample(.3,{index:5,canonical_s:5/24,observed_s:5/24});data.boxes[0].category='plate';
    data.boxes[0].quad_context_eq='c'.repeat(64);data.boxes[0].quad_edit_eligibility='ready';data.boxes[0].quad_eligibility='none';
    await reply(data);candidates.shift().resolve();await tick();await pending;selectPlate(m);
    assert.equal(elements.get('beQuad').disabled,true);assert(elements.get('beQuadStatus').textContent.includes('another frame'));
    beQuadMode();assert(!m.view.quadEdit);assert.equal(JSON.stringify(BE.quads),before);
    assert(EDITS.status.includes('another frame'));""")


def test_quad_ack_retains_newer_corners_and_independent_choices():
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+10)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    const pending=saveAndRender(),sent=copyEdit(calls.at(-1).body),q=m.view.quadEdit.points[1];
    event(m,'pointerdown',q[0]*tr.sx,q[1]*tr.sy);event(m,'pointermove',(q[0]-10)*tr.sx,(q[1]+5)*tr.sy);event(m,'pointerup',0,0);
    const newer=copyEdit(BE.quads[0]);applyDet(1,false);BE.audio=[{t0:0,t1:1,mode:'mute'}];BE.audioLoaded=true;
    const pc=sent.geometry_preconditions['0'],saved={version:1,source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:pc.policy,timeline_eq:pc.timeline_eq},
     points:sent.manual_plate_quads['0'].points.map(p=>[p[0]/640,p[1]/360])};
    await reply({ok:true,geometry_rows:{'0':{...pc,row_context_eq:'e'.repeat(64),manual_plate_quad:saved,quad_baseline:JSON.stringify(saved)}}});await pending;
    assert.deepEqual(BE.quads[0],newer);assert.equal(BE.geometry[0].precondition.row_context_eq,'e'.repeat(64));
    assert.equal(BE.geometry[0].precondition.quad_baseline,JSON.stringify(saved));
    assert.equal(EDITS.enabled[1],false);assert.equal(BE.audio.length,1);
    assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);""")


@pytest.mark.parametrize('kind', ['missing', 'wrong_points', 'wrong_frame', 'missing_token', 'wrong_token'])
def test_quad_malformed_ack_preserves_entire_submission(kind):
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+10)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    applyDet(1,false);const pending=saveAndRender(),sent=copyEdit(calls.at(-1).body),pc=sent.geometry_preconditions['0'];
    const record={version:1,source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:pc.policy,timeline_eq:pc.timeline_eq},
     points:sent.manual_plate_quads['0'].points.map(p=>[p[0]/640,p[1]/360])};
    const row={...pc,row_context_eq:'e'.repeat(64),manual_plate_quad:record,quad_baseline:JSON.stringify(record)};
    if(KIND==='missing')delete row.manual_plate_quad;
    if(KIND==='wrong_points')record.points[0][0]+=.01;
    if(KIND==='wrong_frame')record.frame.index=5;
    if(KIND==='missing_token')delete row.quad_baseline;
    if(KIND==='wrong_token')row.quad_baseline=JSON.stringify({...record,points:[[.1,.1],[.2,.1],[.2,.2],[.1,.2]]});
    await reply({ok:true,geometry_rows:{'0':row}});await pending;
    assert(BE.quads[0]);assert.equal(EDITS.enabled[1],false);assert(EDITS.submitted.everUncertain);
    assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);""".replace('KIND',json.dumps(kind)))


def test_switching_from_plate_corners_to_add_mode_keeps_add_usable():
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();assert(m.view.quadEdit);
    beAddMode();assert.equal(m.view.quadEdit,null,'corner mode intercepted Add box');assert(BE.add);
    event(m,'pointerdown',210,100);event(m,'pointerup',210,100);assert(BE.addAnchor);
    """)


def test_lost_quad_ack_replays_identically_then_retains_newer_quad():
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+10)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    const first=saveAndRender(),sent=copyEdit(calls.at(-1).body);queue.shift().reject(Error('lost ACK'));await tick();await first;
    const q=m.view.quadEdit.points[1];event(m,'pointerdown',q[0]*tr.sx,q[1]*tr.sy);
    event(m,'pointermove',(q[0]-10)*tr.sx,(q[1]+5)*tr.sy);event(m,'pointerup',0,0);const newer=copyEdit(BE.quads[0]);
    const retry=saveAndRender();assert.deepEqual(calls.at(-1).body,sent);
    const pc=sent.geometry_preconditions['0'],record={version:1,source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:pc.policy,timeline_eq:pc.timeline_eq},
     points:sent.manual_plate_quads['0'].points.map(p=>[p[0]/640,p[1]/360])};
    await reply({ok:true,geometry_rows:{'0':{...pc,row_context_eq:'e'.repeat(64),manual_plate_quad:record,quad_baseline:JSON.stringify(record)}}});await retry;
    assert.deepEqual(BE.quads[0],newer);assert.equal(BE.geometry[0].precondition.row_context_eq,'e'.repeat(64));
    assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);""")


def test_box_ack_retirement_retains_newer_corner_draft():
    run_js(PLATE+r"""const m=await plateDraft('ready');selectPlate(m);const row=BE.raw[0];row.quad_eligibility='eligible_sdr_frame';
    row.manual_plate_quad={version:1,source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:'opencv-ffmpeg-zero-cfr-v1',timeline_eq:'a'.repeat(64)},
     points:[[.22,.24],[.46,.24],[.46,.5],[.22,.5]]};row.quad_baseline=JSON.stringify(row.manual_plate_quad);
    event(m,'pointerdown',100,60);event(m,'pointermove',105,65);event(m,'pointerup',105,65);
    assert(BE.ov[0]);const pending=saveAndRender(),sent=copyEdit(calls.at(-1).body),pc=sent.geometry_preconditions['0'];
    assert.equal(pc.quad_context_eq,'c'.repeat(64));assert(!sent.manual_plate_quads);
    beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+8)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    const newer=copyEdit(BE.quads[0]);
    await reply({ok:true,geometry_rows:{'0':{...pc,row_context_eq:'e'.repeat(64),base:{...pc.base,cbox:sent.box_overrides['0']},manual_plate_quad:null,quad_baseline:null}}});await pending;
    assert.deepEqual(BE.quads[0],newer);assert.equal(BE.geometry[0].precondition.row_context_eq,'e'.repeat(64));
    assert(!Object.prototype.hasOwnProperty.call(BE.raw[0],'manual_plate_quad'));assert.equal(BE.raw[0].quad_eligibility,'none');
    assert.equal(BE.geometry[0].precondition.quad_baseline,null);
    assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);""")


def test_quad_discard_removes_only_selected_geometry_and_keeps_other_drafts():
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+10)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    BE.times[9]=[0,1];applyDet(1,false);MAN.push({manual_id:'other'});BE.audio.push({t0:0,t1:1});confirm=()=>true;
    await reviewDiscard('row:0');assert(!(0 in BE.quads));assert(!(0 in BE.geometry));assert(BE.times[9]);
    assert.equal(EDITS.enabled[1],false);assert.equal(MAN[0].manual_id,'other');assert.equal(BE.audio.length,1);""")


def test_retirement_ack_cannot_clear_an_unknown_opaque_quad():
    run_js(PLATE+r"""const m=await plateDraft('ready');selectPlate(m);const row=BE.raw[0];row.quad_eligibility='unsupported';row.manual_plate_quad={version:99,opaque:true};
    event(m,'pointerdown',100,60);event(m,'pointermove',105,65);event(m,'pointerup',105,65);
    const pending=saveAndRender(),sent=copyEdit(calls.at(-1).body),pc=sent.geometry_preconditions['0'];
    await reply({ok:true,geometry_rows:{'0':{...pc,row_context_eq:'e'.repeat(64),base:{...pc.base,cbox:sent.box_overrides['0']},manual_plate_quad:null,quad_baseline:null}}});await pending;
    assert(BE.ov[0]);assert(EDITS.submitted.everUncertain);assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);""")


def test_box_edit_carries_valid_quad_baseline_for_safe_lost_ack_replay():
    run_js(PLATE+r"""const m=await plateDraft('ready');selectPlate(m);const row=BE.raw[0];row.quad_eligibility='eligible_sdr_frame';
    row.manual_plate_quad={version:1,source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:'opencv-ffmpeg-zero-cfr-v1',timeline_eq:'a'.repeat(64)},
     points:[[.22,.24],[.46,.24],[.46,.5],[.22,.5]]};
    row.quad_baseline=JSON.stringify(row.manual_plate_quad).replace('0.22','0.220');
    event(m,'pointerdown',100,60);event(m,'pointermove',105,65);event(m,'pointerup',105,65);
    const save=saveAndRender(),pc=calls.at(-1).body.geometry_preconditions['0'];
    assert.equal(pc.quad_baseline,row.quad_baseline,'baseline witness must be copied without JSON round-tripping');
    """)


@pytest.mark.parametrize('change', ['source', 'timeline', 'row'])
def test_pending_quad_outline_is_hidden_if_same_index_belongs_to_other_context(change):
    run_js(PLATE+r"""const m=await plateDraft();selectPlate(m);beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+10)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    m.view.quadEdit=null;let cyan=0;const drawing=new Proxy({stroke(){if(this.strokeStyle==='#22d3ee')cyan++}},{get(o,k){return k in o?o[k]:(()=>{})},set(o,k,v){o[k]=v;return true}});
    m.cv.getContext=()=>drawing;beDraw();assert.equal(cyan,1,'current draft should be outlined');
    if(CHANGE==='source')m.view.readySample.sample.source_ref='other-source';
    if(CHANGE==='timeline')m.view.readySample.sample.timeline_eq='b'.repeat(64);
    if(CHANGE==='row')BE.raw[0].row_context_eq='e'.repeat(64);
    cyan=0;beQuadControls(m.view);assert(elements.get('beQuad').disabled);beDraw();
    assert.equal(cyan,0,'stale corners must not be outlined on a different context');
    assert(BE.quads[0],'stale corners stay pending for deliberate recovery');""".replace('CHANGE',json.dumps(change)))


def test_non_plate_newer_geometry_does_not_inherit_plate_ack_ownership():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);assert(beCaptureGeometry(m.view,BE.raw[0]));
    BE.ov[0]=[130,85,330,225];const first=saveAndRender(),sent=copyEdit(calls.at(-1).body),pc=sent.geometry_preconditions['0'];
    BE.times[0]=[.1,1];const firstAck={...pc,base:{...pc.base,cbox:sent.box_overrides['0']},quad_context_eq:'c'.repeat(64)};
    await reply({ok:true,geometry_rows:{'0':firstAck}});await first;
    assert(BE.times[0],'newer time edit was lost');
    assert(!Object.prototype.hasOwnProperty.call(BE.geometry[0].precondition,'quad_context_eq'),
     'ordinary ACK must not turn retained geometry into a plate');
    const second=saveAndRender(),later=copyEdit(calls.at(-1).body),laterPC=later.geometry_preconditions['0'];
    const secondAck={...laterPC,base:{...laterPC.base,span:[.1,1,laterPC.base.span[2]]},quad_context_eq:'c'.repeat(64)};
    await reply({ok:true,geometry_rows:{'0':secondAck}});
    assert(calls.at(-1).url.endsWith('/render'),'valid ordinary ACK did not proceed to render');
    await reply({ok:true});await second;assert(!(0 in BE.times));""")


def test_older_frame_quad_ack_keeps_current_frame_notice_and_gesture():
    run_js(PLATE+r"""const m=await plateDraft('ready');selectPlate(m);beQuadMode();const tr=m.view.transform,p=m.view.quadEdit.points[0];
    event(m,'pointerdown',p[0]*tr.sx,p[1]*tr.sy);event(m,'pointermove',(p[0]+10)*tr.sx,(p[1]+5)*tr.sy);event(m,'pointerup',0,0);
    const saving=saveAndRender(),sent=copyEdit(calls.at(-1).body),saveRequest=queue.shift(),pc=sent.geometry_preconditions['0'];
    elements.get('beT').value=.3;const sampling=beScrub();
    const data=sample(.3,{index:5,canonical_s:5/24,observed_s:5/24});data.boxes[0].category='plate';
    data.boxes[0].quad_context_eq='c'.repeat(64);data.boxes[0].quad_baseline=null;
    data.boxes[0].quad_edit_eligibility='ready';data.boxes[0].quad_eligibility='none';
    await reply(data);candidates.shift().resolve();await tick();await sampling;selectPlate(m);
    const current=m.view.readySample,serial=m.view.serial;event(m,'pointerdown',100,60);const gesture=BE.drag;
    assert(gesture);applyDet(1,false);
    const saved={version:1,source:{sha256:'d'.repeat(64),stream:0,width:640,height:360},
     frame:{index:4,count:72,fps:24,policy:pc.policy,timeline_eq:pc.timeline_eq},
     points:sent.manual_plate_quads['0'].points.map(p=>[p[0]/640,p[1]/360])};
    saveRequest.resolve(response({ok:true,geometry_rows:{'0':{...pc,row_context_eq:'e'.repeat(64),
     manual_plate_quad:saved,quad_baseline:JSON.stringify(saved)}}}));await tick();await saving;
    assert.strictEqual(m.view.readySample,current,'ACK replaced current inspected frame');
    assert.equal(m.view.serial,serial);assert.strictEqual(BE.drag,gesture,'ACK interrupted the current gesture');
    assert.equal(m.view.readySample.sample.index,5);assert.equal(BE.raw[0].quad_eligibility,'other_frame');
    assert(elements.get('beQuadStatus').textContent.includes('belong to another frame'));
    assert.equal(EDITS.enabled[1],false);assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);
    event(m,'pointerup',100,60);beQuadMode();assert(m.view.quadEdit);
    const point=m.view.quadEdit.points[0],currentTransform=m.view.transform;
    event(m,'pointerdown',point[0]*currentTransform.sx,point[1]*currentTransform.sy);
    event(m,'pointermove',(point[0]+8)*currentTransform.sx,(point[1]+4)*currentTransform.sy);event(m,'pointerup',0,0);
    const replacement=reviewSubmission(EDITS).payload;
    assert.equal(replacement.geometry_preconditions['0'].index,5);assert(replacement.manual_plate_quads['0'].points);
    """)
