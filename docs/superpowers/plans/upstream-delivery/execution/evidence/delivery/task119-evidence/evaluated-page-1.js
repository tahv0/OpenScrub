
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
let CUR=null, EN={}, MAN=[], DUR=0, POLL=null, PHIST=[], PHPH="", LOGN=0, SHELLPH=null, JOBSJSON="";

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
 if(CUR===id){CUR=null;if(POLL)clearInterval(POLL);detail.innerHTML="";}
 JOBSJSON="";loadJobs();
}
async function openJob(id){
 CUR=id; EN={}; MAN=[]; PHIST=[]; PHPH=""; LOGN=0; SHELLPH=null;
 detail.innerHTML="";
 if(POLL)clearInterval(POLL);
 POLL=setInterval(refresh,900); refresh();
}

function shellHtml(j){
 return `<div class="card" id="jobcard"><h2>${jobNameHtml(j.name)}
  <span class="badge" id="ph"></span><small id="eta"></small></h2>
 <progress id="prog" value="0" max="1"></progress>
 <div class="row" id="actions" style="margin-top:8px"></div>
 <div style="margin-top:8px;text-align:center"><img id="pimg"
   style="max-width:100%;border-radius:8px;display:none;margin:0 auto"></div>
 <div id="pcap" style="font-size:12px;color:#94a3b8"></div>
 <div id="log" style="margin-top:8px"></div>
 <div class="warn" id="warnbox" style="display:none;margin-top:8px"></div>
 </div>`;
}

async function refresh(){
 if(!CUR)return;
 const j=await (await fetch("api/jobs/"+CUR)).json();
 if(SHELLPH===null){
  detail.insertAdjacentHTML("afterbegin",shellHtml(j));SHELLPH="";
  const im=document.getElementById("pimg");
  im.onload=()=>{im.style.display="block";};   // show only once a real frame arrives
  im.onerror=()=>{im.style.display="none";};   // 404 before first preview: stay hidden
 }

 // progress + ETA (updated in place — nothing is rebuilt).
 // The server sends a smoothed per-stage estimate (j.eta, seconds) built
 // from the stage's average processing rate — prefer it. The old
 // client-side extrapolation from bar movement stays only as a fallback
 // (rehydrated jobs mid-phase), with its history reset on phase change so
 // it never extrapolates a scan-speed rate across the render phase.
 if(PHPH!==j.phase){PHIST=[];PHPH=j.phase;}
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

 // incremental log append with stick-to-bottom (respects manual scroll-up)
 const lg=document.getElementById("log");
 const stick=lg.scrollTop+lg.clientHeight>=lg.scrollHeight-40;
 const nl=await (await fetch(`api/jobs/${CUR}/log?from=${LOGN}`)).json();
 if(LOGN===0&&nl.len>400){LOGN=nl.len-400;nl.lines=nl.lines.slice(-400);}
 if(nl.lines.length){
  const NL=String.fromCharCode(10);
  lg.textContent+=(lg.textContent?NL:"")+nl.lines.join(NL);
  LOGN=nl.len;
  if(stick)lg.scrollTop=lg.scrollHeight;
 }

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
   loadReview();
  }
  if(j.phase=="done"&&j.has_output)
   a=`<a href="api/jobs/${CUR}/download"><button>Download redacted video</button></a>
    <a href="api/jobs/${CUR}/report"><button class="sec">Download audit report</button></a>
    <button class="sec" onclick="loadReview()">Re-open review</button>
    <button class="sec" onclick="loadCompare()">Compare before/after</button>
    <button class="sec" onclick="loadBoxEdit()">Preview &amp; edit blur boxes</button>
    <div class="warn" style="width:100%">Reminder: scrub the result before
    sharing. This tool is best-effort, not a compliance guarantee.</div>
    <div id="compare" style="width:100%"></div>
    <div id="beslot_done" style="width:100%"></div>`;
  document.getElementById("actions").innerHTML=a;
  if(j.phase!="scanning")img.style.display="none";
 }
 loadJobs();
}

let BE={t:0,ox:0,oy:0,boxes:[],sel:-1,ov:{},dis:{},times:{},adds:[],
        add:false,addAnchor:null,drag:null,scale:1,dur:10};
