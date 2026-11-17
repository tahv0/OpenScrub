"""Output choices exercise the shipped, evaluated JavaScript and emitted handlers.

The lightweight DOM supplies only mounting/attribute APIs; no decision logic.
Actual pointer, keyboard and layout checks use the separate browser QA run.
"""
import json
import shutil
import subprocess

import pytest

from test_review_save_failures import HARNESS, app_js

DOM = r"""
var mounted='';
// Choice tests mount emitted cards directly; the owning scheduling tests and
// real browser cover admission/geometry. This adapter contains no choice logic.
ReviewScheduler.prototype.start=function(){
 for(const section of this.meta.sections)for(const c of section.cards){const html=reviewCard(c);mount(html);}
 for(const id of this.meta.byId.keys())refreshDet(id);
};
ReviewScheduler.prototype.schedule=function(){};
ReviewScheduler.prototype.listen=function(){};
document.querySelectorAll=s=>[...elements.values()].filter(e=>e.id?.startsWith('det')&&
 e.dataset.cat===s.match(/data-cat=([^\]]+)/)?.[1]);
function mount(html){mounted+=html;
 for(const tag of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)){
  const e=document.createElement('div');e.id=tag[1];e.attrs={};
  e.setAttribute=(k,v)=>e.attrs[k]=String(v);e.getAttribute=k=>e.attrs[k];
  for(const a of tag[0].matchAll(/([\w-]+)="([^"]*)"/g))e.attrs[a[1]]=a[2];
  e.dataset.cat=e.attrs['data-cat'];e.classes=new Set((e.attrs.class||'').split(' '));
  e.classList={toggle(k,on){if(on)e.classes.add(k);else e.classes.delete(k);},remove(k){e.classes.delete(k)}};
  elements.set(e.id,e);
 }
}
detail.insertAdjacentHTML=(where,html)=>mount(html);
function click(id){const e=elements.get(id);if(!e)throw Error('missing action '+id);
 eval(e.attrs.onclick);}
async function review(rows){openJob('A');const p=loadReview();
 await reply({duration:5,detections:rows});await p;}
const row=(i,enabled,category='face',person=-1,track=-1,confidence=.5,zone_dropped=false)=>({
 i,enabled,category,person,track,confidence,zone_dropped,text:'synthetic '+i,t_start:i/10,t_end:2+i/10});
const rows=[row(0,true,'face',0,10,.4),row(1,false,'face',0,11,.9),
 row(2,true,'face',1,10,.8),row(3,false,'face',-1,10),row(4,true,'face',-1,20,.7),
 row(5,false,'face',-1,20,.2),row(6,true,'plate',-1,20),row(7,true,'email'),
 row(8,false,'face',0,11,.95,true),row(9,false,'face',-1,-1,.5,true),
 row(10,true),row(11,true,'face',0,11,.3),row(12,true,'person',0,11)];
function eq(a,b){if(JSON.stringify(a)!==JSON.stringify(b))throw Error(JSON.stringify(a)+' != '+JSON.stringify(b));}
function state(i,text,blur,keep){if(!elements.has('ds'+i))throw Error('missing output state for card '+i);eq(elements.get('ds'+i).textContent,text);
 eq(elements.get('bb'+i).getAttribute('aria-pressed'),String(blur));
 eq(elements.get('kb'+i).getAttribute('aria-pressed'),String(keep));}
"""


