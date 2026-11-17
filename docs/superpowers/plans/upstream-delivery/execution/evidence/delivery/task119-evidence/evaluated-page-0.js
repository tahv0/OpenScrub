
// keep the face literal exactly as-is: the server injects custom category
// colors anchored on it
const CATS={name:"#3b82f6",dob:"#22c55e",phone:"#f59e0b",ssn:"#ef4444",
            email:"#14b8a6",address:"#f97316",card:"#db2777",
            apikey:"#0891b2",ipaddr:"#65a30d",plate:"#7c3aed",
            person:"#0ea5e9",qrcode:"#a16207",screen:"#475569",
            anytext:"#84cc16",bank:"#b45309",crypto:"#7e22ce",
            passport:"#0f766e",phrase:"#6366f1",
            face:"#ec4899",
            ignore:"#334155",trackobj:"#eab308"};
const DN={person:"person (full body)",qrcode:"QR / barcode",
          anytext:"all text (blur every text region)",
          bank:"bank (IBAN/routing/SWIFT)",crypto:"crypto address",
          passport:"passport / ID (MRZ)",phrase:"specific text",
          screen:"screens (tv/laptop/phone)",ignore:"ignore (never blur)",
          trackobj:"track object (blur it)"};
const RULER=24,WROW=20,AROW=34;

let S={file:null,dur:0,vw:0,vh:0,cin:0,cout:0,wins:[],sel:0,ignore:[],
 zoom:1,view0:0,
 audio:[],cls:"face",mode:"draw",selZone:null,anchor:null,fl:null,drag:null,
 seekTo:null,seeking:false,primed:false,paste:null,undo:[],mm:{}};

function $(id){return document.getElementById(id);}
function fmt(t){const d=new Date(Math.max(0,t)*1000).toISOString();
 return t>=3600?d.substr(11,8):d.substr(14,5);}
function newWin(t0,t1,cats){return {t0:t0,t1:t1,
 cats:Object.assign({},cats),zones:{},track:[]};}
function selWin(){return S.wins[S.sel];}

// ---------- load ----------
$("file").addEventListener("change",e=>{
 const f=e.target.files&&e.target.files[0]; if(!f)return;
 S.file=f; $("fname").textContent=f.name; $("spath").value="";
 openEditor(URL.createObjectURL(f), f.name);
});
$("spath").addEventListener("keydown",e=>{
 if(e.key==="Enter"&&e.target.value.trim()){
  S.file=null; $("fname").textContent="choose a video file…";
  openEditor("/api/server_video?path="+encodeURIComponent(e.target.value.trim()),
             e.target.value.trim());
 }});
