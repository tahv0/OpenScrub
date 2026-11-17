import sys,pathlib,random,time,statistics,json,dataclasses,collections,hashlib
sys.path.insert(0,'/tmp/openscrub-task112/base')
import openscrub as c
from rapidfuzz import fuzz
assert pathlib.Path(c.__file__).resolve()==pathlib.Path('/tmp/openscrub-task112/base/openscrub.py')
lines=pathlib.Path(c.__file__).read_text().splitlines()
marks={s:next(i+1 for i,l in enumerate(lines) if l.strip()==s) for s in ['if st <= m.last_seen + 0.01:', 'if m.category != d.category or not boxes_overlap(m.cbox, d.cbox):', 'if scans and fuzz:']}
def fixture(n,k,mode):
    scans=[]; ds=[]
    for i in range(n):
        rng=random.Random(83011+(i if mode=='unique' else 0)); text=''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(24))+'@sample.invalid'
        scans.append((i/3,(0.,0.),[(text,(8,8,150,28),.99)]))
        if i >= n-k: ds.append(c.Detection(i/3,0,(8,8,150,28),'email',text,.99))
    return ds,scans
out=[]
for n,k,mode in [(100,100,'unique'),(300,300,'unique'),(10000,30,'unique'),(1000,1000,'repeated')]:
    samples=[]
    for i in range(8):
        ds,sc=fixture(n,k,mode); t=time.perf_counter_ns(); result=c.merge_detections(ds,.5,scans=sc,fuzz=fuzz); elapsed=time.perf_counter_ns()-t
        if i>=3: samples.append(elapsed)
    ds,sc=fixture(n,k,mode); counts=collections.Counter(); tail_start=[None]
    def trace(f,event,arg):
        if f.f_code is c.merge_detections.__code__ and event=='line':
            for name,line in marks.items():
                if f.f_lineno==line:
                    counts[name]+=1
                    if name=='if scans and fuzz:': tail_start[0]=time.perf_counter_ns()
        return trace
    sys.settrace(trace); start=time.perf_counter_ns(); records=c.merge_detections(ds,.5,scans=sc,fuzz=fuzz); end=time.perf_counter_ns(); sys.settrace(None)
    out.append(dict(n=n,k=k,mode=mode,total_ns=samples,median_ns=statistics.median(samples),trace_counts=counts,trace_total_ns=end-start,trace_tail_ns=end-tail_start[0],records=[dataclasses.asdict(d) for d in records]))
pathlib.Path('/tmp/openscrub-task112/evidence/baseline-attribution.json').write_text(json.dumps(out,indent=2))
for r in out: print({k:v for k,v in r.items() if k!='records'})
