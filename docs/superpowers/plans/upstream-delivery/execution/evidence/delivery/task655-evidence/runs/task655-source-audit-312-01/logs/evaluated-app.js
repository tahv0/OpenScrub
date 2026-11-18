function renderAudioSugg(){
 const el=document.getElementById("beASugg");
 if(!el)return;
 const sg=BE.audioSugg||[];
 if(!sg.length){el.style.display="none";el.innerHTML="";return;}
 el.style.display="block";
 let h='<div style="font-size:12px;color:#f59e0b;margin-bottom:3px">'
  +'&#127908; Spoken PII heard in the audio (local transcription) — '
  +'review each, then Add to mute it:</div>';
 sg.forEach((s,i)=>{
  const used=(BE.audio||[]).some(a=>Math.abs(a.t0-s.t0)<0.05&&Math.abs(a.t1-s.t1)<0.05);
  h+='<div style="font-size:12px;padding:2px 0">'
   +(used?'<span style="color:#4ade80">&#10003; added</span> '
     :'<button class="tog" style="font-size:11px;padding:1px 7px" '
      +'onclick="applyAudioSugg('+i+')">Add</button> ')
   +s.t0.toFixed(1)+'&ndash;'+s.t1.toFixed(1)+'s '
   +'<b>'+(CATDN[s.category]||s.category)+'</b> '
   +'<span style="color:#94a3b8">&ldquo;'
   +String(s.text||"").replace(/[<>&]/g,"")+'&rdquo;</span></div>';
 });
 h+='<div style="margin-top:3px"><button class="tog" style="font-size:11px" '
  +'onclick="applyAudioSugg(-1)">Add all</button></div>';
 el.innerHTML=h;
}
function applyAudioSugg(i){
 const sg=BE.audioSugg||[];
 const list=(i<0)?sg:[sg[i]].filter(Boolean);
 for(const s of list){
  if(!(BE.audio||[]).some(a=>Math.abs(a.t0-s.t0)<0.05&&Math.abs(a.t1-s.t1)<0.05))
   BE.audio.push({t0:s.t0,t1:s.t1,mode:"mute"});
 }
 renderAudioSugg();renderTranscript();beTLDraw();
}
// Full transcript with matched spans highlighted — the fail-closed check
// for spoken PII: ASR patterns can miss (a real half-muted address shipped
// once), but a human reading the transcript catches it in seconds. Click a
// start word then an end word to mute that range directly.
function renderTranscript(){
 const el=document.getElementById("beATx");
 if(!el)return;
 const tx=BE.audioTx||[];
 if(!tx.length){el.style.display="none";el.innerHTML="";return;}
 el.style.display="block";
 const wasOpen=el.querySelector("details")?el.querySelector("details").open:true;
 const esc=s=>String(s).replace(/[<>&]/g,"");
 const muted=w=>(BE.audio||[]).some(a=>w[0]<a.t1&&w[1]>a.t0);
 const sugg=w=>(BE.audioSugg||[]).some(a=>w[0]<a.t1&&w[1]>a.t0);
 let h='<details'+(wasOpen?' open':'')+'><summary style="font-size:12px;color:#94a3b8;cursor:pointer">&#128221; Transcript ('+tx.length+' words) — verify nothing sensitive slipped through</summary>'
  +'<div style="max-height:150px;overflow-y:auto;line-height:2.1;padding:6px 2px;font-size:12.5px;color:#cbd5e1">';
 tx.forEach((wd,i)=>{
  const m=muted(wd),g=sugg(wd),a=i===BE.txAnchor;
  let st='cursor:pointer;border-radius:4px;padding:1px 3px;';
  if(a)st+='outline:2px solid #f59e0b;';
  if(m)st+='background:#7f1d1d;color:#fecaca;text-decoration:line-through;';
  else if(g)st+='background:#78350f;color:#fde68a;';
  h+='<span style="'+st+'" title="'+wd[0].toFixed(2)+'&ndash;'+wd[1].toFixed(2)+'s'+(m?' (will be muted)':'')+'" onclick="txWordClick('+i+')">'+esc(wd[2])+'</span>';
 });
 h+='</div><div style="font-size:11px;color:#64748b">'
  +(BE.txAnchor>=0?'<b style="color:#f59e0b">now click the last word of the range to mute it</b>'
    :'<span style="background:#7f1d1d;border-radius:3px;padding:0 4px">red</span> will be muted &nbsp;'
     +'<span style="background:#78350f;border-radius:3px;padding:0 4px">amber</span> detected PII (not yet added) &nbsp;'
     +'— click a start word, then an end word, to mute a missed range (&plusmn;0.5s pad)')
  +'</div></details>';
 el.innerHTML=h;
}
function txWordClick(i){
 const tx=BE.audioTx||[];if(!tx[i])return;
 if(BE.txAnchor<0){BE.txAnchor=i;renderTranscript();return;}
 const a=Math.min(BE.txAnchor,i),b=Math.max(BE.txAnchor,i);
 BE.txAnchor=-1;
 BE.audio.push({t0:Math.max(0,+(tx[a][0]-0.5).toFixed(2)),
                t1:+(tx[b][1]+0.5).toFixed(2),
                mode:(document.getElementById("beAMode")||{}).value||"mute"});
 renderTranscript();renderAudioSugg();beTLDraw();
}
const CATDN={mrn:"regex",person:"person (full body)",manual:"tracked object",qrcode:"QR / barcode",screen:"screen (tv/laptop/phone)",anytext:"all text",bank:"bank number",crypto:"crypto address",passport:"passport / MRZ",phrase:"specific text"};   // display names — ids are a compat surface
async function refreshModelPanel(){
 // always visible: model choice lives on the settings page now, so users
 // can set up face/plate models before ticking the categories on a job
 document.getElementById("modelpanel").style.display="block";
 for(const kind of ["face","plate","person"]){
  const sec=document.getElementById("msec_"+kind);
  sec.style.display="block";
  try{
   const d=await(await fetch("/api/models/"+kind)).json();
   const dflt=kind==="face"?"Built-in YuNet (no download needed)"
                           :"Automatic — first installed model";
   const row=(val,checked,disabled,inner,right)=>`
    <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-top:1px solid #334155">
     <input type="radio" name="msel_${kind}" ${checked?"checked":""} ${disabled?"disabled":""}
      onchange="selModel('${kind}','${val}')" style="margin:0" title="${disabled?'download the model first':'use this model'}">
     <div style="flex:1;min-width:0">${inner}</div>${right||""}
    </div>`;
   let h=`<div style="font-weight:600;font-size:13.5px;margin:8px 0 2px">${kind==="face"?"Face":kind==="person"?"Person (full-body blur)":"License-plate"} model</div>
    <div style="font-size:12px;margin-bottom:4px;color:${d.active?'#4ade80':'#fbbf24'}">${d.status}</div>`;
   h+=row("",!d.selected,false,
     `<div style="font-size:12.5px;font-weight:600">${dflt}</div>`);
   for(const m of d.models){
    h+=row(m.id,d.selected===m.id,!m.installed,
     `<div style="font-size:12.5px;font-weight:600">${m.label} ${m.recommended?'<span style="color:#4ade80;font-size:11px">★ recommended</span>':''}</div>
      <div style="font-size:11px;color:#94a3b8">${m.notes||""}</div>`,
     `<a href="${m.source_url}" target="_blank" style="font-size:11px;background:#1e3a8a;color:#bfdbfe;border-radius:5px;padding:2px 7px;text-decoration:none" title="${m.attribution||''}">${m.license}</a>
      ${m.installed?'<span style="font-size:11px;color:#4ade80;font-weight:700">installed</span>'
       :(m.verified?`<button onclick="dlModel('${kind}','${m.id}',this)" title="${m.pinned?'SHA-256 verified against pinned hash':'first download: hash will be computed and pinned'}" style="font-size:11.5px;padding:3px 10px">Download</button>`
       :'<span style="font-size:11px;color:#9ca3af" title="registry entry has no download URL">manual install</span>')}`);
   }
   sec.innerHTML=h;
  }catch(e){sec.textContent="model registry unavailable";}
 }
}
async function selModel(kind,id){
 await fetch(`/api/models/${kind}/select`,{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});
 refreshModelPanel();renderTiers();
}
async function dlModel(kind,id,btn){
 btn.disabled=true;btn.textContent="0%";
 const r=await fetch(`/api/models/${kind}/${id}/download`,{method:"POST"});
 if(!r.ok){const d=await r.json();btn.textContent="error";btn.title=d.error||"";return;}
 const t=setInterval(async()=>{
  const s=await(await fetch("/api/models/download_status")).json();
  if(s.state==="downloading"){btn.textContent=(s.pct||0)+"%";}
  else{clearInterval(t);
   if(s.state==="done"){refreshModelPanel();}
   else{btn.disabled=false;btn.textContent="retry";btn.title=s.error||"download failed";}}
 },500);
}

// Detection-quality tiers: one click per tier; scan-time multiples and
// accuracy staging shown beside each. Multiples are honest approximations
// (measured on the person model, the dominant per-frame cost).
const QTIERS=[
 {id:"fast",name:"Fast",mult:"~1× scan time (baseline)",stage:"Good",
  desc:"Built-in YuNet face + nano person model. Lightest and quickest; can miss small, distant or partly hidden subjects."},
 {id:"balanced",name:"Balanced",mult:"~1.5–2× scan time",stage:"Better",
  desc:"CenterFace face + small person model — catches most small or partly hidden subjects the Fast tier misses."},
 {id:"accurate",name:"Accurate",mult:"~2.5–4× scan time",stage:"Best",
  desc:"CenterFace face + medium person model + the most-accurate plate model. Highest recall on crowds, occlusion and distant subjects; best experienced on a GPU."}];
let QAPPLY=0;
async function renderTiers(){
 const el=document.getElementById("qtiers"); if(!el)return;
 try{
  const d=await(await fetch("/api/quality_tier")).json();
  const ap=d.applying||{};
  let h="";
  for(const t of QTIERS){
   const cur=d.tier===t.id, busy=ap.state==="applying"&&ap.tier===t.id;
   const dl=((d.needs&&d.needs[t.id])||[]).length;
   h+=`<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-top:1px solid #334155">
    <input type="radio" name="qtier" ${cur?"checked":""} ${ap.state==="applying"?"disabled":""} onchange="applyTier('${t.id}')" style="margin:0">
    <div style="flex:1;min-width:0">
     <div style="font-size:12.5px;font-weight:600">${t.name}
      <span style="color:#94a3b8;font-weight:400">— ${t.mult}</span>
      <span style="font-size:11px;border-radius:5px;padding:1px 7px;margin-left:4px;background:${t.stage==="Good"?"#374151":t.stage==="Better"?"#1e3a8a":"#14532d"};color:${t.stage==="Good"?"#d1d5db":t.stage==="Better"?"#bfdbfe":"#86efac"}">${t.stage} accuracy</span></div>
     <div style="font-size:11px;color:#94a3b8">${t.desc}</div>
     ${busy?`<div style="font-size:11px;color:#fbbf24">${ap.step||"applying…"}</div>`:""}
    </div>
    ${!cur&&dl?`<span style="font-size:11px;color:#9ca3af;white-space:nowrap">${dl} download${dl>1?"s":""}</span>`:""}
   </div>`;
  }
  if(!d.tier&&ap.state!=="applying")h+=`<div style="font-size:11px;color:#fbbf24;padding-top:5px">Current selection: Custom (models picked individually below)</div>`;
  if(ap.state==="error")h+=`<div style="font-size:11px;color:#f87171;padding-top:5px">${ap.error}</div>`;
  h+=`<div style="font-size:11px;color:#64748b;padding-top:6px">Higher tiers download larger models on demand (person/plate models are AGPL/MIT licensed — shown per model below). For the strongest face detection, SCRFD (non-commercial license) can be selected manually in Detection models.</div>`;
  el.innerHTML=h;
  if(ap.state==="applying"){QAPPLY=1;setTimeout(renderTiers,900);}
  else if(QAPPLY){QAPPLY=0;refreshModelPanel();}
 }catch(e){el.textContent="quality tiers unavailable";}
}
async function applyTier(id){
 const d=await(await fetch("/api/quality_tier")).json();
 const need=(d.needs&&d.needs[id])||[];
 if(need.length&&!confirm(`Switching to this tier downloads ${need.length} model file(s) first (SHA-256 verified). Continue?`)){renderTiers();return;}
 const r=await fetch("/api/quality_tier",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tier:id})});
 if(!r.ok){let e={};try{e=await r.json();}catch(_){/**/}alert(e.error||"could not apply tier");}
 renderTiers();
}
refreshModelPanel();renderTiers();
let CUR=null, EN={}, MAN=[], DUR=0, POLL=null, PHIST=[], PHPH="", LOGN=0, LOGE=null, LOGINIT=false, RECENT_LOG=null, SHELLPH=null, JOBSJSON="";

// VIEW_GEN advances on every openJob (including A -> B -> A) and removal.
// Drafts live only in this page; late acknowledgements reconcile their owner,
// but may never publish into, or start rendering from, a different view.
let VIEW_GEN=0, EDITS=null;
// Polling owns one metadata -> log cycle, using the existing view identity.
let POLL_CYCLE=null, POLL_FAILURES=0, AUTO_REVIEW=null, REVIEW_REQUEST=null;
function pollStatus(message){
 const el=document.getElementById("pollStatus");
 if(el&&el.textContent!==message)el.textContent=message;
}
function stopPolling(){
 if(POLL){clearTimeout(POLL.handle);POLL=null;}
 const old=POLL_CYCLE;POLL_CYCLE=null;
 if(old)old.controller.abort();
}
function schedulePoll(id,gen,delay){
 if(!ownsView(id,gen)||document.hidden)return;
 if(POLL)clearTimeout(POLL.handle);
 const timer={id,gen};POLL=timer;
 timer.handle=setTimeout(()=>{
  if(POLL!==timer||!ownsView(id,gen))return;
  POLL=null;refresh();
 },delay);
}
// Only metadata/log use this deadline. Race body consumption too: abort alone
// cannot settle a transport/body that ignores it. Losing work has no UI effects.
async function pollJson(url,cycle){
 const controller=new AbortController(),signal=cycle.controller.signal;
 let deadline,onCancel;
 const stopped=new Promise((_,reject)=>{
  const fail=message=>{controller.abort();reject(new Error(message));};
  onCancel=()=>fail("Polling cancelled");
  signal.addEventListener("abort",onCancel,{once:true});
  deadline=setTimeout(()=>fail("Polling timed out"),15000);
  if(signal.aborted)onCancel();
 });
 const operation=(async()=>{
  const r=await fetch(url,{signal:controller.signal});
  if(!r.ok)throw new Error("Polling HTTP "+r.status);
  return await r.json();
 })();
 try{return await Promise.race([operation,stopped]);}
 finally{clearTimeout(deadline);signal.removeEventListener("abort",onCancel);}
}
function refresh(){
 if(!CUR||document.hidden)return;
 if(POLL_CYCLE)return POLL_CYCLE.promise;
 if(POLL){clearTimeout(POLL.handle);POLL=null;}
 const cycle={id:CUR,gen:VIEW_GEN,controller:new AbortController()};
 POLL_CYCLE=cycle;
 cycle.promise=(async()=>{
  let delay=900;
  try{
   await refreshCycle(cycle);
   if(POLL_CYCLE!==cycle||!ownsView(cycle.id,cycle.gen))return;
   POLL_FAILURES=0;pollStatus("");
  }catch(e){
   if(POLL_CYCLE!==cycle||!ownsView(cycle.id,cycle.gen))return;
   delay=Math.min(10000,900*Math.pow(2,Math.min(POLL_FAILURES++,4)));
   pollStatus("Job updates interrupted — retrying in "+(delay/1000)+" s.");
  }finally{
   if(POLL_CYCLE===cycle&&ownsView(cycle.id,cycle.gen)){
    POLL_CYCLE=null;
    // Chained after completion: request duration adds to the healthy 900 ms.
    schedulePoll(cycle.id,cycle.gen,delay);
   }
  }
 })();
 return cycle.promise;
}
function wakePolling(){
 if(!CUR||document.hidden)return;
 // A pending immediate wake already coalesces focus/pageshow/online bursts.
 if(POLL&&POLL.wake)return;
 stopPolling();
 schedulePoll(CUR,VIEW_GEN,0);if(POLL)POLL.wake=true;
}
document.addEventListener("visibilitychange",()=>{
 if(document.hidden)stopPolling();else wakePolling();
});
window.addEventListener("pagehide",stopPolling);
for(const event of ["focus","pageshow","online"])window.addEventListener(event,wakePolling);
const REVIEW_DRAFTS=new Map();
function emptyEditor(){return {t:0,ox:0,oy:0,boxes:[],sel:-1,ov:{},dis:{},times:{},adds:[],
 add:false,addAnchor:null,drag:null,scale:1,dur:10,
 audio:[],audioSaved:[],audioLoaded:false};}