function openEditor(url,label){
 const v=$("vd");
 S.primed=false;S.seekTo=null;S.seeking=false;
 v.preload="auto";v.src=url;
 v.onloadedmetadata=()=>{
  S.dur=v.duration||0;S.vw=v.videoWidth;S.vh=v.videoHeight;
  S.cin=0;S.cout=S.dur;
  S.wins=[newWin(0,S.dur,{})];S.sel=0;S.ignore=[];S.undo=[];
  const n=(v.audioTracks&&v.audioTracks.length)||1;
  S.audio=Array.from({length:n},(_,i)=>({muted:false,
   label:n>1?("A"+(i+1)):"Audio"}));
  $("vmeta").textContent=label+" · "+fmt(S.dur)+" · "+S.vw+"×"+S.vh;
  $("empty").style.display="none";$("editor").style.display="block";
  fitCanvas();renderCats();tlHdr();draw();
  S.zoom=1;S.view0=0;setZoom(1);
  buildWave();
 };
 v.addEventListener("seeked",()=>{S.seeking=false;pump();tlDraw();});
 v.addEventListener("timeupdate",tlDraw);
 v.addEventListener("loadeddata",prime,{once:true});
 window.addEventListener("resize",()=>{fitCanvas();draw();tlDraw();});
 hookZC();hookTL();
}
function decodeBuf(ctx,buf){
 // Safari's decodeAudioData was callback-only for years; the modern form
 // returns a promise. Feed both shapes — first settle wins.
 return new Promise((res,rej)=>{
  let p=null;
  try{p=ctx.decodeAudioData(buf,res,rej);}catch(e){rej(e);return;}
  if(p&&p.then)p.then(res,rej);
 });
}
function errName(e){
 if(e==null)return "unknown error";      // old Safari passes null to the
 return e.name||e.message||String(e);    // decode error callback
}
// ---- Plan B for iOS: Safari's decodeAudioData only accepts pure AUDIO
// files — it refuses to demux a video container (.mov/.mp4) at ANY sample
// rate, even though the <video> element plays it fine. So walk the MP4/
// QuickTime boxes ourselves, pull the AAC track's raw samples, and decode
// them with WebCodecs AudioDecoder (iOS 16.4+). Everything stays local.
function demuxMp4Aac(ab){
 const dv=new DataView(ab),u8=new Uint8Array(ab),N=ab.byteLength;
 const fcc=o=>String.fromCharCode(u8[o],u8[o+1],u8[o+2],u8[o+3]);
 function* boxes(o,end){
  while(o+8<=end){
   let sz=dv.getUint32(o),hd=8;
   const typ=fcc(o+4);
   if(sz===1){sz=Number(dv.getBigUint64(o+8));hd=16;}
   else if(sz===0)sz=end-o;
   if(sz<hd||o+sz>end)break;
   yield {typ:typ,body:o+hd,end:o+sz};
   o+=sz;
  }
 }
 const find=(o,end,t)=>{for(const b of boxes(o,end))if(b.typ===t)return b;
                       return null;};
 const moov=find(0,N,"moov");
 if(!moov)throw new Error("not an MP4/QuickTime file");
 let badCodec=null;
 for(const trak of boxes(moov.body,moov.end)){
  if(trak.typ!=="trak")continue;
  const mdia=find(trak.body,trak.end,"mdia");if(!mdia)continue;
  const hdlr=find(mdia.body,mdia.end,"hdlr");
  if(!hdlr||fcc(hdlr.body+8)!=="soun")continue;
  const mdhd=find(mdia.body,mdia.end,"mdhd");
  const tscale=mdhd?(u8[mdhd.body]===1?dv.getUint32(mdhd.body+20)
                                      :dv.getUint32(mdhd.body+12)):44100;
  const minf=find(mdia.body,mdia.end,"minf");if(!minf)continue;
  const stbl=minf?find(minf.body,minf.end,"stbl"):null;if(!stbl)continue;
  const stsd=find(stbl.body,stbl.end,"stsd");if(!stsd)continue;
  // first sample entry: [size][format] at stsd.body+8 (8 = ver/flags+count)
  const ebody=stsd.body+8,eend=Math.min(ebody+dv.getUint32(ebody),stsd.end);
  const efmt=fcc(ebody+4);
  if(efmt!=="mp4a"){badCodec=efmt;continue;}   // e.g. spatial-audio track;
  // AudioSampleEntry fixed fields; v2 entries lie here, fall back to mdhd
  const ch=dv.getUint16(ebody+24)||2;
  const sr=(dv.getUint32(ebody+32)>>>16)||tscale;
  // esds may sit directly in the entry or inside a QT 'wave' wrapper —
  // byte-scan for it, then walk the descriptors (tag + varint length)
  let asc=null;
  for(let o=ebody+36;o+8<=eend;o++){
   if(u8[o]===0x65&&u8[o+1]===0x73&&u8[o+2]===0x64&&u8[o+3]===0x73){
    let p=o+8;                             // skip 4cc + ver/flags
    const rdlen=()=>{let l=0,b;do{b=u8[p++];l=(l<<7)|(b&127);}while(b&128);
                     return l;};
    if(u8[p]===3){p++;rdlen();p+=3;        // ES descr: ES_ID + flags
     if(u8[p]===4){p++;rdlen();p+=13;      // DecoderConfig: oti..bitrates
      if(u8[p]===5){p++;const l=rdlen();asc=u8.slice(p,p+l);}}}
    break;
   }
  }
  if(!asc||!asc.length)throw new Error("AAC config not found");
  const g32=(b,o)=>dv.getUint32(b.body+o);
  const stsz=find(stbl.body,stbl.end,"stsz"),
        stsc=find(stbl.body,stbl.end,"stsc"),
        stts=find(stbl.body,stbl.end,"stts");
  let stco=find(stbl.body,stbl.end,"stco"),co64=false;
  if(!stco){stco=find(stbl.body,stbl.end,"co64");co64=true;}
  if(!stsz||!stsc||!stco)throw new Error("incomplete sample tables");
  const fixed=g32(stsz,4),cnt=g32(stsz,8);
  const sz=i=>fixed||g32(stsz,12+4*i);
  const nch=g32(stco,4),nsc=g32(stsc,4);
  const coff=i=>co64?Number(dv.getBigUint64(stco.body+8+8*i))
                    :g32(stco,8+4*i);
  const durs=[];
  if(stts){const n=g32(stts,4);
   for(let i=0;i<n;i++)durs.push([g32(stts,8+8*i),g32(stts,12+8*i)]);}
  const samples=[];
  let si=0,t=0,di=0,dleft=durs.length?durs[0][0]:Infinity;
  for(let ci=0,sci=0;ci<nch&&si<cnt;ci++){
   while(sci+1<nsc&&g32(stsc,8+12*(sci+1))<=ci+1)sci++;
   let off=coff(ci);
   const per=g32(stsc,12+12*sci);
   for(let k=0;k<per&&si<cnt;k++,si++){
    const s=sz(si);
    samples.push({off:off,size:s,ts:Math.round(t/tscale*1e6)});
    off+=s;
    t+=durs.length?durs[di][1]:1024;
    if(durs.length&&--dleft<=0&&di+1<durs.length){
     di++;dleft=durs[di][0];}
   }
  }
  if(!samples.length)throw new Error("empty audio track");
  return {ch:ch,sr:sr,asc:asc,samples:samples};
 }
 throw new Error(badCodec?"unsupported audio codec ("+badCodec+")"
                         :"no audio track found");
}
function adtsFromAac(m,u8){
 // Rewrap the raw AAC frames as an ADTS stream — a pure AUDIO payload
 // that Safari's decodeAudioData accepts even though it refuses the
 // video container the frames came from. 7-byte header per frame;
 // profile/rate/channels come from the AudioSpecificConfig.
 const aot=(m.asc[0]>>3)||2,
       fi=((m.asc[0]&7)<<1)|(m.asc[1]>>7),
       cc=(m.asc[1]>>3)&15;
 if(fi>=15||aot>4)throw new Error("unsupported AAC config");
 let total=0;
 for(const s of m.samples)total+=s.size+7;
 const out=new Uint8Array(total);
 let o=0;
 for(const s of m.samples){
  const fl=s.size+7;
  out[o]=0xFF;out[o+1]=0xF1;                 // sync, MPEG-4, no CRC
  out[o+2]=((aot-1)<<6)|(fi<<2)|(cc>>2);
  out[o+3]=((cc&3)<<6)|((fl>>11)&3);
  out[o+4]=(fl>>3)&255;
  out[o+5]=((fl&7)<<5)|0x1F;                 // buffer fullness = all ones
  out[o+6]=0xFC;                             // (VBR), 1 AAC frame
  out.set(u8.subarray(s.off,s.off+s.size),o+7);
  o+=fl;
 }
 return out.buffer;
}
async function wavePlanB(buf){
 const m=demuxMp4Aac(buf);
 try{return await waveViaWebCodecs(buf,m);}
 catch(e){
  // no AudioDecoder on this iOS (or it balked) — ADTS + decodeAudioData
  const adts=adtsFromAac(m,new Uint8Array(buf));
  const OC=window.OfflineAudioContext||window.webkitOfflineAudioContext;
  if(!OC)throw e;
  let lastErr=e;
  for(const sr of [8000,16000,22050,44100,48000]){
   let ctx=null;
   try{ctx=new OC(1,sr,sr);}catch(e2){lastErr=e2;continue;}
   try{return peaksFrom(await decodeBuf(ctx,adts.slice(0)));}
   catch(e2){lastErr=e2;}
  }
  throw new Error("AAC decode failed ("+errName(lastErr)+")");
 }
}
async function waveViaWebCodecs(buf,m){
 if(typeof AudioDecoder==="undefined")
  throw new Error("WebCodecs unavailable");
 const cfg={codec:"mp4a.40."+((m.asc[0]>>3)||2),sampleRate:m.sr,
            numberOfChannels:m.ch,description:m.asc};
 const sup=await AudioDecoder.isConfigSupported(cfg).catch(()=>null);
 if(sup&&sup.supported===false)throw new Error("AAC decode unsupported");
 const spans=[];                        // [t0_us,t1_us,peak]
 let derr=null;
 const dec=new AudioDecoder({
  output:ad=>{
   try{
    const n=ad.numberOfFrames,f=new Float32Array(n);
    ad.copyTo(f,{planeIndex:0,format:"f32-planar"});
    let m0=0;for(let i=0;i<n;i+=2){const v=Math.abs(f[i]);if(v>m0)m0=v;}
    spans.push([ad.timestamp,
                ad.timestamp+Math.round(n/ad.sampleRate*1e6),m0]);
   }catch(e){
    try{                                // build without f32 conversion
     const n2=ad.numberOfFrames*ad.numberOfChannels,
           s16=new Int16Array(n2);
     ad.copyTo(s16,{planeIndex:0});
     let m1=0;for(let i=0;i<n2;i+=2){const v=Math.abs(s16[i]);if(v>m1)m1=v;}
     spans.push([ad.timestamp,ad.timestamp+
      Math.round(ad.numberOfFrames/ad.sampleRate*1e6),m1/32768]);
    }catch(e2){}
   }
   ad.close();
  },
  error:e=>{derr=e;}
 });
 const u8=new Uint8Array(buf);
 try{
  dec.configure(cfg);
  for(const s of m.samples){
   if(derr)break;
   dec.decode(new EncodedAudioChunk({type:"key",timestamp:s.ts,
    data:u8.subarray(s.off,s.off+s.size)}));
  }
  await dec.flush();
 }catch(e){if(!derr)derr=e;}
 try{dec.close();}catch(e){}
 if(!spans.length)
  throw new Error("WebCodecs decode failed"
                  +(derr?" ("+errName(derr)+")":""));
 const dur=spans.reduce((a,s)=>Math.max(a,s[1]),0)||1,NB=2000,
       out=new Array(NB).fill(0);
 let mx=0;
 for(const s of spans){
  const b0=Math.max(0,Math.floor(s[0]/dur*NB)),
        b1=Math.min(NB-1,Math.floor(s[1]/dur*NB));
  for(let b=b0;b<=b1;b++)if(s[2]>out[b])out[b]=s[2];
  if(s[2]>mx)mx=s[2];
 }
 if(mx>0)for(let b=0;b<NB;b++)out[b]=+(out[b]/mx).toFixed(3);
 return out;
}
async function buildWave(){
 const tok=(S.waveTok=(S.waveTok||0)+1);
 S.wave=[];S.waveErr=null;S.waveBusy=true;tlDraw();
 try{
  if(S.file){
   if(S.file.size>600*1024*1024){        // too large to decode in-browser
    S.waveErr="file too large";return;}
   const buf=await S.file.arrayBuffer();
   if(tok!==S.waveTok)return;
   const OC=window.OfflineAudioContext||window.webkitOfflineAudioContext;
   if(!OC){S.waveErr="WebAudio unavailable";return;}
   // iOS Safari quirks, both real: pre-2024 WebKit THROWS constructing a
   // context below 22050; newer WebKit constructs an 8k context fine but
   // can still FAIL the AAC decode into it. So retry the WHOLE decode at
   // each rate, low (cheap) to high, and only give up when every rate
   // fails. decodeAudioData detaches its buffer — slice a copy per try.
   let lastErr=null;
   for(const sr of [8000,16000,22050,44100,48000]){
    let ctx=null;
    try{ctx=new OC(1,sr,sr);}catch(e){lastErr=e;continue;}
    try{
     const ab=await decodeBuf(ctx,buf.slice(0));
     if(tok!==S.waveTok)return;
     // browsers demux only the DEFAULT audio track from a video container —
     // extra lanes stay flat for local files (server paths get all tracks)
     S.wave[0]=peaksFrom(ab);
     return;
    }catch(e){lastErr=e;if(tok!==S.waveTok)return;}
   }
   try{                                  // Plan B: demux the container
    const pk=await wavePlanB(buf);
    if(tok!==S.waveTok)return;
    S.wave[0]=pk;
    return;
   }catch(e2){
    if(tok!==S.waveTok)return;
    S.waveErr="decode failed ("+errName(lastErr)+"; "
              +(e2&&e2.message?e2.message:errName(e2))+")";
   }
  }else{
   const path=$("spath").value.trim();
   for(let i=0;i<S.audio.length;i++){
    const r=await fetch("/api/waveform?path="+encodeURIComponent(path)
                        +"&track="+i);
    if(tok!==S.waveTok)return;
    if(r.ok){const d=await r.json();
     if(d.peaks&&d.peaks.length)S.wave[i]=d.peaks;}
   }
  }
 }catch(e){S.waveErr="waveform failed ("+errName(e)+")";}
 finally{
  if(tok===S.waveTok){
   S.waveBusy=false;
   if(S.waveErr)console.warn("[openscrub] "+S.waveErr);
   tlDraw();
  }
 }
}
function peaksFrom(ab){
 const ch=ab.getChannelData(0),N=2000,
       per=Math.max(1,Math.floor(ch.length/N));
 const out=new Array(N).fill(0);let mx=0;
 for(let b=0;b<N;b++){
  let m=0;const s0=b*per,e0=Math.min(ch.length,s0+per);
  for(let j=s0;j<e0;j+=2){const v=Math.abs(ch[j]);if(v>m)m=v;}
  out[b]=m;if(m>mx)mx=m;
 }
 if(mx>0)for(let b=0;b<N;b++)out[b]=+(out[b]/mx).toFixed(3);
 return out;
}
function prime(){
 if(S.primed)return;S.primed=true;
 const v=$("vd");
 try{const p=v.play();if(p&&p.then)p.then(()=>v.pause()).catch(()=>{});
 else v.pause();}catch(err){}
}
function seek(t){S.seekTo=Math.max(0,Math.min(S.dur,t));pump();}
function pump(){
 if(S.seeking||S.seekTo==null)return;
 const v=$("vd"),t=S.seekTo;S.seekTo=null;S.seeking=true;
 try{v.currentTime=t;}catch(e){S.seeking=false;}
}
function fitCanvas(){
 const v=$("vd"),c=$("zc");
 c.width=v.clientWidth;c.height=v.clientHeight;
 c.style.left=v.offsetLeft+"px";
}

