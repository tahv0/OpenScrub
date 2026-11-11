"""Existing production review -> per-frame report -> explicit saved model reuse."""
import json
import os
from pathlib import Path
import pytest
import cv2
import numpy as np
import openscrub_web as web
import learning_session as ls
from test_review_browser import review_server, browser_instance, load_browser_page


@pytest.mark.parametrize('width,height',[(1440,1000),(390,844)])
def test_coverage_report_and_recheck_are_in_place_and_do_not_retrain(review_server,monkeypatch,tmp_path,width,height):
    sync=pytest.importorskip('playwright.sync_api');url,report=review_server
    job=web.JOBS['inline-fixture'];root=Path(job['dir'])/'learning';stage=root/'passes/pass-123456789abc';stage.mkdir(parents=True)
    ls.atomic_json(root/'last-coverage.json',dict(pass_id=stage.name,version='synthetic-saved-model'))
    data=dict(decision='rejected',display_policy={'threshold':.5,'margin_fraction':.02},
        examples=[dict(frame=300,score=.9,coverage=.982,uncovered_pixels=50,excess_pixels_removed=500)],
        previews=[])
    ls.atomic_json(stage/'coverage.json',data)
    queued=[];monkeypatch.setattr(web.WORK_Q,'put',queued.append)
    monkeypatch.delenv('OPENSCRUB_TRAIN_WEIGHTS',raising=False)
    with sync.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':width,'height':height})
        page.set_default_timeout(10000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        load_browser_page(page,url,[],[])
        assert page.title()=='OpenScrub'
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        page.locator('#review').wait_for()
        before=page.locator('#review .det').count()
        page.get_by_role('button',name='Coverage results',exact=True).click()
        host=page.get_by_role('region',name='Saved model coverage results')
        host.get_by_text('98.200%',exact=True).wait_for()
        assert 'synthetic-saved-model' in host.inner_text()
        assert page.locator('#review .det').count()==before
        assert not queued
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(exist_ok=True,parents=True)
        host.screenshot(path=str(evidence/f'coverage-results-{width}.png'))
        page.get_by_role('button',name='Recheck saved model & rescan',exact=True).click()
        page.get_by_role('button',name='Cancel learning pass',exact=True).wait_for()
        assert queued==[('inline-fixture','learn')]
        assert job['learning_request']['reuse_candidate'] is True
        assert not errors,errors
        browser.close()
