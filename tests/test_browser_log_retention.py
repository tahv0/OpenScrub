"""Real Chromium layout and actual producer→HTTP→PAGE recent-log acceptance.

Uses the existing optional, offline Playwright installation. Schedule controls
are explicit; browser layout assertions never use the Node geometry doubles.
"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_job_polling_browser import polling_http  # noqa: F401, shared real-route fixture


BROWSER_SETUP = r"""
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.env.POLLING_BASE,records=[],errors=[],diagnostics=[],requests=[];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn){for(let i=0;i<250;i++){if(await fn())return;await pause(20)}throw Error('condition expired')}
(async()=>{
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1280,height:950}});
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))diagnostics.push(m.text())});
await page.clock.install();
await page.route('**/api/**',route=>{
 const u=new URL(route.request().url());
 if(/^\/api\/jobs\/[AB](\/log)?$/.test(u.pathname)){requests.push(u.pathname+u.search);return route.continue()}
 let body={};if(u.pathname==='/api/jobs')body=[];
 if(u.pathname==='/api/quality_tier')body={tiers:[],current:'fast'};
 if(u.pathname==='/api/persist')body={enabled:false,count:0};
 return route.fulfill({json:body});
});
const control=async data=>{const r=await page.request.post(base+'/__qa__/control',{data});assert.equal(r.status(),200)};
const text=()=>page.locator('#log').textContent();
const cursor=()=>page.evaluate(()=>LOGN);
const note=()=>page.locator('#logStatus').textContent();
async function idle(){await wait(()=>page.evaluate(()=>POLL_CYCLE===null))}
async function poll(){const n=requests.length;await page.clock.runFor(900);await wait(()=>requests.length>=n+2);await idle()}
async function append(lines){await control({action:'append',lines});await poll()}
async function open(count=400){await control({action:'seed',count});await page.goto(base);
 await page.clock.pauseAt(await page.evaluate(()=>Date.now()+100));
 assert.equal(await page.title(),'OpenScrub');assert.match(await page.locator('body').innerText(),/OpenScrub/);
 await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===count);await idle()}
async function snap(){return page.locator('#log').evaluate(e=>({text:e.textContent,count:e.children.length,
 units:e.textContent.length,bytes:2*e.textContent.length,top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight,
 seq:[...e.children].map(n=>+n.dataset.seq),nodes:[...e.children].reduce((n,s)=>n+s.childNodes.length,0)}))}
