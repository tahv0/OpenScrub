"""Production UI -> save annotations -> sample/learning queue; no CUDA required."""
import json
from pathlib import Path
import os
import pytest
import openscrub_web as web
from test_review_browser import review_server, browser_instance, load_browser_page


@pytest.mark.parametrize('width,height',[(1440,1000),(390,844)])
def test_learning_controls_preserve_decisions_and_queue_a_full_pass(review_server,monkeypatch,tmp_path,width,height):
    sync=pytest.importorskip('playwright.sync_api');url,report=review_server
    monkeypatch.delenv('OPENSCRUB_TRAIN_WEIGHTS',raising=False)
    queued=[];monkeypatch.setattr(web.WORK_Q,'put',queued.append)
    with sync.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':width,'height':height})
        page.set_default_timeout(12000);errors=[];dialogs=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def dialog(d):dialogs.append(d.message);d.accept()
        page.on('dialog',dialog)
        load_browser_page(page,url,[],[])
        assert page.title()=='OpenScrub'
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        page.locator('#review').wait_for()
        assert page.locator('#review .det').count()==90
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        page.wait_for_function('document.querySelectorAll("#review .det").length===9')
        assert len(page.evaluate('Object.keys(EN)'))==90
        page.get_by_role('button',name='Show all findings',exact=True).click()
        page.wait_for_function('document.querySelectorAll("#review .det").length===90')
        page.get_by_role('button',name='Train & rescan this video',exact=True).click()
        page.wait_for_function('LEARNING_TERMS===true')
        for _ in range(40):
            if any('Training setup needed' in d for d in dialogs):break
            page.wait_for_timeout(100)
        assert any('Training setup needed' in d for d in dialogs)
        assert not queued and web.JOBS['inline-fixture']['phase']=='review'
        checkpoint=tmp_path/'fixture-seg.pt';checkpoint.write_bytes(b'not executed by browser fixture')
        monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS',str(checkpoint))
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(exist_ok=True,parents=True)
        page.locator('#review').screenshot(path=str(evidence/f'learning-review-{width}.png'))
        page.get_by_role('button',name='Train & rescan this video',exact=True).click()
        page.get_by_role('button',name='Cancel learning pass',exact=True).wait_for()
        assert queued==[('inline-fixture','learn')]
        assert web.JOBS['inline-fixture']['phase']=='learning'
        assert page.locator('#review').count()==0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        page.locator('#jobcard').screenshot(path=str(evidence/f'learning-queued-{width}.png'))
        browser.close()