function sameEdit(a,b){return JSON.stringify(a)===JSON.stringify(b);}
function copyEdit(a){return JSON.parse(JSON.stringify(a));}
function ownsView(id,gen){return CUR===id&&VIEW_GEN===gen;}
function saveStatus(d,message){
 d.status=message;
 if(d!==EDITS)return;
 const el=document.getElementById("reviewSaveStatus");if(el)el.textContent=message;
 document.querySelectorAll("button[data-save-edits]").forEach(b=>{b.disabled=!!d.busy;});
}
function trimReviewDraft(d){
 const b=d.editor;
 // Clean audio is fetched display state even when other edit kinds are pending.
 // An in-flight audio submission may make a toggle-back a newer pending choice.
 if(!d.audioInFlight&&sameEdit(b.audio,b.audioSaved)){
  b.audio=[];b.audioSaved=[];b.audioLoaded=false;
 }
 if(!d.busy&&!hasReviewEdits(d)){
  d.en={};d.editor=emptyEditor();
 }
}
function hasReviewEdits(d){
 const b=d.editor;
 return Object.keys(d.enabled).length||d.manual.length||b.adds.length||
  Object.keys(b.ov).length||Object.keys(b.times).length||
  !sameEdit(b.audio,b.audioSaved);
}

// Job names are text inside the list link and detail heading.
function jobNameHtml(name){
 return String(name).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function loadJobs(){
 const r=await fetch("api/jobs");
 if(r.status===423){jobs.innerHTML='<span style="color:#f87171">&#128274; locked — unlock in the Encryption panel below</span>';JOBSJSON="";return;}
 const js=await r.json();
 const s=JSON.stringify(js);
 if(s===JOBSJSON)return;
 JOBSJSON=s;
 jobs.innerHTML=js.length?js.map(j=>
  `<div class="row" style="justify-content:space-between;padding:4px 0">
   <a href="#" onclick="openJob('${j.id}');return false">${jobNameHtml(j.name)}</a>
   <span style="display:flex;gap:10px;align-items:center"><span class="badge">${j.phase}</span>
   ${(j.phase=="error"||j.phase=="cancelled")?`<a href="#" title="Retry the scan — reuses the file already on the server, nothing is re-uploaded" style="text-decoration:none;font-size:15px" onclick="retryJob('${j.id}');return false">&#8635;</a>`:""}
   <a href="#" title="Delete this job and all of its files" style="text-decoration:none;font-size:15px" onclick="delJob('${j.id}');return false">&#128465;&#65039;</a></span></div>`).join(""):"none yet";
}

async function retryJob(id){
 const r=await fetch("api/jobs/"+id+"/retry",{method:"POST"});
 let j={};try{j=await r.json();}catch(e){}
 if(!r.ok){alert(j.error||"could not retry the job");return;}
 JOBSJSON="";loadJobs();if(typeof openJob==="function")openJob(id);
}
async function delJob(id){
 if(!confirm("Delete this job and ALL of its files — upload, report, and rendered output?\n\nThis cannot be undone."))return;
 const r=await fetch("api/jobs/"+id,{method:"DELETE"});
 if(!r.ok){
  let m="could not delete the job";
  try{const e=await r.json();m=e.error||e.description||m;}catch(_){}
  alert(m);return;
 }
 REVIEW_DRAFTS.delete(id);
 if(CUR===id){disposeReview();REVIEW_LOAD++;beUnmount();stopPolling();disposeRecentLog();VIEW_GEN++;CUR=null;EDITS=null;AUTO_REVIEW=null;REVIEW_REQUEST=null;detail.innerHTML="";}
 JOBSJSON="";loadJobs();
}
async function openJob(id){
 disposeReview();REVIEW_LOAD++;beUnmount();
 const video=document.getElementById("beVid");
 if(video){try{video.pause();}catch(e){}}
 if(EDITS){
  // Retain edit bookkeeping, not fetched box/report/transcript display data.
  EDITS.en={};
  const b=EDITS.editor;delete b.raw;b.boxes=[];
  delete b.tlspans;delete b.audioSugg;delete b.audioTx;b.playing=false;
  trimReviewDraft(EDITS);
 }
 stopPolling();disposeRecentLog();POLL_FAILURES=0;AUTO_REVIEW=null;REVIEW_REQUEST=null;
 VIEW_GEN++;CUR=id;
 EDITS=REVIEW_DRAFTS.get(id);
 if(!EDITS){EDITS={en:{},enabled:{},manual:[],editor:emptyEditor(),busy:false,status:""};
  REVIEW_DRAFTS.set(id,EDITS);}
 EN=EDITS.en;MAN=EDITS.manual;BE=EDITS.editor;
 PHIST=[];PHPH="";LOGN=0;LOGE=null;LOGINIT=false;SHELLPH=null;
 detail.innerHTML='<div id="pollStatus" role="status" aria-live="polite" style="margin:8px 0;color:#fbbf24"></div><div id="reviewSaveStatus" role="status" aria-live="polite" style="margin:8px 0;color:#fbbf24"></div>';
 saveStatus(EDITS,EDITS.status);

 refresh();
}

// One mounted view owns recent entry nodes, never a second transcript string.
function disposeRecentLog(){
 if(RECENT_LOG){RECENT_LOG.dispose();RECENT_LOG=null;}
}
function mountRecentLog(id,gen,element,note){
 const MAX_ENTRIES=800,MAX_UNITS=1048576,ENTRY_UNITS=8192;
 const SUFFIX="... [display entry truncated]",NL=String.fromCharCode(10);
 let entries=[],units=0,saved=null,frame=null,disposed=false;
 let omitted=false,truncated=false,displayTruncated=false,replaced=false,lost=false;
 let width=element.clientWidth,height=element.clientHeight,ownedTop=element.scrollTop;
 const owner={publish,dispose};
 const current=()=>!disposed&&RECENT_LOG===owner&&ownsView(id,gen)&&document.getElementById("log")===element;
 function status(){
  const text=[replaced?"Log history was replaced.":"",omitted?"Earlier log messages were omitted.":"",
   truncated?"Some log messages were truncated.":"",displayTruncated?"Some display entries were truncated.":"",
   lost?"Reading position was omitted; showing oldest retained messages.":""].filter(Boolean).join(" ");
  if(note.textContent!==text)note.textContent=text;
 }
 function capture(){
  const bottom=element.scrollHeight-element.clientHeight-element.scrollTop<=40;
  const top=element.getBoundingClientRect().top+element.clientTop;
  let entry=entries.find(e=>e.node.getBoundingClientRect().bottom>top);
  if(!entry)entry=entries[entries.length-1];
  return {bottom,seq:entry?entry.seq:null,offset:entry?top-entry.node.getBoundingClientRect().top:0};
 }
 function remember(){saved=capture();ownedTop=element.scrollTop;}
 function restore(anchor){
  if(anchor.bottom){element.scrollTop=element.scrollHeight;}
  else{
   const entry=entries.find(e=>e.seq===anchor.seq);
   if(entry){
    const rect=entry.node.getBoundingClientRect(),top=element.getBoundingClientRect().top+element.clientTop;
    // Preserve the entry and pixel offset, clamping an offset after rewrap.
    const offset=Math.min(anchor.offset,Math.max(0,rect.height-1));
    element.scrollTop=Math.max(0,Math.min(element.scrollHeight-element.clientHeight,
     element.scrollTop+rect.top-top+offset));
   }else{element.scrollTop=0;if(anchor.seq!==null)lost=true;}
  }
  remember();
 }
 function scroll(){
  if(!current()||Math.abs(element.scrollTop-ownedTop)<.5)return;
  lost=false;remember();status();
 }
 element.addEventListener("scroll",scroll,{passive:true});
 const observer=typeof ResizeObserver==="undefined"?null:new ResizeObserver(()=>{
  if(!current()||(width===element.clientWidth&&height===element.clientHeight))return;
  width=element.clientWidth;height=element.clientHeight;
  if(frame===null)frame=requestAnimationFrame(()=>{
   frame=null;if(!current())return;
   if(saved)restore(saved);status();
  });
 });
 if(observer)observer.observe(element);
 function entrySize(text){
  if(text.length<=ENTRY_UNITS)return text.length;
  let end=ENTRY_UNITS-SUFFIX.length;
  const a=text.charCodeAt(end-1),b=text.charCodeAt(end);
  if(a>=0xD800&&a<=0xDBFF&&b>=0xDC00&&b<=0xDFFF)end--;
  return end+SUFFIX.length;
 }
 function clearSelection(removed){
  if(!removed.length)return;
  const selection=window.getSelection?.();
  if(!selection||!element.contains(selection.anchorNode)||!element.contains(selection.focusNode))return;
  if(removed.some(e=>e.node.contains(selection.anchorNode)||e.node.contains(selection.focusNode))||
     selection.anchorNode===element||selection.focusNode===element)selection.removeAllRanges();
 }
 function publish(snapshot,replace,initial,modern){
  if(!current())return;
  const lines=snapshot.lines;
  if(replace){omitted=false;truncated=false;displayTruncated=false;replaced=!initial;lost=false;}
  if(modern){omitted=omitted||snapshot.base>0||snapshot.dropped>0;truncated=truncated||snapshot.truncated>0;}
  if(!replace&&!lines.length){status();return;}
  // Select only a surviving suffix, before creating or mounting its nodes.
  const floor=replace?Math.max(0,lines.length-400):0;
  const incoming=[];let total=0,start=lines.length;
  while(start>floor&&incoming.length<MAX_ENTRIES){
   const size=entrySize(lines[start-1]),next=total+size+(incoming.length?1:0);
   if(next>MAX_UNITS)break;
   incoming.push(size);total=next;start--;
  }
  let keep=entries.length;
  if(!replace&&start===0){
   while(keep>0&&incoming.length+entries.length-keep<MAX_ENTRIES){
    const next=total+entries[keep-1].units+(incoming.length+entries.length-keep?1:0);
    if(next>MAX_UNITS)break;
    total=next;keep--;
   }
  }
  // The final pre-mutation sample is after all polling awaits and validation.
  const anchor=replace?null:capture(),removed=entries.slice(0,keep);
  omitted=omitted||start>0||keep>0;
  clearSelection(removed);
  for(const entry of removed)entry.node.remove();
  entries.splice(0,keep);
  const fragment=document.createDocumentFragment();
  for(let i=start;i<lines.length;i++){
   const size=incoming[lines.length-1-i],source=lines[i];
   const clipped=source.length>ENTRY_UNITS;
   const node=document.createElement("span");node.dataset.seq=String(snapshot.from+i);
   node.appendChild(document.createTextNode(clipped?source.slice(0,size-SUFFIX.length)+SUFFIX:source));
   if(i<lines.length-1)node.appendChild(document.createTextNode(NL));
   fragment.appendChild(node);entries.push({seq:snapshot.from+i,node,units:size});
   displayTruncated=displayTruncated||clipped;
  }
  // Delimiters are distinct from stable content nodes, including empty entries.
  if(start<lines.length&&entries.length>lines.length-start){
   entries[entries.length-(lines.length-start)-1].node.appendChild(document.createTextNode(NL));
  }
  element.appendChild(fragment);units=total;
  if(replace){element.scrollTop=element.scrollHeight;remember();}
  else restore(anchor);
  status();
 }
 function dispose(){
  disposed=true;if(observer)observer.disconnect();if(frame!==null)cancelAnimationFrame(frame);
  element.removeEventListener("scroll",scroll);entries.length=0;units=0;saved=null;frame=null;
 }
 return owner;
}

function shellHtml(j){
 return `<div class="card" id="jobcard"><h2>${jobNameHtml(j.name)}
  <span class="badge" id="ph"></span><small id="eta"></small></h2>
 <progress id="prog" value="0" max="1"></progress>
 <div class="row" id="actions" style="margin-top:8px"></div>
 <div style="margin-top:8px;text-align:center"><img id="pimg"
   style="max-width:100%;border-radius:8px;display:none;margin:0 auto"></div>
 <div id="pcap" style="font-size:12px;color:#94a3b8"></div>
 <div id="logStatus" style="margin-top:8px;color:#94a3b8"></div>
 <div id="log" tabindex="0" aria-label="Job log" aria-describedby="logStatus" style="margin-top:8px"></div>
 <div class="warn" id="warnbox" style="display:none;margin-top:8px"></div>
 </div>`;
}

// Save As exports stay bound to the clicked job even while the picker is open.
let EXPORT_NAMES={id:null,video:null,report:null};
const CAN_SAVE_AS=!!(window.isSecureContext&&window.showSaveFilePicker);
const EXPORTS=new Map();
function exportControls(id,kind){
 const label=kind==="video"?"redacted video":"audit report";
 const path=kind==="video"?"download":"report";
 const direct=`<a href="api/jobs/${id}/${path}" onclick="exportDownloadStarted('${kind}')">Download ${label}</a>`;
 return `<div id="export-${kind}" data-job="${id}" style="flex:1 1 260px;min-width:0">
  ${CAN_SAVE_AS?`<button id="save-${kind}" class="${kind==='report'?'sec':''}" onclick="saveExportAs('${kind}',this)">Save ${label} as…</button>
   <span style="font-size:12px"> · ${direct}</span>`:direct}
  <div id="export-${kind}-feedback" hidden>
   <progress id="export-${kind}-progress" max="1" aria-label="${label} save progress" style="width:100%"></progress>
   <div id="export-${kind}-status" style="font-size:12px;overflow-wrap:anywhere"></div>
   <div id="export-${kind}-live" role="status" aria-live="polite" aria-atomic="true"
    style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)"></div>
  </div></div>`;
}
function exportDownloadStarted(kind){
 if(!CUR)return;
 const key=CUR+":"+kind;
 // A direct download cannot observe disk completion or replace a running save.
 if(EXPORTS.get(key)?.active)return;
 EXPORTS.set(key,{id:CUR,kind,phase:"download",written:0,total:null,active:false});
 renderExportProgress();
}
function exportDuration(seconds){
 const s=Math.max(0,Math.floor(seconds));
 return s>=60?`${Math.floor(s/60)} min ${s%60} s`:`${s} s`;
}
function renderExportProgress(){
 const now=performance.now();
 for(const kind of ["video","report"]){
  const box=document.getElementById("export-"+kind),state=EXPORTS.get(CUR+":"+kind);
  if(!box||box.dataset.job!==CUR)continue;
  const button=document.getElementById("save-"+kind);
  if(button)button.disabled=!!state?.active;
  if(!state)continue;
  if(state.active&&state.renderedBox===box&&state.renderedPhase===state.phase&&now-state.renderedAt<250)continue;
  state.renderedBox=box;state.renderedPhase=state.phase;state.renderedAt=now;
  document.getElementById(`export-${kind}-feedback`).hidden=false;
  const bar=document.getElementById(`export-${kind}-progress`);
  if(state.total===null||state.phase==="download")bar.removeAttribute("value");
  else{bar.max=state.total||1;bar.value=state.written;}
  bar.hidden=state.phase==="download";
  let text="Download started — see browser downloads";
  if(state.phase!=="download"){
   const amount=Math.max(state.total||0,state.written);
   const power=amount>0?Math.min(3,Math.floor(Math.log10(amount)/3)):0;
   const unit=["B","KB","MB","GB"][power],scale=1000**power;
   const bytes=n=>`${(n/scale).toFixed(power?1:0)} ${unit}`;
   const elapsed=(now-state.start)/1000;
   const waiting=state.active&&state.phase!=="finalizing"&&now-state.lastWrite>=5000;
   let label=state.phase==="saved"?"Saved":state.phase==="failed"?"Save failed":
    state.phase==="finalizing"?"Finalizing…":state.phase==="choosing"?"Choose a destination…":
    waiting?"Waiting for data or disk…":`Saving ${kind==="video"?"video":"audit report"}`;
   const count=state.total===null?bytes(state.written):
    `${bytes(state.written)} / ${bytes(state.total)} (${state.total?Math.min(100,Math.floor(state.written/state.total*100)):100}%)`;
   text=`${label} — ${count} · ${exportDuration(((state.end??now)-state.start)/1000)} elapsed`;
   if(state.phase==="saving"&&!waiting&&elapsed>=3&&state.samples.length>1){
    // Retain one observation at/before the rolling ten-second boundary.
    while(state.samples.length>2&&state.samples[1][0]<=now-10000)state.samples.shift();
    const [t,b]=state.samples[0],rate=(state.written-b)/((now-Math.max(t,now-10000))/1000);
    if(rate>0){text+=` · ${bytes(rate)}/s`;
     if(state.total!==null&&state.written<state.total)
      text+=` · about ${exportDuration((state.total-state.written)/rate)} left`;}
   }
   if(state.error)text+=` · ${state.error}. Try Save As again or use Download.`;
  }
  document.getElementById(`export-${kind}-status`).textContent=text;
  // Visual updates run at 250ms; live announcements have their own 2s cadence.
  if(state.announcedPhase!==state.phase||now-(state.announcedAt??-Infinity)>=2000){
   document.getElementById(`export-${kind}-live`).textContent=text;
   state.announcedPhase=state.phase;state.announcedAt=now;
  }
 }
}
async function saveExportAs(kind,button){
 const id=CUR,name=EXPORT_NAMES[kind],path=kind==="video"?"download":"report";
 if(!id||EXPORT_NAMES.id!==id||!name||!["video","report"].includes(kind))return;
 const key=id+":"+kind,previous=EXPORTS.get(key);
 if(previous?.active)return;
 const start=performance.now();
 const state={id,kind,phase:"choosing",active:true,written:0,total:null,start,
  lastWrite:start,samples:[[start,0]]};
 EXPORTS.set(key,state);button.disabled=true;renderExportProgress();
 let reader,writable,timer;
 try{
  // Invoke synchronously from the click, before the first network await.
  let handle;
  try{handle=await window.showSaveFilePicker({suggestedName:name});}
  catch(e){if(e.name!=="AbortError")throw e;
   if(previous)EXPORTS.set(key,previous);else EXPORTS.delete(key);
   if(CUR===id){document.getElementById(`export-${kind}-feedback`).hidden=!previous;
    renderExportProgress();}
   return;
  }
  state.phase="saving";state.start=state.lastWrite=performance.now();
  state.samples=[[state.start,0]];
  timer=setInterval(renderExportProgress,250);
  const response=await fetch(`api/jobs/${encodeURIComponent(id)}/${path}`);
  if(!response.ok)throw new Error(response.status===423?"encryption vault is locked":`server returned HTTP ${response.status}`);
  if(!response.body)throw new Error("browser did not provide a file stream");
  reader=response.body.getReader();
  const length=response.headers.get("Content-Length"),encoding=response.headers.get("Content-Encoding");
  // Fetch decodes encoded responses; their transfer length is not a disk total.
  if((!encoding||encoding.toLowerCase()==="identity")&&length!==null&&/^[0-9]+$/.test(length)){
   const total=Number(length);if(Number.isSafeInteger(total))state.total=total;
  }
  writable=await handle.createWritable();
  for(;;){
   const {done,value}=await reader.read();if(done)break;
   await writable.write(value); // backpressure: accepted bytes only
   const now=performance.now();state.written+=value.byteLength;state.lastWrite=now;
   // Coalesce observations to 250ms buckets; keep a bounded ten-second window.
   if(state.samples.length===1||Math.floor(now/250)!==Math.floor(state.samples[state.samples.length-1][0]/250))
    state.samples.push([now,state.written]);
   else state.samples[state.samples.length-1]=[now,state.written];
   while(state.samples.length>2&&state.samples[1][0]<=now-10000)state.samples.shift();
  }
  if(state.total!==null&&state.written!==state.total)throw new Error("received byte count does not match Content-Length");
  state.phase="finalizing";renderExportProgress();
  await writable.close();
  state.phase="saved";
 }catch(e){
  state.phase="failed";state.error=e.message||String(e);
  if(reader)try{await reader.cancel();}catch(_){}
  if(writable)try{await writable.abort();}catch(_){}
 }finally{
  if(timer)clearInterval(timer);
  if(reader)reader.releaseLock();
  state.active=false;state.end=performance.now();
  button.disabled=false;renderExportProgress();
 }
}

async function refreshCycle(cycle){
 const {id,gen}=cycle;
 const current=()=>ownsView(id,gen)&&POLL_CYCLE===cycle;
 const j=await pollJson("api/jobs/"+id,cycle);
 if(!ownsView(id,gen)||!current())return;
 if(!j||typeof j.name!=="string"||typeof j.phase!=="string"||
    typeof j.progress!=="number"||!Number.isFinite(j.progress))throw new Error("Invalid job update");
 EXPORT_NAMES={id,video:j.download_name,report:j.report_name};
 if(SHELLPH===null){
  detail.insertAdjacentHTML("afterbegin",shellHtml(j));SHELLPH="";
  RECENT_LOG=mountRecentLog(id,gen,document.getElementById("log"),document.getElementById("logStatus"));
  const im=document.getElementById("pimg");
  im.onload=()=>{im.style.display="block";};   // show only once a real frame arrives
  im.onerror=()=>{im.style.display="none";};   // 404 before first preview: stay hidden
 }

 // progress + ETA (updated in place — nothing is rebuilt).
 // The server sends a smoothed per-stage estimate (j.eta, seconds) built
 // from the stage's recent processing rate — prefer it. The old
 // client-side extrapolation from bar movement stays only as a fallback
 // (rehydrated jobs mid-phase), with its history reset on phase change so
 // it never extrapolates a scan-speed rate across the render phase.
 if(PHPH!==j.phase){
  PHIST=[];PHPH=j.phase;
  // Phase eligibility is separate from view identity. Leave-and-return creates
  // a new token; slow same-phase review requests remain eligible.
  AUTO_REVIEW=j.phase==="review"?{id,gen,state:"idle"}:null;
 }
 PHIST.push([Date.now(),j.progress]); if(PHIST.length>40)PHIST.shift();
 let sec=null;
 if(typeof j.eta==="number"&&j.progress<1)sec=j.eta;
 else if(j.progress>0&&j.progress<1&&PHIST.length>3){
  const[t0,p0]=PHIST[0],[t1,p1]=PHIST[PHIST.length-1];
  if(p1>p0)sec=(1-p1)*(t1-t0)/(p1-p0)/1000;}
 const eta=sec===null?"":` ~${sec>90?Math.round(sec/60)+" min":Math.round(sec)+" s"} left`;
 document.getElementById("ph").textContent=j.phase;
 document.getElementById("eta").textContent=eta;
 document.getElementById("prog").value=j.progress;

 // Only a fully accepted body publishes to the mount-owned recent transcript.
 let nl=await pollJson(`api/jobs/${id}/log?from=${LOGN}${LOGE===null?"":"&epoch="+encodeURIComponent(LOGE)}`,cycle);
 if(!ownsView(id,gen)||!current())return;
 const index=n=>Number.isSafeInteger(n)&&n>=0;
 const validLog=n=>n&&index(n.from)&&index(n.len)&&Array.isArray(n.lines)&&
  n.lines.every(line=>typeof line==="string");
 if(!validLog(nl))throw new Error("Invalid log update");
 const modern=["epoch","base","reset","dropped","truncated"].some(k=>k in nl);
 let replace=false,lines=nl.lines,nextEpoch=null;
 if(modern){
  if(!index(nl.base)||nl.base>nl.from||nl.from>nl.len||lines.length!==nl.len-nl.from||
     typeof nl.epoch!=="string"||!/^[A-Za-z0-9_-]{1,128}$/.test(nl.epoch)||
     ![null,"stale","future","epoch"].includes(nl.reset)||!index(nl.dropped)||!index(nl.truncated))
   throw new Error("Invalid log snapshot");
  const expected=LOGE!==null&&nl.epoch!==LOGE?"epoch":LOGN<nl.base?"stale":LOGN>nl.len?"future":null;
  if(nl.reset!==expected||nl.from!==(expected?nl.base:LOGN))throw new Error("Invalid log reset");
  replace=!LOGINIT||nl.reset!==null;
  nextEpoch=nl.epoch;
 }else{
  // Explicit old-backend branch: its shrink response may have from > len.
  if(nl.len<LOGN){
   replace=true;
   if(nl.len){
    nl=await pollJson(`api/jobs/${id}/log?from=0`,cycle);
    if(!ownsView(id,gen)||!current())return;
    if(!validLog(nl)||["epoch","base","reset","dropped","truncated"].some(k=>k in nl))
     throw new Error("Invalid legacy log update");
   }
  }
  if((nl.from!==(replace?0:LOGN)&&nl.len!==0)||nl.lines.length!==Math.max(0,nl.len-nl.from))
   throw new Error("Invalid log cursor");
  replace=replace||!LOGINIT;lines=nl.lines;
 }
 RECENT_LOG.publish(nl,replace,!LOGINIT,modern);
 LOGN=nl.len;LOGE=nextEpoch;LOGINIT=true;

 // live preview: swap src in place (browser keeps old frame until new loads)
 const img=document.getElementById("pimg");
 if(j.phase=="scanning"){
  img.src=`api/jobs/${CUR}/preview.jpg?x=${Date.now()}`;
 }

 const wb=document.getElementById("warnbox");
 if(j.error){wb.style.display="block";wb.textContent=j.error;}
 else wb.style.display="none";

 // action buttons rebuilt ONLY when the phase changes
 if(SHELLPH!==j.phase){
  SHELLPH=j.phase;
  let a="";
  if(j.phase=="scanning"||j.phase=="rendering")
   a=`<button class="danger" onclick="cancelJob()">Cancel</button>`;
  if(j.phase=="error"||j.phase=="cancelled")
   a=`<button onclick="retryJob(CUR)">Retry scan (no re-upload)</button>
    <div style="width:100%;font-size:12px;color:#9ca3af">The uploaded file
    is still on the server — Retry re-runs the scan without uploading it
    again. Delete the job (&#128465;&#65039; in the list) to free its disk
    space.</div>`;
  if(j.phase=="review"){
   // no interstitial button: review is the ONLY next step after a scan,
   // so open it directly — both on a live scan finishing and on
   // selecting a job that is already waiting in review
   a="";
   // Automatic review starts below, outside the bounded polling cycle.
  }
  if(j.phase=="done"&&j.has_output)
   a=`${exportControls(id,"video")}${exportControls(id,"report")}
    ${CAN_SAVE_AS?"":'<div style="width:100%;font-size:12px;color:#94a3b8">To choose a destination, enable “Ask where to save each file” in your browser download settings.</div>'}
    <button class="sec" onclick="loadReview()">Re-open review</button>
    <button class="sec" onclick="loadCompare()">Compare before/after</button>
    <button class="sec" onclick="loadBoxEdit()">Preview &amp; edit blur boxes</button>
    <div class="warn" style="width:100%">Reminder: scrub the result before
    sharing. This tool is best-effort, not a compliance guarantee.</div>
    <div id="compare" style="width:100%"></div>
    <div id="beslot_done" style="width:100%"></div>`;
  const actions=document.getElementById("actions");beUnmountIn(actions);actions.innerHTML=a;
  if(j.phase!="scanning")img.style.display="none";
 }
 renderExportProgress();
 if(AUTO_REVIEW&&AUTO_REVIEW.state==="idle"){
  const auto=AUTO_REVIEW;auto.state="loading";
  loadReview(auto).catch(()=>{
   if(AUTO_REVIEW===auto&&ownsView(id,gen)){
    auto.state="idle";pollStatus("Review could not load — retrying job updates.");
   }
  });
 }
 loadJobs();
}

let BE=emptyEditor();
// Display geometry belongs to this DOM mount, never to a retained draft.
let BE_VIEW=null;
function beEndGesture(editor,cv){
 editor.drag=null;editor.addAnchor=null;editor.addFloat=null;
 if(editor.pointerId!=null){
  try{cv.releasePointerCapture(editor.pointerId);}catch(e){}
  delete editor.pointerId;
 }
}
function beUnmount(){
 const view=BE_VIEW;if(!view)return;
 BE_VIEW=null;view.observer.disconnect();
 beEndGesture(view.editor,view.cv);
}
// A panel transition may retain the mounted editor. Dispose only its removed
// subtree, before DOM replacement, so retained video/gestures keep their owner.
function beUnmountIn(root){
 const view=BE_VIEW;if(!view||!root?.contains?.(view.cv))return;
 beUnmount();
 try{if(view.vid&&!view.vid.paused){view.editor.playing=false;view.vid.pause();}}catch(e){}
}
function beMount(img,vid,cv,id,gen,editor){
 beUnmount();
 const view={img,vid,cv,id,gen,editor,transform:null};
 view.current=()=>BE_VIEW===view&&ownsView(id,gen)&&BE===editor&&
  document.getElementById("beCv")===cv;
 view.sync=()=>{
  if(!view.current())return null;
  const media=editor.playing?vid:img,r=media.getBoundingClientRect();
  const sw=media===vid?vid.videoWidth:img.naturalWidth,
        sh=media===vid?vid.videoHeight:img.naturalHeight;
  const loaded=media===vid?vid.readyState>=1:img.complete;
  const valid=loaded&&[sw,sh,r.width,r.height].every(n=>Number.isFinite(n)&&n>0);
  const old=view.transform;
  if(!valid){
   if(old){beEndGesture(editor,cv);view.transform=null;}
   cv.width=0;cv.height=0;cv.style.width="0px";cv.style.height="0px";
   return null;
  }
  const changed=!old||old.media!==media||old.sw!==sw||old.sh!==sh||
   old.width!==r.width||old.height!==r.height;
  if(changed){
   beEndGesture(editor,cv);
   // CSS coordinates keep handles/strokes constant. Rounded backing sizes
   // have their own X/Y ratio, so fractional CSS dimensions lose no scale.
   const dpr=window.devicePixelRatio||1;
   cv.width=Math.max(1,Math.round(r.width*dpr));
   cv.height=Math.max(1,Math.round(r.height*dpr));
   cv.style.width=r.width+"px";cv.style.height=r.height+"px";
   view.transform={media,sw,sh,width:r.width,height:r.height,
    sx:r.width/sw,sy:r.height/sh};
   editor.scale=r.width/sw;
   beDraw();
  }
  return view.transform;
 };
 view.observer=new ResizeObserver(()=>view.sync());
 BE_VIEW=view;view.observer.observe(img);view.observer.observe(vid);
 return view;
}
async function loadBoxEdit(fromReview){
 const id=CUR,gen=VIEW_GEN,editor=BE;
 showPanel(fromReview?"boxedit_rev":"boxedit");
 const mi=await (await fetch(`api/jobs/${id}/mediainfo`)).json();
 if(!ownsView(id,gen)||BE!==editor)return;
 // in review: the slot right under the Preview button; on done: the actions slot
 let c=document.getElementById("beslot")||document.getElementById("beslot_done");
 if(!c){c=document.createElement("div");c.id="beslot";c.style.width="100%";
  (document.getElementById("review")||document.getElementById("jobcard")||detail)
   .appendChild(c);}
 Object.assign(BE,{dur:mi.duration,win:[0,mi.duration],trk:false,muteArm:false,tlDrag:null,
     audioSel:-1,tlspans:[]});

 beUnmountIn(c);
 c.innerHTML=`<div class="row" style="margin-top:8px">
  <button class="sec" id="bePlay" style="padding:3px 11px" title="Play the video with live boxes — pause to edit them" onclick="beTogglePlay()">&#9654;</button>t=
  <input type="range" id="beT" min="0" max="${Math.max(0.2,mi.duration-0.1).toFixed(1)}"
   step="0.1" value="0" style="flex:1" oninput="beScrub()"><span id="beL">0s</span></div>
  <div style="position:relative;display:inline-block;max-width:100%">
   <img id="beImg" style="max-width:100%;border-radius:8px">
   <video id="beVid" style="max-width:100%;border-radius:8px;display:none" playsinline preload="none"></video>
   <canvas id="beCv" style="position:absolute;left:0;top:0;touch-action:none"></canvas></div>
  <canvas id="beTL" style="width:100%;height:72px;display:block;margin-top:6px;
   border-radius:6px;touch-action:none;cursor:crosshair"
   title="Timeline: colored spans = detections. Drag the orange handles to set the active window; click to seek."></canvas>
  <div class="row" style="font-size:12.5px;align-items:center;margin-top:2px">
   <span id="beWinL" style="color:#94a3b8">window: whole video</span>
   <button class="sec" style="padding:3px 8px;font-size:12px" onclick="beWinReset()">reset window</button>
   <span style="flex:1"></span>
   <select id="beAMode" style="font-size:12px"><option value="mute">mute</option>
    <option value="bleep">bleep</option></select>
   <button class="tog" id="beMute" onclick="beMuteMode()">&#128263; Audio span</button>
   <button class="danger" id="beARm" style="display:none" onclick="beAudioRm()">Delete span</button></div>
  <div id="beASugg" style="display:none;margin-top:6px"></div>
  <div id="beATx" style="display:none;margin-top:6px"></div>
  <div class="row" style="margin-top:6px">
   <button class="tog" id="beAdd" onclick="beAddMode()">&#65291; Add box</button>
   <button class="tog" id="beTrk" onclick="beTrackMode()">&#8857; Track object</button>
   <button class="danger" id="beRm" style="display:none" onclick="beRemove()">Remove blur</button>
   <span id="beTimes" style="display:none;align-items:center;gap:4px;font-size:13px">
    from <input type="number" id="beT0" step="0.1" min="0" style="width:74px">
    to <input type="number" id="beT1" step="0.1" style="width:74px"> s
    <button class="sec" onclick="beApplyTimes()">Apply times</button></span>
   <span id="beTrkSt" style="display:none;font-size:13px;color:#fbbf24">tracking&#8230;</span>
   <button data-save-edits onclick="beSave()">Save changes &amp; re-render</button></div>
  <p style="font-size:12px;color:#94a3b8;margin:4px 0 0">&#9654; plays the
   video with the boxes moving live (pause to edit). Click a red box to
   select — drag inside to move, a corner to resize, edit its from/to times,
   or remove its blur. &#65291; Add box: drag a static region. &#8857; Track object:
   drag the timeline handles to the part of the video you care about, scrub
   to a frame where the object is clear, draw a box around it — it will be
   followed and blurred through the window. &#128263; Audio span: drag on the
   timeline's bottom lane to silence (or bleep) that stretch of sound.</p>`;
 const img=document.getElementById("beImg"),bv=document.getElementById("beVid"),
       cv=document.getElementById("beCv");
 const view=beMount(img,bv,cv,id,gen,editor);
 img.onload=()=>{if(view.current()&&!BE.playing){view.sync();beDraw();}};
 bv.addEventListener("loadedmetadata",()=>{if(view.current())view.sync();});
 const stop=()=>{if(ownsView(id,gen)&&BE===editor&&document.getElementById("beVid")===bv&&BE.playing)bePlayStop();};
 bv.addEventListener("pause",stop);bv.addEventListener("ended",stop);
 saveStatus(EDITS,EDITS.status);
 beHook();tlHook();await tlInit();
 if(ownsView(id,gen)&&BE===editor)beScrub();
}

// ---- playback with live boxes (issue #17: review was scrub-only) ----
async function beTogglePlay(){
 const id=CUR,gen=VIEW_GEN,editor=BE;
 const v=document.getElementById("beVid"),img=document.getElementById("beImg");
 if(!v)return;
 const current=()=>ownsView(id,gen)&&BE===editor&&document.getElementById("beVid")===v;
 if(BE.playing){v.pause();return;}          // the pause handler cleans up
 if(!v.src)v.src=`api/jobs/${CUR}/video`;
 BE.playing=true;
 v.style.display="block";img.style.display="none";
 if(BE_VIEW)BE_VIEW.sync();
 // boxes are view-only while playing: freeze pointer edits so a moving
 // box can't be grabbed mid-flight
 const cv=document.getElementById("beCv");cv.style.pointerEvents="none";
 document.getElementById("bePlay").innerHTML="&#10074;&#10074;";
 try{
  if(v.readyState<1)await new Promise((res,rej)=>{
   v.onloadedmetadata=res;
   v.onerror=()=>rej(new Error("the browser cannot decode this file"));
   // preload=none defers I/O until Play; request metadata after installing
   // the listeners rather than waiting for a load that has not started.
   v.load();});
  if(!current())return;
  v.currentTime=BE.t||0;
  await v.play();
  if(!current()){v.pause();return;}
 }catch(e){
  if(!current())return;
  bePlayStop();
  alert("Could not play the video in this browser ("+(e&&e.message||e)
   +") — the scrub slider still works frame by frame.");
  return;
 }
 if(BE_VIEW)BE_VIEW.sync();
 // boxes come from the server per timestamp; refresh them on a throttle
 // while rAF keeps the playhead, label and box painting per-frame smooth
 let lastQ=0,inFlight=false;
 const step=()=>{
  if(!current()||!BE.playing)return;
  BE.t=v.currentTime;
  document.getElementById("beT").value=BE.t;
  document.getElementById("beL").textContent=BE.t.toFixed(1)+"s";
  const now=performance.now();
  if(!inFlight&&now-lastQ>150){
   inFlight=true;lastQ=now;
   fetch(`api/jobs/${id}/boxes_at?t=${BE.t.toFixed(2)}&all=1`)
    .then(r=>r.json())
    .then(d=>{if(!current())return;BE.ox=d.ox;BE.oy=d.oy;BE.raw=d.boxes;beFilter();})
    .catch(()=>{}).finally(()=>{inFlight=false;});
  }
  beDraw();beTLDraw();
  requestAnimationFrame(step);
 };
 requestAnimationFrame(step);
}
function bePlayStop(){
 BE.playing=false;
 const v=document.getElementById("beVid");
 if(v){try{v.pause();}catch(e){}v.style.display="none";}
 const img=document.getElementById("beImg");if(img)img.style.display="";
 if(BE_VIEW)BE_VIEW.sync();
 const b=document.getElementById("bePlay");if(b)b.innerHTML="&#9654;";
 const cv=document.getElementById("beCv");if(cv)cv.style.pointerEvents="auto";
 beScrub();   // crisp frame + authoritative boxes at the pause point
}

const TLC={name:"#3b82f6",dob:"#22c55e",phone:"#f59e0b",ssn:"#ef4444",
 mrn:"#8b5cf6",email:"#14b8a6",address:"#f97316",card:"#db2777",
 apikey:"#0891b2",ipaddr:"#65a30d",plate:"#7c3aed",face:"#ec4899",
 person:"#0ea5e9",manual:"#eab308"};
async function tlInit(){
 const id=CUR,gen=VIEW_GEN,editor=BE;
 // one fetch of the full report: detection spans for the lanes (dense
 // tracks collapse to one span per track) + stored audio redactions
 try{
  const response=await fetch(`api/jobs/${id}/report`);
  if(!response.ok)throw Error("could not load audio");
  const doc=await response.json();
  if(!ownsView(id,gen)||BE!==editor)return;
  const per={};
  for(const d of (doc.detections||[])){
   if(d.enabled===false)continue;
   const key=d.category+((d.track??-1)>=0?(":t"+d.track):(":i"+Math.random()));
   const s=per[key]||(per[key]={cat:d.category,t0:d.t_start,t1:d.t_end});
   s.t0=Math.min(s.t0,d.t_start);s.t1=Math.max(s.t1,d.t_end);
  }
  BE.tlspans=Object.values(per);
  if(!BE.audioLoaded){
   const stored=(doc.audio_redactions||[]).map(s=>({t0:s.t0,t1:s.t1,mode:s.mode||"mute"}));
   // Audio controls can be used while this initial report request is pending.
   BE.audio=[...stored,...BE.audio];BE.audioSaved=copyEdit(stored);BE.audioLoaded=true;
  }
  BE.audioSugg=doc.audio_suggestions||[];
  BE.audioTx=doc.audio_transcript||[];BE.txAnchor=-1;
  renderAudioSugg();renderTranscript();
 }catch(e){if(!ownsView(id,gen)||BE!==editor)return;BE.tlspans=[];}
 beTLDraw();
}
function tlX(t,w){return Math.max(0,Math.min(w,t/Math.max(0.1,BE.dur)*w));}
function beTLDraw(){
 const cv=document.getElementById("beTL");if(!cv)return;
 const w=cv.clientWidth||600;cv.width=w;cv.height=72;
 const g=cv.getContext("2d");
 g.fillStyle="#0f172a";g.fillRect(0,0,w,72);
 // category lanes
 const cats=[...new Set(BE.tlspans.map(s=>s.cat))];
 const laneH=cats.length?Math.min(10,44/Math.max(1,cats.length)):0;
 BE.tlspans.forEach(s=>{
  const row=cats.indexOf(s.cat);
  g.fillStyle=TLC[s.cat]||"#94a3b8";
  g.globalAlpha=0.9;
  g.fillRect(tlX(s.t0,w),4+row*laneH,
             Math.max(2,tlX(s.t1,w)-tlX(s.t0,w)),Math.max(3,laneH-2));
 });
 g.globalAlpha=1;
 // audio lane (bottom 14px)
 g.fillStyle="#1e293b";g.fillRect(0,54,w,14);
 BE.audio.forEach((s,i)=>{
  g.fillStyle=i===BE.audioSel?"#f87171":(s.mode==="bleep"?"#fb923c":"#dc2626");
  g.fillRect(tlX(s.t0,w),55,Math.max(2,tlX(s.t1,w)-tlX(s.t0,w)),12);
 });
 g.fillStyle="#64748b";g.font="9px sans-serif";g.fillText("audio",3,64);
 // dim outside the active window + orange handles
 g.fillStyle="rgba(2,6,23,0.72)";
 g.fillRect(0,0,tlX(BE.win[0],w),72);
 g.fillRect(tlX(BE.win[1],w),0,w-tlX(BE.win[1],w),72);
 g.fillStyle="#f59e0b";
 g.fillRect(tlX(BE.win[0],w)-2,0,4,72);g.fillRect(tlX(BE.win[1],w)-2,0,4,72);
 // playhead
 g.strokeStyle="#f8fafc";g.beginPath();
 g.moveTo(tlX(BE.t,w),0);g.lineTo(tlX(BE.t,w),72);g.stroke();
 const full=BE.win[0]<0.05&&BE.win[1]>BE.dur-0.05;
 document.getElementById("beWinL").textContent=full?"window: whole video"
  :`window: ${BE.win[0].toFixed(1)}–${BE.win[1].toFixed(1)}s`;
}
function tlHook(){
 const cv=document.getElementById("beTL");if(!cv)return;
 const tAt=e=>{const r=cv.getBoundingClientRect();
  return Math.max(0,Math.min(BE.dur,(e.clientX-r.left)/r.width*BE.dur));};
 const yAt=e=>{const r=cv.getBoundingClientRect();return e.clientY-r.top;};
 cv.addEventListener("pointerdown",e=>{
  cv.setPointerCapture(e.pointerId);
  const t=tAt(e),w=cv.clientWidth,px=e.clientX-cv.getBoundingClientRect().left;
  if(Math.abs(px-tlX(BE.win[0],w))<7){BE.tlDrag={k:"w0"};return;}
  if(Math.abs(px-tlX(BE.win[1],w))<7){BE.tlDrag={k:"w1"};return;}
  if(yAt(e)>=54){                                  // audio lane
   if(BE.muteArm){BE.tlDrag={k:"anew",t0:t};
    BE.audio.push({t0:t,t1:t,mode:document.getElementById("beAMode").value});
    BE.audioSel=BE.audio.length-1;beTLDraw();return;}
   const hit=BE.audio.findIndex(s=>t>=s.t0&&t<=s.t1);
   BE.audioSel=hit;
   document.getElementById("beARm").style.display=hit>=0?"inline-block":"none";
   beTLDraw();return;
  }
  BE.tlDrag={k:"seek"};
  document.getElementById("beT").value=t.toFixed(1);beScrub();
 });
 cv.addEventListener("pointermove",e=>{
  if(!BE.tlDrag)return;
  const t=tAt(e);
  if(BE.tlDrag.k==="w0")BE.win[0]=Math.min(t,BE.win[1]-0.2);
  else if(BE.tlDrag.k==="w1")BE.win[1]=Math.max(t,BE.win[0]+0.2);
  else if(BE.tlDrag.k==="anew"){
   const s=BE.audio[BE.audioSel];
   s.t0=Math.min(BE.tlDrag.t0,t);s.t1=Math.max(BE.tlDrag.t0,t);
  }else if(BE.tlDrag.k==="seek"){
   document.getElementById("beT").value=t.toFixed(1);beScrub();}
  beTLDraw();
 });
 cv.addEventListener("pointerup",()=>{
  if(BE.tlDrag&&BE.tlDrag.k==="anew"){
   const s=BE.audio[BE.audioSel];
   if(s.t1-s.t0<0.15){BE.audio.pop();BE.audioSel=-1;}   // stray click
   BE.muteArm=false;document.getElementById("beMute").classList.remove("on");
   document.getElementById("beARm").style.display=BE.audioSel>=0?"inline-block":"none";
   renderTranscript();
  }
  BE.tlDrag=null;beTLDraw();
 });
}
function beWinReset(){BE.win=[0,BE.dur];beTLDraw();}
function beMuteMode(){
 BE.muteArm=!BE.muteArm;BE.trk=false;BE.add=false;BE.addAnchor=null;
 document.getElementById("beMute").classList.toggle("on",BE.muteArm);
 document.getElementById("beTrk").classList.remove("on");
 document.getElementById("beAdd").classList.remove("on");
}
function beAudioRm(){
 if(BE.audioSel>=0){BE.audio.splice(BE.audioSel,1);BE.audioSel=-1;
  document.getElementById("beARm").style.display="none";
  renderTranscript();renderAudioSugg();beTLDraw();}
}
function beTrackMode(){
 BE.trk=!BE.trk;BE.add=false;BE.addAnchor=null;BE.muteArm=false;
 document.getElementById("beTrk").classList.toggle("on",BE.trk);
 document.getElementById("beAdd").classList.remove("on");
 document.getElementById("beMute").classList.remove("on");
}
async function beTrackGo(box){
 const st=document.getElementById("beTrkSt");st.style.display="inline";
 st.textContent=`tracking ${BE.win[0].toFixed(1)}–${BE.win[1].toFixed(1)}s…`;
 const r=await fetch(`api/jobs/${CUR}/track_object`,{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({box,t_ref:BE.t,t0:BE.win[0],t1:BE.win[1]})});
 if(!r.ok){st.textContent="tracking failed to start";return;}
 const poll=setInterval(async()=>{
  const d=await (await fetch(`api/jobs/${CUR}/track_status`)).json();
  if(d.state!=="running"){
   clearInterval(poll);
   st.textContent=d.error?("⚠ "+d.error)
    :`tracked ✓ ${d.added} position(s) — review card added`;
   if(!d.error){await tlInit();beScrub();
    if(document.getElementById("review"))loadReview();}
  }
 },1500);
}
async function beScrub(){
 const id=CUR,gen=VIEW_GEN,editor=BE;
 const sl=document.getElementById("beT");if(!sl)return; // editor was closed
 if(BE.playing){               // dragging the slider while playing = seek
  const v=document.getElementById("beVid");
  if(v)v.currentTime=+sl.value;
  return;                      // the rAF loop keeps label/boxes in sync
 }
 BE.sel=-1;document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
 BE.t=+document.getElementById("beT").value;
 document.getElementById("beL").textContent=BE.t.toFixed(1)+"s";
 document.getElementById("beImg").src=`api/jobs/${CUR}/frame_at?t=${BE.t}`;
 if(BE_VIEW)BE_VIEW.sync();
 const d=await (await fetch(`api/jobs/${id}/boxes_at?t=${BE.t}&all=1`)).json();
 if(!ownsView(id,gen)||BE!==editor)return;
 BE.ox=d.ox;BE.oy=d.oy;BE.raw=d.boxes;
 beFilter();beDraw();beTLDraw();
}
function beFilter(){
 BE.boxes=(BE.raw||[]).filter(b=>{
  const on=(b.i in EN)?EN[b.i]:b.enabled;   // live: review toggles apply here
  return on;
 }).map(b=>{
  let bb=b;
  if(BE.ov[b.i]){const o=BE.ov[b.i];
   bb={...b,box:[o[0]+BE.ox,o[1]+BE.oy,o[2]+BE.ox,o[3]+BE.oy]};}
  if(BE.times[b.i]){bb={...bb,t_start:BE.times[b.i][0],t_end:BE.times[b.i][1]};}
  return bb;
 });
}
function beDraw(){
 const cv=document.getElementById("beCv");if(!cv)return;
 const view=BE_VIEW;if(!view||!view.current())return;
 const x=cv.getContext("2d"),tr=view.transform;
 x.setTransform(1,0,0,1,0,0);x.clearRect(0,0,cv.width,cv.height);
 if(!tr)return;
 x.setTransform(cv.width/tr.width,0,0,cv.height/tr.height,0,0);
 const mapped=box=>box.map((v,i)=>v*(i%2?tr.sy:tr.sx));
 for(const a of BE.adds){
  if(BE.t<a.t0-0.01||BE.t>a.t1+0.01)continue;
  const[a1,b1,a2,b2]=mapped(a.box);
  x.fillStyle="rgba(245,158,11,.25)";x.strokeStyle="#f59e0b";x.lineWidth=2;
  x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);
 }
 if(BE.add&&BE.addAnchor&&BE.addFloat){
  const[p,q]=[BE.addAnchor,BE.addFloat];
  x.strokeStyle="#f59e0b";x.setLineDash([6,4]);x.lineWidth=2;
  x.strokeRect(Math.min(p[0],q[0])*tr.sx,Math.min(p[1],q[1])*tr.sy,
   Math.abs(q[0]-p[0])*tr.sx,Math.abs(q[1]-p[1])*tr.sy);x.setLineDash([]);
 }
 for(const b of BE.boxes){
  const[a1,b1,a2,b2]=mapped(b.box);
  x.fillStyle=b.i===BE.sel?"rgba(37,99,235,.25)":"rgba(220,38,38,.22)";
  x.strokeStyle=b.i===BE.sel?"#2563eb":"#dc2626";x.lineWidth=2;
  x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);
  if(b.i===BE.sel)for(const[hx,hy] of [[a1,b1],[a2,b1],[a1,b2],[a2,b2]]){
   x.fillStyle="#fff";x.fillRect(hx-5,hy-5,10,10);
   x.strokeRect(hx-5,hy-5,10,10);}
 }
}
function beAddMode(){
 BE.add=!BE.add;BE.addAnchor=null;BE.sel=-1;
 BE.trk=false;BE.muteArm=false;
 document.getElementById("beAdd").classList.toggle("on",BE.add);
 const tb=document.getElementById("beTrk");if(tb)tb.classList.remove("on");
 const mb=document.getElementById("beMute");if(mb)mb.classList.remove("on");
 document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
 beDraw();
}
function beApplyTimes(){
 if(BE.sel<0)return;
 const t0=+document.getElementById("beT0").value,
       t1=+document.getElementById("beT1").value;
 if(!(t1>t0&&t0>=0)){alert("'to' must be after 'from'.");return;}
 BE.times[BE.sel]=[t0,Math.min(t1,BE.dur)];
 const b=BE.boxes.find(x=>x.i===BE.sel);
 if(b){b.t_start=t0;b.t_end=t1;}
 beDraw();
}
function beShowTimes(b){
 const el=document.getElementById("beTimes");
 el.style.display="inline-flex";
 document.getElementById("beT0").value=b.t_start.toFixed(1);
 document.getElementById("beT1").value=b.t_end.toFixed(1);
}
function manualId(){
 const c=globalThis.crypto;
 if(c&&typeof c.randomUUID==="function")return c.randomUUID();
 if(!c||typeof c.getRandomValues!=="function")
  throw Error("Secure random generation is unavailable. Use a browser with crypto support to add a box.");
 const b=c.getRandomValues(new Uint8Array(16));
 b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;
 const h=Array.from(b,v=>v.toString(16).padStart(2,"0")).join("");
 return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
function beHook(){
 const cv=document.getElementById("beCv"),view=BE_VIEW;
 const pt=e=>{
  const tr=view&&view.sync();if(!tr||BE.playing)return null;
  const r=cv.getBoundingClientRect();
  return[(e.clientX-r.left)/tr.sx,(e.clientY-r.top)/tr.sy];};
 cv.addEventListener("pointerdown",e=>{
  const p=pt(e);if(!p)return;
  cv.setPointerCapture(e.pointerId);BE.pointerId=e.pointerId;
  if(BE.trk){
   // Track object: same two-click box draw as Add box, but on completion
   // the region is template-tracked through the active timeline window
   if(!BE.addAnchor){BE.addAnchor=p;BE.addFloat=p;}
   else{
    const a=BE.addAnchor,q=p;BE.addAnchor=null;BE.addFloat=null;
    const box=[Math.min(a[0],q[0]),Math.min(a[1],q[1]),
               Math.max(a[0],q[0]),Math.max(a[1],q[1])];
    BE.trk=false;document.getElementById("beTrk").classList.remove("on");
    if(box[2]-box[0]>10&&box[3]-box[1]>10)beTrackGo(box);
    beDraw();
   }
   return;
  }
  if(BE.add){
   if(!BE.addAnchor){BE.addAnchor=p;BE.addFloat=p;}
   else{
    const a=BE.addAnchor,q=p;BE.addAnchor=null;BE.addFloat=null;
    const box=[Math.min(a[0],q[0]),Math.min(a[1],q[1]),
               Math.max(a[0],q[0]),Math.max(a[1],q[1])];
    if(box[2]-box[0]>6&&box[3]-box[1]>6){
     const t0=Math.max(0,+(BE.t-0.5).toFixed(1)),
           t1=Math.min(BE.dur,+(BE.t+3).toFixed(1));
     const fr=prompt("Blur this region FROM (seconds):",t0);
     if(fr===null){beDraw();return;}
     const to=prompt("...TO (seconds):",t1);
     if(to===null){beDraw();return;}
     try{
      BE.adds.push({manual_id:manualId(),box,t0:Math.max(0,+fr||0),
                    t1:Math.min(BE.dur,+to||t1),tref:BE.t});
     }catch(e){saveStatus(EDITS,"Could not add box: "+e.message);}
    }
    beDraw();
   }
   return;
  }
  const sel=BE.boxes.find(b=>b.i===BE.sel);
  if(sel){const[a1,b1,a2,b2]=sel.box,tr=view.transform;
   const corners=[[a1,b1,0],[a2,b1,1],[a1,b2,2],[a2,b2,3]];
   for(const[hx,hy,ci] of corners)
    if(Math.abs(p[0]-hx)<9/tr.sx&&Math.abs(p[1]-hy)<9/tr.sy){
     BE.drag={kind:"corner",ci};return;}
   if(p[0]>=a1&&p[0]<=a2&&p[1]>=b1&&p[1]<=b2){
    BE.drag={kind:"move",off:[p[0]-a1,p[1]-b1]};return;}
  }
  const hit=[...BE.boxes].reverse().find(b=>{
   const[a1,b1,a2,b2]=b.box;
   return p[0]>=a1&&p[0]<=a2&&p[1]>=b1&&p[1]<=b2;});
  BE.sel=hit?hit.i:-1;
  document.getElementById("beRm").style.display=hit?"inline-block":"none";
  if(hit)beShowTimes(hit);
  else document.getElementById("beTimes").style.display="none";
  beDraw();
 });
 cv.addEventListener("pointermove",e=>{
  const p=pt(e);if(!p)return;
  if(BE.add&&BE.addAnchor){BE.addFloat=p;beDraw();return;}
  if(!BE.drag||BE.sel<0)return;
  const b=BE.boxes.find(x=>x.i===BE.sel);if(!b)return;
  let[a1,b1,a2,b2]=b.box;
  if(BE.drag.kind==="move"){
   const w0=a2-a1,h0=b2-b1;a1=p[0]-BE.drag.off[0];b1=p[1]-BE.drag.off[1];
   a2=a1+w0;b2=b1+h0;
  }else{
   if(BE.drag.ci===0){a1=p[0];b1=p[1];}
   if(BE.drag.ci===1){a2=p[0];b1=p[1];}
   if(BE.drag.ci===2){a1=p[0];b2=p[1];}
   if(BE.drag.ci===3){a2=p[0];b2=p[1];}
  }
  b.box=[Math.min(a1,a2),Math.min(b1,b2),Math.max(a1,a2),Math.max(b1,b2)];
  BE.ov[BE.sel]=[b.box[0]-BE.ox,b.box[1]-BE.oy,b.box[2]-BE.ox,b.box[3]-BE.oy];
  beDraw();
 });
 const end=()=>{if(view&&view.current()){BE.drag=null;delete BE.pointerId;}};
 cv.addEventListener("pointerup",end);cv.addEventListener("pointercancel",()=>{
  if(view&&view.current()){beEndGesture(BE,cv);beDraw();}
 });
}
function zoomDet(i){
 let ov=document.getElementById("lb");
 if(!ov){
  ov=document.createElement("div");ov.id="lb";
  ov.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.82);"+
   "z-index:100;display:flex;align-items:center;justify-content:center;"+
   "cursor:zoom-out;padding:18px";
  ov.onclick=()=>ov.remove();
  document.body.appendChild(ov);
 }
 ov.innerHTML=`<img src="api/jobs/${CUR}/detframe/${i}"
  style="max-width:96%;max-height:96%;border-radius:8px;
  box-shadow:0 12px 50px rgba(0,0,0,.6)">`;
}
function beRemove(){
 if(BE.sel<0)return;
 applyDet(BE.sel,false);   // syncs thumbnail + refilters editor
 BE.sel=-1;
 document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
}
async function beSave(){return saveAndRender();}
async function cancelJob(){await fetch("api/jobs/"+CUR+"/cancel",{method:"POST"})}

