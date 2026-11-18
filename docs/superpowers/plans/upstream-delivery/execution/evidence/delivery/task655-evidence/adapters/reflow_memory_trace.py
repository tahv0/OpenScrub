"""Diagnostic: in-memory current log owner/scroll/observer/RAF sequence only."""
import pytest

TRACE = r'''
await page.addInitScript(()=>{
 window.__qaTrace=[];window.__qaLogTrace=(kind,value)=>{const e=document.getElementById('log');if(!e)return;
  const top=e.getBoundingClientRect().top+e.clientTop,n=[...e.children].find(n=>n.getBoundingClientRect().bottom>top);
  window.__qaTrace.push({kind,value,width:e.clientWidth,height:e.clientHeight,top:e.scrollTop,
   visible:n?{seq:n.dataset.seq,offset:top-n.getBoundingClientRect().top}:null});};
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
def exact_trace(request,monkeypatch):
 if request.node.name!='test_actual_layout_anchor_threshold_pending_scroll_and_reflow':
  yield;return
 import openscrub_web as web
 import test_browser_log_retention as test
 page=web.PAGE
 replacements={
  'function remember(){saved=capture();ownedTop=element.scrollTop;}':
  'function remember(){saved=capture();ownedTop=element.scrollTop;globalThis.__qaLogTrace?.("remember",{saved,id,gen,current:current()});}',
  'function restore(anchor){':'function restore(anchor){globalThis.__qaLogTrace?.("restore",{anchor,id,gen,current:current()});',
  'if(frame===null)frame=requestAnimationFrame(()=>{':
  'if(frame===null)frame=requestAnimationFrame(()=>{',
 }
 for old,new in replacements.items():
  assert page.count(old)==1
  page=page.replace(old,new)
 monkeypatch.setattr(web,'PAGE',page)
 monkeypatch.setattr(test,'BROWSER_SETUP',test.BROWSER_SETUP.replace('await page.clock.install();','await page.clock.install();\n'+TRACE))
 original=test.run_browser
 def run_browser(base,script,name):
  old="const reflowAfter=await page.locator('#log').evaluate(e=>({seq:e.children[1].dataset.seq,offset:e.getBoundingClientRect().top-e.children[1].getBoundingClientRect().top}));"
  assert script.count(old)==1
  new="const reflowAfter=await page.locator('#log').evaluate(e=>{window.__qaLogTrace('fixture-read-after-resize');return {seq:e.children[1].dataset.seq,offset:e.getBoundingClientRect().top-e.children[1].getBoundingClientRect().top}});"
  script=script.replace(old,new)
  return original(base,'try{\n'+script+'\n}finally{console.log("MEMORY_TRACE "+JSON.stringify(await page.evaluate(()=>window.__qaTrace)));}\n',name)
 monkeypatch.setattr(test,'run_browser',run_browser)
 yield
