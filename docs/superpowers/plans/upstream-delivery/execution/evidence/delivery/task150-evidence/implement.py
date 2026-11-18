from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub/openscrub_web.py')
s=p.read_text()
s=s.replace(' VIEW_GEN++;CUR=id;',' VIEW_GEN++;CUR=id;\n resetReviewView();')
start=s.index(' const groups={}; const zdrop=[]; TRKMEM={}; ROWCARD={};',s.index('async function loadReview'))
end=s.index(' let html=',start)
s=s[:start]+''' d.detections.forEach(x=>{EN[x.i]=(x.i in EDITS.enabled)?EDITS.enabled[x.i]:x.enabled;});
 REVIEW_META=reviewDescriptors(d.detections);
 const zdrop=REVIEW_META.cards.filter(c=>c.zone).map(c=>c.representative);
'''+s[end:]
s=s.replace(' <div id="beslot"></div>\n <div id="detwrap"',''' <div class="row reviewfilters">
  <label>Detection type <select id="reviewType" onchange="setReviewFilter(this.value||null,REVIEW_FILTER.output)"></select></label>
  <label>Output <select id="reviewOutput" onchange="setReviewFilter(REVIEW_FILTER.type,this.value)"></select></label>
  <button class="sec" id="reviewFilterReset" onclick="setReviewFilter(null,'all')">Show all</button>
 </div>
 <div id="reviewFilterStatus" role="status" aria-live="polite"></div>
 <p class="detscope">Mixed groups appear in both output views. Filters only change the view.</p>
 <p id="reviewFilterHint" class="detscope"></p>
 <p id="reviewFilterEmpty" hidden></p>
 <div id="beslot"></div>
 <div id="detwrap"''',1)
