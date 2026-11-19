"""Real PAGE and HTTP thumbnail recovery with an optional prepared browser."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest
from werkzeug.serving import make_server

import openscrub_web as web
from test_exact_samples import exact
from test_job_lifecycle import store


def test_thumbnail_page_review_recovery(exact, tmp_path):
    module = os.environ.get('OPENSCRUB_PLAYWRIGHT_MODULE')
    chromium = os.environ.get('OPENSCRUB_CHROMIUM')
    node = os.environ.get('OPENSCRUB_NODE') or shutil.which('node')
    if not module or not chromium or not node:
        pytest.skip('prepared Playwright, Chromium, and Node are required for PAGE test')
    doc = json.loads(exact.path.read_text())
    base = doc['detections'][0]
    base.update(track=8, confidence=.95, cbox=[3, 3, 20, 20])
    doc['detections'][1].update(track=8, confidence=.5, t_start=.2, t_end=1.2)
    doc['detections'].append(dict(base, track=-1, text='ordinary', cbox=[25, 5, 45, 25]))
    doc['detections'].append(dict(base, track=-1, text='outside zone', zone_dropped=True, cbox=[4, 20, 24, 40]))
    exact.path.write_text(json.dumps(doc))
    other = web.new_job('', {}, 'synthetic-b.avi')
    other_video = Path(other['dir']) / 'input.avi'
    shutil.copyfile(exact.job['video'], other_video)
    other.update(video=str(other_video), phase='review')
    other_doc = json.loads(json.dumps(doc))
    other_doc['provenance']['input'] = str(other_video)
    (Path(other['dir']) / 'report.json').write_text(json.dumps(other_doc))
    artifacts = Path(os.environ.get('OPENSCRUB_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
    if not artifacts.is_dir():
        artifacts.mkdir(parents=True, exist_ok=True)
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = dict(os.environ, OPENSCRUB_PAGE_URL=f'http://127.0.0.1:{server.server_port}/',
               OPENSCRUB_PAGE_JOB=exact.job['id'], OPENSCRUB_PAGE_JOB_B=other['id'], OPENSCRUB_BROWSER_ARTIFACTS=str(artifacts))
    try:
        result = subprocess.run([node, str(Path(__file__).with_name('thumbnail_page.cjs'))],
                                env=env, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown()
        thread.join(10)
        server.server_close()
        assert not thread.is_alive()
    raw = json.loads(exact.path.read_text())
    assert raw['custom'] == {'preserved': True}
    assert raw['detections'][2]['cbox'] == [2.0, 2.0, 14.0, 14.0]
    assert raw['detections'][2]['enabled'] is True
    assert sum(row.get('manual_id') == 'page-newer' for row in raw['detections']) == 1
    assert len(raw['audio_redactions']) == 2
    print(result.stdout)


def test_final_wave_literal_labels_and_group_controls(exact, tmp_path):
    module = os.environ.get('OPENSCRUB_PLAYWRIGHT_MODULE')
    chromium = os.environ.get('OPENSCRUB_CHROMIUM')
    node = os.environ.get('OPENSCRUB_NODE') or shutil.which('node')
    if not module or not chromium or not node:
        pytest.skip('prepared Playwright, Chromium, and Node are required for PAGE test')
    doc = json.loads(exact.path.read_text())
    category = 'name " <tag> & literal'
    text = 'Label <b>literal</b> & "quote"'
    zone = 'Zone <i>literal</i> & "quote"'
    doc['detections'][0].update(category=category, text=text, track=8, confidence=.95)
    doc['detections'][1].update(category=category, text='second', track=8, confidence=.5)
    doc['detections'].append(dict(doc['detections'][0], track=-1, text=zone, zone_dropped=True))
    exact.path.write_text(json.dumps(doc))
    before = exact.path.read_bytes()
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    env = dict(os.environ, OPENSCRUB_PAGE_URL='http://127.0.0.1:%d/' % server.server_port,
               OPENSCRUB_PAGE_JOB=exact.job['id'])
    script = r"""