def run(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to evaluate the embedded review JavaScript")
    source = "const SOURCE=" + json.dumps(app_js()) + ";const SCENARIO=" + json.dumps(DOM + scenario) + ";" + HARNESS
    result = subprocess.run([node, "-e", source], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_repeated_explicit_actions_and_all_member_state():
    run("""await review(rows);
    state(1,'Mixed — 2 will be blurred; 1 will stay visible',false,false);
    if(elements.get('det1').classes.has('off'))throw Error('mixed group dimmed');
    for(const i of [1,4,10,8]){
      click('bb'+i);click('bb'+i);state(i,'Will be blurred',true,false);
      click('kb'+i);click('kb'+i);state(i,'Will stay visible',false,true);
      for(const m of TRKMEM[i]||[i])eq(EN[m],false);
    }
    eq([2,3,6,7,9,12].map(i=>EN[i]),[true,false,true,true,false,true]);
    """)


def test_grouping_and_context_preserve_boundaries():
    run("""await review(rows);eq(TRKMEM[1],[0,1,11]);eq(TRKMEM[4],[4,5]);
    for(const i of [2,3,6,7,10,12])eq(TRKMEM[i],[i]);
    if(!mounted.includes('Applies to all 3 appearances in this face group'))throw Error('missing scope');
    if(mounted.includes('ALL their appearances')||mounted.includes('NOT blurred'))throw Error('misleading scope');
    for(const i of [1,4,8]){
      const group=elements.get('dc'+i);eq(group.attrs.role,'group');
      if(!group.attrs['aria-label'].includes(String(i+1)))throw Error('missing appearance context');
    }
    """)


def test_member_editor_remove_is_row_local_and_refreshes_containing_card():
    run("""await review(rows);click('bb1');BE.sel=0;elements.set('beTimes',document.createElement('div'));elements.set('beRm',document.createElement('div'));beTimesUI=()=>{};beRemove();
    eq([EN[0],EN[1],EN[11]],[false,true,true]);eq(BE.sel,-1);
    state(1,'Mixed — 2 will be blurred; 1 will stay visible',false,false);
    BE.sel=1;beRemove();eq([EN[0],EN[1],EN[11]],[false,false,false]);
    state(1,'Will stay visible',false,true);eq(BE.sel,-1);
    """)


def test_category_selected_and_zone_setters_preserve_scope():
    run("""await review(rows);setAll('face',false);setAll('face',false);
    eq([0,1,2,3,4,5,10,11].map(i=>EN[i]),Array(8).fill(false));
    eq([6,7,8,9,12].map(i=>EN[i]),[true,true,false,false,true]);
    selSet.add(4);bulkSet(true);eq([...selSet],[]);eq([EN[4],EN[5],EN[1]],[true,true,false]);
    setAllZd(true);setAllZd(true);eq([EN[8],EN[9],EN[1]],[true,true,false]);
    click('kb8');eq([EN[8],EN[9]],[false,true]);
    """)


def test_bulk_refresh_work_is_bounded_by_members_and_cards():
    run("""const many=Array.from({length:600},(_,i)=>row(i,true,'face',Math.floor(i/3)));
    await review(many);let reads=0;const live=EN;EN=new Proxy(live,{get(o,k){reads++;return o[k]}});
    setAll('face',false);if(reads>2400)throw Error('bulk refresh scanned unrelated members: '+reads);
    eq(Object.values(live).filter(Boolean).length,0);
    """)


def test_actions_use_p07a_same_value_equality_acknowledgement():
    run("""await review(rows);click('bb10');const first=saveAndRender();
    eq(calls.at(-1).body.enabled,{10:true});click('bb10');await reply();await reply();await first;
    eq(Object.keys(EDITS.enabled),[]);eq(calls.filter(c=>c.url.endsWith('/render')).length,1);
    """)


def test_newer_opposite_action_survives_acknowledgement():
    run("""await review(rows);click('bb10');const first=saveAndRender();
    click('kb10');await reply();await first;eq(EDITS.enabled[10],false);
    eq(calls.filter(c=>c.url.endsWith('/render')).length,0);
    const retry=saveAndRender();await reply();await reply();await retry;eq(Object.keys(EDITS.enabled),[]);
    """)


def test_action_failed_save_and_job_switch_keep_owning_draft():
    run("""await review(rows);click('kb1');const first=saveAndRender();
    openJob('B');await reply({error:'busy'},423);await first;openJob('A');
    eq(EDITS.enabled,{0:false,1:false,11:false});eq(calls.filter(c=>c.url.endsWith('/render')).length,0);
    const retry=saveAndRender();openJob('B');await reply();await retry;openJob('A');
    eq(Object.keys(EDITS.enabled),[]);eq(calls.filter(c=>c.url.endsWith('/render')).length,0);
    """)
