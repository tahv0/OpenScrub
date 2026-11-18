"""Diagnostic only: record actual log scroll/observer/RAF and private anchors."""
import pytest

TRACE = r'''
await page.addInitScript(()=>{
 window.__qaLogTrace=(kind,value)=>{const e=document.getElementById('log');if(!e)return;
  const top=e.getBoundingClientRect().top+e.clientTop;
  const n=[...e.children].find(n=>n.getBoundingClientRect().bottom>top);
  console.log('LOG_TRACE '+JSON.stringify({kind,value,width:e.clientWidth,height:e.clientHeight,
   top:e.scrollTop,visible:n?{seq:n.dataset.seq,offset:top-n.getBoundingClientRect().top}:null}));};
 const Observe=window.ResizeObserver;
 window.ResizeObserver=class extends Observe{constructor(callback){super((entries,owner)=>{
  if(entries.some(x=>x.target.id==='log'))window.__qaLogTrace('observer-before');
  callback(entries,owner);
  if(entries.some(x=>x.target.id==='log'))window.__qaLogTrace('observer-after');});}};
 const frame=window.requestAnimationFrame.bind(window);
 window.requestAnimationFrame=callback=>frame(t=>{window.__qaLogTrace('raf-before');callback(t);window.__qaLogTrace('raf-after');});
 document.addEventListener('scroll',event=>{if(event.target.id==='log')window.__qaLogTrace('scroll-event');},true);
});
'''

@pytest.fixture(autouse=True)
def trace_exact_reflow(request,monkeypatch):
 if request.node.name!='test_actual_layout_anchor_threshold_pending_scroll_and_reflow':
  yield;return
 import openscrub_web as web
 import test_browser_log_retention as test
 page=web.PAGE
 old='function remember(){saved=capture();ownedTop=element.scrollTop;}'
 assert page.count(old)==1
 page=page.replace(old,'function remember(){saved=capture();ownedTop=element.scrollTop;globalThis.__qaLogTrace?.("remember",saved);}')
 old='function restore(anchor){'
 assert page.count(old)==1
 page=page.replace(old,'function restore(anchor){globalThis.__qaLogTrace?.("restore",anchor);')
 monkeypatch.setattr(web,'PAGE',page)
 assert test.BROWSER_SETUP.count('await page.clock.install();')==1
 monkeypatch.setattr(test,'BROWSER_SETUP',test.BROWSER_SETUP.replace('await page.clock.install();','await page.clock.install();\n'+TRACE))
 yield
