"""Bounded introduced work, uninstrumented timings first; normal GC throughout."""
import base64
import builtins
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

import cv2
import openscrub_web as web
from openscrub_internal import exact_samples as exact

root=Path(os.environ['VERIFY_RUN'])
manifest=json.loads(Path(os.environ['OPENSCRUB_EXACT_MEDIA']).read_text())
video=manifest['cfr5']['path']
web.TOKEN=None
result=dict(python=sys.version,opencv=cv2.__version__,opencv_build=cv2.getBuildInformation(),
    input=manifest['cfr5'],timing_contract='normal GC; fixtures outside timing; five samples; median is not p95; Flask production routes, no network timing',
    source_head=json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())['head'])
facts=dict(stream=0,width=320,height=180)
timelines={n:dict(render_state=dict(fps=30.,cum=[[i*.25,-i*.125] for i in range(n)])) for n in (300,120000)}
traversal={}
for n,doc in timelines.items():
    exact.timeline(doc,facts)
    samples=[];outputs=[]
    for _ in range(5):
        start=time.perf_counter();value=exact.timeline(doc,facts);elapsed=time.perf_counter()-start
        samples.append(elapsed);outputs.append(value[2])
    assert len(set(outputs))==1
    traversal[n]=dict(count=n,samples_s=samples,median_s=statistics.median(samples),digests=outputs)
result['traversal']=traversal

def job():
    value=web.new_job(video,{},'synthetic-cfr5.mp4');value['phase']='review'
    row=dict(category='manual',text='synthetic',enabled=True,t_start=0.,t_end=2.,last_seen=.5,cbox=[20,30,50,60],aoff=[0,0],confidence=1.,opaque={'preserved':[None,False]})
    doc=dict(provenance=dict(input=video,settings={}),render_state=dict(fps=5,cum=[[i,-i] for i in range(10)]),detections=[row,dict(row,enabled=False)])
    (Path(value['dir'])/'report.json').write_text(json.dumps(doc))
    return value

def record(response):
    assert response.status_code==200,response.get_data(as_text=True)
    body=response.get_json();image=body.pop('image',None)
    output=dict(status=response.status_code,response_bytes=len(response.get_data()),body=body)
    if image:
        raw=base64.b64decode(image['base64'])
        output['image']=dict(mime=image['mime'],bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    response.close();return output

cold=[job() for _ in range(5)];warm=job();requests={}
with web.app.test_client() as client:
    for name,jobs in [('cold',cold),('reused',[warm]*5),('legacy_choice',[warm]*5)]:
        if name=='reused':result['warmup']=record(client.get('/api/jobs/'+warm['id']+'/edit_sample?t=0.2'))
        samples=[];outputs=[]
        payloads=[{'enabled':{'0':bool(i%2)}} for i in range(5)]
        for i,current in enumerate(jobs):
            url='/api/jobs/'+current['id']
            start=time.perf_counter()
            response=(client.post(url+'/detections',json=payloads[i]) if name=='legacy_choice' else client.get(url+'/edit_sample?t=0.2'))
            response.get_data();elapsed=time.perf_counter()-start
            samples.append(elapsed);outputs.append(record(response))
        requests[name]=dict(count=5,samples_s=samples,median_s=statistics.median(samples),outputs=outputs)
result['requests']=requests
# Allocation instrumentation is deliberately after ALL elapsed measurements.
allocations={}
for n,doc in timelines.items():
    tracemalloc.start()
    exact.timeline(doc,facts)
    current,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    allocations[n]=dict(current_bytes=current,peak_bytes=peak,boundary='projection/hash only; parsed timeline allocated before tracing')
result['allocation_instrumentation']=allocations
# Count actual production boundaries after timing, without labeling these as elapsed measurements.
counts=dict(probes=0,preparations=0,report_reads=0,source_opens=0,decoder_opens=0,decoder_reads=0,decoder_releases=0,indexed_reads=0,descriptor_commits=0,timelines=0)
original=dict(probe=web._probe_exact_source,prepare=web._prepare_observed_source,select=web._select_observed_locked,read=exact.read_indexed_capture,timeline=exact.timeline,cap=cv2.VideoCapture,open=builtins.open)
active=[None]
def probe(*a,**kw):counts['probes']+=1;return original['probe'](*a,**kw)
def prepare(*a,**kw):counts['preparations']+=1;return original['prepare'](*a,**kw)
def select(*a,**kw):
    before=web.FILES.initialize(a[0]).current_source;selected=original['select'](*a,**kw)
    counts['descriptor_commits']+=int(before is not selected);return selected
def read(*a,**kw):counts['indexed_reads']+=1;return original['read'](*a,**kw)
def timeline(*a,**kw):counts['timelines']+=1;return original['timeline'](*a,**kw)
def opened(file,*a,**kw):
    if isinstance(file,(str,os.PathLike)):
        name=os.fspath(file)
        if name==video:counts['source_opens']+=1
        if active[0] and name==str(Path(active[0]['dir'])/'report.json'):counts['report_reads']+=1
    return original['open'](file,*a,**kw)
class Capture:
    def __init__(self,*a,**kw):counts['decoder_opens']+=1;self.cap=original['cap'](*a,**kw)
    def __getattr__(self,key):return getattr(self.cap,key)
    def read(self):counts['decoder_reads']+=1;return self.cap.read()
    def release(self):counts['decoder_releases']+=1;return self.cap.release()
observations=[]
fresh=job()
try:
    web._probe_exact_source=probe;web._prepare_observed_source=prepare;web._select_observed_locked=select
    exact.read_indexed_capture=read;exact.timeline=timeline;cv2.VideoCapture=Capture;builtins.open=opened
    with web.app.test_client() as client:
        for label,current in [('cold',fresh),('reused',fresh),('legacy_choice',fresh)]:
            active[0]=current;before=dict(counts);url='/api/jobs/'+current['id']
            response=client.post(url+'/detections',json={'enabled':{'0':False}}) if label=='legacy_choice' else client.get(url+'/edit_sample?t=0.2')
            output=record(response)
            delta={key:counts[key]-before[key] for key in counts}
            observations.append(dict(kind=label,counts=delta,output=output))
finally:
    web._probe_exact_source=original['probe'];web._prepare_observed_source=original['prepare'];web._select_observed_locked=original['select']
    exact.read_indexed_capture=original['read'];exact.timeline=original['timeline'];cv2.VideoCapture=original['cap'];builtins.open=original['open']
assert [o['counts']['probes'] for o in observations]==[1,0,0]
assert [o['counts']['descriptor_commits'] for o in observations]==[1,0,0]
assert [o['counts']['decoder_reads'] for o in observations]==[1,1,0]
assert [o['counts']['report_reads'] for o in observations]==[1,1,1]
assert [o['counts']['timelines'] for o in observations]==[1,1,0]
assert web.FILES.count==0
result['instrumented_observations']=observations
result['request_totals']=dict(untimed_warmup=1,timed_cold=5,timed_reused=5,timed_legacy_choice=5,instrumented=3,total=19)
(root/'logs/costs.json').write_text(json.dumps(result,indent=2)+'\n')
print('INTRODUCED_COSTS',json.dumps(dict(traversal={n:v['median_s'] for n,v in traversal.items()},requests={k:v['median_s'] for k,v in requests.items()},allocation=allocations,observations=[dict(kind=o['kind'],counts=o['counts']) for o in observations],totals=result['request_totals'])),flush=True)
