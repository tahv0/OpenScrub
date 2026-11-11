"""Latency regressions: warmed images must not reparse big reports or queue old views."""
import json
import os
from pathlib import Path
import subprocess
import threading
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


def test_oversize_report_is_not_retained(plate_job, monkeypatch):
    _, jid, report, _ = plate_job
    monkeypatch.setattr(web, '_REVIEW_REPORT_MAX_FILE_BYTES', 1)
    with web.app.test_request_context():
        web._load_preview_report(web.JOBS[jid])
    assert all(key[0] != str(report) for key in web._REVIEW_REPORTS)


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
def test_scroll_jump_loads_current_cards_before_old_queue(review_server, width, tmp_path):
    """Hold one cold request, enqueue 70 old cards, jump, then revisit a skipped card."""
    url, report = review_server
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width':width,'height':1000 if width>400 else 844})
        page.set_default_timeout(12000)
        errors=[]; page.on('pageerror', lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept())
        load_browser_page(page,url,[],[])
        assert page.title() == 'OpenScrub'
        page.evaluate('''() => {
          window.__fetchBeforeHold=window.fetch;window.__coldStarts=[];
          window.fetch=async(url,opts)=>{
            const m=String(url).match(/\\/finding-preview\\/(\\d+)/);
            if(m&&!String(url).includes('cache_only=1')){
              __coldStarts.push(Number(m[1]));
              if(!window.__held){window.__held=true;await new Promise(r=>window.__releaseCold=r);}
            }
            return __fetchBeforeHold(url,opts);
          };
        }''')
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        page.locator('#det0').scroll_into_view_if_needed()
        page.wait_for_function("typeof window.__releaseCold==='function'")
        page.evaluate('''() => {for(let i=1;i<75;i++)queueReviewPreview(document.querySelector('#det'+i+' img'));}''')
        page.wait_for_function('REVIEW_MEDIA.cacheActive===0&&REVIEW_MEDIA.cacheQueue.length===0')
        page.locator('#det85').scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det85 img')._previewTask")
        page.wait_for_function('REVIEW_MEDIA.cacheActive===0&&REVIEW_MEDIA.cacheQueue.length===0')
        page.evaluate('__releaseCold()')
        page.wait_for_function("document.querySelector('#det85 img').naturalWidth>0")
        started=page.evaluate('__coldStarts')
        assert all(i>=75 for i in started[1:]), started
        assert len(started)<14, started
        assert page.locator('#det85 canvas').count()==1
        page.locator('#det85').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('CONFIRM_CHAIN')
        assert page.locator('#det85 .det-status').inner_text()=='Will stay visible'
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(evidence/('viewport-priority-%s.png'%width)))
        # Intersection observation must re-enqueue work discarded on the way down.
        page.locator('#det10').scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det10 img')._quadEdit")
        assert page.evaluate('saveAndRender(true)') is True
        assert json.loads(report.read_text())['detections'][85]['verified_label']=='not_plate'
        assert not errors,errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        browser.close()


def test_busy_preview_retries_automatically_without_another_click(review_server,monkeypatch):
    from flask import request,jsonify
    url,_=review_server
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
        page.locator('#det0').scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det0 img')._quadEdit")
        assert cold==[0,0]
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
 initReviewPreviews();const pending=img._previewTask.promise;
 await new Promise(r=>setTimeout(r,30));
 if(CANCEL){clearReviewPreviews();assert.equal(await pending,false);
   await new Promise(r=>setTimeout(r,1800));assert.equal(calls,1);}
 else{assert.equal(await pending,false);assert.equal(calls,3);
   assert.equal(REVIEW_MEDIA.active,0);assert.equal(REVIEW_MEDIA.queue.length,0);clearReviewPreviews();}
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    script=script.replace('if(CANCEL)','if('+str(cancel).lower()+')')
    r=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=8)
    assert r.returncode==0,r.stdout+r.stderr