// ---------- categories panel (per selected window) ----------
function renderCats(){
 const w=selWin(); if(!w)return;
 $("cattitle").textContent="Categories — Window "+(S.sel+1);
 let h="";
 for(const c of Object.keys(CATS)){
  if(c==="ignore"||c==="trackobj")continue;   // pseudo-classes: own rows below
  const on=!!w.cats[c], nz=(w.zones[c]||[]).length,
        act=S.cls===c?"active":"";
  h+='<div class="catrow '+act+'">'
   +'<input type="checkbox" '+(on?"checked":"")
   +' onchange="togCat(\''+c+'\',this.checked)">'
   +'<span class="sw" style="background:'+CATS[c]+'" onclick="setCls(\''+c+'\')"></span>'
   +'<span class="nm" onclick="setCls(\''+c+'\')">'+(DN[c]||c)+'</span>'
   +'<span class="cnt">'+(nz?nz+"z":"")+'</span>'
   +'<select onchange="S.mm[\''+c+'\']=this.value">'
   +'<option value="">default</option>'
   +'<option '+(S.mm[c]==="blur"?"selected":"")+'>blur</option>'
   +'<option '+(S.mm[c]==="box"?"selected":"")+'>box</option>'
   +'<option '+(S.mm[c]==="mosaic"?"selected":"")+'>mosaic</option>'
   +'<option '+(S.mm[c]==="inpaint"?"selected":"")+'>inpaint</option></select>'
   +'</div>';
  // model-requiring categories: say so RIGHT HERE when the model is
  // missing (issue #18: a plate-only scan ran against no model and
  // found nothing — the only hint was one job-log line)
  if(on&&((c==="plate"&&!MS.plate)||((c==="person"||c==="screen")&&!MS.person))){
   h+='<div style="font-size:11px;color:#fbbf24;margin:-2px 0 3px 38px">'
    +(c==="plate"&&MS.plate_autofetch
      ?"no plate model installed yet &mdash; the recommended one downloads automatically when the scan starts"
      :"needs a detection model &mdash; download one in Settings (header gear &rarr; Detection models) or this category detects NOTHING")
    +'</div>';
  }
 }
 // the specific-text box shows whenever ANY window uses the category
 $("phrasebox").hidden=!unionCats().includes("phrase");
 const nTrk=(w.track||[]).length;
 const tact=S.cls==="trackobj"?"active":"";
 h+='<div class="catrow '+tact+'" style="border-top:1px solid #0f172a;margin-top:5px;padding-top:6px">'
  +'<span style="width:13px"></span>'
  +'<span class="sw" style="background:'+CATS.trackobj+'" onclick="setCls(\'trackobj\')"></span>'
  +'<span class="nm" onclick="setCls(\'trackobj\')">'+DN.trackobj+'</span>'
  +'<span class="cnt">'+(nTrk?nTrk+"&#9679;":"")+'</span></div>';
 const iact=S.cls==="ignore"?"active":"";
 h+='<div class="catrow '+iact+'" style="border-top:1px solid #0f172a;margin-top:5px;padding-top:6px">'
  +'<span style="width:13px"></span>'
  +'<span class="sw" style="background:'+CATS.ignore+'" onclick="setCls(\'ignore\')"></span>'
  +'<span class="nm" onclick="setCls(\'ignore\')">'+DN.ignore+'</span>'
  +'<span class="cnt">'+(S.ignore.length?S.ignore.length+"z":"")+'</span></div>';
 $("cats").innerHTML=h;
 winBar();
}
function togCat(c,on){const w=selWin();if(on)w.cats[c]=true;else delete w.cats[c];
 renderCats();summary();
 if(on&&c==="phrase"&&!$("phrases").value.trim())$("phrases").focus();}
