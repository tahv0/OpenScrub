"""Sampling an already loaded review is a local view, not a timed save/fetch."""
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import shutil
import subprocess

import pytest
import openscrub_web as web
import video_learning as vl
from test_review_browser import (review_server, browser_instance, load_browser_page,
                                 drag_corner, plate_points)


def test_local_sampler_matches_server_grouping_and_current_labels(tmp_path):
    """Exercise the production JavaScript, not a replacement sampler."""
    start = web.APP_JS.find('function sampleReviewGroups(')
    assert start >= 0, 'Sampling must have a fetch-independent path'
    end = web.APP_JS.index('\nfunction applyReviewGroupFilter(', start)
    js = web.APP_JS[start:end]
    rng = random.Random(2929)
    cases = []
    for _ in range(100):
        rows = [dict(i=i, category=rng.choice(['plate']*5+['face']),
                     track=rng.randrange(-1, 25), person=rng.choice([-1]*8+[1, 2]),
                     t_start=rng.randrange(15), confidence=rng.random(),
                     zone_dropped=rng.random()<.05,
                     verified_label=rng.choice(['']*8+['plate','not_plate']),
                     learning_conflict='conflict' if rng.random()<.05 else '',
                     fallback_reason='fallback' if rng.random()<.05 else '')
                for i in range(rng.randrange(0, 600))]
        labels = {str(i):rng.choice(['clear','plate','not_plate'])
                  for i in range(len(rows)) if rng.random()<.2}
        effective = deepcopy(rows)
        for i, row in enumerate(effective):
            if str(i) in labels:
                row['verified_label'] = '' if labels[str(i)] == 'clear' else labels[str(i)]
        fraction = rng.choice([.1, .25, 1.])
        cases.append(dict(rows=rows, labels=labels, fraction=fraction,
                          expected=vl.review_sample_details({'detections':effective}, fraction)))
    file = tmp_path/'sample.js'
    file.write_text(js+'''\nconst assert=require('node:assert/strict');
const cases=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
for(const c of cases){
 const before=JSON.stringify(c);
 assert.deepStrictEqual(sampleReviewGroups(c.rows,c.fraction,c.labels),c.expected);
 assert.equal(JSON.stringify(c),before,'Sampler must not mutate data or labels');
}
for(const f of [0,-1,1.1,Infinity,NaN])assert.throws(()=>sampleReviewGroups([],f));
''')
    result=subprocess.run([shutil.which('node') or 'node',str(file)],input=json.dumps(cases),
                          capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def open_review(page, url):
    dialogs, errors = [], []
    page.on('dialog', lambda d: (dialogs.append(d.message), d.accept()))
    page.on('pageerror', lambda e: errors.append(str(e)))
    load_browser_page(page, url, [], [])
    assert page.title()=='OpenScrub'
    page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
    page.locator('#review').wait_for()
    return dialogs, errors


@pytest.mark.parametrize('width',[1440,390])
def test_sample_and_show_all_work_without_report_network(review_server,width,tmp_path):
    url,report=review_server
    doc=json.loads(report.read_text());template=doc['detections'][0]
    doc['detections']=[dict(template,track=t,frame_index=100+f,t_start=(100+f)/30,
                            t_end=(101+f)/30,last_seen=(100+f)/30)
                       for t in range(100) for f in range(100)]
    report.write_text(json.dumps(doc))
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw)
        page=browser.new_page(viewport={'width':width,'height':1000 if width>400 else 844})
        page.set_default_timeout(12000)
        dialogs,errors=open_review(page,url)
        page.locator('#det0').get_by_role('button',name='✕ Not a plate',exact=True).click()
        before=report.read_bytes()
        page.evaluate('''()=>{
         window.__originalReview=document.getElementById('review');
         window.__originalCard=document.getElementById('det0');
         window.__originalFetch=window.fetch;window.__filterRequests=[];
         window.fetch=(url,opts={})=>{
          if(/\\/(detections|learning\\/review)(?:\\?|$)/.test(String(url))){
           __filterRequests.push((opts.method||'GET')+' '+url);
           return new Promise((resolve,reject)=>{
            if(opts.signal)opts.signal.addEventListener('abort',()=>reject(new DOMException('synthetic server stall','AbortError')));
           });
          }
          return __originalFetch(url,opts);
         };
        }''')
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        page.wait_for_function('document.querySelectorAll("#review .det:not([hidden])").length===10',timeout=2500)
        assert page.evaluate('__filterRequests')==[]
        assert '10 of 99' in page.locator('#reviewSampleSummary').inner_text()
        assert page.evaluate('document.getElementById("review")===__originalReview')
        assert page.evaluate('document.getElementById("det0")===__originalCard')
        assert page.evaluate('reviewChoicesPending()') is True
        assert page.evaluate('EN[0]') is False
        assert report.read_bytes()==before,'A filter must not silently save a draft'
        page.get_by_role('button',name='Show all findings',exact=True).click()
        assert page.locator('#review .det:visible').count()==100
        assert page.locator('#det0 .det-status').inner_text()=='Will stay visible'
        assert page.evaluate('__filterRequests')==[]
        assert page.evaluate('document.getElementById("det0")===__originalCard')
        assert 'not saved' in page.locator('#reviewSaveStatus').inner_text().lower()
        assert not dialogs and not errors
        # Explicit saving still persists every group member; sampling didn't.
        page.evaluate('window.fetch=window.__originalFetch')
        assert page.evaluate('saveAndRender(true)') is True
        saved=json.loads(report.read_text())['detections']
        assert all(not r['enabled'] and r['verified_label']=='not_plate' for r in saved[:100])
        assert len(saved)==10000
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        path=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));path.mkdir(parents=True,exist_ok=True)
        page.locator('#reviewSampleSummary').scroll_into_view_if_needed()
        page.screenshot(path=str(path/f'local-sample-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        browser.close()


def test_filter_keeps_failed_corner_draft_and_loaded_image(review_server):
    url,report=review_server
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        dialogs,errors=open_review(page,url)
        card=page.locator('#det1');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det1 img")._quadEdit')
        page.evaluate('''()=>{
         window.__originalFetch=window.fetch;window.__corner=document.querySelector('#det1 img')._quadEdit;
         window.__image=document.querySelector('#det1 img');window.__src=__image.src;
         window.fetch=(url,opts={})=>opts.method==='POST'&&String(url).includes('/plate_quad/')
          ?Promise.resolve(new Response(JSON.stringify({error:'synthetic conflict'}),{status:409,headers:{'Content-Type':'application/json'}}))
          :__originalFetch(url,opts);
        }''')
        drag_corner(page,card)
        page.wait_for_function('__corner.error&&__corner.dirty')
        points=plate_points(card)
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        page.get_by_role('button',name='Show all findings',exact=True).wait_for(timeout=2500)
        assert card.is_hidden()
        assert page.evaluate('PLATE_EDITS.get(1)===__corner && __corner.dirty && !!__corner.error')
        page.get_by_role('button',name='Show all findings',exact=True).click()
        assert plate_points(card)==points
        assert page.evaluate('document.querySelector("#det1 img")===__image && __image.src===__src')
        assert page.evaluate('plateEditsPending()') is True
        assert 'Not saved' in card.locator('.quad-status').inner_text()
        assert not dialogs and not errors
        # Existing explicit rejection recovers the independent draft and saves.
        card.get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('window.fetch=__originalFetch')
        assert page.evaluate('saveAndRender(true)') is True
        assert json.loads(report.read_text())['detections'][1]['verified_label']=='not_plate'
        browser.close()


def test_filter_keeps_inflight_corner_save_alive(review_server):
    url,report=review_server
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        dialogs,errors=open_review(page,url)
        card=page.locator('#det1');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det1 img")._quadEdit')
        page.evaluate('''()=>{
         window.__originalFetch=window.fetch;window.__corner=document.querySelector('#det1 img')._quadEdit;
         window.__gate=new Promise(resolve=>window.__release=resolve);window.__posting=false;
         window.fetch=async(url,opts={})=>{
          if(opts.method==='POST'&&String(url).includes('/plate_quad/')){window.__posting=true;await __gate;}
          return __originalFetch(url,opts);
         };
        }''')
        drag_corner(page,card);page.wait_for_function('__posting')
        points=plate_points(card)
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        page.get_by_role('button',name='Show all findings',exact=True).wait_for(timeout=2500)
        assert card.is_hidden()
        assert page.evaluate('PLATE_EDITS.get(1)===__corner && !!__corner.pending')
        page.evaluate('__release()')
        page.wait_for_function('!__corner.dirty&&!__corner.pending')
        page.get_by_role('button',name='Show all findings',exact=True).click()
        for actual,expected in zip(plate_points(card),points):
            assert actual==pytest.approx(expected,abs=1e-4)  # persisted coordinates are rounded
        assert len(json.loads(report.read_text())['detections'][1]['plate_quad'])==4
        assert not errors and not dialogs
        browser.close()


def test_hidden_preview_never_occupies_decoder_queue(tmp_path):
    start=web.APP_JS.index('function reviewPreviewRank(')
    end=web.APP_JS.index('\nfunction pumpReviewPreviews(',start)
    file=tmp_path/'rank.js'
    file.write_text("const window={innerHeight:1000};const document={documentElement:{}};\n"+
                    web.APP_JS[start:end]+'''
const assert=require('node:assert/strict');
const task={priority:true,img:{isConnected:true,
 closest:selector=>selector==='[hidden]'?{}:null,
 getBoundingClientRect:()=>({top:0,bottom:0})}};
assert.equal(reviewPreviewRank(task),Infinity,'Hidden groups must not use the decoder, even for an old priority task');
''')
    r=subprocess.run(['node',str(file)],capture_output=True,text=True,timeout=5)
    assert r.returncode==0,r.stderr


def test_sample_bulk_action_only_changes_visible_groups(review_server):
    url,report=review_server
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        dialogs,errors=open_review(page,url)
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        page.get_by_role('button',name='Show all findings',exact=True).wait_for()
        ids=page.locator('#review .det:visible').evaluate_all('(cards)=>cards.map(c=>+c.id.slice(3))')
        assert len(ids)==9
        page.get_by_role('button',name='Keep all visible',exact=True).click()
        assert page.evaluate('Object.keys(EN).filter(k=>!EN[k]).map(Number)')==ids
        page.get_by_role('button',name='Show all findings',exact=True).click()
        assert page.locator('#review .det:visible').count()==90
        assert page.evaluate('Object.keys(EN).filter(k=>!EN[k]).map(Number)')==ids
        assert not errors and not dialogs
        browser.close()


def test_empty_sample_and_show_all_keep_other_categories_and_drafts(review_server):
    url,report=review_server
    doc=json.loads(report.read_text())
    doc['detections'][0]['category']='face'
    doc['detections'][1]['zone_dropped']=True
    for row in doc['detections'][2:]: row['verified_label']='plate'
    report.write_text(json.dumps(doc))
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        dialogs,errors=open_review(page,url)
        page.evaluate('''()=>{
          MAN=[{test:'unsaved manual draft'}];BE.ov={'3':[1,2,3,4]};
          BE.times={'4':[1,2]};BE.adds=[{test:'pending region'}];
          window.__drafts=JSON.stringify([MAN,BE.ov,BE.times,BE.adds]);
        }''')
        for _ in range(3):
            page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
            assert '0 of 0' in page.locator('#reviewSampleSummary').inner_text()
            assert page.locator('#review .det:visible').count()==0
            assert page.locator('#reviewZones').is_hidden()
            page.get_by_role('button',name='Show all findings',exact=True).click()
            assert page.locator('#review .det:visible').count()==89
            assert page.locator('#det0').get_attribute('data-cat')=='face'
            assert page.locator('#reviewZones').is_visible()
            assert page.evaluate('JSON.stringify([MAN,BE.ov,BE.times,BE.adds])===__drafts')
        assert json.loads(report.read_text())==doc
        assert not errors and not dialogs
        browser.close()
