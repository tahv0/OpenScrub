"""Large review transactions: bounded encoding, sparse choices, real save deadlines."""
from copy import deepcopy
import json
import os
from pathlib import Path
import time

import pytest
import stop_review
import openscrub_web as web
from test_plate_quad_editor import plate_job
from test_review_browser import review_server, browser_instance
from test_sample_filter_timeout import open_review


def test_atomic_report_compact_roundtrip_and_batched_writes(tmp_path, monkeypatch):
    # Keep the standard JSON encoder's conversions, including non-string keys.
    doc = {'detections': [dict(i=i, poly=[[[.1, .2], [.9, .8]]]) for i in range(4097)],
           'render_state': {'cum': [[0, 0]] * 4097, 'bands': [[0, 2160]] * 4097},
           'extra': {2: ('hello', 'åäö', None, False), 'escaped': '"\\\n'}}
    calls=[]
    fdopen=stop_review.os.fdopen
    class CountWrites:
        def __init__(self, file): self.file=file
        def __enter__(self): self.file.__enter__(); return self
        def __exit__(self,*args): return self.file.__exit__(*args)
        def __getattr__(self,name): return getattr(self.file,name)
        def write(self,text): calls.append(len(text)); return self.file.write(text)
    monkeypatch.setattr(stop_review.os,'fdopen',lambda *a,**k:CountWrites(fdopen(*a,**k)))
    path=tmp_path/'report.json';stop_review.atomic_report(path,doc)
    raw=path.read_text()
    assert json.loads(raw)==json.loads(json.dumps(doc))
    assert (raw==json.dumps(doc,separators=(',',':'))) is True, 'Report must not pretty-print millions of scalars'
    assert len(calls)<300, 'Use bounded C-encoded batches, not a Python write per JSON token'
    assert max(calls)<100000, 'Do not allocate the complete encoded array as a second copy'


@pytest.mark.parametrize('failure',['encode','fsync','replace'])
def test_atomic_report_failure_keeps_previous_bytes(tmp_path,monkeypatch,failure):
    path=tmp_path/'report.json';before=b'{"previous":"review"}';path.write_bytes(before)
    doc={'detections':[{'enabled':False}]*1000}
    if failure=='encode':doc['late_bad_value']=object()
    else:
        def fail(*args):raise OSError('Injected '+failure+' failure')
        monkeypatch.setattr(stop_review.os,failure,fail)
    with pytest.raises((TypeError,OSError)):
        stop_review.atomic_report(path,doc)
    assert path.read_bytes()==before
    assert not list(tmp_path.glob('.report-*'))


def test_noop_review_retry_does_not_rewrite_report(plate_job,monkeypatch):
    client,jid,path,_=plate_job
    payload={'enabled':{'0':False},'verified_labels':{'0':'not_plate'}}
    assert client.post('/api/jobs/%s/detections'%jid,json=payload).status_code==200
    before=path.read_bytes()
    def forbidden(*args):pytest.fail('Already committed choices must not rewrite the whole report')
    monkeypatch.setattr(stop_review,'atomic_report',forbidden)
    response=client.post('/api/jobs/%s/detections'%jid,json=payload)
    assert response.status_code==200 and response.get_json()['ok']
    assert response.get_json()['changed'] is False
    assert path.read_bytes()==before


def test_sparse_decisions_preserve_unmentioned_rows_and_geometry(plate_job):
    client,jid,path,_=plate_job
    doc=json.loads(path.read_text());seed=doc['detections'][0]
    doc['detections']=[dict(deepcopy(seed),track=i,verified_label='plate' if i==2 else '') for i in range(6)]
    doc['detections'][2]['plate_quad']=[[0,0],[1,0],[1,1],[0,1]]
    path.write_text(json.dumps(doc))
    response=client.post('/api/jobs/%s/detections'%jid,json={
        'enabled':{'1':False},'verified_labels':{'1':'not_plate','2':'clear'}})
    assert response.status_code==200
    saved=json.loads(path.read_text())
    assert saved['detections'][1]['enabled'] is False
    assert saved['detections'][1]['verified_label']=='not_plate'
    assert saved['detections'][2]['verified_label']==''
    assert saved['detections'][2]['plate_quad']==doc['detections'][2]['plate_quad']
    for i in [0,3,4,5]:assert saved['detections'][i]==doc['detections'][i]
    assert set(response.get_json()['timings_ms'])=={'parse','load','apply','write'}
    assert not (path.parent/'plate_annotations').exists()


