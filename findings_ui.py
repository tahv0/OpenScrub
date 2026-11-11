"""Compact confirmed-example library UI, embedded by openscrub_web.

Only saved JPEGs are used here. Selection is explicit and retained across pages;
no video or report is fetched to browse, edit, forget, or train examples.
"""

CSS = r"""
#findingsview{max-width:1100px;margin:auto;padding:0 16px 32px;color:var(--text)}
#findingsview .card{margin:16px 0;padding:18px;min-width:0}
.findings-copy{font-size:13px;color:var(--mut);line-height:1.5;overflow-wrap:anywhere}
.findings-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.findings-fields{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.findings-fields label{display:flex;flex:1 1 150px;min-width:0;flex-direction:column;gap:6px;font-size:13px}
#findingsview select,#findingsview input:not([type=checkbox]){max-width:100%;box-sizing:border-box;min-width:0;width:100%;padding:9px;background:var(--bg);color:var(--text);border:1px solid #475569;border-radius:7px}
#findingsview button,.pending-findings button{min-height:36px}
#findingsview input[type=checkbox]{width:18px;height:18px;flex:0 0 auto;accent-color:#2563eb}
.findings-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin:14px 0}
.finding-card{border:1px solid #334155;border-radius:9px;min-width:0;overflow:hidden;background:var(--bg)}
.finding-card img{display:block;width:100%;height:118px;object-fit:contain;background:#0b1220}
.finding-body{padding:10px;font-size:13px;overflow-wrap:anywhere}
.finding-body strong{display:block;margin-bottom:5px}.finding-label{display:block;color:#bfdbfe;margin:7px 0;font-weight:600}
.finding-body label{display:flex;align-items:center;gap:8px;margin:9px 0}
.findings-note{font-size:13px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;margin:10px 0}
.findings-error{color:#fca5a5}.finding-editor-picture{position:relative;width:100%;max-width:640px;margin:12px 0;background:#0b1220}
.finding-editor-picture img{display:block;width:100%;height:auto}.finding-editor-picture svg{position:absolute;inset:0;width:100%;height:100%;touch-action:none}
.finding-editor-picture circle{fill:#2563eb;stroke:white;stroke-width:2;vector-effect:non-scaling-stroke;cursor:grab}
.finding-editor-picture polygon{fill:#2563eb22;stroke:#60a5fa;stroke-width:2;vector-effect:non-scaling-stroke;pointer-events:none}
.finding-corners{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;max-width:640px}
.finding-corners label{display:flex;align-items:center;gap:6px;font-size:12px;min-width:0}.finding-corners input{width:70px!important}
.findings-license{display:flex;align-items:flex-start;gap:9px;font-size:13px;line-height:1.5;margin:14px 0}
.pending-findings{margin:16px 0;padding:16px}.pending-findings .findings-grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr));max-height:400px;overflow:auto}.pending-findings img{height:88px}
@media(max-width:500px){#findingsview{padding:0 10px 20px}#findingsview .card{padding:13px}.findings-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.finding-card img{height:95px}.finding-body{padding:8px;font-size:12px}.finding-corners{grid-template-columns:1fr}.findings-row>*{max-width:100%}}
"""

