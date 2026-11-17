from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub_web.py')
s=p.read_text()
s=s.replace('if(CUR===id){VIEW_GEN++;', 'if(CUR===id){beUnmount();VIEW_GEN++;')
s=s.replace('async function openJob(id){\n const video=', 'async function openJob(id){\n beUnmount();\n const video=')
s=s.replace('let BE=emptyEditor();\n', '''let BE=emptyEditor();
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
''')
s=s.replace(''' const img=document.getElementById("beImg");
 img.onload=()=>{if(!ownsView(id,gen)||BE!==editor||document.getElementById("beImg")!==img||BE.playing)return;const cv=document.getElementById("beCv");
  cv.width=img.clientWidth;cv.height=img.clientHeight;
  BE.scale=img.clientWidth/(img.naturalWidth||1);beDraw();};
 const bv=document.getElementById("beVid");''',''' const img=document.getElementById("beImg"),bv=document.getElementById("beVid"),
       cv=document.getElementById("beCv");
 const view=beMount(img,bv,cv,id,gen,editor);
 img.onload=()=>{if(view.current()&&!BE.playing){view.sync();beDraw();}};
 bv.addEventListener("loadedmetadata",()=>{if(view.current())view.sync();});''')
s=s.replace(''' v.style.display="block";img.style.display="none";
''',''' v.style.display="block";img.style.display="none";
 if(BE_VIEW)BE_VIEW.sync();
''')
s=s.replace(''' if(v.clientWidth){cv.width=v.clientWidth;cv.height=v.clientHeight;
  BE.scale=v.clientWidth/(v.videoWidth||1);}
''',''' if(BE_VIEW)BE_VIEW.sync();
''')
s=s.replace(''' const b=document.getElementById("bePlay");if(b)b.innerHTML="&#9654;";''',''' if(BE_VIEW)BE_VIEW.sync();
 const b=document.getElementById("bePlay");if(b)b.innerHTML="&#9654;";''')
s=s.replace(''' document.getElementById("beImg").src=`api/jobs/${CUR}/frame_at?t=${BE.t}`;
''',''' document.getElementById("beImg").src=`api/jobs/${CUR}/frame_at?t=${BE.t}`;
 if(BE_VIEW)BE_VIEW.sync();
''')
s=s.replace(''' const x=cv.getContext("2d"),s=BE.scale;
 x.clearRect(0,0,cv.width,cv.height);
''',''' const view=BE_VIEW;if(!view||!view.current())return;
 const x=cv.getContext("2d"),tr=view.transform;
 x.setTransform(1,0,0,1,0,0);x.clearRect(0,0,cv.width,cv.height);
 if(!tr)return;
 x.setTransform(cv.width/tr.width,0,0,cv.height/tr.height,0,0);
 const mapped=box=>box.map((v,i)=>v*(i%2?tr.sy:tr.sx));
''')
s=s.replace('a.box.map(v=>v*s)','mapped(a.box)').replace('b.box.map(v=>v*s)','mapped(b.box)')
s=s.replace('''Math.min(p[0],q[0])*s,Math.min(p[1],q[1])*s,
   Math.abs(q[0]-p[0])*s,Math.abs(q[1]-p[1])*s''','''Math.min(p[0],q[0])*tr.sx,Math.min(p[1],q[1])*tr.sy,
   Math.abs(q[0]-p[0])*tr.sx,Math.abs(q[1]-p[1])*tr.sy''')
s=s.replace(''' const cv=document.getElementById("beCv");
 const pt=e=>{const r=cv.getBoundingClientRect();
  return[(e.clientX-r.left)/BE.scale,(e.clientY-r.top)/BE.scale];};
 cv.addEventListener("pointerdown",e=>{
  const p=pt(e);cv.setPointerCapture(e.pointerId);''',''' const cv=document.getElementById("beCv"),view=BE_VIEW;
 const pt=e=>{
  const tr=view&&view.sync();if(!tr||BE.playing)return null;
  const r=cv.getBoundingClientRect();
  return[(e.clientX-r.left)/tr.sx,(e.clientY-r.top)/tr.sy];};
 cv.addEventListener("pointerdown",e=>{
  const p=pt(e);if(!p)return;
  cv.setPointerCapture(e.pointerId);BE.pointerId=e.pointerId;''')
s=s.replace('''if(sel){const[a1,b1,a2,b2]=sel.box,hs=9/BE.scale;''','''if(sel){const[a1,b1,a2,b2]=sel.box,tr=view.transform;''')
s=s.replace('Math.abs(p[0]-hx)<hs&&Math.abs(p[1]-hy)<hs','Math.abs(p[0]-hx)<9/tr.sx&&Math.abs(p[1]-hy)<9/tr.sy')
s=s.replace(''' cv.addEventListener("pointermove",e=>{
  if(BE.add&&BE.addAnchor){BE.addFloat=pt(e);beDraw();return;}
  if(!BE.drag||BE.sel<0)return;
  const p=pt(e),b=BE.boxes.find(x=>x.i===BE.sel);if(!b)return;''',''' cv.addEventListener("pointermove",e=>{
  const p=pt(e);if(!p)return;
  if(BE.add&&BE.addAnchor){BE.addFloat=p;beDraw();return;}
  if(!BE.drag||BE.sel<0)return;
  const b=BE.boxes.find(x=>x.i===BE.sel);if(!b)return;''')
s=s.replace(''' cv.addEventListener("pointerup",()=>{BE.drag=null;});''',''' const end=()=>{if(view&&view.current()){BE.drag=null;delete BE.pointerId;}};
 cv.addEventListener("pointerup",end);cv.addEventListener("pointercancel",()=>{
  if(view&&view.current()){beEndGesture(BE,cv);beDraw();}
 });''')
s=s.replace('''function showPanel(which){
''','''function showPanel(which){
 beUnmount();
''')
p.write_text(s)
