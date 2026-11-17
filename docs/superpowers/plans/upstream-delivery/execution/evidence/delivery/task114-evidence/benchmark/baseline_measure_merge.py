#!/usr/bin/env python3
"""Task114 measured adoption gate; full modules, normal GC, mutable copies.
Run validation before declaring hashes to the supervisor. No clocks used by validate.
"""
import argparse, collections, copy, dataclasses, gc, gzip, hashlib, importlib.util
import inspect, json, pathlib, platform, random, re, statistics, sys, time
ROOT=pathlib.Path('/tmp/openscrub-task114')
EVIDENCE=ROOT/'evidence'
BASE_HASH='0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7'
SIZES=(120,480)
WORKLOADS=('mixed_grid','email_grid','email_colocated','repeated_colocated')

def digest(b):return hashlib.sha256(b).hexdigest()
def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def load(label, path, expected):
    path=pathlib.Path(path).resolve()
    assert digest(path.read_bytes())==expected,(path,expected)
    spec=importlib.util.spec_from_file_location('task114_'+label,path)
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    assert pathlib.Path(m.__file__).resolve()==path
    print(json.dumps({'source':label,'path':str(path),'sha256':expected}),flush=True)
    return m

def text_for(i, category):
    rng=random.Random(11483011+i)
    if category=='email':return ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(24))+'@demo.org'
    if category=='phone':return '202-555-'+str(1000+i%9000)
    if category=='mrn':return str(7000000+i)
    raise AssertionError(category)