async function loadBoxEdit(fromReview){
 showPanel(fromReview?"boxedit_rev":"boxedit");
 const mi=await (await fetch(`api/jobs/${CUR}/mediainfo`)).json();
 // in review: the slot right under the Preview button; on done: the actions slot
 let c=document.getElementById("beslot")||document.getElementById("beslot_done");
 if(!c){c=document.createElement("div");c.id="beslot";c.style.width="100%";
  (document.getElementById("review")||document.getElementById("jobcard")||detail)
   .appendChild(c);}
 BE={t:0,ox:0,oy:0,boxes:[],sel:-1,ov:{},dis:{},times:{},adds:[],
     add:false,addAnchor:null,drag:null,scale:1,dur:mi.duration,
     win:[0,mi.duration],trk:false,muteArm:false,tlDrag:null,
     tlspans:[],audio:[],audioSel:-1};
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
   <button onclick="beSave()">Save changes &amp; re-render</button></div>
  <p style="font-size:12px;color:#94a3b8;margin:4px 0 0">&#9654; plays the
   video with the boxes moving live (pause to edit). Click a red box to
   select — drag inside to move, a corner to resize, edit its from/to times,
   or remove its blur. &#65291; Add box: drag a static region. &#8857; Track object:
   drag the timeline handles to the part of the video you care about, scrub
   to a frame where the object is clear, draw a box around it — it will be
   followed and blurred through the window. &#128263; Audio span: drag on the
   timeline's bottom lane to silence (or bleep) that stretch of sound.</p>`;
 const img=document.getElementById("beImg");
 img.onload=()=>{if(BE.playing)return;const cv=document.getElementById("beCv");
  cv.width=img.clientWidth;cv.height=img.clientHeight;
  BE.scale=img.clientWidth/(img.naturalWidth||1);beDraw();};
 const bv=document.getElementById("beVid");
 bv.addEventListener("pause",()=>{if(BE.playing)bePlayStop();});
 bv.addEventListener("ended",()=>{if(BE.playing)bePlayStop();});
 beHook();tlHook();await tlInit();beScrub();
}