// the three post-render views (compare, review, box editor) are mutually
// exclusive: opening one closes the others instead of stacking them
function showPanel(which){
 const clear=element=>{if(element){beUnmountIn(element);element.innerHTML="";}};
 // boxedit_rev keeps the review, its scheduler and its in-review editor slot.
 if(which!=="compare")clear(document.getElementById("compare"));
 const b=document.getElementById("beslot_done"),b2=document.getElementById("beslot");
 if(which==="boxedit_rev")clear(b);
 else{
  if(which!=="boxedit")clear(b);
  clear(b2);
  if(which!=="review"){
   disposeReview();const rev=document.getElementById("review");
   if(rev){beUnmountIn(rev);rev.remove();}
  }
 }
}

async function loadCompare(){
 showPanel("compare");
 const d=await (await fetch(`api/jobs/${CUR}/detections`)).json();
 const c=document.getElementById("compare");
 c.innerHTML=`<div class="row" style="margin-top:8px">t=
  <input type="range" id="cmpT" min="0" max="${d.duration.toFixed(1)}" step="0.2"
   value="0" style="flex:1" oninput="cmpShow()">
  <span id="cmpLbl">0s</span></div>
  <div class="grid2"><div><b>Original</b><br><img id="cmpO" style="max-width:100%"></div>
  <div><b>Redacted</b><br><img id="cmpR" style="max-width:100%"></div></div>`;
 cmpShow();
}
function cmpShow(){
 const t=document.getElementById("cmpT").value;
 document.getElementById("cmpLbl").textContent=t+"s";
 document.getElementById("cmpO").src=`api/jobs/${CUR}/frame_at?t=${t}`;
 document.getElementById("cmpR").src=`api/jobs/${CUR}/frame_at?t=${t}&src=output`;
}