try{
"""
BROWSER_FINISH = r"""
assert.deepEqual(errors,[]);assert.deepEqual(diagnostics,[]);
console.log(JSON.stringify({records,requests,errors,diagnostics,browser:browser.version(),url:page.url(),title:await page.title()}));
if(process.env.POLLING_ARTIFACTS)fs.writeFileSync(process.env.POLLING_ARTIFACTS+'/'+process.env.RETENTION_CASE+'.json',JSON.stringify({records,requests,errors,diagnostics,browser:browser.version()},null,2));
}finally{await control({release:true}).catch(()=>{});await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
"""


def run_browser(polling_http, script, name):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed for optional Playwright acceptance')
    available = subprocess.run([node, '-e', "require('playwright')"], capture_output=True)
    if available.returncode:
        pytest.skip('Existing Playwright required; no dependency installation attempted')
    env = dict(os.environ, POLLING_BASE=polling_http, RETENTION_CASE=name)
    result = subprocess.run([node, '-e', BROWSER_SETUP + script + BROWSER_FINISH],
                            capture_output=True, text=True, env=env, timeout=150)
    if os.environ.get('POLLING_ARTIFACTS'):
        Path(os.environ['POLLING_ARTIFACTS'], name + '.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


def test_production_polling_bounds_recent_entries_and_keeps_content_nodes(polling_http):
    # Removing display eviction must fail even though the producer is bounded.
    run_browser(polling_http, r"""
await open();
for(let batch=0;batch<6;batch++)await append(Array.from({length:100},(_,i)=>'L'+(400+batch*100+i)));
const s=await snap();console.log(JSON.stringify({observedEntries:s.text.split('\n').length,cursor:await cursor(),units:s.units}));
assert.equal(s.text.split('\n').length,800,'recent transcript must stop growing at800');
assert.equal(s.text,Array.from({length:800},(_,i)=>'L'+(200+i)).join('\n'));
assert.equal(s.count,800);assert.equal(s.nodes,1599);assert.deepEqual(s.seq,Array.from({length:800},(_,i)=>200+i));
assert.ok(s.bytes<=2097152);assert.match(await note(),/omitted/);
await page.evaluate(()=>window.retainedNode=document.querySelector('#log [data-seq="500"]').firstChild);
await append(['tail']);assert.equal(await cursor(),1001);
assert.equal(await page.evaluate(()=>window.retainedNode===document.querySelector('#log [data-seq="500"]').firstChild),true);
const before=await snap();await poll();assert.deepEqual(await snap(),before,'empty normal poll preserves display/scroll');
await page.locator('#log').focus();await page.evaluate(()=>{const r=document.createRange(),node=document.getElementById('log').firstChild.firstChild;r.setStart(node,0);r.setEnd(node,2);getSelection().removeAllRanges();getSelection().addRange(r)});
await append(['selection-eviction']);assert.equal(await page.evaluate(()=>getSelection().rangeCount),0);assert.equal(await page.locator('#log').evaluate(e=>document.activeElement===e),true);
if(process.env.POLLING_ARTIFACTS){await page.locator('#log').scrollIntoViewIfNeeded();await page.screenshot({path:process.env.POLLING_ARTIFACTS+'/retention-desktop.png'})}
await append(Array.from({length:1000},(_,i)=>'large-batch-'+i));assert.equal(await cursor(),2002);assert.equal((await snap()).count,800);assert.equal(await text(),Array.from({length:800},(_,i)=>'large-batch-'+(200+i)).join('\n'));
records.push({case:'count-bound',...s,text:undefined,first:s.seq[0],last:s.seq.at(-1),largeBatchCursor:2002});
""", 'count-bound')


def test_actual_layout_anchor_threshold_pending_scroll_and_reflow(polling_http):
    # Taking stickiness before the awaited body loses the reader's final position.
    run_browser(polling_http, r"""
await open(600);
const geometry=()=>page.locator('#log').evaluate(e=>({top:e.scrollTop,max:e.scrollHeight-e.clientHeight,
 anchor:[...e.children].find(s=>s.getBoundingClientRect().bottom>e.getBoundingClientRect().top+e.clientTop)?.dataset.seq}));
for(const distance of [39,40,41]){
 await page.locator('#log').evaluate((e,d)=>e.scrollTop=e.scrollHeight-e.clientHeight-d,distance);
 const before=await geometry();await append(['threshold-'+distance]);const after=await geometry();
 if(distance<=40)assert.ok(after.max-after.top<=1,JSON.stringify({distance,before,after}));
 else{assert.equal(after.anchor,before.anchor);assert.ok(Math.abs(after.top-before.top)<=2)}
 records.push({case:'threshold',distance,before,after});
}
// The response body is created by Flask before the browser scrolls up.
await control({action:'append',lines:['held-body']});await control({kind:'log'});
let headers=0;page.on('response',r=>{if(r.headers()['x-qa-body-gate']==='log')headers++});
await page.locator('#log').evaluate(e=>e.scrollTop=e.scrollHeight);await page.clock.runFor(900);await wait(()=>headers===1);
await page.locator('#log').evaluate(e=>e.scrollTop=700);const pending=await geometry();
await control({release:true});await idle();assert.equal((await geometry()).anchor,pending.anchor);
assert.ok(Math.abs((await geometry()).top-pending.top)<=2);records.push({case:'scroll-during-body',pending,after:await geometry()});
// Retain a mid-history entry while a prefix is evicted.
await page.locator('#log').evaluate(e=>{const s=e.querySelector('[data-seq="400"]');e.scrollTop+=s.getBoundingClientRect().top-e.getBoundingClientRect().top+7});
const before=await page.locator('#log').evaluate(e=>{const s=e.querySelector('[data-seq="400"]');return s.getBoundingClientRect().top-e.getBoundingClientRect().top});
await append(Array.from({length:400},(_,i)=>'retained-'+i));
const after=await page.locator('#log').evaluate(e=>e.querySelector('[data-seq="400"]').getBoundingClientRect().top-e.getBoundingClientRect().top);
assert.ok(Math.abs(after-before)<=2,JSON.stringify({before,after}));
await page.locator('#log').evaluate(e=>e.scrollTop=0);await append(Array.from({length:400},(_,i)=>'evict-'+i));
assert.equal((await geometry()).top,0);assert.match(await note(),/position/);records.push({case:'evicted-anchor',...await geometry()});
// A genuine keyboard scroll clears the fixed lost-position notice and retains focus.
await page.locator('#log').focus();await page.keyboard.press('PageDown');await page.clock.runFor(300);await pause(350);console.log(JSON.stringify({keyboard:await geometry(),note:await note()}));
assert.equal(await page.locator('#log').evaluate(e=>document.activeElement===e),true);assert.doesNotMatch(await note(),/position/);
// Rewrap a tall multiline entry; position is entry+clamped pixel, not character.
await control({action:'replace',count:0});await poll();
const multiline=Array.from({length:20},(_,i)=>'wide paragraph '+i+' '+('word '.repeat(25))).join('\n');
await append(['prefix '+('words '.repeat(100)),multiline,'tail'+String.fromCharCode(10).repeat(500)]);
await page.locator('#log').evaluate(e=>{const s=e.children[1];e.scrollTop+=s.getBoundingClientRect().top-e.getBoundingClientRect().top+30});
const reflowBefore=await page.locator('#log').evaluate(e=>({seq:e.children[1].dataset.seq,offset:e.getBoundingClientRect().top-e.children[1].getBoundingClientRect().top}));
await page.setViewportSize({width:390,height:844});await pause(40);await page.clock.runFor(40);await pause(20);
const reflowAfter=await page.locator('#log').evaluate(e=>({seq:e.children[1].dataset.seq,offset:e.getBoundingClientRect().top-e.children[1].getBoundingClientRect().top}));
assert.equal(reflowAfter.seq,reflowBefore.seq);assert.ok(Math.abs(reflowAfter.offset-reflowBefore.offset)<=2,JSON.stringify({reflowBefore,reflowAfter}));
assert.equal(await page.locator('#log').getAttribute('aria-label'),'Job log');assert.equal(await page.locator('#log').getAttribute('aria-describedby'),'logStatus');
assert.equal(await page.locator('#log').getAttribute('aria-live'),null);assert.equal(await page.locator('#logStatus').getAttribute('role'),null);
assert.equal(await page.locator('#log').evaluate(e=>getComputedStyle(e).overflowAnchor),'none');
if(process.env.POLLING_ARTIFACTS){await page.locator('#log').scrollIntoViewIfNeeded();await page.screenshot({path:process.env.POLLING_ARTIFACTS+'/retention-narrow.png'})}
records.push({case:'narrow-reflow',reflowBefore,reflowAfter,...await geometry()});
await page.locator('#log').evaluate(e=>{const s=e.children[1];e.scrollTop+=s.getBoundingClientRect().top-e.getBoundingClientRect().top+1000});await pause(40);await page.clock.runFor(40);
const clampBefore=await page.locator('#log').evaluate(e=>e.getBoundingClientRect().top-e.children[1].getBoundingClientRect().top);
await page.setViewportSize({width:1280,height:950});await pause(40);await page.clock.runFor(40);await pause(20);
const clampAfter=await page.locator('#log').evaluate(e=>({offset:e.getBoundingClientRect().top-e.children[1].getBoundingClientRect().top,height:e.children[1].getBoundingClientRect().height}));
assert.ok(clampBefore>clampAfter.height,JSON.stringify({clampBefore,clampAfter}));assert.ok(Math.abs(clampAfter.offset-(clampAfter.height-1))<=2,JSON.stringify({clampBefore,clampAfter}));
await page.locator('#log').evaluate(e=>new Promise(resolve=>{const before=e.scrollTop;e.addEventListener('scroll',()=>resolve(),{once:true});e.scrollTop=e.scrollHeight;if(e.scrollTop===before)resolve()}));await page.clock.runFor(40);await page.setViewportSize({width:390,height:844});await pause(40);await page.clock.runFor(40);await pause(20);const bottomReflow=await geometry();assert.ok(bottomReflow.max-bottomReflow.top<=1,JSON.stringify(bottomReflow));
assert.equal(await page.locator('#log').evaluate(e=>document.activeElement===e),true,'accepted reset/reflow never moves keyboard focus');
records.push({case:'clamped-reflow-bottom',clampBefore,clampAfter});
""", 'layout')


def test_blank_multiline_unicode_copy_and_selection_ownership(polling_http):
    # Stable entry nodes must preserve literal separators and retained selection.
    run_browser(polling_http, r"""
await open(0);const entries=['','alpha\nbeta','','😀e\u0301\t漢字\r\nend',''];await append(entries);
assert.equal(await text(),entries.join('\n'));let s=await snap();assert.equal(s.count,5);assert.deepEqual(s.seq,[0,1,2,3,4]);assert.equal(s.nodes,9);
await page.evaluate(()=>{const e=document.getElementById('log'),r=document.createRange();r.selectNodeContents(e);const s=getSelection();s.removeAllRanges();s.addRange(r)});
assert.equal(await page.evaluate(()=>getSelection().toString()),entries.join('\n'));
// Real browser copy dispatch to clipboard, including blank and multiline entries.
await page.context().grantPermissions(['clipboard-read','clipboard-write']);await page.locator('#log').focus();
await page.keyboard.press('Control+c');assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),entries.join('\n'));
await append(['after-copy']);assert.equal(await page.evaluate(()=>getSelection().rangeCount),1,'append keeps retained container selection');
await page.evaluate(()=>{const e=document.getElementById('log'),r=document.createRange();r.setStart(e.children[1].firstChild,1);r.setEnd(e.children[3].firstChild,2);const s=getSelection();s.removeAllRanges();s.addRange(r);window.selectedStart=s.anchorNode;window.selectedEnd=s.focusNode;window.selectedText=s.toString()});
await append(['retained']);assert.equal(await page.evaluate(()=>getSelection().anchorNode===window.selectedStart&&getSelection().focusNode===window.selectedEnd&&getSelection().toString()===window.selectedText),true);
// Outside and mixed selections are owned by the document; no explicit clearing.
await page.evaluate(()=>{const p=document.createElement('p');p.id='outside';p.textContent='outside text';document.body.append(p);const r=document.createRange();r.selectNodeContents(p);const s=getSelection();s.removeAllRanges();s.addRange(r);window.clearCalls=0;const old=s.removeAllRanges.bind(s);s.removeAllRanges=()=>{window.clearCalls++;old()}});
await control({action:'replace',count:2});await poll();assert.equal(await page.evaluate(()=>getSelection().toString()),'outside text');assert.equal(await page.evaluate(()=>window.clearCalls),0);
await page.evaluate(()=>{const r=document.createRange();r.setStart(document.querySelector('#log span').firstChild,0);r.setEnd(document.getElementById('outside').firstChild,7);getSelection().removeAllRanges();getSelection().addRange(r);window.clearCalls=0});
assert.equal(await page.evaluate(()=>document.getElementById('log').contains(getSelection().anchorNode)&&document.getElementById('outside').contains(getSelection().focusNode)),true);
await control({action:'replace',count:3});await poll();assert.equal(await page.evaluate(()=>window.clearCalls),0);
await page.evaluate(()=>{const s=getSelection();s.removeAllRanges();const r=document.createRange();r.selectNodeContents(document.getElementById('log'));s.addRange(r);window.clearCalls=0});
await control({action:'replace',count:0});await poll();assert.equal(await text(),'');assert.equal(await page.evaluate(()=>window.clearCalls),1);assert.equal(await page.evaluate(()=>getSelection().rangeCount),0);
records.push({case:'literal-content-copy-selection',entries,bytes:s.bytes});
""", 'selection')


def test_text_budget_long_entries_and_legacy_defense(polling_http):
    # A count-only cap admits more than2MiB when long accepted entries accumulate.
    run_browser(polling_http, r"""