def fixture(m, workload, n):
    primary=[]; scans=[]; claimed=[]
    for i in range(n):
        cat=('email','phone','mrn')[i%3] if workload=='mixed_grid' else 'email'
        text=text_for(0 if workload=='repeated_colocated' else i,cat)
        slot=0 if 'colocated' in workload else i%48
        x=25+(slot%4)*300;y=20+(slot//4)*55
        box=(x,y,x+220,y+28);t=i*.5
        words=[(text,box,.99),('velvet',(25,690,95,710),.99),('harbor',(115,690,185,710),.99)]
        # Actual detector; no miniature classifier, no namer/model inference.
        found=m.detect_phi(words, [], t, (0,0), None, re.compile(m.RE_MRN_DEFAULT))
        hits=[d for d in found if d.category==cat and d.text==text and d.cbox==box]
        assert len(hits)==1,(workload,i,text,[(d.category,d.text) for d in found])
        assert len(found)==1,(workload,i,[(d.category,d.text) for d in found])
        d=hits[0];primary.append(dataclasses.asdict(d)); scans.append((t,(0,0),words));claimed.append((cat,text))
    # Represent the primary + duplicate recall records demonstrated by the
    # retained actual scan baseline, without benchmarking reverse_pass here.
    dets=primary+copy.deepcopy(primary)
    return {'name':f'{workload}_{n}','workload':workload,'scans_n':n,
            'frame':[1280,720],'duration_seconds':(n-1)*.5,
            'hold':.8,'bridge_gap':4.,'dets':dets,'scans':scans,'claimed':claimed}

def validate(m):
    from rapidfuzz import fuzz
    import rapidfuzz,cv2,numpy
    fixtures=[];details=[]
    for workload in WORKLOADS:
        for n in SIZES:
            f=fixture(m,workload,n)
            for cat,text in f['claimed']:
                norm=m.PhiMemory.norm(text);assert len(norm)>=4 and norm not in m.STOPWORDS
                mem=m.PhiMemory();mem.add(text,cat);assert mem.items[norm]==cat
                assert mem._gated(norm,cat)==cat and mem.recall(text)==cat
            maxratio=maxpartial=0; collisions=0
            unique=list(dict.fromkeys(text for cat,text in f['claimed'] if cat=='email'))
            for i,a in enumerate(unique):
                for b in unique[:i]:
                    ra=fuzz.ratio(m.PhiMemory.norm(a),m.PhiMemory.norm(b));pa=fuzz.partial_ratio(m.PhiMemory.norm(a),m.PhiMemory.norm(b))
                    maxratio=max(maxratio,ra);maxpartial=max(maxpartial,pa)
                    collisions+=int(ra>=70 or pa>=85)
            assert collisions==0
            benign=[]
            for text in ('velvet','harbor'):
                norm=m.PhiMemory.norm(text);assert len(norm)>=4 and norm not in m.STOPWORDS
                mem=m.PhiMemory()
                for cat,t in f['claimed']:mem.add(t,cat)
                # Reverse uses lenient ratio and +/-2 length; all email tokens
                # are longer, phone/numeric tokens cannot match this alpha.
                assert mem.recall(text) is None
                eligible=[(k,c) for k,c in mem.items.items() if c in set(c for c,t in f['claimed']) and mem._gated(k,c) is not None]
                matches=[k for k,c in eligible if (k.isdigit() and norm.isdigit() and len(k)==len(norm) and sum(x!=y for x,y in zip(k,norm))<=2) or (not k.isdigit() and not norm.isdigit() and abs(len(k)-len(norm))<=2 and fuzz.ratio(k,norm)>=76)]
                assert not matches
                benign.append({'text':text,'normalized':norm,'stopword':False,'forward_recall':None,'reverse_matches':matches})
            f.pop('claimed');fixtures.append(f)
            details.append({'case':f['name'],'actual_primary_count':n,'raw_count':len(f['dets']),
                            'category_counts':dict(collections.Counter(d['category'] for d in f['dets'])),
                            'unique_email_count':len(unique),'email_pair_max_ratio':maxratio,
                            'email_pair_max_partial':maxpartial,'email_matching_pairs':collisions,
                            'benign':benign,'frame':f['frame'],'positions':1 if 'colocated' in workload else 48,
                            'recipe_sha256':digest(encode(f))})
    data=encode(fixtures);(EVIDENCE/'fixtures.json.gz').write_bytes(gzip.compress(data,mtime=0))
    result={'python':platform.python_version(),'opencv':cv2.__version__,'numpy':numpy.__version__,
            'rapidfuzz':rapidfuzz.__version__,'gc_enabled':gc.isenabled(),'fixtures_sha256':digest(data),
            'fixtures_compressed_sha256':digest((EVIDENCE/'fixtures.json.gz').read_bytes()),'cases':details}
    (EVIDENCE/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

def fresh(m,f):
    fields=copy.deepcopy(f['dets'])
    for d in fields:
        for k in ('cbox','aoff','poly'):d[k]=tuple(d[k])
    dets=[m.Detection(**d) for d in fields]
    scans=copy.deepcopy(f['scans'])
    return dets,scans

def run(m,f):
    from rapidfuzz import fuzz
    dets,scans=fresh(m,f)
    assert gc.isenabled()
    start=time.perf_counter_ns()
    result=m.merge_detections(dets,f['hold'],scans=scans,bridge_gap=f['bridge_gap'],fuzz=fuzz)
    elapsed=time.perf_counter_ns()-start
    ids={id(d):i for i,d in enumerate(dets)}
    complete={'result':[dataclasses.asdict(d) for d in result],
              'result_input_indices':[ids[id(d)] for d in result],
              'mutated_inputs':[dataclasses.asdict(d) for d in dets]}
    return elapsed,complete

def instrument(m,f):
    from rapidfuzz import fuzz
    dets,scans=fresh(m,f)
    fn=m.merge_detections
    lines,start=inspect.getsourcelines(fn)
    # Complete line counts are retained as the trace's authoritative output.
    counts=collections.Counter()
    def trace(frame,event,arg):
        if frame.f_code.co_filename==m.__file__:
            if event=='line':counts[frame.f_lineno]+=1
            return trace
        return None
    sys.settrace(trace)
    try:result=fn(dets,f['hold'],scans=scans,bridge_gap=f['bridge_gap'],fuzz=fuzz)
    finally:sys.settrace(None)
    selected={}
    markers=('for m in reversed(mergeable):','if m.category != d.category','for st, _cum, words in scans:',
             'for m in merged:','for entry in endpoints[', 'for entry in endpoints:',
             'candidates.sort(', 'insort(', 'endpoints.pop(', 'bisect_right(')
    source=pathlib.Path(m.__file__).read_text().splitlines()
    for ln,n in sorted(counts.items()):
        line=source[ln-1].strip()
        if any(marker in line for marker in markers):selected[f'{ln}: {line}']=n
    return {'all_line_counts':dict(sorted(counts.items())),'selected':selected,
            'result_count':len(result),'input_count':len(dets)}

def measure(base,head=None):
    data=gzip.decompress((EVIDENCE/'fixtures.json.gz').read_bytes());fixtures=json.loads(data)
    validation=json.loads((EVIDENCE/'validation.json').read_text());assert digest(data)==validation['fixtures_sha256']
    labels=[('base',base)]+([('head',head)] if head else [])
    results={'boundary':'merge_detections only: includes stable sort, candidate creation/maintenance/order restoration, predicates, contradiction and tail; excludes reverse, dense smoothing, inference and report serialization',
             'warmups':3,'samples':5,'gc_enabled':gc.isenabled(),'cases':[]}
    for f in fixtures:
        expected=None;warm=[];samples=[];outputs={}
        for i in range(3):
            for label,m in labels:
                elapsed,out=run(m,f)
                if expected is None:expected=out
                assert out==expected,(f['name'],label,'warmup',i)
                warm.append({'implementation':label,'index':i,'ns':elapsed,'output_sha256':digest(encode(out))})
        for i in range(5):
            order=labels if i%2==0 else list(reversed(labels))
            for label,m in order:
                elapsed,out=run(m,f);assert out==expected,(f['name'],label,'sample',i)
                outputs[label]=out
                samples.append({'implementation':label,'index':i,'ns':elapsed,'output_sha256':digest(encode(out))})
        case={'name':f['name'],'recipe_sha256':digest(encode(f)),'warmup_samples':warm,'samples':samples,
              'median_ns':{label:statistics.median(s['ns'] for s in samples if s['implementation']==label) for label,m in labels},
              'all_outputs_equal':True,'outputs':outputs}
        results['cases'].append(case)
        print(json.dumps({k:v for k,v in case.items() if k!='outputs'}),flush=True)
    # All timed runs across the predeclared matrix finish before tracing.
    for f,case in zip(fixtures,results['cases']):
        case['instrumentation']={label:instrument(m,f) for label,m in labels}
        print(json.dumps({'case':f['name'],'instrumentation':{k:v['selected'] for k,v in case['instrumentation'].items()}}),flush=True)
    raw=encode(results);name='comparison' if head else 'baseline'
    (EVIDENCE/(name+'.json.gz')).write_bytes(gzip.compress(raw,mtime=0))
    print(json.dumps({'result':name,'uncompressed_bytes':len(raw),'sha256':digest(raw),'compressed_bytes':(EVIDENCE/(name+'.json.gz')).stat().st_size}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('validate','baseline','compare'));p.add_argument('--head');p.add_argument('--head-sha');a=p.parse_args()
    m=load('base',ROOT/'base'/'openscrub.py',BASE_HASH)
    if a.mode=='validate':validate(m)
    elif a.mode=='baseline':measure(m)
    else:measure(m,load('head',a.head,a.head_sha))