HTML = r"""
<section id="findingsview" style="display:none" aria-labelledby="findingsTitle">
 <h2 id="findingsTitle">Confirmed findings</h2>
 <p class="findings-copy">Your explicit confirmations, kept with their source video. Browse and adjust small saved pictures without reopening videos. Ordinary Blur/Keep choices do not create training examples.</p>
 <div class="card">
  <div class="findings-fields">
   <label>Video<select id="findingsVideo"><option value="">All videos</option></select></label>
   <label>Category<select id="findingsCategory"><option value="">All categories</option><option value="plate">Plate</option><option value="face">Face</option><option value="person">Person</option><option value="text">Text</option></select></label>
   <label>Confirmation<select id="findingsLabel"><option value="">Positive and negative</option><option value="positive">Positive — Is a …</option><option value="negative">Negative — Not a …</option></select></label>
  </div>
  <div class="findings-row"><button type="button" class="sec" id="findingsRefresh">Refresh findings</button><button type="button" class="sec" id="findingsSelectPage">Select plate examples on this page</button><button type="button" class="sec" id="findingsClear">Clear selection</button></div>
  <p id="findingsStatus" class="findings-note" role="status" aria-live="polite"></p>
  <div id="findingsList" class="findings-grid"></div>
  <div class="findings-row"><button type="button" class="sec" id="findingsPrevious">Previous page</button><span id="findingsPage" class="findings-copy"></span><button type="button" class="sec" id="findingsNext">Next page</button></div>
 </div>
 <div id="findingEditor" class="card" hidden></div>
 <div class="card" aria-labelledby="findingsTrainingTitle">
  <h3 id="findingsTrainingTitle">Train a named plate model</h3>
  <p class="findings-copy">Only selected confirmed plate examples are used. Select examples from another video explicitly to include them. Training creates a new version and keeps previous models. More examples do not guarantee better accuracy.</p>
  <p id="findingsSelection" class="findings-note" role="status">No plate examples selected.</p>
  <div class="findings-fields"><label>Model name (optional)<input id="findingsModelName" maxlength="80" placeholder="Automatic name from selected videos and UTC time"></label><label>Start from<select id="findingsParent"><option value="">Configured base checkpoint</option></select></label></div>
  <p id="findingsParentStatus" class="findings-copy" role="status"></p>
  <label class="findings-license"><input id="findingsLicense" type="checkbox"><span>I acknowledge that the local training environment uses Ultralytics and have reviewed its AGPL/Enterprise terms in <a href="https://github.com/ultralytics/ultralytics/blob/main/LICENSE" target="_blank" rel="noopener noreferrer">the framework license</a> and docs/PLATE_TRAINING.md.</span></label>
  <button type="button" id="findingsTrain" disabled>Train selected plate examples</button>
  <p id="findingsTrainStatus" class="findings-note" role="status" aria-live="polite"></p>
 </div>
</section>
"""