function setCls(c){S.cls=c;S.selZone=null;
 // picking a zone class IS the intent to draw — switch modes for the user
 // (play is the default, so without this the first zone needs two clicks
 // and nothing explains why the frame ignores the pointer)
 if(S.mode!=="draw")setMode("draw");
 renderCats();draw();}
function hint(){
 if(S.mode==="play"){
  $("hint").innerHTML="&#9654; video controls active &mdash; "
   +"&#9998; Draw adds zones, &#8857; track objects";
  return;
 }
 if(S.mode==="draw"&&S.cls==="trackobj"){
  $("hint").innerHTML='&#127919; scrub to a frame where the object is '
   +'clear, then draw ON it — the scan tracks and blurs it through '
   +'<b style="color:#fbbf24">Window '+(S.sel+1)+'</b>';
  return;
 }
 $("hint").innerHTML=S.mode==="draw"
  ?('✏️ drawing <b style="color:'+CATS[S.cls]+'">'+(DN[S.cls]||S.cls)
    +'</b> zones for <b style="color:#fbbf24">Window '+(S.sel+1)+'</b>')
  :"select mode — click a zone to move it, Del removes it";
}

// ---------- zone drawing on the frame ----------
function listFor(cat){
 if(cat==="ignore")return S.ignore;
 if(cat==="trackobj")return (selWin().track=selWin().track||[]);
 return (selWin().zones[cat]=selWin().zones[cat]||[]);
}
function zoneList(){return listFor(S.cls);}
function pushUndo(){S.undo.push(JSON.stringify({w:S.wins,i:S.ignore}));
 if(S.undo.length>40)S.undo.shift();}