await open(0);const line='x'.repeat(8192);
for(let i=0;i<5;i++)await append(Array.from({length:50},()=>line));
const s=await snap();assert.equal(s.count,127);assert.equal(s.bytes,2081020);assert.deepEqual(s.seq,Array.from({length:127},(_,i)=>123+i));assert.equal(await cursor(),250);
assert.equal(s.text,Array.from({length:127},()=>line).join('\n'));assert.match(await note(),/omitted/);
await append(['y'.repeat(8065)]);assert.equal((await snap()).count,128);assert.equal((await snap()).bytes,2097152,'exact UTF16 ceiling includes127 LFs');
await append(['']);assert.equal((await snap()).count,128);assert.equal((await snap()).bytes,2080768,'one LF over budget evicts a complete entry');
// A compliant producer's Unicode truncation remains byte-for-byte unchanged.
await append(['😀'.repeat(10000)]);const response=await page.request.get(base+'/api/jobs/A/log?from=252');const body=await response.json();
assert.equal(await page.locator('#log span').last().textContent(),body.lines[0]);assert.match(body.lines[0],/message truncated/);
// A near-full compliant producer snapshot still admits all400 initial entries.
await control({action:'replace',count:0});await poll();const compliant='c'.repeat(1310);await append(Array.from({length:400},()=>compliant));
await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===400);await idle();assert.equal((await snap()).count,400);assert.equal((await snap()).bytes,1048798);assert.doesNotMatch(await note(),/display.*truncated/);
// Controlled old server input tests the browser defense, not the producer cap.
await page.unroute('**/api/**');let responseIndex=0;
const suffix='... [display entry truncated]',oversize='a'.repeat(8192-suffix.length-1)+'😀'+'z'.repeat(10000);
await page.route('**/api/**',route=>{const u=new URL(route.request().url());
 if(/^\/api\/jobs\/[AB](\/log)?$/.test(u.pathname))requests.push(u.pathname+u.search);
 if(u.pathname==='/api/jobs/A')return route.fulfill({json:{id:'A',name:'legacy',phase:'queued',progress:0}});
 if(u.pathname.endsWith('/log'))return route.fulfill({json:responseIndex++?{from:3,len:3,lines:[]}:{from:0,len:3,lines:['',oversize,'']}});
 return route.fulfill({json:u.pathname==='/api/jobs'?[]:{}})});
