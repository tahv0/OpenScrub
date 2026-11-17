"""Task632 throwaway stdlib candidate attribution; never imported by runtime."""
import sys, json, tempfile, time, hashlib, os, gc, resource, statistics, subprocess
from pathlib import Path
sys.path.insert(0, '/home/tahv0/.codex/worktrees/c832/OpenScrub')
from benchmark.review_io import fixture, sha_file, memory
from openscrub_internal.reports import atomic_report
ROOT=Path('/tmp/openscrub-task632')

def publish(path, doc, candidate):
    staged=None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',dir=path.parent,prefix='.report-',suffix='.tmp',delete=False) as stream:
            staged=stream.name
            if candidate=='dump': json.dump(doc, stream, indent=1)
            elif candidate=='writelines': stream.writelines(json.JSONEncoder(indent=1).iterencode(doc))
            else:
                chunks=[]; size=0
                for chunk in json.JSONEncoder(indent=1).iterencode(doc):
                    chunks.append(chunk); size+=len(chunk)
                    if size >= 65536:
                        stream.write(''.join(chunks)); chunks.clear(); size=0
                if chunks: stream.write(''.join(chunks))
            stream.flush(); os.fsync(stream.fileno())
        os.replace(staged,path)
    finally:
        if staged is not None:
            try: os.unlink(staged)
            except OSError: pass

def main():
    rows=int(sys.argv[1]); doc=fixture(rows)
    target=ROOT/('attribution-%s.json'%rows)
    atomic_report(target,doc); expected=sha_file(target)
    result={'rows':rows,'python':sys.version,'executable':sys.executable,'source':str(Path(atomic_report.__code__.co_filename).resolve()),'source_sha256':sha_file(Path(atomic_report.__code__.co_filename)),'base':subprocess.check_output(['git','-C','/home/tahv0/.codex/worktrees/c832/OpenScrub','rev-parse','HEAD'],text=True).strip(),'initial_memory':memory(os.getpid()),'samples':[]}
    candidates=['dump','writelines','aggregate65536']
    for i in range(8):
        for name in candidates[i%3:]+candidates[:i%3]:
            gc.collect(); start=time.perf_counter_ns(); publish(target,doc,name); elapsed=(time.perf_counter_ns()-start)/1e6
            assert sha_file(target)==expected
            result['samples'].append({'candidate':name,'index':i,'warmup':i<3,'milliseconds':elapsed,'memory_after':memory(os.getpid())})
    result['bytes']=target.stat().st_size; result['sha256']=expected
    result['summary']={name:statistics.median(s['milliseconds'] for s in result['samples'] if s['candidate']==name and not s['warmup']) for name in candidates}
    (ROOT/('attribution-%s-results.json'%rows)).write_text(json.dumps(result,indent=2))
    print(json.dumps(result['summary']),flush=True)
if __name__=='__main__':main()
