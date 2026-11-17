import json,importlib.util
from pathlib import Path
art=Path('/tmp/openscrub-task651');root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
spec=importlib.util.spec_from_file_location('review_io',root/'benchmark/review_io.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
source=json.loads(Path('/tmp/openscrub-task631/measurement/results.json').read_text())['sources']['before'];assert source['revision']=='12919c96c6f7558136b50d7b4d85e5e6b62f1971'
for name,digest in source['sha256'].items():assert m.sha_file(Path(source['export'])/name)==digest
try:m.count_operations({},6,art,before_noop_publications=2)
except ValueError:pass
else:raise AssertionError('invalid expected count accepted')
evidence=art/'count-default';evidence.mkdir();counts=m.count_operations({'before':source},6,evidence)
for name,digest in source['sha256'].items():assert m.sha_file(Path(source['export'])/name)==digest
(evidence/'results.json').write_text(json.dumps(counts,indent=2))
print('default1 historical behavior: three actual six-row counted HTTP cases passed; invalid expectation rejected; no timing claim')