function undoZone(){
 const s=S.undo.pop();if(!s)return;
 const d=JSON.parse(s);S.wins=d.w;S.ignore=d.i;
 if(S.sel>=S.wins.length)S.sel=S.wins.length-1;
 tlHdr();renderCats();draw();tlDraw();
}
function hookZC(){
 const c=$("zc");
 if(c.dataset.hooked)return;c.dataset.hooked=1;
 // clamp to the frame: pointer capture keeps reporting past the canvas
 // edge, and a drag released below the video once stored a rect with
 // ny2=1.82 — an off-frame seed box that degraded tracking
 const pt=e=>{const r=c.getBoundingClientRect();
  return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),
          Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
 c.addEventListener("pointerdown",e=>{
  c.setPointerCapture(e.pointerId);prime();
  const p=pt(e);
  if(S.mode==="draw"){
   if(!S.anchor){S.anchor=p;S.fl=p;}
   else{finishRect(S.anchor,p);S.anchor=null;S.fl=null;}
   draw();return;
  }
  S.selZone=null;
  const w=selWin();
  const all=[["ignore",S.ignore],["trackobj",w.track||[]]]
   .concat(Object.entries(w.zones));
  outer:
  for(const [cat,rs] of all)
   for(let i=rs.length-1;i>=0;i--){const r=rs[i];
    if(p[0]>=r[0]&&p[0]<=r[2]&&p[1]>=r[1]&&p[1]<=r[3]){
     S.selZone={cat:cat,i:i};S.drag={off:[p[0]-r[0],p[1]-r[1]]};break outer;}}
  draw();
 });
 c.addEventListener("pointermove",e=>{
  const p=pt(e);
  if(S.mode==="draw"&&S.anchor){S.fl=p;draw();return;}
  if(S.mode==="select"&&S.selZone&&S.drag){
   const rs=listFor(S.selZone.cat);
   const r=rs[S.selZone.i],w=r[2]-r[0],h=r[3]-r[1];
   const x=Math.max(0,Math.min(1-w,p[0]-S.drag.off[0])),
         y=Math.max(0,Math.min(1-h,p[1]-S.drag.off[1]));
   rs[S.selZone.i]=[x,y,x+w,y+h].concat(r.slice(4));draw();
  }
 });
 c.addEventListener("pointerup",e=>{
  if(S.mode==="draw"&&S.anchor){
   const p=pt(e);
   if(Math.abs(p[0]-S.anchor[0])>0.01||Math.abs(p[1]-S.anchor[1])>0.01){
    finishRect(S.anchor,p);S.anchor=null;S.fl=null;draw();}
  }
  S.drag=null;
 });
 document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){
   if(S.anchor){S.anchor=null;S.fl=null;draw();}
   else if(S.mode!=="play")setMode("play");   // Esc closes the draw tool
  }
  if((e.key==="Delete"||e.key==="Backspace")&&S.mode==="select"&&S.selZone
     &&document.activeElement.tagName!=="INPUT"
     &&document.activeElement.tagName!=="TEXTAREA"){
   pushUndo();
   const rs=listFor(S.selZone.cat);
   rs.splice(S.selZone.i,1);S.selZone=null;renderCats();draw();
  }
 });
}
function finishRect(a,b){
 const r=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),
          Math.max(a[0],b[0]),Math.max(a[1],b[1])];
 if(r[2]-r[0]<0.01||r[3]-r[1]<0.01)return;
 pushUndo();
 const rr=r.map(v=>+v.toFixed(4));
 if(S.cls==="trackobj"){
  // a tracked object is drawn ON the object at THIS frame: remember the
  // reference time so the scan can template-track it both ways from here
  const v=$("vd");
  rr.push(+((v.currentTime||0)/Math.max(0.1,S.dur)).toFixed(4));
  listFor("trackobj").push(rr);
 }else{
  zoneList().push(rr);
  if(S.cls!=="ignore")selWin().cats[S.cls]=true;   // drawing switches it on
 }
 renderCats();summary();
}
function draw(){
 const c=$("zc"),g=c.getContext("2d");
 g.clearRect(0,0,c.width,c.height);
 const w=selWin(); if(!w)return;
 const rect=(r,col,label,seld)=>{
  const x=r[0]*c.width,y=r[1]*c.height,
        ww=(r[2]-r[0])*c.width,hh=(r[3]-r[1])*c.height;
  g.fillStyle=col+"22";g.fillRect(x,y,ww,hh);
  g.lineWidth=seld?3:2;g.strokeStyle=col;g.strokeRect(x,y,ww,hh);
  g.fillStyle=col;g.font="bold 11px sans-serif";
  g.fillRect(x,y,g.measureText(label).width+10,15);
  g.fillStyle="#fff";g.fillText(label,x+5,y+11);
 };
 for(const [cat,rs] of Object.entries(w.zones))
  rs.forEach((r,i)=>rect(r,CATS[cat]||"#94a3b8",DN[cat]||cat,
   S.selZone&&S.selZone.cat===cat&&S.selZone.i===i));
 S.ignore.forEach((r,i)=>rect(r,CATS.ignore,"ignore",
   S.selZone&&S.selZone.cat==="ignore"&&S.selZone.i===i));
 (w.track||[]).forEach((r,i)=>rect(r,CATS.trackobj,
   "track @"+fmt((r[4]||0)*S.dur),
   S.selZone&&S.selZone.cat==="trackobj"&&S.selZone.i===i));
 if(S.anchor&&S.fl){
  const a=S.anchor,b=S.fl;
  g.setLineDash([5,4]);g.strokeStyle=CATS[S.cls];g.lineWidth=2;
  g.strokeRect(Math.min(a[0],b[0])*c.width,Math.min(a[1],b[1])*c.height,
   Math.abs(b[0]-a[0])*c.width,Math.abs(b[1]-a[1])*c.height);
  g.setLineDash([]);
 }
 hint();
}
function setMode(m){S.mode=m;S.anchor=null;S.selZone=null;
 $("mplay").classList.toggle("on",m==="play");
 $("mdraw").classList.toggle("on",m==="draw");
 $("msel").classList.toggle("on",m==="select");
 // Play mode (the DEFAULT): the overlay lets clicks fall through to the
 // video's native controls. Without it the canvas swallowed every click,
 // so the video could not even be played and the draw tool looked
 // impossible to close (issue #17). Zones still render on the overlay.
 $("zc").style.pointerEvents=m==="play"?"none":"auto";
 $("zc").style.cursor=m==="draw"?"crosshair":"default";hint();draw();}

// ---------- windows ----------
function winBar(){
 const w=selWin(); if(!w)return;
 $("wname").textContent="◧ Window "+(S.sel+1);
 $("wtime").textContent=fmt(w.t0)+" – "+fmt(w.t1);
 const zs=Object.entries(w.zones).filter(([c,r])=>r.length)
   .map(([c,r])=>(DN[c]||c)+" ×"+r.length).join(", ");
 const nt=(w.track||[]).length;
 $("wzsum").textContent=(zs?("zones: "+zs):"no zones (whole frame)")
   +(nt?(" · tracked objects: "+nt):"");
 $("pastebtn").disabled=!S.paste;
 summary();
}
function addWin(){
 const v=$("vd");
 const c=Math.min(Math.max(v.currentTime||0,S.cin),S.cout);
 const half=Math.max(1,S.dur*0.03);
 pushUndo();
 S.wins.push(newWin(Math.max(S.cin,c-half),Math.min(S.cout,c+half),{}));
 S.sel=S.wins.length-1;
 tlHdr();renderCats();draw();tlDraw();
}
function delWin(){
 pushUndo();
 if(S.wins.length<=1){    // last window resets to the whole-clip default
  S.wins=[newWin(S.cin,S.cout,{})];S.sel=0;
 }else{S.wins.splice(S.sel,1);S.sel=Math.max(0,S.sel-1);}
 tlHdr();renderCats();draw();tlDraw();
}
function copyZones(){S.paste=JSON.parse(JSON.stringify(selWin().zones));winBar();}
function pasteZones(){if(!S.paste)return;pushUndo();
 selWin().zones=JSON.parse(JSON.stringify(S.paste));
 for(const c of Object.keys(selWin().zones))
  if(selWin().zones[c].length)selWin().cats[c]=true;
 renderCats();draw();}
function clearZones(){pushUndo();selWin().zones={};renderCats();draw();}
function clampWins(){
 S.wins.forEach(w=>{w.t0=Math.max(w.t0,S.cin);w.t1=Math.min(w.t1,S.cout);});
 S.wins=S.wins.filter(w=>w.t1-w.t0>0.2);
 if(!S.wins.length){S.wins=[newWin(S.cin,S.cout,{})];}
 if(S.sel>=S.wins.length)S.sel=S.wins.length-1;
}

// ---------- timeline (one lane per window + audio lanes) ----------
function tlH(){return RULER+WROW*S.wins.length+AROW*S.audio.length;}
function tlHdr(){
 let h='<div style="height:'+RULER+'px;color:#64748b;border-top:none">timeline</div>';
 S.wins.forEach((w,i)=>{h+='<div style="height:'+WROW+'px;'
  +(i===S.sel?'color:#fbbf24;font-weight:700':'')+'">W'+(i+1)+'</div>';});
 S.audio.forEach((a,i)=>{h+='<div style="height:'+AROW+'px">'+a.label
  +'<button class="mbtn '+(a.muted?"on":"off")
  +'" title="mute: remove this track from the output"'
  +' onclick="S.audio['+i+'].muted=!S.audio['+i+'].muted;tlHdr();tlDraw();summary()">M</button></div>';});
 $("tlhdr").innerHTML=h;
}
// txr: raw view-mapped x (may be off-canvas — used for handle hit tests so
// an off-view handle can never be grabbed at the clamped edge). tx: clamped
// for drawing.
function txr(t,w){const span=S.dur/S.zoom;
 return (t-S.view0)/Math.max(0.1,span)*w;}
