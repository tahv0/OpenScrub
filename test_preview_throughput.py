"""Latency regressions: warmed images must not reparse big reports or queue old views."""
import json
import os
from pathlib import Path
import subprocess
import threading
import shutil
from unittest.mock import patch

import cv2
import numpy as np
import pytest
import openscrub_web as web
from test_plate_quad_editor import plate_job


def test_warm_thumbnail_requests_parse_report_once(plate_job, monkeypatch):
    client, jid, report, _ = plate_job
    # Count the actual JSON file parser, not a helper invocation.
    real_load = web.json.load
    parses = []
    def counted(file, *a, **kw):
        if os.fspath(file.name) == str(report):
            parses.append(file.name)
        return real_load(file, *a, **kw)
    monkeypatch.setattr(web.json, 'load', counted)
    for _ in range(8):
        r = client.get('/api/jobs/%s/thumb/0' % jid)
        assert r.status_code == 200
    assert len(parses) == 1, 'Every warmed image reparsed the complete report'


def test_thumbnail_report_cache_refreshes_after_atomic_same_size_replace(plate_job):
    client, jid, report, _ = plate_job
    url = '/api/jobs/%s/thumb/0' % jid
    initial = client.get(url)
    assert initial.status_code == 200
    doc = json.loads(report.read_text())
    # Same-size, same-mtime replacements must not retain old geometry.
    doc['detections'][0]['cbox'][0] += 1
    stat = report.stat()
    staged = report.with_suffix('.new')
    staged.write_text(json.dumps(doc))
    assert staged.stat().st_size == stat.st_size
    os.utime(staged, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    os.replace(staged, report)
    response = client.get(url+'?cache_only=1')
    assert response.status_code == 204
    updated = client.get(url)
    assert updated.status_code == 200
    assert json.loads(updated.headers['X-Plate-Geometry'])['box'][0] == doc['detections'][0]['cbox'][0]


def test_mutating_writer_document_does_not_mutate_thumbnail_snapshot(plate_job):
    client, jid, report, _ = plate_job
    url = '/api/jobs/%s/thumb/0' % jid
    original = client.get(url).headers['X-Plate-Geometry']
    independent = web._load_job_report(web.JOBS[jid])
    independent['detections'][0]['cbox'][0] += 5
    assert client.get(url).headers['X-Plate-Geometry'] == original


def test_internal_frame_transport_does_not_compress_a_full_frame_as_png(tmp_path, monkeypatch):
    path = tmp_path/'transport.mp4'; path.write_bytes(b'synthetic')
    pixels = np.full((4, 4, 3), 71, np.uint8)
    ok, encoded = cv2.imencode('.ppm', pixels); assert ok
    calls = []
    monkeypatch.setattr(web, '_review_probe', lambda *_: {'fps':30., 'start':0., 'cfr':True})
    def process(command):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, encoded.tobytes(),
            b'config in time_base: 1/30\nn: 0 pts: 1 pts_time:0.0333333\n')
    monkeypatch.setattr(web, '_review_process', process)
    with web.app.test_request_context():
        assert np.array_equal(web._read_exact_frame(str(path), 1), pixels)
    assert calls[0][calls[0].index('-vcodec')+1] == 'ppm'


def test_current_view_overtakes_obsolete_cold_queue(tmp_path):
    source = web.APP_JS
    # Execute the production queue, including any newly added ranking helper.
    helpers = source[source.index('let REVIEW_MEDIA=null;'):source.index('let QEDIT=null;')]
    script = r'''
const assert=require('node:assert/strict');
const window={innerHeight:800},document={documentElement:{clientHeight:800}};
let started=[];
''' + helpers + r'''
loadReviewPreview=(state,task,cached)=>{state[cached?'cacheActive':'active']++;started.push(task.id);};
function task(id,top,priority=false){const t={id,priority,resolve(){this.resolved=true;},
 img:{isConnected:true,getBoundingClientRect(){return {top,bottom:top+180,width:250,height:180};}}};
 t.img._previewTask=t;return t;}
const old=task('old-offscreen',-8000),near=task('prefetch',950),current=task('visible',250);
REVIEW_MEDIA={queue:[old,near,current],cacheQueue:[],active:0,cacheActive:3,controllers:new Set(),urls:new Set()};
pumpReviewPreviews(REVIEW_MEDIA);
assert.equal(started[0],'visible','Visible card waited behind obsolete offscreen decode');
assert.equal(old.img._previewTask,null,'Obsolete queued task must be released');
assert.equal(old.resolved,true);
assert.equal(REVIEW_MEDIA.active,1,'Decoder budget must remain one');
console.log('visible work overtakes offscreen backlog');
'''
    result = subprocess.run(['node','-e',script],text=True,capture_output=True,timeout=10)
    assert result.returncode == 0,result.stdout+result.stderr