// Complete metadata stays authoritative even when its cards are unmounted.
let TRKMEM={},ROWCARD={},REVIEW_META=null,REVIEW_SCHED=null,REVIEW_LOAD=0;
const THUMB_FLIGHTS=new Set(); // unsettled fetch + body operations, across views
function reviewDescriptors(rows){
 const groups={},zones=[];TRKMEM={};ROWCARD={};
 for(const x of rows){
  EN[x.i]=(x.i in EDITS.enabled)?EDITS.enabled[x.i]:x.enabled;
  if(x.zone_dropped)zones.push(x);
  else (groups[x.category]=groups[x.category]||[]).push(x);
 }
 const sections=[];
 function section(category,items,zone=false){
  const cards=items.map(x=>({id:x.i,category,zone,representative:x,members:TRKMEM[x.i]||[x.i]}));
  for(const c of cards)for(const m of c.members)ROWCARD[m]=c.id;
  sections.push({category,zone,cards,ids:cards.map(c=>c.id)});
 }
 if(zones.length)section('zdrop',zones,true);
 for(const [cat,raw] of Object.entries(groups)){
  const grouped={},items=[];
  for(const x of raw){
   const key=x.person>=0?'p'+x.person:x.track>=0?'t'+x.track:null;
   if(key)(grouped[key]=grouped[key]||[]).push(x);
   else{TRKMEM[x.i]=[x.i];items.push(x);}
  }
  for(const [key,members] of Object.entries(grouped)){
   members.sort((a,b)=>a.t_start-b.t_start);
   let best=members[0];
   for(const m of members)if((m.confidence||0)>(best.confidence||0))best=m;
   const rep={...best,t_start:members[0].t_start,t_end:members[members.length-1].t_end,
    frames:members.length,personcard:key[0]==='p'};
   TRKMEM[rep.i]=members.map(m=>m.i);items.push(rep);
  }
  items.sort((a,b)=>((b.personcard?1:0)-(a.personcard?1:0))||a.t_start-b.t_start);
  section(cat,items);
 }
 return sections;
}
function reviewCard(c){
 const x=c.representative,cat=c.category;
 return `<div class="det" id="det${c.id}" data-cat="${detLabel(cat)}">
  <div class="thumbwell"><img alt="Detection preview" style="cursor:zoom-in" onclick="zoomDet(${c.id})"></div>
  <div>${x.personcard?`<b>Person ${x.person+1}</b>`:`&quot;${detLabel(x.text)}&quot;`}${x.frames?` <span class="badge">×${x.frames} frames</span>`:''}${x.confidence?` <span class="badge" title="detector confidence — low values on a non-face thumbnail usually mean a false detection">${Math.round(x.confidence*100)}%</span>`:''}<br>${x.t_start.toFixed(1)}–${x.t_end.toFixed(1)}s</div>
  ${x.frames>1?`<div class="detscope">Applies to all ${x.frames} appearances in this ${detLabel(CATDN[cat]||cat)} group</div>`:''}
  ${detChoices(c.id,c.zone?'Outside-zone detection':CATDN[cat]||cat)}</div>`;
}
async function loadReview(auto=null){
 const id=CUR,gen=VIEW_GEN,request=++REVIEW_LOAD,reviewRequest={};REVIEW_REQUEST=reviewRequest;
 disposeReview();showPanel('review');
 const r=await fetch(`api/jobs/${id}/detections`);
 if(!r.ok)throw new Error("Review HTTP "+r.status);
 const d=await r.json();
 if(!ownsView(id,gen)||request!==REVIEW_LOAD||
    (auto&&(REVIEW_REQUEST!==reviewRequest||AUTO_REVIEW!==auto||PHPH!=="review")))return;
 if(auto)auto.state="ready";
 DUR=d.duration;
 const sections=reviewDescriptors(d.detections);
 REVIEW_META={sections,byId:new Map(sections.flatMap(s=>s.cards.map(c=>[c.id,c])))};
 let html=`<div class="card" id="review"><h2>Review — choose Blur or Keep visible.
 Drag a box around several to bulk-set.</h2>
 <div class="row" style="margin:0 0 8px"><button class="sec" onclick="loadBoxEdit(1)">▶ Preview video &amp; edit boxes (before rendering)</button></div>
 <div id="beslot"></div><div class="row reviewranges">
 <button class="sec" data-review-prev onclick="REVIEW_SCHED?.range(-1)">Previous review cards</button>
 <span data-review-range role="status" aria-live="polite"></span>
 <button class="sec" data-review-next onclick="REVIEW_SCHED?.range(1)">Next review cards</button></div>
 <div id="detwrap" style="position:relative;user-select:none">`;
 sections.forEach((section,n)=>{
  const cat=section.category;
  if(section.zone)html+=`<details data-review-zones style="margin:4px 0 10px;border:1px dashed #f59e0b;border-radius:9px;padding:8px 10px;background:#26200a">
   <summary style="cursor:pointer;color:#fbbf24;font-weight:600">⚠ ${section.ids.length} detection(s) outside your zones — choose output below (mostly logos/labels by design; open only if something real was zoned out)</summary>
   <div class="row" style="margin:8px 0 4px"><button class="sec" onclick="setAllZd(true)">Blur all</button><button class="sec" onclick="setAllZd(false)">Keep all visible</button></div>`;
  else html+=`<h3 style="margin:10px 0 6px">${detLabel(CATDN[cat]||cat)} <span class="badge">${section.ids.length}</span>
   <button class="sec" style="padding:3px 8px;font-size:12px" onclick="setAll(this.dataset.cat,true)" data-cat="${detLabel(cat)}">Blur all</button>
   <button class="sec" style="padding:3px 8px;font-size:12px" onclick="setAll(this.dataset.cat,false)" data-cat="${detLabel(cat)}">Keep all visible</button></h3>`;
  html+=`<div class="grid3 reviewgrid" data-review-section="${n}"></div>`;
  if(section.zone)html+='</details>';
 });
 html+=`</div><div class="row" style="margin-top:12px"><button data-save-edits onclick="saveAndRender()">Save edits &amp; render</button>
 <span style="font-size:12px;color:#94a3b8">missed something? use ▶ Preview video &amp; edit boxes above — its ＋ Add box replaces the old add-region tool</span></div></div>`;
 const old=document.getElementById('review');if(old){beUnmountIn(old);old.remove();}
 detail.insertAdjacentHTML('beforeend',html);
 REVIEW_SCHED=new ReviewScheduler(id,gen,document.getElementById('review'),REVIEW_META);
 REVIEW_SCHED.start();initMarquee();saveStatus(EDITS,EDITS.status);
}
function disposeReview(){
 if(REVIEW_SCHED){const old=REVIEW_SCHED;REVIEW_SCHED=null;old.dispose();}
}
// P15 seam: matchingCardIds is the COMPLETE matching descriptor set. P15 owns
// predicates/counts/focus fallback. This local hook never writes choices or I/O.
function refreshReviewVisibleSet({jobId,viewGen,matchingCardIds}={}){
 const s=REVIEW_SCHED;
 if(!s||s.jobId!==jobId||s.viewGen!==viewGen||!s.owns())return;
 if(matchingCardIds)s.matching=new Set(matchingCardIds.filter(i=>s.meta.byId.has(i)));
 s.schedule();
}
// One review-instance owner. It never owns output, editor or unrelated requests.
class ReviewScheduler{
 constructor(jobId,viewGen,root,meta){
  Object.assign(this,{jobId,viewGen,root,meta});
  this.token={};this.disposed=false;this.frame=0;this.bindings=new Map();
  this.retries=new Map();this.eligible=new Map();this.queue=[];this.listeners=[];
  this.matching=new Set(meta.byId.keys());this.sections=[];this.normalIds=[];
  this.gesture=false;this.selectionCleanup=null;
 }
 owns(){return !this.disposed&&REVIEW_SCHED===this&&ownsView(this.jobId,this.viewGen)&&
  this.root.isConnected&&document.getElementById('review')===this.root;}
 valid(b,eligible=true){return this.owns()&&this.bindings.get(b.id)===b&&b.img.isConnected&&
  b.card.isConnected&&(!eligible||this.eligible.has(b.id));}
 listen(target,event,fn,options){target.addEventListener(event,fn,options);
  this.listeners.push(()=>target.removeEventListener(event,fn,options));}
 start(){
  this.sections=this.meta.sections.map((data,n)=>({data,el:this.root.querySelector(`[data-review-section="${n}"]`),
   ids:[],columns:0,width:0,heights:[],prefix:[0],rows:new Map(),spacers:[]}));
  this.observer=new ResizeObserver(()=>this.schedule());
  this.observer.observe(this.root);
  this.listen(window,'scroll',()=>this.schedule(),{passive:true});
  this.listen(window,'resize',()=>this.schedule(),{passive:true});
  this.listen(this.root,'focusin',()=>this.schedule());
  this.listen(this.root,'focusout',()=>this.schedule());
  const zones=this.root.querySelector('[data-review-zones]');
  if(zones)this.listen(zones,'toggle',()=>{
   if(!zones.open){for(const section of this.meta.sections)if(section.zone)
    for(const id of section.ids)selSet.delete(id);
    if(menuEl){menuEl.remove();menuEl=null;}if(selSet.size)showSelMenu(12,12);
   }this.schedule();
  });
  this.listen(window,'pagehide',()=>this.dispose({suspend:true}));
  this.layout();
 }
 schedule(){if(!this.owns()||this.frame)return;
  this.frame=requestAnimationFrame(()=>{this.frame=0;if(this.owns())this.layout();});}
 prefix(section){
  section.prefix=[0];for(const h of section.heights)section.prefix.push(section.prefix.at(-1)+h+9);
  section.el.style.height=Math.max(0,section.prefix.at(-1)-9)+'px';
 }
 rowAt(section,y){
  let lo=0,hi=section.heights.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(section.prefix[mid+1]<=y)lo=mid+1;else hi=mid;}
  return Math.min(lo,Math.max(0,section.heights.length-1));
 }
 anchor(){
  let best=null;
  for(const b of this.bindings.values()){
   if(b.card.dataset.focusPin==='1')continue;
   const r=b.card.getBoundingClientRect();
   if(r.bottom>0&&r.top<window.innerHeight&&(!best||r.top<best.top))best={id:b.id,top:r.top};
  }return best;
 }
 // Reconcile siblings around the actual focused subtree. Moving its other
 // siblings preserves native Tab order without detaching the focused ancestor.
 orderNodes(parent,nodes,active){
  let next=null;
  for(let n=nodes.length-1;n>=0;n--){const node=nodes[n];
   if(!node.contains(active)&&node.nextElementSibling!==next)parent.insertBefore(node,next);
   next=node;
  }
 }
 layout(){
  if(!this.owns()||this.gesture)return;
  let anchor=this.anchor();const active=document.activeElement;
  const focus=active?.closest?.('.det'),focusId=focus?+focus.id.slice(3):null;
  let changed=false;
  for(const section of this.sections){
   const open=!section.data.zone||section.el.closest('details').open;
   const ids=open?section.data.ids.filter(id=>this.matching.has(id)):[];
   const rect=section.el.getBoundingClientRect(),width=section.el.clientWidth;
   section.scale=width?rect.width/width:1;
   const tracks=getComputedStyle(section.el).gridTemplateColumns;
   const columns=tracks&&tracks!=='none'?tracks.split(' ').length:1;
   if(section.width!==width||section.columns!==columns||ids.length!==section.ids.length||ids.some((id,n)=>id!==section.ids[n])){
    if(section.width&&section.width!==width&&this.lastAnchor)anchor=this.lastAnchor;
    section.width=width;section.columns=columns;section.ids=ids;
    section.heights=Array(Math.ceil(ids.length/columns)).fill(260);changed=true;
   }else for(const [n,row] of section.rows){
    if(row.dataset.pin==='1')continue;
    const h=row.getBoundingClientRect().height/section.scale;
    if(h&&Math.abs(section.heights[n]-h)>.5){section.heights[n]=h;changed=true;}
   }
   this.prefix(section);
  }
  // Correct estimates/widths without shifting the user's first visible card.
  if(changed&&anchor){
   for(const section of this.sections){const n=section.ids.indexOf(anchor.id);if(n<0)continue;
    const top=section.el.getBoundingClientRect().top+section.prefix[Math.floor(n/section.columns)]*section.scale;
    window.scrollBy(0,top-anchor.top);break;}
  }
  const candidates=[],nearby=[];
  for(const section of this.sections){
   if(!section.ids.length)continue;
   const top=section.el.getBoundingClientRect().top;
   const end=section.prefix.at(-1)-9,scale=section.scale;
   if(top>window.innerHeight||top+end*scale<0)continue;
   const first=this.rowAt(section,Math.max(0,-top/scale));
   const last=this.rowAt(section,Math.min(end,(window.innerHeight-top)/scale));
   for(let n=first;n<=last;n++)candidates.push({section,n,rank:0});
   for(let n=last+1;n<section.heights.length&&(section.prefix[n]-section.prefix[last+1])*scale<window.innerHeight;n++)
    nearby.push({section,n,rank:1});
   for(let n=first-1;n>=0&&(section.prefix[first]-section.prefix[n+1])*scale<window.innerHeight;n--)
    nearby.push({section,n,rank:1});
  }
  const selected=new Map(),desired=new Map();let used=0,prefetch=0;
  function admit(item){const {section,n,rank}=item;
   const ids=section.ids.slice(n*section.columns,(n+1)*section.columns);
   if(used+ids.length>64)return false;
   if(rank&&prefetch+(section.heights[n]+9)*section.scale>window.innerHeight)return false;
   if(!selected.has(section))selected.set(section,new Set());selected.get(section).add(n);
   for(const id of ids)desired.set(id,{rank,order:desired.size});
   used+=ids.length;if(rank)prefetch+=(section.heights[n]+9)*section.scale;return true;
  }
  candidates.forEach(admit);nearby.forEach(admit);
  this.normalIds=[...desired.keys()];
  // Keep one actual focused subtree. Its row contains only that card, at its
  // original column; a selected card alone never receives a retention pin.
  const pin=focusId!==null&&!desired.has(focusId)&&this.bindings.has(focusId)&&
   this.sections.some(s=>s.ids.includes(focusId))?focusId:null;
  for(const [id,b]of this.bindings)if(!desired.has(id)&&id!==pin)this.retire(b);
  for(const section of this.sections){
   const rows=selected.get(section)||new Set();
   const pinIndex=pin===null?-1:section.ids.indexOf(pin),pinRow=pinIndex<0?-1:Math.floor(pinIndex/section.columns);
   for(const [n,row]of section.rows)if(!rows.has(n)&&n!==pinRow){this.observer.unobserve(row);row.remove();section.rows.delete(n);}
   const needed=new Set(rows);if(pinRow>=0)needed.add(pinRow);
   const orderedRows=[];
   for(const n of [...needed].sort((a,b)=>a-b)){
    let row=section.rows.get(n);
    if(!row){row=document.createElement('div');row.className='grid3 reviewrow';section.el.appendChild(row);
     section.rows.set(n,row);this.observer.observe(row);}
    orderedRows.push(row);
    row.style.top=section.prefix[n]+'px';row.dataset.pin=String(!rows.has(n)?1:0);
    const ids=section.ids.slice(n*section.columns,(n+1)*section.columns),orderedCards=[];
    for(const [col,id]of ids.entries()){
     if(!desired.has(id)&&id!==pin)continue;
     let b=this.bindings.get(id);
     if(!b){
      const holder=document.createElement('div');holder.innerHTML=reviewCard(this.meta.byId.get(id));
      const card=holder.firstElementChild,img=card.querySelector('img');
      b={id,card,img,token:{},url:null,op:null};this.bindings.set(id,b);
     }
     if(b.card.parentElement!==row)row.appendChild(b.card);orderedCards.push(b.card);
     b.card.style.gridColumn=String(col+1);b.card.dataset.focusPin=String(id===pin?1:0);
     b.card.classList.toggle('selected',selSet.has(id));refreshDet(id);
    }
    this.orderNodes(row,orderedCards,active);
   }
   for(const spacer of section.spacers)spacer.remove();section.spacers=[];
   this.orderNodes(section.el,orderedRows,active);
   // Constant before/after spacers (plus a focused row, if any). Offscreen
   // rows are numeric heights only; no per-group placeholder/HTML is kept.
   const ns=[...rows].sort((a,b)=>a-b),first=ns[0]??0,last=ns.at(-1)??-1;
   for(const [top,height]of [[0,section.prefix[first]||0],[section.prefix[last+1]||0,
    section.prefix.at(-1)-(section.prefix[last+1]||0)]]){
    const spacer=document.createElement('div');spacer.className='reviewspacer';
    spacer.setAttribute('aria-hidden','true');spacer.style.top=top+'px';spacer.style.height=height+'px';
    section.el.appendChild(spacer);section.spacers.push(spacer);
   }
  }
  if(active?.isConnected&&document.activeElement!==active)active.focus({preventScroll:true});
  this.eligible=desired;this.updateQueue();this.rangeFeedback();this.lastAnchor=this.anchor();
 }
 rangeFeedback(){
  const ids=this.sections.flatMap(s=>s.ids),mounted=new Set(this.normalIds),positions=[];
  ids.forEach((id,n)=>{if(mounted.has(id))positions.push(n)});
  const first=positions[0]??-1,last=positions.at(-1)??-1;
  this.rangeIds=ids;this.rangeFirst=first;this.rangeLast=last;
  const status=this.root.querySelector('[data-review-range]');
  status.textContent=first<0?`${ids.length} review cards; scroll to view`:`Cards ${first+1}–${last+1} of ${ids.length}`;
  this.root.querySelector('[data-review-prev]').disabled=!ids.length||first===0;
  this.root.querySelector('[data-review-next]').disabled=!ids.length||last===ids.length-1;
 }
 range(direction){
  if(!this.owns())return;
  const ids=this.rangeIds||[],index=direction>0?Math.max(0,this.rangeLast+1):
   (this.rangeFirst<0?ids.length-1:Math.max(0,this.rangeFirst-1));
  const id=ids[index];if(id===undefined)return;
  for(const section of this.sections){const n=section.ids.indexOf(id);if(n<0)continue;
   const top=section.el.getBoundingClientRect().top+window.scrollY+section.prefix[Math.floor(n/section.columns)]*section.scale;
   window.scrollTo(0,Math.max(0,top-55));this.layout();
   this.bindings.get(id)?.card.querySelector('button')?.focus({preventScroll:true});break;}
 }
 retryState(id){if(!this.retries.has(id))this.retries.set(id,{failures:0,readyAt:0,timer:0});return this.retries.get(id);}
 clearURL(b){
  b.img.onload=null;b.img.onerror=null;b.img.removeAttribute('src');
  if(b.url){URL.revokeObjectURL(b.url);b.url=null;}
 }
 cancel(b){if(b.op&&!b.op.cancelled){b.op.cancelled=true;b.op.controller.abort();}}
 retire(b){
  this.cancel(b);this.clearURL(b);this.bindings.delete(b.id);
  const r=this.retries.get(b.id);if(r?.timer){clearTimeout(r.timer);r.timer=0;}
  b.card.remove?.();
 }
 unavailable(b){if(this.valid(b,false))b.img.parentElement.classList.add('unavailable');}
 fail(b){
  if(!this.valid(b))return;
  this.clearURL(b);const r=this.retryState(b.id);r.failures++;
  if(r.failures>=4){this.unavailable(b);return;}
  r.readyAt=Date.now()+600*r.failures;this.updateQueue();
 }
 updateQueue(){
  if(!this.owns())return;
  this.queue=[];
  for(const [id,b]of this.bindings){
   const r=this.retryState(id),priority=this.eligible.get(id);
   if(!priority){this.cancel(b);if(r.timer){clearTimeout(r.timer);r.timer=0;}continue;}
   if(b.url||b.op)continue;
   if(r.failures>=4){this.unavailable(b);continue;}
   if(r.readyAt>Date.now()){
    if(!r.timer){const token=b.token;
     r.timer=setTimeout(()=>{r.timer=0;if(this.valid(b)&&b.token===token)this.updateQueue();},r.readyAt-Date.now());}
    continue;
   }
   this.queue.push({b,rank:priority.rank?2:r.failures?1:0,order:priority.order});
  }
  this.queue.sort((a,b)=>a.rank-b.rank||a.order-b.order);this.pump();
 }
 pump(){
  if(!this.owns())return;
  while(THUMB_FLIGHTS.size<4&&this.queue.length){
   const {b}=this.queue.shift();if(!this.valid(b)||b.op||b.url)continue;
   this.request(b);
  }
 }
 async request(b){
  const controller=new AbortController(),op={controller,cancelled:false,token:b.token};
  b.op=op;THUMB_FLIGHTS.add(op);
  try{
   const url=new URL(`api/jobs/${this.jobId}/thumb/${b.id}`,document.baseURI);
   const r=this.retryState(b.id);if(r.failures)url.searchParams.set('r',String(Date.now()));
   const response=await fetch(url.href,{signal:controller.signal});
   const blob=await response.blob();
   if(!response.ok)throw Error('Thumbnail HTTP '+response.status);
   if(op.cancelled||!this.valid(b)||b.token!==op.token)return;
   const urlValue=URL.createObjectURL(blob);
   if(op.cancelled||!this.valid(b)||b.token!==op.token){URL.revokeObjectURL(urlValue);return;}
   b.url=urlValue;b.img.parentElement.classList.remove('unavailable');
   b.img.onload=()=>{if(!this.valid(b)||b.token!==op.token||b.url!==urlValue)return;};
   b.img.onerror=()=>{if(this.valid(b)&&b.token===op.token&&b.url===urlValue)this.fail(b);};
   b.img.src=urlValue;
  }catch(error){if(!op.cancelled&&this.valid(b)&&b.token===op.token)this.fail(b);}
  finally{
   if(b.op===op)b.op=null;THUMB_FLIGHTS.delete(op);
   // Replacements can mount immediately, but never borrow an unsettled slot.
   if(REVIEW_SCHED?.owns())REVIEW_SCHED.updateQueue();
  }
 }
 dispose({suspend=false}={}){
  if(this.disposed){if(!suspend){this.retries.clear();this.suspended=false;}return;}
  this.disposed=true;this.suspended=suspend;
  if(this.frame)cancelAnimationFrame(this.frame);this.frame=0;
  this.observer?.disconnect();this.listeners.splice(0).forEach(remove=>remove());
  this.selectionCleanup?.();this.selectionCleanup=null;
  const wrap=this.root.querySelector?.('#detwrap');if(wrap)delete wrap.dataset.mq;
  for(const b of [...this.bindings.values()])this.retire(b);
  for(const section of this.sections){
   for(const row of section.rows.values())row.remove();section.rows.clear();
   for(const spacer of section.spacers)spacer.remove();section.spacers=[];
  }
  for(const r of this.retries.values())if(r.timer)clearTimeout(r.timer);
  // A hidden page keeps only numeric retry history for this exact view.
  // Timers/bindings/controllers belong to the retired scheduler, never resume.
  this.retries=suspend?new Map([...this.retries].map(([id,r])=>
   [id,{failures:r.failures,readyAt:r.readyAt,timer:0}])):new Map();
  this.eligible.clear();this.queue=[];
  clearSel();if(marqEl){marqEl.remove();marqEl=null;}mStart=null;
 }
}
// Back/forward-cache restoration reuses this view's complete metadata/drafts.
window.addEventListener?.('pageshow',()=>{
 const s=REVIEW_SCHED;
 if(s?.disposed&&s.suspended&&ownsView(s.jobId,s.viewGen)&&s.root.isConnected&&document.getElementById('review')===s.root){
  REVIEW_SCHED=new ReviewScheduler(s.jobId,s.viewGen,s.root,s.meta);
  REVIEW_SCHED.matching=s.matching;REVIEW_SCHED.retries=s.retries;
  s.retries=new Map();s.suspended=false;
  REVIEW_SCHED.start();initMarquee();
 }
});
function detLabel(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function detChoices(i,category){
 const count=(TRKMEM[i]||[i]).length;
 return `<div class="detstate" id="ds${i}"></div>
 <div class="detchoices" id="dc${i}" role="group"
  aria-label="${detLabel(category)} output, appearance ${i+1}, ${count} appearance${count===1?"":"s"}"
  aria-describedby="ds${i}">
  <button class="blurbtn blur" id="bb${i}" aria-pressed="false"
   onclick="applyDet(${i},true)">Blur</button>
  <button class="blurbtn keep" id="kb${i}" aria-pressed="false"
   onclick="applyDet(${i},false)">Keep visible</button></div>`;
}
function refreshDet(i){
 const members=TRKMEM[i]||[i],blurred=members.reduce((n,m)=>n+(EN[m]?1:0),0);
 const kept=members.length-blurred;
 const state=document.getElementById("ds"+i),card=document.getElementById("det"+i);
 if(state)state.textContent=kept===0?"Will be blurred":blurred===0?"Will stay visible":
  `Mixed — ${blurred} will be blurred; ${kept} will stay visible`;
 const blur=document.getElementById("bb"+i),keep=document.getElementById("kb"+i);
 if(blur)blur.setAttribute("aria-pressed",String(kept===0));
 if(keep)keep.setAttribute("aria-pressed",String(blurred===0));
 if(card)card.classList.toggle("off",blurred===0);
}
let DET_BATCH=0,DET_DIRTY=new Set();
function finishDetChoices(){
 DET_DIRTY.forEach(refreshDet);DET_DIRTY.clear();
 if(document.getElementById('beCv')){beFilter();beDraw();}
 refreshReviewVisibleSet({jobId:CUR,viewGen:VIEW_GEN});
}
function applyDet(i,blur){
 for(const m of (TRKMEM[i]||[i])){
  EN[m]=blur;EDITS.enabled[m]=blur;DET_DIRTY.add(ROWCARD[m]??m);
 }
 if(!EDITS.busy)saveStatus(EDITS,'Unsaved edits — save to include them in the render.');
 if(!DET_BATCH)finishDetChoices();
}
function applyDetBatch(ids,on){
 const targets=[...ids];DET_BATCH++;
 try{for(const i of targets)applyDet(i,on);}
 finally{if(!--DET_BATCH)finishDetChoices();}
}
function setAll(cat,on){
 applyDetBatch(REVIEW_META?.sections.filter(s=>!s.zone&&s.category===cat).flatMap(s=>s.ids)||[],on);
}
function setAllZd(on){applyDetBatch(REVIEW_META?.sections.filter(s=>s.zone).flatMap(s=>s.ids)||[],on);}

let selSet=new Set(),marqEl=null,menuEl=null,mStart=null;
function clearSel(){
 selSet.forEach(i=>{const t=document.getElementById("det"+i);
  if(t)t.classList.remove("selected");});
 selSet.clear();
 if(menuEl){menuEl.remove();menuEl=null;}
}
function initMarquee(){
 const wrap=document.getElementById('detwrap'),owner=REVIEW_SCHED;
 if(!wrap||!owner||wrap.dataset.mq)return;wrap.dataset.mq=1;
 owner.listen(wrap,'pointerdown',e=>{
  if(e.pointerType==='touch'||e.target.closest('button')||!owner.owns())return;
  clearSel();owner.gesture=true;mStart=[e.pageX,e.pageY];
  // A bounded frozen set; scrolling during the gesture does not mount more.
  const targets=[...owner.bindings.values()].filter(b=>b.card.dataset.focusPin!=='1'&&
   b.card.getBoundingClientRect().bottom>0&&b.card.getBoundingClientRect().top<window.innerHeight);
  marqEl=document.createElement('div');marqEl.className='marq';document.body.appendChild(marqEl);
  const cleanup=()=>{
   document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);
   document.removeEventListener('pointercancel',cancel);document.removeEventListener('keydown',key);
   if(marqEl){marqEl.remove();marqEl=null;}mStart=null;owner.gesture=false;owner.selectionCleanup=null;
   owner.schedule();
  };
  const move=ev=>{
   if(!owner.owns()||!mStart)return;
   const x1=Math.min(mStart[0],ev.pageX),y1=Math.min(mStart[1],ev.pageY),
    x2=Math.max(mStart[0],ev.pageX),y2=Math.max(mStart[1],ev.pageY);
   Object.assign(marqEl.style,{left:x1+'px',top:y1+'px',width:(x2-x1)+'px',height:(y2-y1)+'px'});
  };
  const up=ev=>{
   if(!owner.owns()||!marqEl){cleanup();return;}
   const r=marqEl.getBoundingClientRect();cleanup();
   if(r.width<8&&r.height<8)return;
   for(const b of targets){if(!owner.valid(b,false))continue;
    const t=b.card,rect=t.getBoundingClientRect();
    if(rect.left<r.right&&rect.right>r.left&&rect.top<r.bottom&&rect.bottom>r.top){selSet.add(b.id);t.classList.add('selected');}}
   if(selSet.size)showSelMenu(ev.pageX,ev.pageY);
  };
  const cancel=()=>cleanup(),key=ev=>{if(ev.key==='Escape')cleanup();};
  owner.selectionCleanup=cleanup;
  document.addEventListener('pointermove',move);document.addEventListener('pointerup',up);
  document.addEventListener('pointercancel',cancel);document.addEventListener('keydown',key);
  e.preventDefault();
 });
}
function showSelMenu(x,y){
 menuEl=document.createElement("div");menuEl.className="selmenu";
 menuEl.innerHTML=`<span>${selSet.size} selected</span>
  <button class="mkeep" onclick="bulkSet(false)">Keep visible</button>
  <button class="mblur" onclick="bulkSet(true)">Blur</button>`;
 Object.assign(menuEl.style,{left:x+"px",top:(y+10)+"px"});
 document.body.appendChild(menuEl);
}
function bulkSet(blur){applyDetBatch([...selSet].filter(i=>REVIEW_META?.byId.has(i)),blur);clearSel();}
document.addEventListener("pointerdown",e=>{
 if(menuEl&&!e.target.closest(".selmenu")
    &&!e.target.closest("#detwrap"))clearSel();});