function tx(t,w){return Math.max(0,Math.min(w,txr(t,w)));}
const MAXZ=40;
function setZoom(z){
 z=Math.max(1,Math.min(MAXZ,z));
 const span=S.dur/S.zoom,c=S.view0+span/2;   // keep the view center fixed
 S.zoom=z;
 const ns=S.dur/z;
 S.view0=Math.max(0,Math.min(Math.max(0,S.dur-ns),c-ns/2));
 $("zslide").value=Math.log(z)/Math.log(MAXZ);
 $("zlab").textContent=(z>=10?z.toFixed(0):z.toFixed(1).replace(/\.0$/,""))+"\u00d7";
 const ps=$("pslide");
 ps.disabled=z<=1.001;
 ps.value=S.dur-ns>0.01?Math.round(1000*S.view0/(S.dur-ns)):0;
 tlDraw();
}
function zoomBy(f){setZoom(S.zoom*f);}
function zoomSlide(v){setZoom(Math.pow(MAXZ,v));}
function panSlide(v){
 const ns=S.dur/S.zoom;
 S.view0=Math.max(0,Math.min(Math.max(0,S.dur-ns),(v/1000)*(S.dur-ns)));
 tlDraw();
}
function tlDraw(){
 const c=$("tl");if(!c||!S.dur)return;
 const w=c.clientWidth||600,H=tlH();
 c.width=w;c.height=H;c.style.height=H+"px";
 const g=c.getContext("2d");
 g.fillStyle="#0b1120";g.fillRect(0,0,w,H);
 g.fillStyle="#1e293b";g.fillRect(0,0,w,RULER);
 g.fillStyle="#64748b";g.font="9px ui-monospace,monospace";
 const span=S.dur/S.zoom;
 const step=span>1200?300:span>240?60:span>60?15:span>12?5:span>4?1:0.5;
 for(let t=Math.max(0,Math.ceil(S.view0/step)*step);
     t<=Math.min(S.dur,S.view0+span)+1e-6;t+=step){
  g.fillRect(tx(t,w),RULER-6,1,6);
  g.fillText(step>=1?fmt(t):t.toFixed(1)+"s",tx(t,w)+2,10);}
 S.wins.forEach((win,i)=>{
  const y=RULER+WROW*i;
  g.fillStyle="#181207";g.fillRect(0,y,w,WROW);
  g.fillStyle=i===S.sel?"#f59e0b":"#b45309";
  g.fillRect(tx(win.t0,w),y+3,Math.max(2,tx(win.t1,w)-tx(win.t0,w)),WROW-6);
  g.fillStyle="#fde68a";
  g.fillRect(tx(win.t0,w),y+2,3,WROW-4);g.fillRect(tx(win.t1,w)-3,y+2,3,WROW-4);
 });
 S.audio.forEach((a,i)=>{
  const y=RULER+WROW*S.wins.length+AROW*i;
  g.fillStyle=a.muted?"#111827":"#0a1428";g.fillRect(0,y,w,AROW);
  const ax0=tx(S.cin,w),ax1=tx(S.cout,w);
  g.fillStyle=a.muted?"#374151":"#1d4ed8";
  g.fillRect(ax0,y+3,Math.max(2,ax1-ax0),AROW-6);
  const wv=S.wave&&S.wave[i];
  if(wv&&wv.length){
   // per-pixel peak columns THROUGH the bar: scrub straight to a loud
   // noise or the first spoken words
   g.fillStyle=a.muted?"#6b7280":"#93c5fd";
   const span=S.dur/S.zoom,mid=y+AROW/2,hh=(AROW-10)/2;
   const px0=Math.max(0,Math.ceil(ax0)),px1=Math.min(w,Math.floor(ax1));
   for(let x=px0;x<px1;x++){
    const t=S.view0+x/w*span;
    if(t<S.cin||t>S.cout)continue;
    const pk=wv[Math.min(wv.length-1,
                         Math.max(0,Math.floor(t/S.dur*wv.length)))]||0;
    const hgt=Math.max(1,pk*hh);
    g.fillRect(x,mid-hgt,1,hgt*2);
   }
  }
  if(a.muted){g.fillStyle="#9ca3af";g.font="8.5px sans-serif";
   g.fillText("muted — removed from output",ax0+6,y+11);}
  else if(!(wv&&wv.length)&&i===0){
   // honest lane status instead of a silently flat bar: while decoding
   // show progress; on failure show the error so a report can name it
   const msg=S.waveBusy?"analyzing audio…":(S.waveErr||null);
   if(msg){g.fillStyle="#dbeafe";g.font="8.5px sans-serif";
    g.fillText(msg,ax0+6,y+AROW/2+3);}
  }
 });
 g.fillStyle="rgba(2,6,23,0.68)";
 g.fillRect(0,0,tx(S.cin,w),H);g.fillRect(tx(S.cout,w),0,w-tx(S.cout,w),H);
 g.fillStyle="#f8fafc";
 g.fillRect(tx(S.cin,w)-1,0,2,H);g.fillRect(tx(S.cout,w)-1,0,2,H);
 const v=$("vd");
 g.strokeStyle="#e2e8f0";g.beginPath();
 g.moveTo(tx(v.currentTime||0,w),0);g.lineTo(tx(v.currentTime||0,w),H);g.stroke();
 const full=S.cin<0.05&&S.cout>S.dur-0.05;
 $("foot").innerHTML=
  'keep: <b style="color:#e2e8f0">'+(full?"whole video":fmt(S.cin)+"–"+fmt(S.cout))+'</b>'
  +" · "+S.wins.map((x,i)=>'<b style="color:#fbbf24">W'+(i+1)+'</b> '
    +fmt(x.t0)+"–"+fmt(x.t1)).join(" · ");
 winBar();
}
function hookTL(){
 const c=$("tl");
 if(c.dataset.hooked)return;c.dataset.hooked=1;
 const tAt=e=>{const r=c.getBoundingClientRect();
  return Math.max(0,Math.min(S.dur,
   S.view0+(e.clientX-r.left)/r.width*(S.dur/S.zoom)));};
 c.addEventListener("pointerdown",e=>{
  c.setPointerCapture(e.pointerId);prime();
  const r=c.getBoundingClientRect(),px=e.clientX-r.left,py=e.clientY-r.top,
        w=c.clientWidth,t=tAt(e);
  if(Math.abs(px-txr(S.cin,w))<7){S.drag={k:"cin"};seek(S.cin);return;}
  if(Math.abs(px-txr(S.cout,w))<7){S.drag={k:"cout"};seek(S.cout);return;}
  if(py>=RULER&&py<RULER+WROW*S.wins.length){
   const i=Math.floor((py-RULER)/WROW),win=S.wins[i];
   if(S.sel!==i){S.sel=i;tlHdr();renderCats();draw();}
   if(Math.abs(px-txr(win.t0,w))<7){S.drag={k:"w0",i:i};seek(win.t0);}
   else if(Math.abs(px-txr(win.t1,w))<7){S.drag={k:"w1",i:i};seek(win.t1);}
   else if(t>=win.t0&&t<=win.t1){S.drag={k:"wm",i:i,off:t-win.t0};seek(t);}
   else{S.drag={k:"seek"};seek(t);}
   tlDraw();return;
  }
  S.drag={k:"seek"};seek(t);tlDraw();
 });
 c.addEventListener("pointermove",e=>{
  if(!S.drag)return;
  const t=tAt(e),d=S.drag;
  if(d.k==="cin"){S.cin=Math.min(t,S.cout-0.3);clampWins();seek(S.cin);tlHdr();}
  else if(d.k==="cout"){S.cout=Math.max(t,S.cin+0.3);clampWins();seek(S.cout);tlHdr();}
  else if(d.k==="w0"){const w0=S.wins[d.i];
   if(w0){w0.t0=Math.max(S.cin,Math.min(t,w0.t1-0.3));seek(w0.t0);}}
  else if(d.k==="w1"){const w1=S.wins[d.i];
   if(w1){w1.t1=Math.min(S.cout,Math.max(t,w1.t0+0.3));seek(w1.t1);}}
  else if(d.k==="wm"){const wm=S.wins[d.i];
   if(wm){const len=wm.t1-wm.t0;
    const a=Math.max(S.cin,Math.min(t-d.off,S.cout-len));
    wm.t0=a;wm.t1=a+len;seek(a);}}
  else if(d.k==="seek"){seek(t);}
  tlDraw();
 });
 c.addEventListener("pointerup",()=>{S.drag=null;tlHdr();tlDraw();});
}