def test_review_prefetch_reads_offscreen_cache_before_any_observer_event():
    """Opening Review should warm even cards far beyond the scroll threshold.

    Cache JPEG reads run ahead of the user, but cold source-video decoding
    must remain bounded to the next few screens and hidden cards stay idle.
    """
    source = web.APP_JS
    helpers = source[source.index('let REVIEW_MEDIA=null;'):source.index('let QEDIT=null;')]
    script = r'''
const assert=require('node:assert/strict');
const window={innerHeight:900};
const cards=[100,1600,5000,14000,24000].map((top,id)=>({
  id,top,isConnected:true,naturalWidth:0,
  dataset:{previewUrl:'/thumb/'+id},
  closest(selector){return null;},
  getBoundingClientRect(){return {top:this.top,bottom:this.top+180}}
}));
const document={documentElement:{clientHeight:900},querySelectorAll(){return cards}};
let observed=[],started=[];
global.IntersectionObserver=class{
  constructor(callback){this.callback=callback;}
  observe(img){observed.push(img.id);}
  disconnect(){}
};
''' + helpers + r'''
loadReviewPreview=(state,task,cacheOnly)=>{
  state[cacheOnly?'cacheActive':'active']++;
  started.push({id:task.img.id,cacheOnly});
};
initReviewPreviews();
// No IntersectionObserver event was delivered, yet even the far cards
// have been registered for automatic cache reads.
assert.deepEqual(observed,[0,1,2,3,4]);
assert.deepEqual(started.map(item=>item.id),[0,1,2]);
REVIEW_MEDIA.cacheActive=0;pumpReviewPreviews(REVIEW_MEDIA);
assert.deepEqual(started.map(item=>item.id),[0,1,2,3,4]);
const near={img:cards[0],resolve(){}},far={img:cards[4],resolve(){}};
REVIEW_MEDIA.cacheActive=3;REVIEW_MEDIA.active=0;
REVIEW_MEDIA.queue=[far,near];
pumpReviewPreviews(REVIEW_MEDIA);
assert.equal(started.at(-1).id,0,'visible cold miss must outrank speculative work');
assert.equal(started.at(-1).cacheOnly,false);
assert.equal(REVIEW_MEDIA.queue.length,1,'far-ahead cold decode was not deferred');
assert.equal(REVIEW_MEDIA.queue[0],far);
clearReviewPreviews();
'''
    result = subprocess.run(['node', '-e', script], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.timeout(75)
def test_offscreen_review_jpeg_is_ready_before_user_scrolls(review_server):
    """Real browser: cached images several screens below are downloaded early."""
    from test_review_browser import browser_instance, load_browser_page

    url, _ = review_server
    sync_api = pytest.importorskip('playwright.sync_api')
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width':1440, 'height':1000})
        page.set_default_timeout(20000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        load_browser_page(page, url, [], [])
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.locator('#review').wait_for()
        # Do not scroll this card into view. The old IntersectionObserver-only
        # implementation would never fetch it until the user moved down.
        offscreen = page.locator('#det30 img')
        distance = offscreen.evaluate(
            '(img)=>img.getBoundingClientRect().top - window.innerHeight')
        assert distance > 1600, 'The test card must be outside the old preload margin'
        page.wait_for_function(
            'document.querySelector("#det30 img").naturalWidth > 0',
            timeout=25000)
        assert 'pictures ready' in page.locator('#reviewPreloadStatus').inner_text()
        assert not errors, errors
        browser.close()


def test_parallel_cache_misses_parse_only_one_report(plate_job, monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor
    _, jid, report, _ = plate_job
    real_load = web.json.load
    parses = []
    def load(file, *a, **kw):
        if os.fspath(file.name) == str(report):
            parses.append(True); time.sleep(.03)
        return real_load(file, *a, **kw)
    monkeypatch.setattr(web.json, 'load', load)
    def request(_):
        with web.app.test_client() as c:
            return c.get('/api/jobs/%s/thumb/0?cache_only=1' % jid).status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(request, range(6))) == [204]*6
    assert len(parses) == 1


def test_oversize_report_retains_only_indexed_row_accessor(plate_job, monkeypatch):
    import review_preview_index
    _, jid, report, _ = plate_job
    monkeypatch.setattr(web, '_REVIEW_REPORT_MAX_FILE_BYTES', 1)
    web._REVIEW_REPORTS.clear()
    with web.app.test_request_context():
        doc = web._load_preview_report(web.JOBS[jid])
    assert isinstance(doc['detections'], review_preview_index.IndexedRows)
    assert any(key[0] == str(report) for key in web._REVIEW_REPORTS)
    assert len(doc['detections']) == 1


def test_vault_lock_forgets_preview_report_snapshot(plate_job, monkeypatch):
    client, jid, _, _ = plate_job
    assert client.get('/api/jobs/%s/thumb/0?cache_only=1' % jid).status_code == 204
    assert web._REVIEW_REPORTS
    monkeypatch.setitem(web.VAULT, 'key', b'synthetic-key')
    def encrypt(*a):
        assert not web._REVIEW_REPORTS
        return 0
    monkeypatch.setattr(web.vault, 'encrypt_tree', encrypt)
    assert web._vault_lock_now() == 0


from test_review_browser import review_server, browser_instance, load_browser_page


@pytest.mark.parametrize('width', [1440, 390])
def test_scroll_jump_automatically_loads_visible_cache_misses(review_server, width, tmp_path):
    """A missing thumbnail is decoded automatically but only when near the viewport."""
    url, report = review_server
    shutil.rmtree(report.parent / 'compact_previews')
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width':width,'height':1000 if width>400 else 844})
        page.set_default_timeout(12000)
        errors=[]; page.on('pageerror', lambda e:errors.append(str(e)))
        load_browser_page(page,url,[],[])
        assert page.title() == 'OpenScrub'
        page.evaluate(r'''() => {
          window.__fetchBeforeObserve=window.fetch;window.__coldStarts=[];
          window.fetch=async(url,opts)=>{
            const m=String(url).match(/\/finding-preview\/(\d+)/);
            if(m&&!String(url).includes('cache_only=1'))__coldStarts.push(Number(m[1]));
            return __fetchBeforeObserve(url,opts);
          };
        }''')
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        page.locator('#det0').scroll_into_view_if_needed()
        page.wait_for_function("document.querySelector('#det0 img').naturalWidth>0",timeout=60000)
        assert 0 in page.evaluate('__coldStarts'), 'Visible cache miss did not decode automatically'
        page.locator('#det85').scroll_into_view_if_needed()
        page.wait_for_function("document.querySelector('#det85 img').naturalWidth>0",timeout=60000)
        starts=page.evaluate('__coldStarts')
        # Same-frame, same-geometry findings may correctly share one exact
        # cached crop. No second video decode is required for that image.
        assert 0 in starts, 'The first visible card did not load automatically'
        assert len(starts)<40, 'Scrolling started a source decoder for every offscreen card'
        assert page.locator('#det85 canvas').count()==1
        assert not errors,errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        browser.close()


def test_busy_preview_retries_automatically_with_bounded_budget(review_server,monkeypatch):
    from flask import request,jsonify
    url,report=review_server
    shutil.rmtree(report.parent / 'compact_previews')
    old=web.app.view_functions['finding_preview'];cold=[]
    def busy_once(jid,index):
        if index==0 and request.args.get('cache_only')!='1':
            cold.append(index)
            if len(cold)==1:return jsonify(error='Synthetic busy decoder'),503
        return old(jid,index)
    monkeypatch.setitem(web.app.view_functions,'finding_preview',busy_once)
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(12000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det0 img')._quadEdit",timeout=60000)
        assert cold==[0,0], 'A busy decoder should be retried only twice, not loop forever'
        assert not errors,errors
        browser.close()


@pytest.mark.timeout(70)
def test_large_review_pages_keep_all_group_choices_and_sample_members(review_server):
    """Only mount the first 48 cards; bulk choices and sampled groups still cover all."""
    from copy import deepcopy
    url, report = review_server
    doc = json.loads(report.read_text())
    template = doc['detections'][0]
    doc['detections'] = [dict(deepcopy(template), track=i, text='Synthetic plate %s' % i)
                         for i in range(530)]
    report.write_text(json.dumps(doc))
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(12000)
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        page.locator('#review').wait_for()
        mounted = page.locator('#review .det').count()
        assert 48 <= mounted < 530, 'Mount pages ahead, not the entire 530-card report'
        # Additional cards should be mounted and queued while still far below
        # the viewport, without the reviewer having to scroll to "Load more".
        page.wait_for_function(
            'document.querySelectorAll("#review .det").length > 48',
            timeout=10000)
        assert page.locator('#review .det').count() < 530
        assert page.evaluate('Object.keys(FINDING_META).length')==530
        assert page.evaluate('Object.keys(TRKMEM).length')==530
        page.get_by_role('button',name='Keep all visible',exact=True).first.click()
        assert page.evaluate('Object.values(EN).every(v=>v===false)')
        delta=page.evaluate('reviewChoiceDelta()')
        assert len(delta['enabled'])==530, 'Bulk actions must include unmounted groups'
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        assert page.locator('#review .det:visible').count()==53
        assert '53 of 530' in page.locator('#reviewSampleSummary').inner_text()
        page.get_by_role('button',name='Show all findings',exact=True).click()
        before=page.locator('#review .det').count()
        page.evaluate("appendReviewPage('plate')")
        assert page.locator('#review .det').count()>before
        assert page.evaluate('Object.values(EN).every(v=>v===false)')
        assert not errors,errors
        browser.close()


@pytest.mark.parametrize('cancel', [False, True])
def test_busy_retry_budget_and_teardown_are_bounded(cancel):
    helpers=web.APP_JS[web.APP_JS.index('let REVIEW_MEDIA=null;'):web.APP_JS.index('let QEDIT=null;')]
    script=r'''
const assert=require('node:assert/strict');
const img={isConnected:true,naturalWidth:0,dataset:{previewUrl:'/thumb/0'},src:'',
 closest(selector){if(selector==='[hidden]')return null;assert.equal(selector,'.det');
  return {querySelector(){return {textContent:'',hidden:false}}}}};
const document={querySelectorAll(){return [img]}};let calls=0;
''' + helpers + r'''
reviewRequest=async(url)=>{
 if(url.includes('cache_only=1'))return {response:{status:204,headers:{get(){return null}}},data:{}};
 calls++;const e=new Error('busy');e.status=503;throw e;
};
(async()=>{
 initReviewPreviews();
 const automatic=img._previewTask.promise;
 await new Promise(r=>setTimeout(r,30));
 assert.equal(calls,1,'automatic cold decoding should use one worker');
 if(CANCEL){
   clearReviewPreviews();assert.equal(await automatic,false);
   await new Promise(r=>setTimeout(r,1800));assert.equal(calls,1);
 }else{
   assert.equal(await automatic,false);
   assert.equal(calls,3,'busy retries must stop after two retries');
   assert.equal(REVIEW_MEDIA.active,0);
   assert.equal(REVIEW_MEDIA.queue.length,0);
   clearReviewPreviews();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    script=script.replace('if(CANCEL)','if('+str(cancel).lower()+')')
    r=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=8)
    assert r.returncode==0,r.stdout+r.stderr