// "?" help tips: keep the bubble fully on screen (a tip beside a phone's
// screen edge used to be cut off), and a tap on a "?" inside a checkbox
// label must open the tip, not tick the box
function qmPlace(q){
 const w=Math.min(250,window.innerWidth-24),r=q.getBoundingClientRect(),
       c=r.left+r.width/2;
 let dx=0;
 if(c-w/2<12)dx=12-(c-w/2);
 else if(c+w/2>window.innerWidth-12)dx=(window.innerWidth-12)-(c+w/2);
 q.style.setProperty("--qw",w+"px");q.style.setProperty("--qx",dx+"px");
 q.classList.toggle("below",r.top<260);}   // no room above: open downward
document.addEventListener("mouseover",e=>{
 const q=e.target.closest&&e.target.closest(".qm");if(q)qmPlace(q);});
document.addEventListener("click",e=>{
 const q=e.target.closest(".qm");
 document.querySelectorAll(".qm.open").forEach(x=>{if(x!==q)x.classList.remove("open");});
 if(q){e.preventDefault();qmPlace(q);q.classList.toggle("open");}});
document.addEventListener("keydown",e=>{
 if(e.key==="Escape"){clearSel();
  const lb=document.getElementById("lb");if(lb)lb.remove();}});

async function reviewPost(url,payload){
 const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},
  ...(payload===undefined?{}:{body:JSON.stringify(payload)})});
 let body;
 try{body=await response.json();}catch(e){throw Error("Invalid server response (HTTP "+response.status+")");}
 if(!response.ok||!body||body.error||body.ok!==true)
  throw Error((body&&body.error)||("Request failed (HTTP "+response.status+")"));
 return body;
}
function acknowledgeMap(current,submitted){
 for(const [key,value] of Object.entries(submitted))
  if(sameEdit(current[key],value))delete current[key];
}
function acknowledgeAdds(current,refs,submitted){
 for(let i=current.length-1;i>=0;i--){
  const index=refs.indexOf(current[i]);
  if(index>=0&&sameEdit(current[i],submitted[index]))current.splice(i,1);
 }
}
async function saveAndRender(){
 const id=CUR,gen=VIEW_GEN,d=EDITS,reviewOwner=REVIEW_SCHED;
 if(!id||!d||d.busy)return false;
 const b=d.editor;
 try{
  // Compatibility drafts acquire an identity once, on the original object.
  for(const a of [...d.manual,...b.adds])if(!Object.prototype.hasOwnProperty.call(a,"manual_id"))a.manual_id=manualId();
 }catch(e){saveStatus(d,"Could not save edits: "+e.message);return false;}
 const manRefs=[...d.manual],addRefs=[...b.adds];
 const man=copyEdit(d.manual),adds=copyEdit(b.adds);
 const payload=copyEdit({enabled:d.enabled,manual:[...man,...adds.map(a=>({
  manual_id:a.manual_id,t_start:a.t0,t_end:a.t1,t_ref:a.tref,screen_box:a.box}))],
  box_overrides:b.ov,time_overrides:b.times});
 // Plain review must never wipe audio that the editor has not loaded.
 if(b.audioLoaded&&!sameEdit(b.audio,b.audioSaved)){payload.audio=copyEdit(b.audio);}
 d.audioInFlight=payload.audio!==undefined;
 d.busy=true;saveStatus(d,"Saving edits… You can keep editing; newer edits stay pending.");
 let saved=false;
 try{
  const result=await reviewPost(`api/jobs/${id}/detections`,payload);
  saved=true;d.audioInFlight=false;
  acknowledgeMap(d.enabled,payload.enabled);
  acknowledgeMap(b.ov,payload.box_overrides);acknowledgeMap(b.times,payload.time_overrides);
  acknowledgeAdds(d.manual,manRefs,man);acknowledgeAdds(b.adds,addRefs,adds);
  if(payload.audio!==undefined)b.audioSaved=copyEdit(payload.audio);
  // A switched-away view never opens a confirmation or changes current UI.
  if(!ownsView(id,gen)){
   saveStatus(d,"Edits saved. Review pending edits, then save to render this job.");return false;
  }
  let allowError="";
  if(result.suggest_allowlist&&result.suggest_allowlist.length&&
     confirm("You disabled every instance of: "+result.suggest_allowlist.join(", ")+". Add these to the permanent allow-list so future scans skip them?")){
   try{await reviewPost("api/allowlist",{words:result.suggest_allowlist});loadPersist();}
   catch(e){allowError=" Allow-list update failed: "+e.message;}
  }
  if(!ownsView(id,gen)){
   saveStatus(d,"Edits saved. Review pending edits, then save to render this job."+allowError);return false;
  }
  if(hasReviewEdits(d)){
   saveStatus(d,"Submitted edits saved. Newer edits are still pending — save again to include them before rendering."+allowError);return false;
  }
  saveStatus(d,"Edits saved; requesting render…");
  await reviewPost(`api/jobs/${id}/render`);
  // Edits can also arrive while the render request is pending.
  if(hasReviewEdits(d)){
   saveStatus(d,"Render started with submitted edits. Newer edits are pending — save again to render them."+allowError);return true;
  }
  saveStatus(d,"Rendering with saved edits…"+allowError);
  if(ownsView(id,gen)&&REVIEW_SCHED===reviewOwner){
   disposeReview();const rv=document.getElementById("review");if(rv){beUnmountIn(rv);rv.remove();}
   const c=document.getElementById("beslot_done");if(c){beUnmountIn(c);c.innerHTML="rendering with your edits…";}
  }
  return true;
 }catch(e){
  // A failed response leaves the audio baseline uncertain. Retain even a
  // newer toggle-back to the old baseline and deliberately send it on retry.
  if(!saved&&payload.audio!==undefined)b.audioSaved=null;
  saveStatus(d,(saved?"Edits saved; render was not confirmed. Retry with Save to render. ":
   "Save was not confirmed; drafts retained. Retry with Save. ")+e.message);
  return false;
 }finally{d.audioInFlight=false;d.busy=false;saveStatus(d,d.status);if(d!==EDITS)trimReviewDraft(d);}
}
function persistFailure(error){
 const nt=document.getElementById("persistnote"),message=String(error.message||error);
 nt.style.display="block";nt.style.color="#f87171";
 nt.textContent=message.includes("HTTP 423")?
  "Allow-list unavailable: the vault is locked or needs recovery. Unlock and retry.":
  "Allow-list request failed: "+message;
}
async function loadPersist(){
 try{
  const response=await fetch("api/allowlist");
  if(!response.ok)throw Error("Request failed (HTTP "+response.status+")");
  const a=await response.json();
  if(!a||!Array.isArray(a.words))throw Error("Invalid allow-list response");
  const el=document.getElementById("persistlist"),
        nt=document.getElementById("persistnote");
  const html=a.words.map(x=>
   `<div class="pw">${x}<span title="remove from allow-list"
     onclick="rmPersist('${x.replace(/'/g,"")}')">✕</span></div>`).join("");
  el.innerHTML=html;nt.style.color="";
  if(a.words.length){
   nt.style.display="block";
   nt.textContent="Green words load automatically from "+a.path+
    " — marked safe during previous reviews. They are always applied in "+
    "addition to anything typed above. Click ✕ to remove one.";
  }else nt.style.display="none";
  document.getElementById("clearpersist").style.display=
   a.words.length?"inline-block":"none";
  return true;
 }catch(error){persistFailure(error);return false;}
}
async function clearPersist(){
 if(!confirm("Remove ALL learned safe words? Future scans will flag them again until re-reviewed."))return;
 try{
  await reviewPost("api/allowlist",{clear:true});
  return await loadPersist();
 }catch(error){persistFailure(error);return false;}
}
async function rmPersist(word){
 try{
  await reviewPost("api/allowlist",{remove:[word]});
  return await loadPersist();
 }catch(error){persistFailure(error);return false;}
}
async function loadCertInfo(){
 try{
  const c=await (await fetch("api/certinfo")).json();
  document.getElementById("certinfo").textContent=
   `Current: ${c.mode} certificate — ${c.subject}, expires ${c.expires}`;
 }catch(e){
  document.getElementById("certinfo").textContent=
   "Running over plain HTTP (started with --http).";
 }
}
async function uploadCerts(){
 const cf=document.getElementById("certfile").files[0],
       kf=document.getElementById("keyfile").files[0];
 if(!cf||!kf){alert("Choose both a certificate file and a key file.");return;}
 const fd=new FormData();fd.append("cert",cf);fd.append("key",kf);
 const r=await fetch("api/certs",{method:"POST",body:fd});
 alert(r.ok?(await r.json()).note:"Upload failed: "+await r.text());
 loadCertInfo();
}
async function removeCerts(){
 if(!confirm("Remove the custom certificate and return to self-signed on next restart?"))return;
 const r=await fetch("api/certs",{method:"DELETE"});
 alert((await r.json()).note);
 loadCertInfo();
}
async function updCheck(){
 try{
  const d=await (await fetch("/api/update_check")).json();
  if(!d.available)return;
  const el=document.getElementById("upd");
  if(d.can_update===false){
   // Docker/Podman: the in-place updater would write into the ephemeral
   // container and be lost on recreate — inform only, never offer.
   el.innerHTML='· <span style="color:#fbbf24" title="Pull the new image tag and recreate the container — job data lives in the mounted volume and is preserved.">v'
    +d.latest+' available — pull the new image to update</span> ';
  }else{
   el.innerHTML='· <a href="#" style="color:#fbbf24" onclick="updRun();return false">v'
    +d.latest+' available — update</a> ';
  }
 }catch(e){}
}
async function updRun(){
 if(!confirm("Update OpenScrub to the newest release now?\n\nJobs must be idle, and the server needs a restart afterwards to run the new version."))return;
 const r=await fetch("/api/update_run",{method:"POST"});
 if(!r.ok){alert(await r.text());return;}
 const el=document.getElementById("upd");
 el.textContent="· updating… ";
 const t=setInterval(async()=>{
  const s=await (await fetch("/api/update_status")).json();
  if(!s.running&&s.ok!==null){
   clearInterval(t);
   el.textContent=s.ok?"· updated — restart the server to finish ":"· update failed ";
   alert((s.ok?"Update installed.\nRestart the OpenScrub server to run the new version.":"Update failed:")+"\n\n"+s.log.slice(-8).join("\n"));
  }
 },2000);
}
async function vaultStatus(){
 try{
  const d=await (await fetch("/api/vault")).json();
  const st=document.getElementById("vstat");
  document.getElementById("vsetup").style.display=d.enabled?"none":"block";
  document.getElementById("vunlock").style.display=(d.enabled&&d.locked)?"flex":"none";
  document.getElementById("vlock").style.display=(d.enabled&&!d.locked)?"flex":"none";
  if(!d.enabled){st.textContent="Disabled — job files (PII) are stored in plaintext. Set a password to enable at-rest encryption.";st.style.color="#fbbf24";}
  else if(d.locked){st.textContent="LOCKED — "+d.encrypted_files+" file(s) encrypted on disk. Unlock to work with jobs.";st.style.color="#f87171";}
  else{st.textContent="Unlocked — files decrypt while you work; they re-encrypt when you lock or shut down. Losing the password makes encrypted files unrecoverable.";st.style.color="#4ade80";}
  if(d.enabled&&!d.locked){
   document.getElementById("valk").checked=d.autolock_min>0;
   if(d.autolock_min>0)document.getElementById("valkmin").value=d.autolock_min;
  }
 }catch(e){}
}
async function vaultSetup(){
 const a=document.getElementById("vpw1").value,b=document.getElementById("vpw2").value;
 if(a.length<8){alert("Password must be at least 8 characters.");return;}
 if(a!==b){alert("Passwords do not match.");return;}
 if(!confirm("Enable at-rest encryption?\n\nTHERE IS NO PASSWORD RESET. If you lose this password, every encrypted job file is PERMANENTLY UNRECOVERABLE.\n\nContinue?"))return;
 const r=await fetch("/api/vault/setup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:a})});
 alert(r.ok?(await r.json()).note:await r.text());
 vaultStatus();
}
async function vaultUnlock(){
 const r=await fetch("/api/vault/unlock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:document.getElementById("vpw").value})});
 if(!r.ok){alert(await r.text());return;}
 document.getElementById("vpw").value="";
 vaultStatus();loadJobs();
}
async function vaultAutolockSave(){
 const on=document.getElementById("valk").checked;
 const m=on?parseInt(document.getElementById("valkmin").value||"30",10):0;
 await fetch("/api/vault/autolock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({minutes:m})});
 vaultStatus();
}
async function vaultDoLock(){
 if(!confirm("Encrypt all job files now?\n\nYou will need the password to access them again."))return;
 const r=await fetch("/api/vault/lock",{method:"POST"});
 alert(r.ok?("Locked — "+(await r.json()).encrypted+" file(s) encrypted."):await r.text());
 vaultStatus();loadJobs();
}
let EXTPOLL=null;
async function extrasStatus(){
 try{
  const d=await (await fetch("/api/extras")).json();
  const el=document.getElementById("extras");
  if(d.frozen){el.innerHTML='This standalone install has no pip, so optional engines cannot be added here. Use the pip install of OpenScrub (<code>pip install "OpenScrub[ner]"</code>) if you need spaCy NER or PaddleOCR.';return;}
  el.innerHTML=d.items.map(i=>{
   let right;
   if(i.installed)right='<span style="color:#4ade80">installed</span>';
   else if(d.state==="installing"&&d.target===i.id)right='<span style="color:#fbbf24">installing… '+(d.log.length?d.log[d.log.length-1]:'')+'</span>';
   else right=`<button onclick="extraInstall('${i.id}')">Install</button>`;
   return '<div class="row" style="justify-content:space-between;gap:10px;padding:5px 0"><span><b>'+i.label+'</b><br><span style="color:#94a3b8;font-size:12px">'+i.desc+'</span></span>'+right+'</div>';
  }).join("");
  if(d.state==="installing"){if(!EXTPOLL)EXTPOLL=setInterval(extrasStatus,3000);}
  else if(EXTPOLL){clearInterval(EXTPOLL);EXTPOLL=null;
   if(d.state==="error")alert("Engine install failed:\n"+d.log.join("\n"));}
 }catch(e){}
}
async function extraInstall(id){
 const r=await fetch("/api/extras/"+id+"/install",{method:"POST"});
 if(!r.ok){alert(await r.text());return;}
 extrasStatus();
}
loadPersist();loadCertInfo();loadJobs();setInterval(loadJobs,5000);
function showView(){
 const s=location.hash==="#settings";
 document.getElementById("mainview").style.display=s?"none":"block";
 document.getElementById("settingsview").style.display=s?"block":"none";
 if(s)window.scrollTo(0,0);
}
window.addEventListener("hashchange",showView);
updCheck();vaultStatus();extrasStatus();showView();