const assert=require('node:assert/strict');
const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
(async()=>{const browser=await chromium.launch({executablePath:process.env.OPENSCRUB_CHROMIUM,headless:true,args:['--no-sandbox']});
try{const page=await browser.newPage();await page.goto(process.env.OPENSCRUB_PAGE_URL);
 await page.evaluate(id=>openJob(id),process.env.OPENSCRUB_PAGE_JOB);
 await page.waitForSelector('#thumb0');
 const state=await page.evaluate(()=>{const root=document.getElementById('review');
  const card=document.getElementById('det0'),zone=document.getElementById('det2');
  return {category:card.dataset.cat,card:card.textContent,zone:zone.textContent,
   markup:card.querySelector('b')!==null||zone.querySelector('i')!==null,
   binding:REVIEW_IMAGES.bindings.get(0).node===card.querySelector('img'),
   group:TRKMEM[0],heading:[...root.querySelectorAll('h3')].find(n=>n.textContent.includes('name'))?.textContent};});
 assert.equal(state.category,'name " <tag> & literal');
 assert.ok(state.card.includes('Label <b>literal</b> & "quote"'));
 assert.ok(state.zone.includes('Zone <i>literal</i> & "quote"'));
 assert.equal(state.markup,false);assert.equal(state.binding,true);assert.deepEqual(state.group,[0,1]);
 assert.ok(state.heading.includes('name " <tag> & literal'));
 await page.evaluate(()=>[...document.querySelectorAll('#review h3')].find(n=>n.textContent.includes('name')).querySelectorAll('button')[1].click());
 assert.equal(await page.evaluate(()=>EN[0]===false&&EN[1]===false),true);
 await page.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
"""
    try:
        result = subprocess.run([node], input=script, env=env, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown(); thread.join(10); server.server_close()
        assert not thread.is_alive()
    assert exact.path.read_bytes() == before


@pytest.mark.parametrize("failure", ["http", "network", "json"])
def test_final_wave_first_review_failure_has_manual_retry(exact, failure):
    module = os.environ.get('OPENSCRUB_PLAYWRIGHT_MODULE')
    chromium = os.environ.get('OPENSCRUB_CHROMIUM')
    node = os.environ.get('OPENSCRUB_NODE') or shutil.which('node')
    if not module or not chromium or not node:
        pytest.skip('prepared Playwright, Chromium, and Node are required for PAGE test')
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    env = dict(os.environ, OPENSCRUB_PAGE_URL='http://127.0.0.1:%d/' % server.server_port, OPENSCRUB_PAGE_JOB=exact.job['id'], OPENSCRUB_FAILURE=failure)
    script = r"""
const assert=require('node:assert/strict');const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
(async()=>{const browser=await chromium.launch({executablePath:process.env.OPENSCRUB_CHROMIUM,headless:true,args:['--no-sandbox']});
try{const page=await browser.newPage(),job=process.env.OPENSCRUB_PAGE_JOB;let calls=0;
 const pattern='**/api/jobs/'+job+'/detections';
 const fail=route=>{calls++;if(process.env.OPENSCRUB_FAILURE==='network')return route.abort('failed');
  if(process.env.OPENSCRUB_FAILURE==='json')return route.fulfill({status:200,contentType:'application/json',body:'{'});
  return route.fulfill({status:409,contentType:'application/json',body:'{}'});};
 await page.route(pattern,fail);await page.goto(process.env.OPENSCRUB_PAGE_URL);await page.evaluate(id=>openJob(id),job);
 await page.waitForSelector('[data-review-retry]',{timeout:2500});assert.equal(calls,1);
 await page.evaluate(()=>refresh());assert.equal(calls,1);
 await page.unroute(pattern,fail);await page.locator('[data-review-retry]').click();
 await page.waitForSelector('#thumb0');assert.equal(await page.locator('[data-review-retry]').count(),0);
 await page.close();}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
"""
    try:
        result = subprocess.run([node], input=script, env=env, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown(); thread.join(10); server.server_close()
        assert not thread.is_alive()
