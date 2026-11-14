"""Regression: recover compact corner-save HTTP 409 without losing a drawn quad."""
import json
import shutil
import subprocess

import pytest

import openscrub_web as web
from test_findings_web import findings_job


def test_pinned_image_409_is_json_and_can_be_retried_with_fresh_preview(findings_job):
    client, job, _, report = findings_job
    path = f"/api/jobs/{job['id']}/plate_quad/0"
    preview = client.get(f"/api/jobs/{job['id']}/finding-preview/0")
    assert preview.status_code == 200
    meta = json.loads(preview.headers["X-Finding-Geometry"])
    points = [list(p) for p in meta["points"]]
    points[0][0] += 1
    before = report.read_bytes()

    # A cache-key eviction used to return a Flask HTML 409, which the
    # browser rendered as the unhelpful "Server returned HTTP 409".
    response = client.post(path, json=dict(
        compact=True, points=points, autosave=True, edit_id="stale-image-1",
        preview_key="invalid-cached-preview-key", preview_token=meta["preview_token"]))
    assert response.status_code == 409
    body = response.get_json()
    assert body["conflict"] == "stale_preview"
    assert "no longer a valid cached sample" in body["error"]
    assert report.read_bytes() == before

    refreshed = client.get(path + "?compact=1")
    assert refreshed.status_code == 200
    current = refreshed.get_json()
    good = client.post(path, json=dict(
        compact=True, points=points, autosave=True, edit_id="new-image-2",
        preview_key=current.get("key"), preview_token=current["preview_token"]))
    assert good.status_code == 200, good.get_data(as_text=True)
    assert web._load_job_report(job)["detections"][0]["human_region_confirmed"]