SCRIPT = r"""
// Confirmed library state is independent of the currently opened scan job.
const FINDINGS={offset:0,limit:24,total:0,items:[],selected:new Map(),request:0,editorRequest:0,editor:null,bound:false,training:false,parentRequest:0};
const FINDINGS_QUEUES=new Map();
function findingEscape(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function findingTime(value){const n=Number(value);return Number.isFinite(n)?n.toFixed(2)+' s':'Unknown time';}
function findingLabel(item){return (item.label==='positive'?'Confirmed ':'Not a ')+(item.category||'finding');}
function findingImageURL(id){return 'api/findings/'+encodeURIComponent(id)+'/image';}
function findingCard(item){
 const id=findingEscape(item.id),plate=item.category==='plate';
 return `<article class="finding-card" data-finding="${id}"><img loading="lazy" decoding="async" src="${findingEscape(findingImageURL(item.id))}" alt="Saved ${findingEscape(item.category)} finding"><div class="finding-body"><strong>${findingEscape(item.video?.name||'Video')}</strong><span>Frame ${findingEscape(item.frame)} · ${findingTime(item.time)}</span><span class="finding-label">${findingEscape(findingLabel(item))}</span>${plate?`<label><input type="checkbox" data-select-finding="${id}" ${FINDINGS.selected.has(item.id)?'checked':''}>Use for plate training</label>`:'<p class="findings-copy">Stored confirmation; plate training only.</p>'}<button type="button" class="sec" data-edit-finding="${id}">Edit confirmation</button></div></article>`;
}
function findingNotice(id,message,error=false){const node=document.getElementById(id);if(node){node.textContent=message;node.classList.toggle('findings-error',error);}}
function findingSelection(){
 const rows=[...FINDINGS.selected.values()],videos=new Set(rows.map(i=>i.video_id));
 findingNotice('findingsSelection',rows.length?`${rows.length} plate example${rows.length===1?'':'s'} selected from ${videos.size} video${videos.size===1?'':'s'}. ${rows.filter(i=>i.label==='positive').length} positive · ${rows.filter(i=>i.label==='negative').length} negative. Selection stays when changing filters or pages.`:'No plate examples selected.');
 const train=document.getElementById('findingsTrain');if(train)train.disabled=FINDINGS.training||!rows.length||!document.getElementById('findingsLicense').checked;
}
function bindConfirmedFindings(){
 if(FINDINGS.bound)return;FINDINGS.bound=true;
 for(const id of ['findingsVideo','findingsCategory','findingsLabel'])document.getElementById(id).onchange=()=>{FINDINGS.offset=0;loadConfirmedFindings();};
 document.getElementById('findingsRefresh').onclick=()=>loadConfirmedFindings();
 document.getElementById('findingsPrevious').onclick=()=>{FINDINGS.offset=Math.max(0,FINDINGS.offset-FINDINGS.limit);loadConfirmedFindings();};
 document.getElementById('findingsNext').onclick=()=>{FINDINGS.offset+=FINDINGS.limit;loadConfirmedFindings();};
 document.getElementById('findingsSelectPage').onclick=()=>{for(const item of FINDINGS.items)if(item.category==='plate')FINDINGS.selected.set(item.id,item);renderConfirmedFindings();};
 document.getElementById('findingsClear').onclick=()=>{FINDINGS.selected.clear();renderConfirmedFindings();};
 document.getElementById('findingsLicense').onchange=findingSelection;
 document.getElementById('findingsTrain').onclick=trainConfirmedFindings;
 const list=document.getElementById('findingsList');
 list.onchange=event=>{const id=event.target.dataset.selectFinding;if(!id)return;const item=FINDINGS.items.find(i=>i.id===id);if(event.target.checked&&item?.category==='plate')FINDINGS.selected.set(id,item);else FINDINGS.selected.delete(id);findingSelection();};
 list.onclick=event=>{const button=event.target.closest('[data-edit-finding]');if(button)openFindingEditor(button.dataset.editFinding);};
}
function renderConfirmedFindings(){
 document.getElementById('findingsList').innerHTML=FINDINGS.items.map(findingCard).join('');
 document.getElementById('findingsPrevious').disabled=FINDINGS.offset===0;
 document.getElementById('findingsNext').disabled=FINDINGS.offset+FINDINGS.items.length>=FINDINGS.total;
 document.getElementById('findingsSelectPage').disabled=!FINDINGS.items.some(i=>i.category==='plate');
 document.getElementById('findingsPage').textContent=FINDINGS.total?`${FINDINGS.offset+1}–${FINDINGS.offset+FINDINGS.items.length} of ${FINDINGS.total}`:'0 examples';
 findingSelection();
}
async function loadConfirmedFindings(){
 if(!document.getElementById('findingsview'))return;bindConfirmedFindings();
 const request=++FINDINGS.request,params=new URLSearchParams({offset:FINDINGS.offset,limit:FINDINGS.limit});
 for(const [field,key] of [['findingsVideo','video_id'],['findingsCategory','category'],['findingsLabel','label']]){const value=document.getElementById(field).value;if(value)params.set(key,value);}
 findingNotice('findingsStatus','Loading saved pictures…');
 // Model discovery is independent of the list and never resets its selection.
 loadFindingsParents();
 try{
  const {data}=await reviewRequest('api/findings?'+params.toString());
  if(request!==FINDINGS.request)return;
  const video=document.getElementById('findingsVideo'),selected=video.value;
  video.replaceChildren(new Option('All videos',''));
  for(const item of data.videos||[])video.add(new Option(item.name+' ('+item.count+')',item.id));
  if(selected&&!Array.from(video.options).some(o=>o.value===selected))video.add(new Option('Selected video',selected));
  video.value=selected;FINDINGS.items=data.items;FINDINGS.total=data.total;
  if(!data.items.length&&FINDINGS.offset>0&&data.total>0){FINDINGS.offset=Math.floor((data.total-1)/FINDINGS.limit)*FINDINGS.limit;return loadConfirmedFindings();}
  renderConfirmedFindings();findingNotice('findingsStatus',data.total?'Saved confirmations only. Select the examples you want to train with.':'No confirmed findings match these filters. Confirm Is a … or Not a … in a video review to save examples.');
 }catch(error){if(request===FINDINGS.request)findingNotice('findingsStatus','Could not load confirmed findings: '+error.message,true);}
}
function openFindingsForVideo(videoId){
 bindConfirmedFindings();const select=document.getElementById('findingsVideo');
 if(!Array.from(select.options).some(o=>o.value===videoId))select.add(new Option('Current video',videoId));
 select.value=videoId;FINDINGS.offset=0;
 // No examples from this or any other video are selected implicitly.
 if(location.hash==='#findings')loadConfirmedFindings();else location.hash='#findings';
}
async function loadFindingsParents(){
 const request=++FINDINGS.parentRequest;
 try{
  const {data}=await reviewRequest('api/jobs/learned-models');if(request!==FINDINGS.parentRequest)return;
  const select=document.getElementById('findingsParent'),chosen=select.value;
  select.replaceChildren(new Option('Configured base checkpoint',''));
  for(const model of data.models||[])if(model.training?.trainable===true)select.add(new Option(model.name,model.id));
  select.value=Array.from(select.options).some(o=>o.value===chosen)?chosen:'';
  findingNotice('findingsParentStatus','Only locally trainable models are listed. Imported inference-only models cannot start training.');
 }catch(error){if(request===FINDINGS.parentRequest)findingNotice('findingsParentStatus','Could not load parent models: '+error.message,true);}
}
async function trainConfirmedFindings(){
 const ids=[...FINDINGS.selected.keys()],accepted=document.getElementById('findingsLicense').checked;
 if(FINDINGS.training)return;if(!ids.length||!accepted){findingNotice('findingsTrainStatus','Select plate examples and acknowledge the training terms.',true);return;}
 const body={example_ids:ids,name:document.getElementById('findingsModelName').value.trim(),parent_model_id:document.getElementById('findingsParent').value||null,license_accepted:true};
 FINDINGS.training=true;findingSelection();findingNotice('findingsTrainStatus','Starting named training from selected plate examples…');
 try{
  const {data}=await reviewRequest('api/findings/train',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),timeoutMs:120000});
  findingNotice('findingsTrainStatus','Training queued: '+data.name+'. Follow progress in the job.');
  if(typeof refreshLearnedModels==='function')refreshLearnedModels();
  location.hash='';if(typeof openJob==='function')await openJob(data.id);
 }catch(error){findingNotice('findingsTrainStatus','Training could not start: '+error.message,true);}
 finally{FINDINGS.training=false;findingSelection();}
}
function findingSourcePoint(crop,rect,x,y){return [Math.max(crop[0],Math.min(crop[2],crop[0]+(x-rect.left)*(crop[2]-crop[0])/rect.width)),Math.max(crop[1],Math.min(crop[3],crop[1]+(y-rect.top)*(crop[3]-crop[1])/rect.height))];}
function findingConvex(points){
 let sign=0;if(points.length!==4||points.some(p=>p.length!==2||p.some(n=>!Number.isFinite(n))))return false;
 for(let i=0;i<4;i++){const a=points[i],b=points[(i+1)%4],c=points[(i+2)%4],v=(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]);if(Math.abs(v)<1e-6)return false;if(sign&&Math.sign(v)!==sign)return false;sign=Math.sign(v);}
 return true;
}
async function openFindingEditor(id){
 const request=++FINDINGS.editorRequest,panel=document.getElementById('findingEditor');
 FINDINGS.editor=null;panel.hidden=false;panel.innerHTML='<p class="findings-note" role="status">Loading saved confirmation…</p>';
 try{const {data}=await reviewRequest('api/findings/'+encodeURIComponent(id));if(request!==FINDINGS.editorRequest)return;renderFindingEditor(data.finding);}
 catch(error){if(request===FINDINGS.editorRequest){panel.replaceChildren();const note=document.createElement('p');note.className='findings-note findings-error';note.textContent='Could not open saved finding: '+error.message;panel.append(note);}}
}
function renderFindingEditor(item){
 const panel=document.getElementById('findingEditor'),box=item.box,crop=item.crop.box;
 const points=(item.points||[[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]]).map(p=>p.slice());
 const editable=item.category==='plate';
 const state={item,points,original:points.map(p=>p.slice()),busy:false,drag:null,shapeDirty:false};FINDINGS.editor=state;
 panel.hidden=false;
 panel.innerHTML=`<div class="findings-row"><h3 style="margin:0">Edit saved confirmation</h3><button type="button" class="sec" id="findingEditorClose">Close editor</button></div><p class="findings-copy">${findingEscape(item.video?.name)} · Frame ${findingEscape(item.frame)} · ${findingTime(item.time)} · revision ${findingEscape(item.revision)}</p><p class="finding-label">${findingEscape(findingLabel(item))}</p><div class="finding-editor-picture"><img id="findingEditorImage" src="${findingEscape(findingImageURL(item.id))}" alt="Saved picture for region adjustment">${editable?`<svg id="findingEditorSvg" viewBox="${crop.join(' ')}" preserveAspectRatio="none" aria-label="Four-corner region; drag a corner or use coordinate fields"><polygon></polygon>${points.map((p,i)=>`<circle data-corner="${i}" r="7"></circle>`).join('')}</svg>`:''}</div><p class="findings-copy">${editable?'Drag the blue corners or edit original source coordinates below. Changes stay in the saved picture. Click Save confirmation to store this revision.':'This category supports label changes; four-corner editing applies to plates.'}</p>${editable?'<div class="finding-corners">'+points.map((p,i)=>`<label>Corner ${i+1} x<input type="number" step="0.1" aria-label="Corner ${i+1} x" data-point="${i}" data-axis="0"> y<input type="number" step="0.1" aria-label="Corner ${i+1} y" data-point="${i}" data-axis="1"></label>`).join('')+'</div>':''}<div class="findings-fields"><label>Confirmation label<select id="findingEditorLabel"><option value="positive">Is a ${findingEscape(item.category)}</option><option value="negative">Not a ${findingEscape(item.category)}</option></select></label></div><div class="findings-row"><button type="button" id="findingEditorSave">Save confirmation</button><button type="button" class="sec" id="findingEditorReload">Reload current revision</button><button type="button" class="sec" id="findingEditorForget">Forget this example</button></div><p id="findingEditorStatus" class="findings-note" role="status" aria-live="polite"></p>`;
 // SVG viewBox needs width/height, while persisted crop uses x1/y1/x2/y2.
 const svg=document.getElementById('findingEditorSvg');if(svg)svg.setAttribute('viewBox',[crop[0],crop[1],crop[2]-crop[0],crop[3]-crop[1]].join(' '));
 document.getElementById('findingEditorLabel').value=item.label;
 document.getElementById('findingEditorClose').onclick=()=>{FINDINGS.editorRequest++;FINDINGS.editor=null;panel.hidden=true;};
 document.getElementById('findingEditorReload').onclick=()=>{if(!state.busy&&confirm('Reload the saved revision? Unsaved changes in this editor will be discarded.'))openFindingEditor(item.id);};
 document.getElementById('findingEditorSave').onclick=()=>saveFindingEditor(state);
 document.getElementById('findingEditorForget').onclick=()=>forgetFindingEditor(state);
 if(svg){
  const update=()=>paintFindingEditor(state);update();
  panel.querySelectorAll('[data-point]').forEach(input=>input.onchange=()=>{const next=state.points.map(p=>p.slice());next[Number(input.dataset.point)][Number(input.dataset.axis)]=Number(input.value);if(findingValidPoints(next,crop)){state.points=next;state.shapeDirty=true;findingNotice('findingEditorStatus','Region changed. Save confirmation to store it.');}else findingNotice('findingEditorStatus','Keep four corners inside the saved picture in a convex, non-crossing shape.',true);update();});
  svg.onpointerdown=event=>{const circle=event.target.closest('[data-corner]');if(!circle||state.busy)return;event.preventDefault();state.drag={id:event.pointerId,index:Number(circle.dataset.corner),before:state.points.map(p=>p.slice())};svg.setPointerCapture(event.pointerId);};
  svg.onpointermove=event=>{if(state.drag?.id!==event.pointerId)return;const next=state.points.map(p=>p.slice());next[state.drag.index]=findingSourcePoint(crop,svg.getBoundingClientRect(),event.clientX,event.clientY);if(findingValidPoints(next,crop)){state.points=next;state.shapeDirty=true;update();findingNotice('findingEditorStatus','Region changed. Save confirmation to store it.');}};
  svg.onpointerup=event=>{if(state.drag?.id===event.pointerId)state.drag=null;};
  svg.onpointercancel=()=>{if(state.drag){state.points=state.drag.before;state.drag=null;update();}};
 }
 panel.scrollIntoView({block:'nearest'});
}
function findingValidPoints(points,crop){return findingConvex(points)&&points.every(([x,y])=>x>=crop[0]&&x<=crop[2]&&y>=crop[1]&&y<=crop[3]);}
function paintFindingEditor(state){
 if(FINDINGS.editor!==state)return;const svg=document.getElementById('findingEditorSvg');if(!svg)return;
 svg.querySelector('polygon').setAttribute('points',state.points.map(p=>p.join(',')).join(' '));
 const crop=state.item.crop.box,radius=(crop[2]-crop[0])*9/Math.max(150,svg.getBoundingClientRect().width);
 svg.querySelectorAll('circle').forEach((circle,i)=>{circle.setAttribute('cx',state.points[i][0]);circle.setAttribute('cy',state.points[i][1]);circle.setAttribute('r',radius);});
 document.getElementById('findingEditor').querySelectorAll('[data-point]').forEach(input=>input.value=Number(state.points[Number(input.dataset.point)][Number(input.dataset.axis)].toFixed(2)));
}
function findingEditorBusy(state,busy){state.busy=busy;if(FINDINGS.editor!==state)return;for(const id of ['findingEditorSave','findingEditorReload','findingEditorForget','findingEditorLabel'])document.getElementById(id).disabled=busy;document.getElementById('findingEditor').querySelectorAll('[data-point]').forEach(input=>input.disabled=busy);}
async function saveFindingEditor(state){
 if(state.busy||FINDINGS.editor!==state)return;
 const payload={expected_revision:state.item.revision,label:document.getElementById('findingEditorLabel').value};
 if(state.shapeDirty)payload.points=state.points.map(p=>p.slice());
 findingEditorBusy(state,true);findingNotice('findingEditorStatus','Saving confirmation…');
 try{
  const {data}=await reviewRequest('api/findings/'+encodeURIComponent(state.item.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(FINDINGS.selected.has(data.finding.id))FINDINGS.selected.set(data.finding.id,data.finding);
  if(FINDINGS.editor!==state)return;renderFindingEditor(data.finding);findingNotice('findingEditorStatus','Saved confirmation · revision '+data.finding.revision+'.');loadConfirmedFindings();
 }catch(error){if(FINDINGS.editor===state)findingNotice('findingEditorStatus',error.status===409?'Revision conflict: this example changed elsewhere. Your draft is kept. Reload the current revision before saving again.':'Could not save confirmation: '+error.message,true);}
 finally{findingEditorBusy(state,false);}
}
async function forgetFindingEditor(state){
 if(state.busy||FINDINGS.editor!==state)return;
 if(!confirm('Forget this confirmed example? It will be removed from future training selections. Existing trained models are kept.'))return;
 findingEditorBusy(state,true);findingNotice('findingEditorStatus','Forgetting example…');
 try{
  await reviewRequest('api/findings/'+encodeURIComponent(state.item.id),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:state.item.revision})});
  FINDINGS.selected.delete(state.item.id);if(FINDINGS.editor===state){FINDINGS.editor=null;FINDINGS.editorRequest++;document.getElementById('findingEditor').hidden=true;}loadConfirmedFindings();
 }catch(error){if(FINDINGS.editor===state)findingNotice('findingEditorStatus',error.status===409?'Revision conflict: this example changed elsewhere. Reload its current revision before forgetting it.':'Could not forget example: '+error.message,true);}
 finally{findingEditorBusy(state,false);}
}
function refreshPendingFindings(job,id,view){
 // Intentionally returns immediately: queue thumbnails must never delay global
 // progress/log polling, including a slow or failed preview request.
 if(job.kind==='model_training')return;
 const active=job.phase==='scanning'||(job.phase==='learning'&&['rescanning','postprocessing'].includes(job.learning?.stage));
 let queue=FINDINGS_QUEUES.get(id);if(!queue){queue={last:0,busy:false};FINDINGS_QUEUES.set(id,queue);if(FINDINGS_QUEUES.size>24)FINDINGS_QUEUES.delete(FINDINGS_QUEUES.keys().next().value);}
 const existing=document.getElementById('pendingFindings');if(!active){queue.active=false;if(existing)existing.remove();return;}
 queue.active=active;queue.view=view;
 if(queue.busy||Date.now()-queue.last<3000)return;queue.busy=true;queue.last=Date.now();
 reviewRequest('api/jobs/'+encodeURIComponent(id)+'/review-queue').then(({data})=>{
  if(!queue.active||queue.view!==view)return;
  if(typeof CUR!=='undefined'&&(CUR!==id||JOBVIEW!==view))return;
  const detail=document.getElementById('detail');if(!detail)return;
  let panel=document.getElementById('pendingFindings');if(!panel){panel=document.createElement('section');panel.id='pendingFindings';panel.className='card pending-findings';detail.append(panel);}
  const signature=JSON.stringify([data.total,data.truncated,(data.items||[]).map(i=>i.key)]);if(panel.dataset.signature===signature)return;panel.dataset.signature=signature;
  panel.innerHTML=`<h3>Pending review · ${Number(data.total)||0} sampled findings</h3><p class="findings-copy">Scanning continues while these findings wait for review. These are requests for review, not calibrated probabilities. Use Pause or Stop &amp; Review to classify them; no individual decision blocks the scan.${data.truncated?' The bounded preview queue is full; this is a sample, not every detection.':''}</p><div class="findings-grid">${(data.items||[]).slice(0,12).map(item=>`<article class="finding-card"><img loading="lazy" decoding="async" src="api/jobs/${encodeURIComponent(id)}/review-queue/${encodeURIComponent(item.key)}/image" alt="Pending ${findingEscape(item.category)} finding"><div class="finding-body"><strong>${findingEscape(item.category)}</strong><span>Frame ${findingEscape(item.frame)} · ${findingTime(item.t)}</span><span class="finding-label">Not reviewed</span></div></article>`).join('')}</div>${data.total>12?'<p class="findings-copy">Showing the first 12 compact samples. Full review is available after pausing or stopping.</p>':''}`;
 }).catch(error=>{
  if(!queue.active||queue.view!==view)return;
  if(typeof CUR!=='undefined'&&(CUR!==id||JOBVIEW!==view))return;
  let panel=document.getElementById('pendingFindings');if(!panel){const detail=document.getElementById('detail');if(!detail)return;panel=document.createElement('section');panel.id='pendingFindings';panel.className='card pending-findings';detail.append(panel);}
  const note=document.createElement('p');note.className='findings-copy';note.textContent='Pending previews unavailable: '+error.message+'. Scanning continues; retrying automatically.';panel.replaceChildren(note);delete panel.dataset.signature;
 }).finally(()=>{queue.busy=false;});
}
function showTrainingResult(job){
 if(job.kind!=='model_training')return;
 const detail=document.getElementById('detail');if(!detail)return;
 let panel=document.getElementById('findingsTrainingResult');if(!panel){panel=document.createElement('section');panel.id='findingsTrainingResult';panel.className='card';detail.append(panel);}
 const result=job.training_result;
 panel.replaceChildren();const title=document.createElement('h3');title.textContent=job.name||'Named plate model';panel.append(title);
 const copy=document.createElement('p');copy.className='findings-copy';copy.textContent=result?'Saved automatically as a new named model. Select it in Scan Setup to use it on another video. Review its assessment before enabling automatic filtering.':job.error||'Training selected confirmed plate examples. Progress and training logs appear above.';panel.append(copy);
 if(result){const assessment=document.createElement('pre');assessment.className='findings-copy';assessment.style.whiteSpace='pre-wrap';assessment.textContent=JSON.stringify(result.assessment||result.validation||{},null,2);panel.append(assessment);}
}
"""
