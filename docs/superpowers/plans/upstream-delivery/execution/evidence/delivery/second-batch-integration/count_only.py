import importlib.util,json,subprocess,hashlib
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task651');evidence=art/'counted-amendment';evidence.mkdir()
spec=importlib.util.spec_from_file_location('review_io',root/'benchmark/review_io.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=json.loads((art/'measurement/results.json').read_text());assert len(original['runs'])==3
for run in original['runs']:
 assert len(run['warmup'])==6 and len(run['recorded'])==10
 assert all(v['status']==200 for v in run['warmup']+run['recorded'])
 for label in ['before','after']:
  assert run['files_after'][label]['sha256']==m.expected_hash(100000,run['operation'],8)
# Every blob in both original pinned exports is verified, not a partial import list.
for source in original['sources'].values():
 for name,digest in source['sha256'].items():assert m.sha_file(Path(source['export'])/name)==digest,name
counts=m.count_operations(original['sources'],100000,evidence,before_noop_publications=0)
for source in original['sources'].values():
 for name,digest in source['sha256'].items():assert m.sha_file(Path(source['export'])/name)==digest,name
result={'timing_sources':{k:v['revision'] for k,v in original['sources'].items()},'timings_unmodified':True,'before_noop_publications':0,'exports_reverified_before_and_after':True,'instrumented':counts,'driver_sha256':hashlib.sha256((root/'benchmark/review_io.py').read_bytes()).hexdigest()}
(evidence/'results.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:{v:x['after']['counts'] for v,x in values.items()} for k,values in counts.items()},indent=2))