@pytest.mark.parametrize('width',[1440,390])
def test_sparse_payload_and_newer_decisions_survive_save(review_server,width,tmp_path):
    url,report=review_server
    doc=json.loads(report.read_text());seed=doc['detections'][0]
    doc['detections']=[dict(deepcopy(seed),track=i//20,verified_label='plate' if i<20 else '') for i in range(2000)]
    report.write_text(json.dumps(doc))
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':width,'height':1000 if width>400 else 844})
        page.set_default_timeout(15000)
        dialogs,errors=open_review(page,url)
        page.evaluate('''()=>{window.__savedFetch=fetch;window.__payloads=[];
          window.fetch=async(url,opts={})=>{
           if(String(url).endsWith('/detections')&&opts.method==='POST'){
            __payloads.push(JSON.parse(opts.body));
            if(__payloads.length===1)await new Promise(r=>window.__releaseSave=r);
           }return __savedFetch(url,opts);};}''')
        page.locator('#det20').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('window.__saveResult=saveAndRender(true);void 0')
        page.wait_for_function('typeof __releaseSave==="function"')
        first=page.evaluate('__payloads[0]')
        assert len(first['enabled'])==20, 'Do not resend 2,000 unchanged visibility entries'
        assert len(first['verified_labels'])==20, 'Do not resend old confirmed labels'
        assert set(first['enabled'])=={str(i) for i in range(20,40)}
        page.locator('#det40').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('__releaseSave()')
        assert page.evaluate('__saveResult') is False, 'Newer changes must remain unsaved'
        assert page.evaluate('reviewChoicesPending()')
        assert page.evaluate('saveAndRender(true)') is True
        second=page.evaluate('__payloads[1]')
        assert set(second['enabled'])=={str(i) for i in range(40,60)}
        # An explicit output-only click clears, rather than confirms, a saved label.
        page.locator('#det0').get_by_role('button',name='Blur',exact=True).click()
        assert page.evaluate('saveAndRender(true)') is True
        third=page.evaluate('__payloads[2]')
        assert third['enabled']=={str(i):True for i in range(20)}, 'Explicit same-value Blur preserves the human override'
        assert third['verified_labels']=={str(i):'clear' for i in range(20)}
        saved=json.loads(report.read_text())['detections']
        assert all(r['enabled'] is True and r.get('plate_verification_override') is True for r in saved[:20])
        assert all(r['enabled'] is False and r['verified_label']=='not_plate' for r in saved[20:60])
        assert all(r.get('verified_label','')=='' for r in saved[:20]+saved[60:])
        assert not any(r.get('plate_verification_override') for r in saved[60:]), 'Untouched findings must remain untouched'
        # The explicit clear is acknowledged once, rather than replayed on
        # every save of the otherwise unchanged report.
        acknowledged=report.read_bytes()
        assert page.evaluate('saveAndRender(true)') is True
        fourth=page.evaluate('__payloads[3]')
        assert fourth['enabled']=={} and fourth['verified_labels']=={}
        assert report.read_bytes()==acknowledged
        page.evaluate('loadReview()');page.locator('#det20').wait_for()
        assert page.locator('#det20 .det-status').inner_text()=='Will stay visible'
        assert not errors and not dialogs,(errors,dialogs)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(exist_ok=True,parents=True)
        page.screenshot(path=str(evidence/('sparse-save-%d.png'%width)))
        browser.close()


def test_actual_save_over_fifteen_seconds_waits_for_disk_confirmation(review_server,monkeypatch):
    """Not a larger test-client timeout: exercise the production browser helper."""
    url,report=review_server
    original=stop_review.atomic_report
    def slow_write(path,doc):
        time.sleep(16.5)
        return original(path,doc)
    if os.environ.get('REVIEW_INPROCESS')!='1':
        monkeypatch.setattr(stop_review,'atomic_report',slow_write)
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(25000)
        dialogs,errors=open_review(page,url)
        page.locator('#det0').get_by_role('button',name='✕ Not a plate',exact=True).click()
        if os.environ.get('REVIEW_INPROCESS')=='1':
            # The local Flask bridge cannot interrupt a Python binding; inject
            # the same delay at fetch with real browser AbortSignal handling.
            page.evaluate('''()=>{const original=window.fetch;window.fetch=async(url,opts={})=>{
             if(String(url).endsWith('/detections')&&opts.method==='POST'){
              await new Promise((resolve,reject)=>{
               const t=setTimeout(resolve,16500);
               opts.signal.addEventListener('abort',()=>{clearTimeout(t);reject(new DOMException('Aborted','AbortError'));},{once:true});
              });
             }return original(url,opts);};}''')
        started=time.monotonic()
        assert page.evaluate('saveAndRender(true)') is True
        assert time.monotonic()-started>=16
        assert 'saved to disk' in page.locator('#reviewSaveStatus').inner_text().lower()
        assert json.loads(report.read_text())['detections'][0]['verified_label']=='not_plate'
        assert not dialogs and not errors,(dialogs,errors)
        browser.close()


def test_other_requests_retain_fifteen_second_deadline(tmp_path):
    import shutil
    import subprocess
    start=web.APP_JS.index('async function reviewRequest(')
    end=web.APP_JS.index('\nfunction clearReviewPreviews(',start)
    script=web.APP_JS[start:end]+'''
const assert=require('node:assert/strict');
const deadlines=[],aborts=[];
global.setTimeout=(f,ms)=>{deadlines.push(ms);aborts.push(f);return deadlines.length;};
global.clearTimeout=()=>{};
global.fetch=async(url,opts)=>{
 assert.equal('timeoutMs' in opts,false,'Do not pass internal timeout policy to fetch');
 return {ok:true,json:async()=>({ok:true})};
};
(async()=>{
 await reviewRequest('/api/jobs/fixture/thumb/0');
 await reviewRequest('/api/jobs/fixture/detections',{method:'POST',timeoutMs:120000});
 await reviewRequest('/api/jobs');
 assert.deepEqual(deadlines,[15000,120000,15000]);
})();
'''
    path=tmp_path/'deadline.js';path.write_text(script)
    result=subprocess.run([shutil.which('node') or 'node',str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_large_legacy_payload_saves_over_real_http(production_server,monkeypatch,tmp_path):
    """105,267 rows; synthetic labels/polygons. Never embed a user's payload."""
    import gc
    import http.client
    import math
    url,path,errors,_=production_server
    n=105267
    polygon=[[.5+.4*math.cos(k*2*math.pi/48),.5+.4*math.sin(k*2*math.pi/48)] for k in range(48)]
    doc=json.loads(path.read_text());seed=doc['detections'][0]
    doc['detections']=[dict(seed,track=i//100,poly=[polygon],frame_index=i,enabled=True,verified_label='') for i in range(n)]
    doc['render_state']['cum']=[[0,0]]*n;doc['render_state']['bands']=[[0,2160]]*n
    path.write_text(json.dumps(doc,separators=(',',':')))
    del doc;gc.collect()
    payload={'enabled':{str(i):i>=28523 for i in range(n)},
             'verified_labels':{str(i):'not_plate' if i<28523 else 'plate' for i in range(37618)}}
    def forbidden(*args,**kwargs):pytest.fail('A choice save must not decode video')
    monkeypatch.setattr(web,'_frame_at',forbidden)
    conn=http.client.HTTPConnection('127.0.0.1',int(url.rsplit(':',1)[1]),timeout=60)
    try:
        started=time.monotonic()
        conn.request('POST','/api/jobs/inline-fixture/detections',body=json.dumps(payload,separators=(',',':')),
                     headers={'Content-Type':'application/json'})
        response=conn.getresponse();data=json.loads(response.read())
        elapsed=time.monotonic()-started
        assert response.status==200 and data['ok'] and data['changed'],data
        assert 'write;dur=' in response.getheader('Server-Timing')
        saved=json.loads(path.read_text())['detections']
        assert len(saved)==n
        assert all(row['enabled'] is payload['enabled'][str(i)] for i,row in enumerate(saved))
        assert all(saved[int(i)]['verified_label']==label for i,label in payload['verified_labels'].items())
        assert all(row['verified_label']=='' for row in saved[37618:]), 'Default blur must not become verification'
        assert saved[-1]['poly']==[polygon]
        assert not errors,errors
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(exist_ok=True,parents=True)
        (evidence/'large-save-http.json').write_text(json.dumps({'rows':n,'seconds':elapsed,'report_bytes':path.stat().st_size,
                                                              'timings_ms':data['timings_ms'],'synthetic':True},indent=2))
    finally:conn.close()


# Actual Cheroot service, separate from the restricted-local browser bridge.
from test_review_save_confirmation import production_server


def test_output_choice_can_clear_a_label_written_by_corner_autosave(review_server):
    """The sparse baseline must follow successful independent corner writes."""
    from test_review_browser import drag_corner
    url,path=review_server
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(12000)
        dialogs,errors=open_review(page,url)
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,card)
        assert page.evaluate('flushPlateSaves()') is True
        assert json.loads(path.read_text())['detections'][0]['verified_label']=='plate'
        card.get_by_role('button',name='Blur',exact=True).click()
        assert page.evaluate('saveAndRender(true)') is True
        assert json.loads(path.read_text())['detections'][0]['verified_label']=='', 'Explicit clear must reach disk'
        assert not dialogs and not errors,(dialogs,errors)
        browser.close()