// ---------- summary + custom cats + start ----------
function summary(){
 const el=$("summary");
 if(!S.dur){el.textContent="";return;}
 const muted=S.audio.filter(a=>a.muted).map(a=>a.label);
 const full=S.cin<0.05&&S.cout>S.dur-0.05;
 // categories start ALL OFF — flag the nothing-selected state loudly so an
 // empty scan is always a deliberate choice, never a surprise
 const nTrkAll=S.wins.reduce((a,w)=>a+((w.track||[]).length),0);
 if(!unionCats().length&&!nTrkAll){
  el.innerHTML='<span style="color:#fbbf24">&#9888; no categories selected '
   +'&mdash; nothing will be detected (check categories or draw a zone)</span>';
  return;
 }
 el.textContent=
  S.wins.length+" window"+(S.wins.length>1?"s":"")
  +(muted.length?" · muted: "+muted.join(","):"")
  +(full?"":" · output "+fmt(S.cin)+"–"+fmt(S.cout));
}
async function addCustom(){
 const n=$("ccname").value.trim(),rx=$("ccrx").value.trim();
 if(!n||!rx){alert("Both a name and a regex are required.");return;}
 const r=await fetch("/api/custom_cats",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({name:n,regex:rx})});
 if(r.ok){location.reload();return;}
 // show the server's reason (bad regex, duplicate name, matches empty
 // text…) — a bare "could not add" left people guessing
 let why="";
 try{const t=await r.text(),m=t.match(/<p>([\s\S]*?)<\/p>/);
  // DOMParser: decodes entities without running anything in the text
  why=new DOMParser().parseFromString(m?m[1]:"","text/html")
   .body.textContent.trim();}catch(e){}
 alert("Could not add the category"+(why?": "+why:"."));
}
async function loadCustomList(){
 try{
  const d=await (await fetch("/api/custom_cats")).json();
  const cats=Array.isArray(d)?d:(d.cats||[]);
  $("cclist").innerHTML=cats.map(x=>
   '<span class="chip"><span class="dot" style="background:'
   +(CATS[x.id]||"#94a3b8")+'"></span>'+x.id
   +' <b style="font-family:monospace">'+(x.regex||"")+'</b>'
   +' <span style="cursor:pointer;color:#f87171" title="remove this category"'
   +' onclick="delCustom(\''+x.id+'\')">&#10005;</span></span>').join("");
 }catch(e){}
}
async function delCustom(id){
 if(!confirm("Remove this category? Future scans stop detecting it; "
   +"existing reports are unaffected."))return;
 await fetch("/api/custom_cats/"+id,{method:"DELETE"});
 location.reload();
}
function unionCats(){
 const u={};S.wins.forEach(w=>Object.keys(w.cats).forEach(c=>u[c]=true));
 return Object.keys(u);
}
// Scan speed presets (engine SCAN_SPEEDS). Hints are the MEASURED trade
// on a synthetic moving-face clip with exact ground truth — keep them in
// step with the engine comment if the presets change.
const SPEED_HINT={
 thorough:"Detects on every frame at full resolution. Slowest, most complete.",
 balanced:"Every 2nd frame, with the gaps interpolated along each face's path. "
  +"Measured coverage is essentially unchanged.",
 fast:"Every 3rd frame. Fast-moving faces lose a little coverage, and a face "
  +"on screen for under 3 frames can be missed. Review carefully.",
 fastest:"Every 3rd frame at half detection resolution: misses many small or "
  +"distant faces. Use only for close-up footage, and review carefully."};
function speedHint(){
 const v=$("sspeed").value,h=$("sspeedhint");
 h.textContent=SPEED_HINT[v]||"";
 h.style.color=(v==="fast"||v==="fastest")?"#fbbf24":"";
}
const MAXUP=+"8589934592"||0;  // server upload cap in bytes (0 = unlimited),
                              // injected at serve time like 1.0.96
const FREEDISK=+"0"||0; // server free disk at page load (bytes,
                              // 0 = unknown): refuse a doomed upload EARLY
// which model-requiring detectors would actually find a model (issue #18):
// optimistic defaults so nothing cries wolf before the fetch lands
let MS={plate:true,person:true,plate_autofetch:true};
fetch("/api/model_status").then(r=>r.json())
 .then(d=>{MS=Object.assign(MS,d);if(S.dur)renderCats();}).catch(()=>{});