s=s.replace('<details style="margin:4px 0 10px;','<details id="reviewZones" ontoggle="reviewZoneToggle()" style="margin:4px 0 10px;',1)
s=s.replace('⚠ ${zdrop.length} detection(s) outside your zones — choose output below','⚠ <span id="reviewZoneCount">${zdrop.length} of ${zdrop.length}</span> detection(s) outside your zones — choose output below',1)
s=s.replace('<button class="sec" onclick="setAllZd(false)">Keep all visible</button></div>','<button class="sec" onclick="setAllZd(false)">Keep all visible</button></div>\n   <div class="detscope">These actions affect all outside-zone detections, including filtered-out detections.</div>',1)
start=s.index(' for(const[cat,rawItems] of Object.entries(groups)){',s.index('async function loadReview'))
end=s.index('  for(const x of items){',start)
s=s[:start]+''' for(const section of REVIEW_META.sections.filter(s=>!s.zone)){
  const cat=section.category,items=section.cards.map(c=>c.representative);
  html+=`<section id="reviewSection${section.index}"><h3 style="margin:10px 0 6px">${detLabel(CATDN[cat]||cat)} <span class="badge" id="reviewCount${section.index}">${items.length}</span>
  <button class="sec" style="padding:3px 8px;font-size:12px"
   onclick="setAll(REVIEW_META.sections[${section.index}].category,true)">Blur all</button>
  <button class="sec" style="padding:3px 8px;font-size:12px"
   onclick="setAll(REVIEW_META.sections[${section.index}].category,false)">Keep all visible</button></h3>
   <div class="detscope">Category actions affect all ${detLabel(CATDN[cat]||cat)} groups, including filtered-out groups.</div><div class="grid3">`;
'''+s[end:]
s=s.replace('data-cat="${cat}"','data-cat="${detLabel(cat)}"',1)
s=s.replace('  html+=`</div>`}\n html+=`</div>','  html+=`</div></section>`}\n html+=`</div>',1)
s=s.replace(' initMarquee();saveStatus(EDITS,EDITS.status);',' refreshReviewFilters();initMarquee();saveStatus(EDITS,EDITS.status);',1)
anchor='let TRKMEM={},ROWCARD={};'
metadata=r'''
// Display metadata retains complete P02 groups; EN remains the only live output map.
let REVIEW_META={cards:[],sections:[],byId:{}},REVIEW_FILTER={jobId:null,viewGen:0,type:null,output:"all"};
function resetReviewView(){
 cancelReviewMarquee();clearSel();TRKMEM={};ROWCARD={};
 REVIEW_META={cards:[],sections:[],byId:{}};
 REVIEW_FILTER={jobId:CUR,viewGen:VIEW_GEN,type:null,output:"all"};
}
function reviewDescriptors(rows){
 const groups=new Map(),zones=[];TRKMEM={};ROWCARD={};
 for(const x of rows){if(x.zone_dropped)zones.push(x);
  else{if(!groups.has(x.category))groups.set(x.category,[]);groups.get(x.category).push(x);}}
 const meta={cards:[],sections:[],byId:{}};
 function section(category,zone,items){
  const s={category,zone,index:meta.sections.length,cards:[],ids:[]};
  for(const x of items){const c={id:x.i,category,realCategory:x.category,zone,representative:x,members:zone?[x.i]:TRKMEM[x.i]};
   s.cards.push(c);s.ids.push(c.id);meta.cards.push(c);meta.byId[c.id]=c;
   for(const m of c.members)ROWCARD[m]=c.id;}
  meta.sections.push(s);
 }
 if(zones.length)section("zdrop",true,zones);
 for(const [cat,rawItems]of groups){
  const byGroup=new Map(),items=[];
  for(const x of rawItems){
   const key=x.person>=0?("p"+x.person):(x.track>=0?("t"+x.track):null);
   if(key){if(!byGroup.has(key))byGroup.set(key,[]);byGroup.get(key).push(x);}
   else{TRKMEM[x.i]=[x.i];items.push(x);}
  }
  for(const [key,members]of byGroup){
   members.sort((a,b)=>a.t_start-b.t_start);
   let best=members[0];
   for(const m of members)if((m.confidence||0)>(best.confidence||0))best=m;
   const rep={...best,t_start:members[0].t_start,t_end:members[members.length-1].t_end,
    frames:members.length,personcard:key[0]==="p"};
   TRKMEM[rep.i]=members.map(m=>m.i);items.push(rep);
  }
  items.sort((a,b)=>((b.personcard?1:0)-(a.personcard?1:0))||a.t_start-b.t_start);
  section(cat,false,items);
 }
 return meta;
}
function reviewMatches(card,type,output){
 return (type===null||card.realCategory===type)&&(output==="all"||
  card.members.some(i=>output==="blur"?!!EN[i]:!EN[i]));
}
function setReviewFilter(type,output){
 if(!ownsView(REVIEW_FILTER.jobId,REVIEW_FILTER.viewGen))return;
 cancelReviewMarquee();clearSel();REVIEW_FILTER.type=type;REVIEW_FILTER.output=output;
 refreshReviewFilters();
}
function reviewSelectable(i){
 const c=REVIEW_META.byId[i];if(!c||!reviewMatches(c,REVIEW_FILTER.type,REVIEW_FILTER.output))return false;
 return !c.zone||!!document.getElementById("reviewZones")?.open;
}
function pruneReviewSelection(){
 let changed=false;
 for(const i of [...selSet])if(!reviewSelectable(i)){
  selSet.delete(i);document.getElementById("det"+i)?.classList.remove("selected");changed=true;}
 if(changed&&menuEl){
  if(!selSet.size){menuEl.remove();menuEl=null;}
  else menuEl.querySelector("span").textContent=selSet.size+" selected";
 }
}
function reviewZoneToggle(){pruneReviewSelection();refreshReviewFilters();}
function refreshReviewFilters(){
 if(!ownsView(REVIEW_FILTER.jobId,REVIEW_FILTER.viewGen))return;
 const typeControl=document.getElementById("reviewType"),outputControl=document.getElementById("reviewOutput");
 if(!typeControl||!outputControl)return;
 const types=[...new Set([...REVIEW_META.cards.filter(c=>!c.zone),...REVIEW_META.cards.filter(c=>c.zone)].map(c=>c.realCategory))];
 if(REVIEW_FILTER.type!==null&&!types.includes(REVIEW_FILTER.type))REVIEW_FILTER.type=null;
 const {type,output}=REVIEW_FILTER,typeCounts=new Map(types.map(t=>[t,0])),outputCounts={all:0,blur:0,visible:0};
 let count=0,ordinary=0,zones=0,otherTypeCount=0;
 const sectionCounts=new Map(REVIEW_META.sections.map(s=>[s.index,0]));
 const active=document.activeElement,focusedCard=active?.closest?.(".det");
 let lostFocus=false;
 // Derive aggregates once per transaction, independently of mounted/closed cards.
 for(const s of REVIEW_META.sections)for(const c of s.cards){
  let blurred=0;for(const i of c.members)if(EN[i])blurred++;
  const kept=c.members.length-blurred,typeMatch=type===null||c.realCategory===type;
  const outputMatch=output==="all"||(output==="blur"?blurred>0:kept>0),match=typeMatch&&outputMatch;
  if(outputMatch){typeCounts.set(c.realCategory,typeCounts.get(c.realCategory)+1);otherTypeCount++;}
  if(typeMatch){outputCounts.all++;if(blurred)outputCounts.blur++;if(kept)outputCounts.visible++;}
  if(match){count++;if(c.zone)zones++;else ordinary++;sectionCounts.set(s.index,sectionCounts.get(s.index)+1);}
  const node=document.getElementById("det"+c.id);
  if(node){if(!match&&focusedCard===node)lostFocus=true;node.hidden=!match;}
 }
 typeControl.innerHTML=`<option value="">All detected types (${otherTypeCount})</option>`+types.map(t=>`<option value="${detLabel(t)}">${detLabel(CATDN[t]||t)} (${typeCounts.get(t)})</option>`).join("");
 typeControl.value=type??"";
 outputControl.innerHTML=[["all","All outputs"],["blur","Includes blurred appearances"],["visible","Includes visible appearances"]].map(([v,label])=>`<option value="${v}">${label} (${outputCounts[v]})</option>`).join("");
 outputControl.value=output;
 const zoneDetails=document.getElementById("reviewZones");
 for(const s of REVIEW_META.sections){
  const n=sectionCounts.get(s.index),node=document.getElementById(s.zone?"reviewZones":"reviewSection"+s.index);
  if(node){if(!n&&node.contains?.(active))lostFocus=true;node.hidden=!n;}
  const badge=document.getElementById(s.zone?"reviewZoneCount":"reviewCount"+s.index);
  if(badge)badge.textContent=s.zone?`${n} of ${s.cards.length}`:String(n);
 }
 document.getElementById("reviewFilterStatus").textContent=`${count} of ${REVIEW_META.cards.length} cards match`;
 const empty=document.getElementById("reviewFilterEmpty");empty.hidden=count>0;
 empty.textContent=REVIEW_META.cards.length?"No cards match these filters.":"No detections in this job.";
 document.getElementById("reviewFilterHint").textContent=count>0&&!ordinary&&zones&&!zoneDetails?.open?
  `${zones} matching card${zones===1?" is":"s are"} outside your zones; open that section to inspect them.`:"";
 pruneReviewSelection();
 if(lostFocus)outputControl.focus();
}
'''
s=s.replace(anchor,anchor+'\n'+metadata)
start=s.index('function applyDet(i,blur){')
end=s.index('function thumbRetry',start)
s=s[:start]+r'''let DET_BATCH=0,DET_DIRTY=new Set();
function finishDetChoices(){
 if(!EDITS.busy)saveStatus(EDITS,"Unsaved edits — save to include them in the render.");
 DET_DIRTY.forEach(refreshDet);DET_DIRTY.clear();
 if(document.getElementById("beCv")){beFilter();beDraw();}
 refreshReviewFilters();
}
function applyDet(i,blur){
 for(const m of (TRKMEM[i]||[i])){
  EN[m]=blur;EDITS.enabled[m]=blur;DET_DIRTY.add(ROWCARD[m]??m);
 }
 if(!DET_BATCH)finishDetChoices();
}
function applyDetBatch(ids,on){
 DET_BATCH++;
 try{for(const i of ids)applyDet(i,on);}
 finally{if(!--DET_BATCH)finishDetChoices();}
}
function setAll(cat,on){applyDetBatch(REVIEW_META.cards.filter(c=>!c.zone&&c.realCategory===cat).map(c=>c.id),on);}
'''+s[end:]
start=s.index('function setAllZd(on){')
end=s.index('\nlet selSet',start)
s=s[:start]+'function setAllZd(on){applyDetBatch(REVIEW_META.cards.filter(c=>c.zone).map(c=>c.id),on);}\n'+s[end:]
s=s.replace('let selSet=new Set(),marqEl=null,menuEl=null,mStart=null;','''let selSet=new Set(),marqEl=null,menuEl=null,mStart=null,marqCancel=null;
function cancelReviewMarquee(){if(marqCancel)marqCancel();}''')
s=s.replace('  clearSel();\n  mStart=[e.pageX,e.pageY];','  cancelReviewMarquee();clearSel();\n  const id=CUR,gen=VIEW_GEN;\n  mStart=[e.pageX,e.pageY];',1)
s=s.replace('  const up=ev=>{\n   document.removeEventListener("pointermove",move);\n   document.removeEventListener("pointerup",up);\n   const r=marqEl.getBoundingClientRect();\n   marqEl.remove();marqEl=null;','''  const cancel=()=>{
   document.removeEventListener("pointermove",move);
   document.removeEventListener("pointerup",up);
   if(marqEl)marqEl.remove();marqEl=null;mStart=null;marqCancel=null;
  };
  const up=ev=>{
   const r=marqEl.getBoundingClientRect();cancel();
   if(!ownsView(id,gen))return;''',1)
s=s.replace('    const b=t.getBoundingClientRect();\n    if(b.left<r.right','    if(!reviewSelectable(+t.id.slice(3))||t.hidden)return;\n    const b=t.getBoundingClientRect();\n    if(b.width&&b.height&&b.left<r.right',1)
s=s.replace('  document.addEventListener("pointermove",move);','  marqCancel=cancel;\n  document.addEventListener("pointermove",move);',1)
s=s.replace('function bulkSet(blur){selSet.forEach(i=>applyDet(i,blur));clearSel();}','function bulkSet(blur){const ids=[...selSet].filter(reviewSelectable);clearSel();applyDetBatch(ids,blur);}')
# Native hidden must override card/section display rules.
s=s.replace('APP_CSS = r"""','APP_CSS = r"""\n[hidden]{display:none!important}\n.reviewfilters{flex-wrap:wrap;align-items:end}\n.reviewfilters label{display:flex;flex-direction:column;gap:4px;min-width:0;max-width:100%}\n.reviewfilters select{max-width:100%}\n',1)
p.write_text(s)
