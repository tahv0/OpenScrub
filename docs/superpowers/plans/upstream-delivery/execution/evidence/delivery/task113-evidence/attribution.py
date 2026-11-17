import argparse, inspect, collections, dataclasses, hashlib, importlib.util, json, pathlib, random, statistics, sys, time
from rapidfuzz import fuzz
ROOT=pathlib.Path('/tmp/openscrub-task113')
BASE=ROOT/'base'
sys.path.insert(0,str(BASE))
import openscrub as c
assert pathlib.Path(c.__file__).resolve()==BASE/'openscrub.py'
c.cv2.setNumThreads(1)

def fixture(mode, n=500):
    memory=c.PhiMemory(); raw=[]; scans=[]; unmatched=[]
    for i in range(n):
        rng=random.Random(83011+(0 if mode=='repeated' else i))
        size=4+(i*17)%77 if mode=='heterogeneous' else 24
        text=''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(size))+'@sample.invalid'
        miss='pending' if mode!='same_length' else ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(len(text)))
        words=[(text,(8,8,150,28),.99),(miss,(8,40,150,60),.99)]
        t=i/3
        found=c.detect_phi(words,c.group_lines(words),t,(0.,0.),None,None)
        assert len(found)==1 and found[0].text==text and found[0].category=='email', (mode,i,found)
        assert memory.recall(miss) is None, (mode,i,miss)
        raw.extend(found)
        for d in found: memory.add(d.text,d.category)
        scans.append((t,(0.,0.),words))
        unmatched.append(miss)
    assert len(memory.items)==(1 if mode=='repeated' else n)
    # No final-memory forward recall on the benign words either.
    assert all(memory.recall(w) is None for w in unmatched)
    return scans,memory,raw

def records(ds): return [dataclasses.asdict(d) for d in ds]
def digest(ds): return hashlib.sha256(json.dumps(records(ds),sort_keys=True).encode()).hexdigest()

def main():
    out={'source_sha256':hashlib.sha256((BASE/'openscrub.py').read_bytes()).hexdigest(),'gc':'normal enabled','n':500,'cases':[]}
    for mode in ['heterogeneous','same_length','repeated']:
        samples={k:[] for k in ['reverse','merge','reverse_plus_merge']}; expected={}
        meta=None
        for boundary in samples:
            for rep in range(8):
                scans,memory,raw=fixture(mode)
                if meta is None:
                    meta={'scans':len(scans),'words':sum(len(x[2]) for x in scans),'memory':len(memory.items),'primary':len(raw),'key_lengths':dict(collections.Counter(map(len,memory.items)))}
                if boundary=='merge':
                    extra=c.reverse_pass(scans,memory,{'email'},None)
                start=time.perf_counter_ns()
                if boundary=='reverse': result=c.reverse_pass(scans,memory,{'email'},None)
                else:
                    if boundary=='reverse_plus_merge': extra=c.reverse_pass(scans,memory,{'email'},None)
                    result=c.merge_detections(raw+extra,hold=1/3+.3,scans=scans,fuzz=fuzz)
                elapsed=time.perf_counter_ns()-start
                val=records(result)
                if boundary not in expected: expected[boundary]=val
                assert expected[boundary]==val
                if rep>=3:samples[boundary].append(elapsed)
        scans,memory,raw=fixture(mode)
        owner_lines, owner_start = inspect.getsourcelines(c.reverse_pass)
        mark=next(owner_start+i for i,l in enumerate(owner_lines) if l.strip()=='if cat not in cats:')
        counts=collections.Counter()
        def trace(frame,event,arg):
            if event=='line' and frame.f_code is c.reverse_pass.__code__ and frame.f_lineno==mark: counts['candidate_visits']+=1
            return trace
        sys.settrace(trace)
        try: extra=c.reverse_pass(scans,memory,{'email'},None)
        finally: sys.settrace(None)
        row={'case':mode,'fixture':meta,'samples_ns':samples,'median_ns':{k:statistics.median(v) for k,v in samples.items()},'work':counts,'outputs':expected}
        out['cases'].append(row)
        print({k:v for k,v in row.items() if k!='outputs'},flush=True)
    (ROOT/'evidence/baseline-attribution.json').write_text(json.dumps(out,indent=2))
if __name__=='__main__':main()