await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===3);await idle();
assert.equal(await page.locator('#log span').count(),3);
const guarded=await page.locator('#log span').nth(1).evaluate(e=>e.firstChild.data);
assert.equal(guarded,'a'.repeat(8192-suffix.length-1)+suffix);assert.equal(guarded.length,8191);assert.match(await note(),/display.*truncated/);
assert.equal(await text(),'\n'+guarded+'\n');const emptyBefore=await snap();await poll();assert.deepEqual(await snap(),emptyBefore);
records.push({case:'byte-budget',count:s.count,bytes:s.bytes,first:s.seq[0],last:s.seq.at(-1),guardUnits:guarded.length});
""", 'text-budget')



def test_view_disposal_owns_observers_frames_notes_and_controlled_lifecycle(polling_http):
    # Old view observers/frames must not publish after an A→B→A replacement.
    run_browser(polling_http, r"""
await page.addInitScript(()=>{
 const Native=ResizeObserver;window.observers=[];window.frames=new Set();window.cancelledFrames=0;
 window.ResizeObserver=class{constructor(callback){this.callback=callback;this.native=new Native(callback);this.active=false;window.observers.push(this)}
 observe(e){this.element=e;this.active=true;this.native.observe(e)}disconnect(){this.active=false;this.native.disconnect()}};
 const request=window.requestAnimationFrame.bind(window),cancel=window.cancelAnimationFrame.bind(window);
 window.requestAnimationFrame=callback=>{let id=request(time=>{window.frames.delete(id);callback(time)});window.frames.add(id);return id};
 window.cancelAnimationFrame=id=>{if(window.frames.delete(id))window.cancelledFrames++;cancel(id)};
});
await open(500);await page.clock.runFor(40);
await page.evaluate(()=>{window.oldLog=document.getElementById('log');oldLog.style.width='200px';window.observers[0].callback();});
assert.equal(await page.evaluate(()=>window.frames.size),1);
await page.evaluate(()=>openJob('B'));await wait(async()=>await cursor()===1);await idle();
assert.equal(await text(),'log-B');assert.equal(await page.evaluate(()=>window.observers.filter(o=>o.active).length),1);
assert.equal(await page.evaluate(()=>window.observers[0].active),false);assert.equal(await page.evaluate(()=>window.cancelledFrames),1);
await page.evaluate(()=>window.observers[0].callback());await page.clock.runFor(40);assert.equal(await text(),'log-B');assert.equal(await note(),'');
await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===500);await idle();
assert.equal((await snap()).count,400);assert.match(await text(),/^L100\n/);
// Controlled schedule only; this does not simulate native suspension.
await page.evaluate(()=>{window.testHidden=true;Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.testHidden});document.dispatchEvent(new Event('visibilitychange'))});
const n=requests.length;await control({action:'append',lines:['while-background']});await page.clock.runFor(20000);assert.equal(requests.length,n);
await page.evaluate(()=>{window.testHidden=false;document.dispatchEvent(new Event('visibilitychange'));for(const name of ['focus','pageshow','online'])window.dispatchEvent(new Event(name))});
await page.clock.runFor(0);await wait(async()=>await cursor()===501);await idle();assert.ok((await text()).endsWith('while-background'));
assert.equal(await page.evaluate(()=>window.observers.filter(o=>o.active).length),1);
await control({action:'cancel'});page.once('dialog',dialog=>dialog.accept());await page.evaluate(()=>delJob('A'));await wait(()=>page.evaluate(()=>CUR===null));
assert.equal(await page.locator('#log').count(),0);assert.equal(await page.evaluate(()=>window.observers.filter(o=>o.active).length),0);assert.equal(await page.evaluate(()=>RECENT_LOG===null&&window.frames.size===0),true);
await page.evaluate(()=>{for(const observer of window.observers)observer.callback()});await page.clock.runFor(40);assert.equal(await page.locator('#logStatus').count(),0);
records.push({case:'owned-cleanup-controlled-background',observers:await page.evaluate(()=>window.observers.length)});
""", 'lifecycle')



def test_blank_entry_anchor_survives_trim_and_has_real_geometry(polling_http):
    run_browser(polling_http, r"""
await open(0);await append(Array.from({length:400},()=>''));
assert.equal((await snap()).count,400);assert.equal(await text(),'\n'.repeat(399));
await page.locator('#log').evaluate(e=>{const s=e.children[100];e.scrollTop+=s.getBoundingClientRect().top-e.getBoundingClientRect().top+5});
const anchor=()=>page.locator('#log').evaluate(e=>{const s=e.querySelector('[data-seq="100"]');return s?{offset:s.getBoundingClientRect().top-e.getBoundingClientRect().top,height:s.getBoundingClientRect().height}:null});
const before=await anchor();assert.ok(before.height>0);
await append(Array.from({length:400},()=>''));await append(Array.from({length:100},()=>''));
assert.ok(Math.abs((await anchor()).offset-before.offset)<=2);assert.equal((await snap()).seq[0],100);assert.equal(await text(),'\n'.repeat(799));
await append(['']);assert.equal((await snap()).seq[0],101);assert.equal((await snap()).top,0);assert.match(await note(),/position/);
records.push({case:'blank-anchor',before,oldest:101,count:(await snap()).count});
""", 'blank-anchor')
