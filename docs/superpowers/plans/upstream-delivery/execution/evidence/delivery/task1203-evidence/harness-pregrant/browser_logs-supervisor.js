// Synthetic inputs and independent DOM/cursor validation; never imported by PAGE.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const base=process.env.POLLING_BASE,label=process.env.MEASURE_LABEL,phase=process.env.MEASURE_PHASE;
const identity=JSON.parse(process.env.MEASURE_IDENTITY),root=process.env.TASK1203_ROOT;
const cases=['short','multiline','long','dense-multiline'],checkpoints=[1000,2000,3000],batchSize=20;
function fixture(kind,i){const n=String(i).padStart(6,'0');
 if(kind==='short')return 'progress '+n+' 50% synthetic callback';
 if(kind==='multiline')return Array.from({length:8},(_,j)=>'tool '+n+' line '+j+' ordinary output').join('\n');
 if(kind==='long')return n+'x'.repeat(8192-6);
 const first=n+'x'.repeat(25);return first+'\n'+('x'.repeat(31)+'\n').repeat(254)+'x'.repeat(32);
}
const hash=text=>crypto.createHash('sha256').update(text).digest('hex');
const records=[];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn){for(let i=0;i<2000;i++){if(await fn())return;await pause(5)}throw Error('measurement condition expired')}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{for(const kind of cases){
  const page=await browser.newPage({viewport:{width:1280,height:950},deviceScaleFactor:1}),errors=[],diagnostics=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))diagnostics.push(m.text())});
  await page.route('**/api/**',route=>{const u=new URL(route.request().url());
   if(/^\/api\/jobs\/A(\/log)?$/.test(u.pathname))return route.continue();
   return route.fulfill({json:u.pathname==='/api/jobs'?[]:u.pathname==='/api/quality_tier'?{tiers:[],current:'fast'}:{}})});
  await page.addInitScript(instrument=>{
   window.qaSamples=[];window.qaTransport=[];window.qaLongTasks=[];window.qaFrames=[];window.qaPublishing=false;window.qaCounts={units:0,textNodes:0,spans:0,fragments:0};
   const fetchNative=fetch.bind(window);window.fetch=async(...args)=>{const url=String(args[0]),start=performance.now(),r=await fetchNative(...args),headers=performance.now();
    if(/^api\/jobs\/A(?:\/log\?|$)/.test(url)){const json=r.json.bind(r);r.json=async()=>{const begin=performance.now(),body=await json();window.qaTransport.push({url,headersMs:headers-start,bodyMs:performance.now()-begin,totalMs:performance.now()-start,bytes:+r.headers.get('content-length'),from:body.from,len:body.len,base:body.base,reset:body.reset,count:body.lines?.length});return body}}return r};
   new PerformanceObserver(list=>{for(const e of list.getEntries())window.qaLongTasks.push({start:e.startTime,duration:e.duration})}).observe({type:'longtask',buffered:true});
   let previous=performance.now();function beat(now){window.qaFrames.push({start:previous,end:now,duration:now-previous});previous=now;requestAnimationFrame(beat)}requestAnimationFrame(beat);
   if(instrument){
    const descriptor=Object.getOwnPropertyDescriptor(Node.prototype,'textContent');Object.defineProperty(Node.prototype,'textContent',{...descriptor,set(value){if(window.qaPublishing&&this.id==='log')window.qaCounts.units+=String(value).length;descriptor.set.call(this,value)}});
    const text=document.createTextNode.bind(document),element=document.createElement.bind(document),fragment=document.createDocumentFragment.bind(document);
    document.createTextNode=value=>{if(window.qaPublishing){window.qaCounts.units+=String(value).length;window.qaCounts.textNodes++}return text(value)};
    document.createElement=(name,...args)=>{if(window.qaPublishing&&name==='span')window.qaCounts.spans++;return element(name,...args)};
    document.createDocumentFragment=()=>{if(window.qaPublishing)window.qaCounts.fragments++;return fragment()};
   }
  },phase==='instrumentation');
  const control=async data=>{const r=await page.request.post(base+'/__qa__/control',{data});assert.equal(r.status(),200)};
  await control({action:'seed',count:0});
  let emitted=0,producer=[],producerBytes=0,expected=[];
  const inputHash=crypto.createHash('sha256');
  async function emit(count){const lines=Array.from({length:count},(_,j)=>fixture(kind,emitted+j));
   for(const line of lines){const size=Buffer.byteLength(line);assert.ok(size<=8192);inputHash.update(line+'\n');
    while(producer.length&&(producer.length>=2000||producerBytes+size>524288))producerBytes-=Buffer.byteLength(producer.shift());
    producer.push(line);producerBytes+=size;}
   await control({action:'append',lines});emitted+=count;return lines;
  }
  await emit(400);
  await page.goto(base);assert.equal(await page.title(),'OpenScrub');
  async function validate(stage,lines,initial=false){
   if(initial)expected=producer.slice(-400);else expected.push(...lines);
   if(label==='candidate')while(expected.length>800||2*(expected.reduce((n,s)=>n+s.length,0)+Math.max(0,expected.length-1))>2097152)expected.shift();
   const record=await page.evaluate(async()=>{
    if(POLL){clearTimeout(POLL.handle);POLL=null}
    const e=document.getElementById('log'),text=e.textContent,buffer=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
    const data={cursor:LOGN,units:text.length,hash:[...new Uint8Array(buffer)].map(x=>x.toString(16).padStart(2,'0')).join(''),entries:e.children.length,
     contentNodes:[...e.children].filter(s=>s.firstChild?.nodeType===3).length,delimiters:[...e.children].reduce((n,s)=>n+Math.max(0,s.childNodes.length-1),0),
     first:e.firstElementChild?.dataset.seq,last:e.lastElementChild?.dataset.seq,top:e.scrollTop,max:e.scrollHeight-e.clientHeight,
     sample:window.qaSamples.shift(),transport:window.qaTransport.splice(0),counts:{...window.qaCounts},longTasks:window.qaLongTasks.splice(0),frames:window.qaFrames.splice(0)};
    return data;
   });
   assert.equal(record.cursor,emitted);assert.equal(record.units,expected.join('\n').length);assert.equal(record.hash,hash(expected.join('\n')));
   assert.equal(record.sample.cursor,emitted);assert.equal(record.transport.filter(r=>r.url.includes('/log?')).length,1);
   const log=record.transport.find(r=>r.url.includes('/log?'));assert.equal(log.len,emitted);assert.equal(log.from,emitted-(initial?producer.length:lines.length));assert.equal(log.base,emitted-producer.length);assert.equal(log.count,initial?producer.length:lines.length);assert.equal(log.reset,initial&&producer.length<emitted?'stale':null);
   if(label==='candidate'){assert.equal(record.entries,expected.length);assert.equal(record.contentNodes,expected.length);assert.equal(record.delimiters,Math.max(0,expected.length-1));assert.equal(+record.first,emitted-expected.length);assert.equal(+record.last,emitted-1);assert.ok(2*record.units<=2097152)}
   record.stage=stage;record.emitted=emitted;record.expectedEntries=expected.length;record.kind=kind;record.label=label;record.phase=phase;
   records.push(record);return record;
  }
  await page.evaluate(()=>{window.qaCycleStart=performance.now();openJob('A')});await wait(()=>page.evaluate(n=>LOGN===n&&POLL_CYCLE===null,emitted));await validate('initial',[],true);
  const steps=phase==='timing'?130:31;
  for(let step=0;step<steps;step++){
   const lines=await emit(batchSize);await page.evaluate(()=>{window.qaCounts={units:0,textNodes:0,spans:0,fragments:0};window.qaCycleStart=performance.now();refresh()});
   await wait(()=>page.evaluate(n=>LOGN===n&&POLL_CYCLE===null,emitted));const result=await validate(step<5&&phase==='timing'?'warmup':'observed',lines);
   if(checkpoints.includes(emitted)){
    await page.locator('#log').scrollIntoViewIfNeeded();await page.locator('#log').hover();
    await page.evaluate(()=>{window.qaInput={start:performance.now()};document.getElementById('log').addEventListener('wheel',()=>{window.qaInput.eventMs=performance.now()-window.qaInput.start;requestAnimationFrame(()=>window.qaInput.frameMs=performance.now()-window.qaInput.start)},{once:true,passive:true})});
    await page.mouse.wheel(0,-100);await wait(()=>page.evaluate(()=>window.qaInput.frameMs!==undefined));await pause(80);
    const moved=await page.locator('#log').evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop);assert.ok(moved>=50);
    result.idlePostBatchWheel={...await page.evaluate(()=>window.qaInput),distanceFromBottom:moved};
    await page.locator('#log').evaluate(e=>e.scrollTop=e.scrollHeight);

   }
  }
  assert.equal(emitted,phase==='timing'?3000:1020);assert.deepEqual(errors,[]);assert.deepEqual(diagnostics,[]);
  records.push({kind,label,phase,fixtureHash:inputHash.digest('hex'),emitted,errors,diagnostics,browser:browser.version(),identity});
  fs.writeFileSync(root+'/measurement-'+label+'-'+phase+'.json',JSON.stringify(records));
  console.log(JSON.stringify({kind,label,phase,emitted,observations:phase==='timing'?125:31,errors,diagnostics}));await page.close();
 }}finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