// ---- playback with live boxes (issue #17: review was scrub-only) ----
async function beTogglePlay(){
 const v=document.getElementById("beVid"),img=document.getElementById("beImg");
 if(!v)return;
 if(BE.playing){v.pause();return;}          // the pause handler cleans up
 if(!v.src)v.src=`api/jobs/${CUR}/video`;
 BE.playing=true;
 v.style.display="block";img.style.display="none";
 // boxes are view-only while playing: freeze pointer edits so a moving
 // box can't be grabbed mid-flight
 const cv=document.getElementById("beCv");cv.style.pointerEvents="none";
 document.getElementById("bePlay").innerHTML="&#10074;&#10074;";
 try{
  if(v.readyState<1)await new Promise((res,rej)=>{
   v.onloadedmetadata=res;
   v.onerror=()=>rej(new Error("the browser cannot decode this file"));});
  v.currentTime=BE.t||0;
  await v.play();
 }catch(e){
  bePlayStop();
  alert("Could not play the video in this browser ("+(e&&e.message||e)
   +") — the scrub slider still works frame by frame.");
  return;
 }
 if(v.clientWidth){cv.width=v.clientWidth;cv.height=v.clientHeight;
  BE.scale=v.clientWidth/(v.videoWidth||1);}
 // boxes come from the server per timestamp; refresh them on a throttle
 // while rAF keeps the playhead, label and box painting per-frame smooth
 let lastQ=0,inFlight=false;
 const step=()=>{
  if(!BE.playing)return;
  BE.t=v.currentTime;
  document.getElementById("beT").value=BE.t;
  document.getElementById("beL").textContent=BE.t.toFixed(1)+"s";
  const now=performance.now();
  if(!inFlight&&now-lastQ>150){
   inFlight=true;lastQ=now;
   fetch(`api/jobs/${CUR}/boxes_at?t=${BE.t.toFixed(2)}&all=1`)
    .then(r=>r.json())
    .then(d=>{BE.ox=d.ox;BE.oy=d.oy;BE.raw=d.boxes;beFilter();})
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
 const b=document.getElementById("bePlay");if(b)b.innerHTML="&#9654;";
 const cv=document.getElementById("beCv");if(cv)cv.style.pointerEvents="auto";
 beScrub();   // crisp frame + authoritative boxes at the pause point
}

const TLC={name:"#3b82f6",dob:"#22c55e",phone:"#f59e0b",ssn:"#ef4444",
 mrn:"#8b5cf6",email:"#14b8a6",address:"#f97316",card:"#db2777",
 apikey:"#0891b2",ipaddr:"#65a30d",plate:"#7c3aed",face:"#ec4899",
 person:"#0ea5e9",manual:"#eab308"};
async function tlInit(){
 // one fetch of the full report: detection spans for the lanes (dense
 // tracks collapse to one span per track) + stored audio redactions
 try{
  const doc=await (await fetch(`api/jobs/${CUR}/report`)).json();
  const per={};
  for(const d of (doc.detections||[])){
   if(d.enabled===false)continue;
   const key=d.category+((d.track??-1)>=0?(":t"+d.track):(":i"+Math.random()));
   const s=per[key]||(per[key]={cat:d.category,t0:d.t_start,t1:d.t_end});
   s.t0=Math.min(s.t0,d.t_start);s.t1=Math.max(s.t1,d.t_end);
  }
  BE.tlspans=Object.values(per);
  BE.audio=(doc.audio_redactions||[]).map(s=>({t0:s.t0,t1:s.t1,mode:s.mode||"mute"}));
  BE.audioSugg=doc.audio_suggestions||[];
  BE.audioTx=doc.audio_transcript||[];BE.txAnchor=-1;
  renderAudioSugg();renderTranscript();
 }catch(e){BE.tlspans=[];}
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
 const d=await (await fetch(`api/jobs/${CUR}/boxes_at?t=${BE.t}&all=1`)).json();
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
 const x=cv.getContext("2d"),s=BE.scale;
 x.clearRect(0,0,cv.width,cv.height);
 for(const a of BE.adds){
  if(BE.t<a.t0-0.01||BE.t>a.t1+0.01)continue;
  const[a1,b1,a2,b2]=a.box.map(v=>v*s);
  x.fillStyle="rgba(245,158,11,.25)";x.strokeStyle="#f59e0b";x.lineWidth=2;
  x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);
 }
 if(BE.add&&BE.addAnchor&&BE.addFloat){
  const[p,q]=[BE.addAnchor,BE.addFloat];
  x.strokeStyle="#f59e0b";x.setLineDash([6,4]);x.lineWidth=2;
  x.strokeRect(Math.min(p[0],q[0])*s,Math.min(p[1],q[1])*s,
   Math.abs(q[0]-p[0])*s,Math.abs(q[1]-p[1])*s);x.setLineDash([]);
 }
 for(const b of BE.boxes){
  const[a1,b1,a2,b2]=b.box.map(v=>v*s);
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
function beHook(){
 const cv=document.getElementById("beCv");
 const pt=e=>{const r=cv.getBoundingClientRect();
  return[(e.clientX-r.left)/BE.scale,(e.clientY-r.top)/BE.scale];};
 cv.addEventListener("pointerdown",e=>{
  const p=pt(e);cv.setPointerCapture(e.pointerId);
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
     BE.adds.push({box,t0:Math.max(0,+fr||0),
                   t1:Math.min(BE.dur,+to||t1),tref:BE.t});
    }
    beDraw();
   }
   return;
  }
  const sel=BE.boxes.find(b=>b.i===BE.sel);
  if(sel){const[a1,b1,a2,b2]=sel.box,hs=9/BE.scale;
   const corners=[[a1,b1,0],[a2,b1,1],[a1,b2,2],[a2,b2,3]];
   for(const[hx,hy,ci] of corners)
    if(Math.abs(p[0]-hx)<hs&&Math.abs(p[1]-hy)<hs){
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
  if(BE.add&&BE.addAnchor){BE.addFloat=pt(e);beDraw();return;}
  if(!BE.drag||BE.sel<0)return;
  const p=pt(e),b=BE.boxes.find(x=>x.i===BE.sel);if(!b)return;
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
 cv.addEventListener("pointerup",()=>{BE.drag=null;});
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
async function beSave(){
 await saveAndRender();
 const c=document.querySelector("#beslot");
 if(c)c.innerHTML="rendering with your edits…";
}
async function cancelJob(){await fetch("api/jobs/"+CUR+"/cancel",{method:"POST"})}

// the three post-render views (compare, review, box editor) are mutually
// exclusive: opening one closes the others instead of stacking them
function showPanel(which){
 // a playing box-editor video must be PAUSED before its DOM is wiped —
 // an element removed via innerHTML can keep its audio running
 try{const v=document.getElementById("beVid");
  if(v&&!v.paused){BE.playing=false;v.pause();}}catch(e){}
 // "boxedit_rev" = the editor button INSIDE the review card: the editor
 // mounts in the review's own slot, so the review stays. Everything else
 // is standalone and closes the other panels.
 if(which!=="compare"){
  const c=document.getElementById("compare");if(c)c.innerHTML="";}
 const b=document.getElementById("beslot_done");
 const b2=document.getElementById("beslot");
 if(which==="boxedit_rev"){if(b)b.innerHTML=""}
 else{
  if(which!=="boxedit"){if(b)b.innerHTML=""}
  if(b2)b2.innerHTML="";
  if(which!=="review"){
   const rev=document.getElementById("review");if(rev)rev.remove();}
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

async function loadReview(){
 showPanel("review");
 const d=await (await fetch(`api/jobs/${CUR}/detections`)).json();
 DUR=d.duration;
 const groups={}; const zdrop=[]; TRKMEM={};
 d.detections.forEach(x=>{
  EN[x.i]=x.enabled;
  if(x.zone_dropped){zdrop.push(x);return;}
  (groups[x.category]=groups[x.category]||[]).push(x);});
 let html=`<div class="card" id="review"><h2>Review — red = will be blurred,
 green = kept visible. Drag a box around several to bulk-set.</h2>
 <div class="row" style="margin:0 0 8px">
  <button class="sec" onclick="loadBoxEdit(1)">▶ Preview video &amp; edit boxes
  (before rendering)</button></div>
 <div id="beslot"></div>
 <div id="detwrap" style="position:relative;user-select:none">`;
 if(zdrop.length){
  html+=`<details style="margin:4px 0 10px;border:1px dashed #f59e0b;border-radius:9px;padding:8px 10px;background:#26200a">
   <summary style="cursor:pointer;color:#fbbf24;font-weight:600">
    ⚠ ${zdrop.length} detection(s) outside your zones — NOT blurred
    (mostly logos/labels by design; open only if something real was zoned out)
   </summary>
   <div class="row" style="margin:8px 0 4px">
    <button class="sec" onclick="setAllZd(true)">blur all of these</button>
    <button class="sec" onclick="setAllZd(false)">keep all</button></div>
   <div class="grid3">`;
  for(const x of zdrop){
   html+=`<div class="det ${EN[x.i]?'':'off'}" id="det${x.i}" data-cat="zdrop">
    <img src="api/jobs/${CUR}/thumb/${x.i}" loading="lazy"
     style="cursor:zoom-in" onclick="zoomDet(${x.i})" onerror="thumbRetry(this)">
    <div>"${x.text}" <br>${x.t_start.toFixed(1)}–${x.t_end.toFixed(1)}s</div>
    <button class="blurbtn ${EN[x.i]?"blur":"keep"}" id="bb${x.i}"
     onclick="toggleDet(${x.i})">${EN[x.i]?"Blur":"Keep"}</button>
   </div>`;
  }
  html+=`</div></details>`;
 }
 for(const[cat,rawItems] of Object.entries(groups)){
  // collapse dense tracks: one card per physical object, not per frame
  const byGroup={},items=[];
  for(const x of rawItems){
   // identity first: one card per PERSON (all their tracks); then per
   // track; ungrouped detections stand alone
   const key=x.person>=0?("p"+x.person):(x.track>=0?("t"+x.track):null);
   if(key){(byGroup[key]=byGroup[key]||[]).push(x);}
   else{TRKMEM[x.i]=[x.i];items.push(x);}
  }
  for(const [key,members] of Object.entries(byGroup)){
   members.sort((a,b)=>a.t_start-b.t_start);
   let best=members[0];             // clearest thumbnail = highest-confidence
   for(const m of members)if((m.confidence||0)>(best.confidence||0))best=m;
   const rep={...best};
   rep.t_start=members[0].t_start;
   rep.t_end=members[members.length-1].t_end;
   rep.frames=members.length;
   rep.personcard=key[0]==="p";
   TRKMEM[rep.i]=members.map(m=>m.i);
   items.push(rep);
  }
  // person cards first, then everything else chronologically
  items.sort((a,b)=>((b.personcard?1:0)-(a.personcard?1:0))||a.t_start-b.t_start);
  html+=`<h3 style="margin:10px 0 6px">${CATDN[cat]||cat} <span class="badge">${items.length}</span>
  <button class="sec" style="padding:3px 8px;font-size:12px"
   onclick="setAll('${cat}',true)">all on</button>
  <button class="sec" style="padding:3px 8px;font-size:12px"
   onclick="setAll('${cat}',false)">all off</button></h3><div class="grid3">`;
  for(const x of items){
   html+=`<div class="det ${EN[x.i]?'':'off'}" id="det${x.i}" data-cat="${cat}">
    <img src="api/jobs/${CUR}/thumb/${x.i}"
     style="cursor:zoom-in" onclick="zoomDet(${x.i})"
     onerror="thumbRetry(this)">
    <div>${x.personcard?`<b>Person ${x.person+1}</b> — one decision for ALL their appearances`:`"${x.text}"`}${x.frames?` <span class="badge">×${x.frames} frames</span>`:""}${x.confidence?` <span class="badge" title="detector confidence — low values on a non-face thumbnail usually mean a false detection">${Math.round(x.confidence*100)}%</span>`:""} <br>${x.t_start.toFixed(1)}–${x.t_end.toFixed(1)}s</div>
    <button class="blurbtn ${EN[x.i]?"blur":"keep"}" id="bb${x.i}"
     onclick="toggleDet(${x.i})">${EN[x.i]?"Blur":"Keep"}</button>
   </div>`}
  html+=`</div>`}
 html+=`</div>
 <div class="row" style="margin-top:12px">
 <button onclick="saveAndRender()">Save edits &amp; render</button>
 <span style="font-size:12px;color:#94a3b8">missed something? use
  ▶ Preview video &amp; edit boxes above — its ＋ Add box replaces the old
  add-region tool</span></div></div>`;
 const old=document.getElementById("review"); if(old)old.remove();
 detail.insertAdjacentHTML("beforeend",html);
 initMarquee();
}

let TRKMEM={};
function applyDet(i,blur){
 for(const m of (TRKMEM[i]||[i]))EN[m]=blur;
 const b=document.getElementById("bb"+i),t=document.getElementById("det"+i);
 if(b){b.className="blurbtn "+(blur?"blur":"keep");
       b.textContent=blur?"Blur":"Keep";}
 if(t)t.classList.toggle("off",!blur);
 if(document.getElementById("beCv")){beFilter();beDraw();}   // live sync
}
function toggleDet(i){applyDet(i,!EN[i]);}
function setAll(cat,on){document.querySelectorAll(`.det[data-cat=${cat}]`)
 .forEach(el=>applyDet(+el.id.slice(3),on));}
function thumbRetry(img){
 const n=+(img.dataset.r||0);
 if(n>=3)return;
 img.dataset.r=n+1;
 setTimeout(()=>{img.src=img.src.split("?r=")[0]+"?r="+Date.now();},
            600*(n+1));
}
function setAllZd(on){document.querySelectorAll(`.det[data-cat=zdrop]`)
 .forEach(el=>applyDet(+el.id.slice(3),on));}

let selSet=new Set(),marqEl=null,menuEl=null,mStart=null;
function clearSel(){
 selSet.forEach(i=>{const t=document.getElementById("det"+i);
  if(t)t.classList.remove("selected");});
 selSet.clear();
 if(menuEl){menuEl.remove();menuEl=null;}
}
function initMarquee(){
 const wrap=document.getElementById("detwrap");
 if(!wrap||wrap.dataset.mq)return;
 wrap.dataset.mq=1;
 wrap.addEventListener("pointerdown",e=>{
  if(e.pointerType==="touch")return;         // touch keeps normal scrolling
  if(e.target.closest("button"))return;      // button clicks stay clicks
  clearSel();
  mStart=[e.pageX,e.pageY];
  marqEl=document.createElement("div");marqEl.className="marq";
  document.body.appendChild(marqEl);
  const move=ev=>{
   const x1=Math.min(mStart[0],ev.pageX),y1=Math.min(mStart[1],ev.pageY),
         x2=Math.max(mStart[0],ev.pageX),y2=Math.max(mStart[1],ev.pageY);
   Object.assign(marqEl.style,{left:x1+"px",top:y1+"px",
    width:(x2-x1)+"px",height:(y2-y1)+"px"});
  };
  const up=ev=>{
   document.removeEventListener("pointermove",move);
   document.removeEventListener("pointerup",up);
   const r=marqEl.getBoundingClientRect();
   marqEl.remove();marqEl=null;
   if(r.width<8&&r.height<8)return;          // just a click — not a drag
   document.querySelectorAll("#detwrap .det").forEach(t=>{
    const b=t.getBoundingClientRect();
    if(b.left<r.right&&b.right>r.left&&b.top<r.bottom&&b.bottom>r.top){
     selSet.add(+t.id.slice(3));t.classList.add("selected");}});
   if(selSet.size)showSelMenu(ev.pageX,ev.pageY);
  };
  document.addEventListener("pointermove",move);
  document.addEventListener("pointerup",up);
  e.preventDefault();
 });
}
function showSelMenu(x,y){
 menuEl=document.createElement("div");menuEl.className="selmenu";
 menuEl.innerHTML=`<span>${selSet.size} selected</span>
  <button class="mkeep" onclick="bulkSet(false)">Keep</button>
  <button class="mblur" onclick="bulkSet(true)">Blur</button>`;
 Object.assign(menuEl.style,{left:x+"px",top:(y+10)+"px"});
 document.body.appendChild(menuEl);
}
function bulkSet(blur){selSet.forEach(i=>applyDet(i,blur));clearSel();}
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

async function saveAndRender(){
 const manual=[...MAN,...BE.adds.map(a=>({t_start:a.t0,t_end:a.t1,
  t_ref:a.tref,screen_box:a.box}))];
 const payload={enabled:EN,manual,box_overrides:BE.ov,
   time_overrides:BE.times};
 // only send audio spans when the box editor actually loaded them —
 // otherwise a save from plain review would wipe stored spans with []
 if(Array.isArray(BE.audio)&&BE.tlspans!==undefined)payload.audio=BE.audio;
 const r=await (await fetch(`api/jobs/${CUR}/detections`,{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify(payload)})).json();
 BE.adds=[];BE.ov={};BE.times={};
 if(r.suggest_allowlist&&r.suggest_allowlist.length){
  if(confirm("You disabled every instance of: "+r.suggest_allowlist.join(", ")+". Add these to the permanent allow-list so future scans skip them?"))
   {await fetch("api/allowlist",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({words:r.suggest_allowlist})});
    loadPersist();}}
 MAN=[];
 await fetch(`api/jobs/${CUR}/render`,{method:"POST"});
 const rv=document.getElementById("review"); if(rv)rv.remove();
}
async function loadPersist(){
 const a=await (await fetch("api/allowlist")).json();
 const el=document.getElementById("persistlist"),
       nt=document.getElementById("persistnote");
 el.innerHTML=(a.words||[]).map(x=>
  `<div class="pw">${x}<span title="remove from allow-list"
    onclick="rmPersist('${x.replace(/'/g,"")}')">✕</span></div>`).join("");
 if((a.words||[]).length){
  nt.style.display="block";
  nt.textContent="Green words load automatically from "+a.path+
   " — marked safe during previous reviews. They are always applied in "+
   "addition to anything typed above. Click ✕ to remove one.";
 }else nt.style.display="none";
 document.getElementById("clearpersist").style.display=
  (a.words||[]).length?"inline-block":"none";
}
async function clearPersist(){
 if(!confirm("Remove ALL learned safe words? Future scans will flag them again until re-reviewed."))return;
 await fetch("api/allowlist",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({clear:true})});
 loadPersist();
}
async function rmPersist(word){
 await fetch("api/allowlist",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({remove:[word]})});
 loadPersist();
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

