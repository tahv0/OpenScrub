"""Small research-artifact verification; does not modify product or Git state."""
import json,hashlib,re
from pathlib import Path
here=Path(__file__).resolve().parent
runtime=Path('/tmp/openscrub-editor-resize-baseline-20261117')
r=json.loads((here/'results.json').read_text())
assert len(r['versions'])==2 and r['browserClosed']
assert json.loads((here/'cleanup.json').read_text())['all_reaped']
provenance=json.loads((here/'source-provenance.json').read_text())
for p,v in zip(provenance,r['versions']):
 assert p['verified_all_archive_files']
 assert hashlib.sha256(Path(p['export'],'openscrub_web.py').read_bytes()).hexdigest()==p['web_sha256']
 ident=json.loads((here/(v['label']+'-server-identity.json')).read_text())
 assert ident['sha']==p['sha'] and ident['web_sha256']==p['web_sha256']
 assert ident['web_import']==p['export']+'/openscrub_web.py'
 assert v['errors']==[] and v['mutations']==[]
 assert v['liveResize']=={'sameElements':True,'imageLoadEvents':0,'frameRequests':[]}
 assert v['livePointerHit']['selected']==-1 and v['scrubPointerHit']['selected']==0
 assert v['editorClosed'] and v['reopenNewElements']
 assert v['report']['detections'][0]['cbox']==[120,80,320,220]
 for s in v['states']:
  delta=max(map(abs,s['paint']['edgeDelta']))
  if s['name'] in ('mobile-live','mobile-redraw'):
   assert delta==158 and s['paint']['expectedCenterPixel']==[0,0,0,0]
  else:assert delta<=1.1 and s['paint']['expectedCenterPixel'][3]==56
  assert (here/f"{v['label']}-{s['name']}-editor.png").is_file()
for f in here.iterdir():
 if (runtime/f.name).is_file():assert f.read_bytes()==(runtime/f.name).read_bytes(),f.name
report=here.parent/'editor-resize-baseline-research.md'
text=report.read_text()
assert r['environment']['browser'] in text and r['environment']['node'] in text
for rel in re.findall(r'\]\(([^)]+)\)',text):
 if not rel.startswith(('http:','https:','/')):assert (report.parent/rel).exists(),rel
print('PASS: both pins, 10 measured states, painted pixels, pointer/reopen checks, unchanged report, source identity, artifact copies, report links/environment, server/browser cleanup')
print(f'Evidence: {len(list(here.iterdir()))} files, {sum(f.stat().st_size for f in here.iterdir() if f.is_file())} bytes')
