"""Section controls through the real served UI; synthetic footage only."""
import json
import os
from pathlib import Path
import threading
import pytest
from werkzeug.serving import make_server
import openscrub_web as web
from test_section_workflow import section_job, create_section
from test_review_browser import browser_instance, load_browser_page


@pytest.mark.parametrize('width,height',[(1440,1000),(390,844)])
def test_approve_and_export_section_from_review(section_job,width,height,tmp_path):
    client,job,doc,queued=section_job
    server=make_server('127.0.0.1',0,web.app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    sync=pytest.importorskip('playwright.sync_api')
    try:
        with sync.sync_playwright() as pw:
            browser=browser_instance(pw)
            page=browser.new_page(viewport={'width':width,'height':height})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_default_timeout(12000)
            load_browser_page(page,'http://127.0.0.1:%s'%server.server_port,[],[])
            assert page.title()=='OpenScrub'
            page.get_by_role('link',name='Synthetic source',exact=True).click()
            page.locator('#sectionName').fill('Finished middle')
            page.locator('#sectionStart').fill('0:01')
            page.locator('#sectionEnd').fill('0:02')
            page.get_by_role('button',name='Add section',exact=True).click()
            page.get_by_role('button',name='Approve current results',exact=True).click()
            page.get_by_text('Approved · revision 1',exact=False).wait_for()
            saved=json.loads((Path(job['dir'])/'report.json').read_text())
            assert saved['video_sections']['items'][0]['approved']['revision']==1
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)))
            evidence.mkdir(parents=True,exist_ok=True)
            page.locator('#jobcard').screenshot(path=str(evidence/f'sections-approved-{width}.png'))
            page.get_by_role('button',name='Export approved section',exact=True).click()
            page.wait_for_function('CUR!=="parent"')
            assert len(queued)==1 and queued[0][1]=='render'
            assert web.JOBS[queued[0][0]]['options']['section_range']==[10,20]
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();thread.join(timeout=5)


@pytest.mark.parametrize('phase,surface', [('error', 'detail'), ('cancelled', 'sidebar')])
def test_retry_section_export_keeps_the_approved_report(section_job, monkeypatch, phase, surface):
    client, _, _, queued = section_job
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    assert client.post(endpoint + '/approve', json={}).status_code == 200
    response = client.post(endpoint + '/export', json={})
    assert response.status_code == 202
    job = web.JOBS[response.get_json()['job_id']]
    job['phase'], job['error'] = phase, 'Synthetic interrupted export'
    job['cancel'].set()
    report = Path(job['dir']) / 'report.json'
    approved = report.read_bytes()
    queued.clear()
    monkeypatch.setattr(web, 'openscrub_update', None)
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sync = pytest.importorskip('playwright.sync_api')
    try:
        with sync.sync_playwright() as pw:
            browser = browser_instance(pw)
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.set_default_timeout(10000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            load_browser_page(page, 'http://127.0.0.1:%s' % server.server_port, [], [])
            page.get_by_role('link', name=job['name'], exact=True).click()
            page.locator('#actions').get_by_role('button', name='Retry section export', exact=True).wait_for()
            if surface == 'detail':
                page.locator('#actions').get_by_role('button', name='Retry section export', exact=True).click()
            else:
                page.locator('#jobs').get_by_role('link', name='Retry section export', exact=True).click()
            page.wait_for_function("document.querySelector('#ph')?.textContent === 'queued_render'")
            assert queued == [(job['id'], 'render')]
            assert report.read_bytes() == approved
            assert job['error'] is None and not job['cancel'].is_set()
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