async function startScan(){
 if(!S.dur){alert("Load a video first.");return;}
 if(!S.file&&!$("spath").value.trim()){alert("Choose a file or server path.");return;}
 if(S.file&&MAXUP>0&&S.file.size>MAXUP){
  alert("This file is "+(S.file.size/1073741824).toFixed(1)+" GB — over the "
   +"server's "+(MAXUP/1073741824).toFixed(0)+" GB upload limit, so the "
   +"upload would be rejected. Either restart the server with a higher "
   +"limit (--max-upload-gb N, or OPENSCRUB_MAX_UPLOAD_GB=N in Docker; "
   +"0 = unlimited), or — better for files this big — put the file where "
   +"the server can read it and use the 'path on the server' box instead "
   +"of uploading.");return;}
 if(S.file&&FREEDISK>0&&S.file.size+1073741824>FREEDISK){
  alert("This file is "+(S.file.size/1073741824).toFixed(1)+" GB but the "
   +"server only has "+(FREEDISK/1073741824).toFixed(1)+" GB of disk free — "
   +"the upload would fill the disk and be refused. Delete old jobs in the "
   +"Jobs list below (each keeps its upload and output until deleted), or "
   +"use the 'path on the server' box, which reads the file in place "
   +"without copying it.");return;}
 if(S.file){
  // the same file may ALREADY be on the server: a failed job keeps its
  // upload for Retry, and re-uploading stores another full copy — a real
  // user disk filled up exactly this way (issue #16)
  try{
   const js=await(await fetch("/api/jobs")).json();
   const dup=Array.isArray(js)&&js.find(j=>j.name===S.file.name&&j.size===S.file.size&&j.size>0);
   if(dup&&!confirm("“"+S.file.name+"” ("+(S.file.size/1073741824).toFixed(1)
    +" GB) is already on the server — job “"+dup.name+"”, status: "+dup.phase
    +".\n\nA failed job has a ↻ Retry button in the Jobs list that re-runs "
    +"the scan WITHOUT uploading again.\n\nUpload a duplicate copy anyway?"))return;
  }catch(e){}
 }
 const cats=unionCats();
 if(cats.includes("phrase")&&!$("phrases").value.trim()){
  alert("Specific text is checked but no text is entered — type the "
   +"words or phrases to blur (one per line), or uncheck the category.");
  $("phrases").focus();return;}
 const nTrk=S.wins.reduce((a,w)=>a+((w.track||[]).length),0);
 if(!cats.length&&!nTrk
   &&!confirm("No categories are enabled and no objects are marked for "
   +"tracking — nothing will be detected. Start anyway?"))return;
 // model-requiring categories with no model detect NOTHING (issue #18) —
 // re-check live (a model may have been downloaded since page load)
 try{MS=Object.assign(MS,await(await fetch("/api/model_status")).json());}catch(e){}
 if((cats.includes("person")||cats.includes("screen"))&&!MS.person
   &&!confirm("The person/screen categories need a detection model that "
   +"isn't installed — they will detect NOTHING this scan.\n\nDownload one "
   +"in Settings (header gear → Detection models), or pick a Detection "
   +"quality tier there.\n\nStart the scan anyway?"))return;
 if(cats.includes("plate")&&!MS.plate&&!MS.plate_autofetch
   &&!confirm("The plate category needs a detection model that isn't "
   +"installed and can't be fetched automatically — it will detect "
   +"NOTHING this scan.\n\nDownload one in Settings → Detection "
   +"models.\n\nStart anyway?"))return;
 // iOS Safari can hand back a <select> with NO selection (value ""),
 // e.g. after restoring the page — the server then got engine:"" (a real
 // job hung on it). Put any such select back on its page default first.
 document.querySelectorAll("select").forEach(s=>{
  if(s.selectedIndex<0&&s.options.length){
   const d=[...s.options].findIndex(op=>op.defaultSelected);
   s.selectedIndex=d>=0?d:0;}});
 const o={
  engine:$("engine").value,device:$("device").value,encoder:$("encoder").value,
  mode:$("mode").value,coverage:$("coverage").value,sample_interval:+$("si").value,scan_trigger:+$("st").value,
  pad:+$("pad").value,bridge_gap:+$("bgap").value,
  face_expand:+$("fex").value,face_threshold:+$("fthr").value,
  plate_threshold:$("pthr").value.trim()===""?null:+$("pthr").value,
  face_shape:$("fshape").value,detect_scale:+$("dscale").value,
  scan_speed:$("sspeed").value,
  hdr_output:$("hdrout").value,codec:$("vcodec").value,
  out_format:$("outfmt").value,
  out_quality:$("outqual").value,
  allow_names:$("allow").value,extra_names:$("extra").value,
  phrases:cats.includes("phrase")?$("phrases").value:"",
  face_heads:$("faceheads").checked,
  audio_pii:$("audiopii").checked,skip_review:$("skiprev").checked,
  no_memory:$("nomem").checked,preview_mode:$("pmode").checked,
  draw_scores:$("drawscores").checked,
  use_zones:false,           // zones travel inside the windows now
  categories:cats.length?cats.join(","):"none",
  mode_map:Object.entries(S.mm).filter(([c,m])=>m)
    .map(([c,m])=>c+"="+m).join(","),
  clip_frac:(S.cin>0.05||S.cout<S.dur-0.05)
    ?((S.cin/S.dur).toFixed(4)+"-"+(S.cout/S.dur).toFixed(4)):"",
  mute_tracks:S.audio.length===1&&S.audio[0].muted?"all"
    :S.audio.map((a,i)=>a.muted?String(i+1):"").filter(Boolean).join(","),
  // how many lanes the browser showed: it lists only playable tracks
  // (iPhone spatial audio is hidden), so the engine needs this to map
  // the mute numbers onto the file's real tracks — and fails closed
  audio_lanes:S.audio.length,
  windows:S.wins.map(w=>({t0:+(w.t0/S.dur).toFixed(4),
    t1:+(w.t1/S.dur).toFixed(4),cats:Object.keys(w.cats),zones:w.zones,
    track:w.track||[]})),
  ignore_zones:S.ignore,
 };
 const fd=new FormData();
 if(S.file)fd.append("video",S.file);
 fd.append("server_path",$("spath").value.trim());
 fd.append("options",JSON.stringify(o));
 const btns=document.querySelectorAll("button");btns.forEach(b=>b.disabled=true);
 const sum=$("summary");
 // XHR instead of fetch: it reports UPLOAD progress, which is the whole
 // wait when the UI is reached over the internet (upstream-bound)
 const xhr=new XMLHttpRequest();
 xhr.open("POST","/api/jobs");
 xhr.upload.onprogress=e=>{if(e.lengthComputable){
  const p=Math.round(100*e.loaded/e.total);
  sum.textContent=p<100?("uploading… "+p+"%"):"upload received — queuing…";}};
 const fail=msg=>{btns.forEach(b=>b.disabled=false);summary();
  alert("Could not start: "+msg);};
 xhr.onerror=()=>fail("upload failed — check the connection and try again");
 xhr.onload=()=>{
  let j={};try{j=JSON.parse(xhr.responseText);}catch(e){}
  if(xhr.status>=400||j.error)fail(j.error||("HTTP "+xhr.status));
  else{
   // queued — jobs live on this same page now: refresh the list, jump to
   // it, and free the editor for the next clip
   btns.forEach(b=>b.disabled=false);
   sum.textContent="job queued ✓ — progress in Jobs below";
   if(typeof loadJobs==="function"){loadJobs();
    if(j.jobs&&j.jobs.length&&typeof openJob==="function")openJob(j.jobs[0]);}
   const jl=document.getElementById("jobs");
   if(jl)jl.scrollIntoView({behavior:"smooth"});
  }
 };
 sum.textContent=S.file?"uploading… 0%":"submitting…";
 xhr.send(fd);
}
setMode("play");loadCustomList();   // play by default: drawing is opt-in (#17)
speedHint();