def test_409_browser_retries_identical_picture_but_demands_review_for_new_source(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node required for client-side conflict coverage")
    js = web.APP_JS
    helpers = js[js.index("let QEDIT=null;"):js.index("function initPlateCorners(")]
    harness = r'''
const assert=require('node:assert/strict');
const window={removeEventListener(){},addEventListener(){}};
const document={getElementById(){return null}};
let VLBL={0:''},CUR='fixture',gets=0,posts=[],responses=[],fresh;
let confirmations=0,refreshes=0;
function setTimeout(){return 1} function clearTimeout(){}
function confirm(){confirmations++;return true;}
function queueReviewPreview(img){
 refreshes++;img._plateMeta={...fresh};return Promise.resolve(true);
}
function reviewRequest(url,options={}){
 if(options.method==='POST'){
  posts.push(JSON.parse(options.body));
  return new Promise((resolve,reject)=>responses.push({resolve,reject}));
 }
 gets++;return Promise.resolve({data:{...fresh}});
}
''' + helpers + r'''
const base={compact:true,frame:9227,width:640,height:360,box:[100,100,200,140],
 crop:[60,70,240,190],key:'sample-01',source_token:'video-frame-box-1',preview_token:'old',
 points:[[100,100],[200,100],[200,140],[100,140]],track:14};
const corners=[[110,103],[192,103],[192,134],[110,134]];
function make(){
 return {i:0,job:'fixture',meta:{...base},img:{_plateMeta:{...base}},
  points:plateCopy(corners),saved:plateCopy(base.points),
  version:1,dirty:true,pending:null,readyAt:0,failures:0,selected:0,
  status:{textContent:''},retry:{hidden:true,textContent:''},draw(){},
  card:null,conflictAttempts:0,needsSourceReview:false};
}
function reject409(){responses.at(-1).reject(Object.assign(
 new Error('The finding changed. Reload its picture.'),{status:409,details:{conflict:'stale_preview'}}));}
function ack(s){responses.at(-1).resolve({data:{preview:{...s.meta,points:plateCopy(posts.at(-1).points),
 preview_token:'saved'},applied:1,classification_required:true,verified_label:''}});}
(async()=>{
 const s=make();PLATE_EDITS.set(0,s);
 // Stale revision with the SAME image: safe automatic rebase.
 fresh={...base,preview_token:'new-revision'};
 let first=pumpPlateSaves(),old=posts.at(-1).edit_id;reject409();await first;
 assert.equal(gets,1);
 assert.equal(s.error,null);
 assert.equal(s.conflict,false);
 assert.equal(s.pending,null);
 assert.deepEqual(s.points,corners);
 assert.equal(s.meta.preview_token,'new-revision');
 let second=pumpPlateSaves();
 assert.deepEqual(posts.at(-1).points,corners);
 assert.notEqual(posts.at(-1).edit_id,old,'A definite 409 releases rejected ID');
 ack(s);await second;assert.equal(s.dirty,false);
 // A second 409 with NO new revision may represent an evicted cache item:
 // reload once, but a third rejection of the still-identical JPEG must stop
 // rather than enter an endless retry loop.
 s.points=plateCopy(corners);s.points[0][0]+=2;s.version++;s.dirty=true;s.readyAt=0;
 fresh={...s.meta,preview_token:s.meta.preview_token};
 let blocked=pumpPlateSaves();reject409();await blocked;
 assert.equal(s.conflict,false);assert.equal(s.dirty,true);
 assert.equal(refreshes,1,'one automatic reload of potentially evicted JPEG');
 let refusedAgain=pumpPlateSaves();reject409();await refusedAgain;
 assert.equal(s.conflict,true);assert.equal(s.dirty,true);
 assert.equal(s.retry.textContent,'Refresh picture (keep corners)');
 const kept=plateCopy(s.points);
 // Human refreshes a genuinely DIFFERENT frame. Keep draft and only offer
 // an explicit save after the refreshed picture is on screen.
 fresh={...base,frame:11821,source_token:'other-frame',preview_token:'new-frame',
        key:'sample-02',points:plateCopy(base.points)};
 await retryPlateSave(s);
 assert.equal(refreshes,2);
 assert.deepEqual(s.points,kept,'Refreshing cannot discard a human gesture');
 assert.equal(s.meta.frame,11821);
 assert.equal(s.needsSourceReview,true);
 assert.equal(s.retry.textContent,'Save on refreshed picture');
 assert.equal(s.error.message.includes('Verify corners'),true);
 assert.equal(posts.length,4,'A new source must never be autosaved');
 // Additional gestures on the new image also require explicit review.
 const before=plateCopy(s.points);s.points[0][0]+=1;
 commitPlateGesture(s,before);assert.equal(posts.length,4);
 assert.equal(s.needsSourceReview,true);
 await retryPlateSave(s);assert.equal(confirmations,1);
 const final=pumpPlateSaves();
 assert.equal(posts.at(-1).preview_token,'new-frame');
 assert.deepEqual(posts.at(-1).points,s.points);
 ack(s);await final;
 assert.equal(s.dirty,false);assert.equal(s.needsSourceReview,false);
 console.log('409 safe-rebase, bounded retry, non-destructive source refresh and explicit approval OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    target = tmp_path / "review-409-recovery.js"
    target.write_text(harness)
    result = subprocess.run(["node", str(target)], text=True, capture_output=True, timeout=12)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cropping_change_is_not_automatically_rebased():
    """A different crop cannot safely reuse coordinates of the old picture."""
    if not shutil.which("node"):
        pytest.skip("Node required")
    js = web.APP_JS
    matcher = js[js.index("function plateSameSourceCorners("):js.index("function plateQuadValid(")]
    code = ("const assert=require('node:assert/strict');\n" + matcher + r"""
const same={source_token:'same',frame_source_token:'verified-frame',
 frame:4,width:100,height:80,key:'a',
 box:[10,10,40,30],crop:[0,0,50,40],
 points:[[10,10],[40,10],[40,30],[10,30]]};
assert.equal(plateSamePreviewSource(same,{...same}),true);
assert.equal(plateSamePreviewSource(same,{...same,crop:[0,0,60,40]}),false);
assert.equal(plateSameSourceFrame(same,{...same,key:'b',source_token:'new-jpeg'}),true);
assert.equal(plateSameSourceFrame(same,{...same,crop:[0,0,60,40]}),false);
assert.equal(plateSamePreviewSource(same,{...same,key:'b'}),false);
assert.equal(plateSamePreviewSource(same,{...same,frame:5}),false);
assert.equal(plateSamePreviewSource(same,{...same,source_token:'changed'}),false);
assert.equal(plateSamePreviewSource({},{}),false);
""")
    r = subprocess.run(["node", "-e", code], text=True, capture_output=True, timeout=6)
    assert r.returncode == 0, r.stdout + r.stderr
