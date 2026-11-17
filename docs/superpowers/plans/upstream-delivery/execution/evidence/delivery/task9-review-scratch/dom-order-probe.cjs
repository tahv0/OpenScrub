
const handlers={};let REVIEW_SCHED=null,selSet=new Set(),marqEl=null,mStart=null;
const ownsView=()=>true,clearSel=()=>{},initMarquee=()=>{},refreshDet=()=>{};
const THUMB_FLIGHTS=new Set();let gridTop=-3000;
class N {
 constructor(type='div'){this.type=type;this.children=[];this.dataset={};this.style={};this.isConnected=true;this.clientWidth=200;this.classList={toggle(){},remove(){},add(){}};}
 appendChild(n){if(n.parentElement){const old=n.parentElement.children;old.splice(old.indexOf(n),1);}this.children.push(n);n.parentElement=this;return n;}
 remove(){if(this.parentElement){this.parentElement.children.splice(this.parentElement.children.indexOf(this),1);this.parentElement=null;}this.isConnected=false;}
 getBoundingClientRect(){const top=this.type==='grid'?gridTop:this.type==='card'?this.parentElement.getBoundingClientRect().top:gridTop+(parseFloat(this.style.top)||0);return {top,bottom:top+260,width:200,height:260};}
 setAttribute(){} removeAttribute(){} addEventListener(){} removeEventListener(){}
 querySelector(s){if(s==='img')return this.img;if(s==='button')return null;return null;}
 set innerHTML(value){const card=new N('card');card.id='det'+value;card.img=new N('img');card.img.parentElement={classList:card.classList};this.firstElementChild=card;}
}
const grid=new N('grid'),status=new N(),prev=new N(),next=new N(),root=new N('root');
root.querySelector=s=>s.startsWith('[data-review-section')?grid:s==='[data-review-range]'?status:s==='[data-review-prev]'?prev:s==='[data-review-next]'?next:null;
const document={getElementById:id=>id==='review'?root:null,activeElement:null,createElement:()=>new N()};
const window={innerHeight:800,scrollY:0,scrollBy(){},scrollTo(){},addEventListener:(e,f)=>handlers[e]=f,removeEventListener(){}};
const getComputedStyle=()=>({gridTemplateColumns:'200px'});
const ResizeObserver=class {observe(){}unobserve(){}disconnect(){}};
const requestAnimationFrame=()=>1,cancelAnimationFrame=()=>{};
const reviewCard=c=>String(c.id);
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
  this.listen(window,'pagehide',()=>this.dispose());
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
   for(const n of [...needed].sort((a,b)=>a-b)){
    let row=section.rows.get(n);
    if(!row){row=document.createElement('div');row.className='grid3 reviewrow';section.el.appendChild(row);
     section.rows.set(n,row);this.observer.observe(row);}
    row.style.top=section.prefix[n]+'px';row.dataset.pin=String(!rows.has(n)?1:0);
    const ids=section.ids.slice(n*section.columns,(n+1)*section.columns);
    for(const [col,id]of ids.entries()){
     if(!desired.has(id)&&id!==pin)continue;
     let b=this.bindings.get(id);
     if(!b){
      const holder=document.createElement('div');holder.innerHTML=reviewCard(this.meta.byId.get(id));
      const card=holder.firstElementChild,img=card.querySelector('img');
      b={id,card,img,token:{},url:null,op:null};this.bindings.set(id,b);
     }
     if(b.card.parentElement!==row)row.appendChild(b.card);
     b.card.style.gridColumn=String(col+1);b.card.dataset.focusPin=String(id===pin?1:0);
     b.card.classList.toggle('selected',selSet.has(id));refreshDet(id);
    }
   }
   for(const spacer of section.spacers)spacer.remove();section.spacers=[];
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
 dispose(){
  if(this.disposed)return;this.disposed=true;
  if(this.frame)cancelAnimationFrame(this.frame);this.frame=0;
  this.observer?.disconnect();this.listeners.splice(0).forEach(remove=>remove());
  this.selectionCleanup?.();this.selectionCleanup=null;
  const wrap=this.root.querySelector?.('#detwrap');if(wrap)delete wrap.dataset.mq;
  for(const b of [...this.bindings.values()])this.retire(b);
  for(const r of this.retries.values())if(r.timer)clearTimeout(r.timer);
  this.retries.clear();this.eligible.clear();this.queue=[];
  clearSel();if(marqEl){marqEl.remove();marqEl=null;}mStart=null;
 }
}
// Back/forward-cache restoration reuses this view's complete metadata/drafts.
window.addEventListener?.('pageshow',()=>{
 const s=REVIEW_SCHED;
 if(s?.disposed&&ownsView(s.jobId,s.viewGen)&&s.root.isConnected&&document.getElementById('review')===s.root){
  REVIEW_SCHED=new ReviewScheduler(s.jobId,s.viewGen,s.root,s.meta);
  REVIEW_SCHED.matching=s.matching;REVIEW_SCHED.start();initMarquee();
 }
});

ReviewScheduler.prototype.updateQueue=function(){};

const ids=Array.from({length:30},(_,n)=>n+1),meta={sections:[{zone:false,ids,cards:ids.map(id=>({id}))}],byId:new Map(ids.map(id=>[id,{id}]))};
REVIEW_SCHED=new ReviewScheduler('A',1,root,meta);REVIEW_SCHED.start();
const snapshot=()=>({descriptorOrder:REVIEW_SCHED.normalIds,domOrder:grid.children.filter(n=>n.className==='grid3 reviewrow').flatMap(n=>n.children.map(c=>Number(c.id.slice(3))))});
const lower=snapshot();gridTop=-2000;REVIEW_SCHED.layout();const upward=snapshot();console.log(JSON.stringify({lower,upward}));
