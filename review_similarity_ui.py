"""Visual-only grouping of already-loaded review JPEGs.

No scan/report mutations occur while grouping. Every source-verified
confirmation still passes through the existing per-finding save endpoint.
"""

SCRIPT = r"""
// Similarity groups affect *presentation* only. Never use image fingerprints
// as source identity, training labels or automatic redaction decisions.
let REVIEW_SIMILAR_ENABLED=false,REVIEW_SIMILAR_HASHES=new Map();
let REVIEW_SIMILAR_GROUPS=new Map(),REVIEW_SIMILAR_EXPANDED=new Set();
let REVIEW_SIMILAR_TIMER=null,REVIEW_SIMILAR_LAYOUT="",REVIEW_SIMILAR_BUSY=false;
try{REVIEW_SIMILAR_ENABLED=localStorage.getItem("openscrub.reviewSimilar")==="on";}catch(_){}
function reviewSimilarReset(){
 if(REVIEW_SIMILAR_TIMER)clearTimeout(REVIEW_SIMILAR_TIMER);
 REVIEW_SIMILAR_TIMER=null;REVIEW_SIMILAR_HASHES.clear();REVIEW_SIMILAR_GROUPS.clear();
 REVIEW_SIMILAR_EXPANDED.clear();REVIEW_SIMILAR_LAYOUT="";REVIEW_SIMILAR_BUSY=false;
}
function reviewSimilarFingerprint(img){
 const card=img?.closest?.(".det"),meta=img?._plateMeta;
 if(!card||card.dataset.cat!=="plate"||!img.naturalWidth||
    !meta||!Array.isArray(meta.box)||meta.box.length!==4)return;
 const i=Number(card.id.slice(3)),row=REVIEW_DISPLAY_META[i];
 if(!row)return;
 const canvas=document.createElement("canvas");canvas.width=9;canvas.height=8;
 const ctx=canvas.getContext("2d",{willReadFrequently:true});if(!ctx)return;
 let p;
 try{ctx.drawImage(img,0,0,9,8);p=ctx.getImageData(0,0,9,8).data;}
 catch(_){return;}
 const luminance=[],color=[0,0,0],bits=[0,0];
 for(let k=0;k<72;k++){
  const j=k*4,r=p[j],g=p[j+1],b=p[j+2];
  luminance.push((299*r+587*g+114*b)/1000);
  color[0]+=r;color[1]+=g;color[2]+=b;
 }
 let edge=0;
 for(let y=0;y<8;y++)for(let x=0;x<8;x++){
  const j=y*9+x,k=y*8+x;
  if(luminance[j]>luminance[j+1])bits[k>>>5]=(bits[k>>>5]|(1<<(k&31)))>>>0;
  edge+=Math.abs(luminance[j]-luminance[j+1]);
 }
 const box=meta.box.map(Number);
 if(!box.every(Number.isFinite)||box[2]<=box[0]||box[3]<=box[1])return;
 REVIEW_SIMILAR_HASHES.set(i,{i,bits,color:color.map(c=>c/72),edge:edge/64,
  start:Number(row.t_start),end:Number(row.t_end),box});
 if(REVIEW_SIMILAR_ENABLED)reviewSimilarSchedule();
}
function reviewSimilarPopcount(n){
 n=(n-((n>>>1)&0x55555555))>>>0;
 n=((n&0x33333333)+((n>>>2)&0x33333333))>>>0;
 return (((n+(n>>>4))&0x0f0f0f0f)*0x01010101)>>>24;
}
function reviewSimilarMatch(a,b){
 if(!Number.isFinite(a.start)||!Number.isFinite(b.start)||
    !Number.isFinite(a.end)||!Number.isFinite(b.end)||
    Math.max(a.start,b.start)>Math.min(a.end,b.end)+1.5)return false;
 // A reused background much later in the video is not the same sighting.
 if(Math.abs(a.start-b.start)>30&&Math.abs(a.end-b.end)>30)return false;
 const [x1,y1,x2,y2]=a.box,[u1,v1,u2,v2]=b.box;
 const aw=x2-x1,ah=y2-y1,bw=u2-u1,bh=v2-v1;
 if(aw/bw>2.5||bw/aw>2.5||ah/bh>2.5||bh/ah>2.5)return false;
 if(Math.abs((x1+x2-u1-u2)/2)>Math.max(aw,bw)*.8+12||
    Math.abs((y1+y2-v1-v2)/2)>Math.max(ah,bh)*.8+12)return false;
 if(Math.min(a.edge,b.edge)<2)return false; // Featureless crops are ambiguous.
 if(Math.hypot(...a.color.map((v,k)=>v-b.color[k]))>65)return false;
 return reviewSimilarPopcount(a.bits[0]^b.bits[0])+
        reviewSimilarPopcount(a.bits[1]^b.bits[1])<=10;
}
function reviewSimilarSchedule(){
 if(REVIEW_SIMILAR_TIMER)return;
 REVIEW_SIMILAR_TIMER=setTimeout(()=>{REVIEW_SIMILAR_TIMER=null;reviewSimilarRender();},180);
}
function reviewSimilarLabel(i){
 const label=FINDING_META[i]?.human_confirmation?.label;
 return label==="positive"||label==="negative"?label:null;
}
function reviewSimilarSummary(root){
 const members=REVIEW_SIMILAR_GROUPS.get(root)||[];
 const yes=members.filter(i=>reviewSimilarLabel(i)==="positive").length;
 const no=members.filter(i=>reviewSimilarLabel(i)==="negative").length;
 const pending=members.length-yes-no;
 const summary=document.getElementById("similarSummary"+root);
 if(summary)summary.textContent=(yes+no)+" confirmed · "+pending+" awaiting confirmation"+
  (yes&&no?" · CONFLICTING HUMAN DECISIONS":"");
 const expand=document.getElementById("similarExpand"+root);
 if(expand)expand.textContent=REVIEW_SIMILAR_EXPANDED.has(root)
  ?"Collapse similar pictures":"Show all "+members.length+" pictures";
 for(const button of document.querySelectorAll('[data-similar-batch="'+root+'"]'))
  button.disabled=REVIEW_SIMILAR_BUSY||pending===0;
 for(const button of document.querySelectorAll('[data-similar-output="'+root+'"]'))
  button.disabled=REVIEW_SIMILAR_BUSY;
}
function reviewSimilarRender(){
 const panel=document.getElementById("review");if(!panel)return;
 const enabled=REVIEW_SIMILAR_ENABLED&&!LEARNING_SELECTION;
 const entries=enabled?[...REVIEW_SIMILAR_HASHES.values()].filter(e=>
  !!document.getElementById("det"+e.i)).sort((a,b)=>a.start-b.start||a.i-b.i):[];
 const clusters=[];
 for(const entry of entries){
  const same=clusters.find(c=>reviewSimilarMatch(entry,c[0]));
  if(same)same.push(entry);else clusters.push([entry]);
 }
 const groups=new Map();
 for(const cluster of clusters)if(cluster.length>1)
  groups.set(cluster[0].i,cluster.map(e=>e.i));
 const expanded=REVIEW_SIMILAR_EXPANDED;
 REVIEW_SIMILAR_EXPANDED=new Set();
 for(const [root,members] of groups)
  if(members.some(i=>expanded.has(i)))REVIEW_SIMILAR_EXPANDED.add(root);
 REVIEW_SIMILAR_GROUPS=groups;
 const signature=enabled?[...groups].map(([i,ids])=>i+":"+ids.join(",")).join("|"):"off";
 if(signature!==REVIEW_SIMILAR_LAYOUT){
  // Restore original order first, including when toggling off and after
  // another paginated batch is added. Never discard or recreate card editors.
  for(const [category,ids] of Object.entries(REVIEW_CATEGORY_GROUPS)){
   const grid=[...panel.querySelectorAll("[data-review-category]")]
    .find(g=>g.dataset.reviewCategory===category);
   if(!grid)continue;
   const mounted=new Map([...grid.children].filter(el=>el.classList?.contains("det"))
    .map(el=>[Number(el.id.slice(3)),el]));
   for(const i of ids)if(mounted.has(i))grid.appendChild(mounted.get(i));
  }
  for(const [root,members] of groups){
   let after=document.getElementById("det"+root);
   if(!after)continue;
   for(const i of members.slice(1)){
    const card=document.getElementById("det"+i);
    if(card&&card.parentElement===after.parentElement){after.after(card);after=card;}
   }
  }
  REVIEW_SIMILAR_LAYOUT=signature;
 }
 const childRoot=new Map();
 for(const [root,members] of groups)
  for(const id of members.slice(1))childRoot.set(id,root);
 for(const card of panel.querySelectorAll('.det[data-cat="plate"]')){
  const i=Number(card.id.slice(3)),root=childRoot.get(i);
  const excluded=!!LEARNING_SELECTION&&!(TRKMEM[i]||[i]).some(m=>LEARNING_SELECTION.has(m));
  card.hidden=excluded||(enabled&&root!==undefined&&!REVIEW_SIMILAR_EXPANDED.has(root));
 }
 for(const slot of panel.querySelectorAll(".review-similar-slot")){
  const i=Number(slot.id.slice(7));
  if(!enabled||!groups.has(i)){
   if(slot.dataset.members){slot.textContent="";delete slot.dataset.members;}
  }
 }
 for(const [root,members] of groups){
  const slot=document.getElementById("similar"+root);if(!slot)continue;
  const key=members.join(",");
  if(slot.dataset.members!==key){
   slot.dataset.members=key;
   slot.innerHTML='<div style="border:1px solid #64748b;border-radius:8px;padding:7px;margin:8px 0">'+
    '<strong>'+members.length+' visually similar pictures</strong>'+
    '<div id="similarSummary'+root+'" style="font-size:12px;margin:5px 0"></div>'+
    '<button type="button" class="sec" id="similarExpand'+root+'" onclick="reviewSimilarExpand('+root+')"></button>'+
    '<details style="margin-top:6px"><summary>Group actions (explicit)</summary>'+
    '<p class="review-copy">Visual matching never confirms a plate. Human decisions remain editable. Group actions require confirmation.</p>'+
    '<div class="row">'+
    '<button type="button" class="sec" data-similar-batch="'+root+'" onclick="reviewSimilarBatch('+root+',\'positive\')">Is a plate · unreviewed</button>'+
    '<button type="button" class="sec" data-similar-batch="'+root+'" onclick="reviewSimilarBatch('+root+',\'negative\')">Not a plate · unreviewed</button>'+
    '<button type="button" class="sec" data-similar-output="'+root+'" onclick="reviewSimilarOutput('+root+',true)">Blur all</button>'+
    '<button type="button" class="sec" data-similar-output="'+root+'" onclick="reviewSimilarOutput('+root+',false)">Keep all visible</button>'+
    '</div></details></div>';
  }
  reviewSimilarSummary(root);
 }
 const toggle=document.getElementById("reviewSimilarToggle");
 if(toggle){
  toggle.textContent=REVIEW_SIMILAR_ENABLED?"Show individual pictures":"Group similar pictures";
  toggle.disabled=REVIEW_SIMILAR_BUSY;
 }
 const note=document.getElementById("reviewSimilarInfo");
 if(note)note.textContent=enabled
  ?[...groups.values()].reduce((n,ids)=>n+ids.length-1,0)+" similar cards grouped from loaded previews. Expand any group to correct a decision."
  :REVIEW_SIMILAR_ENABLED?"10% sampling temporarily shows individual findings."
  :"Uses already loaded pictures · no rescan or automatic classification.";
 if(REVIEW_MEDIA)pumpReviewPreviews(REVIEW_MEDIA);
}
function reviewSimilarExpand(root){
 if(!REVIEW_SIMILAR_GROUPS.has(root))return;
 if(REVIEW_SIMILAR_EXPANDED.has(root))REVIEW_SIMILAR_EXPANDED.delete(root);
 else REVIEW_SIMILAR_EXPANDED.add(root);
 reviewSimilarRender();
}
function toggleReviewSimilarity(){
 if(REVIEW_SIMILAR_BUSY)return;
 REVIEW_SIMILAR_ENABLED=!REVIEW_SIMILAR_ENABLED;
 try{localStorage.setItem("openscrub.reviewSimilar",REVIEW_SIMILAR_ENABLED?"on":"off");}catch(_){}
 clearSel();
 if(REVIEW_SIMILAR_ENABLED)for(const img of document.querySelectorAll("#review img[data-preview-url]"))
  if(img.naturalWidth&&img._plateMeta)reviewSimilarFingerprint(img);
 reviewSimilarRender();
}
function reviewSimilarOutput(root,blur){
 if(REVIEW_SIMILAR_BUSY)return;
 const members=REVIEW_SIMILAR_GROUPS.get(root);
 if(!members||!confirm("Apply "+(blur?"Blur":"Keep visible")+" to all "+members.length+
   " visually similar findings? This changes output choices, not human classifications. All original pictures stay editable."))return;
 for(const i of members)applyDet(i,blur);
 reviewSimilarRender();
}
async function reviewSimilarBatch(root,label){
 if(REVIEW_SIMILAR_BUSY||!["positive","negative"].includes(label))return;
 const members=REVIEW_SIMILAR_GROUPS.get(root)||[];
 const targets=members.filter(i=>!reviewSimilarLabel(i));
 if(!targets.length)return;
 const name=label==="positive"?"Is a plate":"Not a plate";
 if(!confirm("Confirm "+targets.length+" unreviewed pictures as '"+name+
  "'? Every source-verified picture is saved separately. Existing human decisions will NOT be overwritten. Expand the group first if any image is uncertain."))return;
 REVIEW_SIMILAR_BUSY=true;reviewSimilarRender();
 const job=CUR,view=JOBVIEW;
 let saved=0,failure="";
 try{
  for(const i of targets){
   if(CUR!==job||JOBVIEW!==view){failure="The review changed.";break;}
   const img=document.getElementById("thumb"+i);
   if(!img||!await queueReviewPreview(img,true)||!img._plateMeta||
      img._plateMeta.classification_allowed===false){
    failure="Finding #"+i+" has no source-verified picture. Open it individually.";break;
   }
   await confirmFinding(i,label);
   if(CONFIRM_FAILED.has(i)||reviewSimilarLabel(i)!==label){
    failure="Finding #"+i+" could not be saved. Resolve its displayed error before retrying.";break;
   }
   saved++;
  }
 }catch(error){failure=error.message;}
 finally{
  REVIEW_SIMILAR_BUSY=false;reviewSimilarRender();
  const status=document.getElementById("reviewSimilarityStatus");
  if(status)status.textContent=failure
   ?saved+" of "+targets.length+" confirmations saved; "+failure
   :saved+" confirmations saved. All original cards remain editable.";
 }
}
"""
