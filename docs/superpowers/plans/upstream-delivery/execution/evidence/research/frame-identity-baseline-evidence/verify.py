"""Verify saved baseline observations; intentionally no product tests/changes."""
from pathlib import Path
import json,hashlib
E=Path(__file__).resolve().parent
r=json.loads((E/'results.json').read_text());b=json.loads((E/'browser-results.json').read_text());p=json.loads((E/'source-provenance.json').read_text())
assert r['source_sha']==p['commit']=='e21ebdf6e3ee46e6c65050dc956a9a3459152269'
for name,digest in r['source_sha256'].items():
 assert digest==p['sha256'][name]==hashlib.sha256((Path(p['export'])/name).read_bytes()).hexdigest()
for label,media in r['media'].items():assert media['sha256']==hashlib.sha256(Path(media['path']).read_bytes()).hexdigest()
def s(label,t,schedule='natural'):
 return next(x for x in r['samples'] if x['job']==label and x['url']==f'/api/jobs/{label}/frame_at?t={t}' and x['schedule']==schedule)
assert s('cfr24',0.2)['matching_sequential_source_indices']==[5]
assert s('cfr24',0.2)['geometry_frame']==4
assert s('cfr5',1.9)['matching_sequential_source_indices']==[8]
assert s('cfr5',1.9)['geometry_frame']==9
assert s('cfr5',1.9)['capture_traces'][0]['seeks'][0]['read']['ok'] is False
assert s('cfr5',1.9)['capture_traces'][0]['seeks'][1]['read']['marker']==8
assert s('normalized',0.5)['matching_sequential_source_indices']==[7]
assert s('normalized',0.5)['geometry_frame']==6
assert r['sequential_reference']['normalized'][6]['marker']==5
assert r['sequential_reference']['normalized'][7]['marker']==6
assert s('cfr24',0.9,[True,False])['marker']==13
assert s('cfr24',0.9,[True,True,True,True])['status']==404
for item in r['samples']:
 assert all(c['released'] for c in item['capture_traces'])
 if item['status']==200 and '/frame_at' in item['url']:
  assert item['matching_sequential_source_indices']
  assert not any('frame' in h.lower() or 'source' in h.lower() for h in item['headers'])
thumbs=[x for x in r['samples'] if '/thumb/0' in x['url']]
assert [x['matching_sequential_source_crops'] for x in thumbs]==[[4],[24]]
assert not b['errors'] and not b['mutations']
for state,marker,t,ox in zip(b['states'],[5,8,6],[.2,1.9,.5],[8,18,10]):
 assert state['image']['marker']==marker and state['BE']['t']==t and state['BE']['ox']==ox
 assert state['selected']==0 and state['pointerEvents']=='auto' and state['localDraft']['ov']['0']==[55,70,95,110]
 assert state['nonblank'] and not state['overlays']
 assert (E/(state['job']+'-editor.png')).is_file()
print(f'PASS: {len(r["samples"])} route observations, {sum(len(x["capture_traces"]) for x in r["samples"])} released captures, 3 ordinary browser editor states; pinned source/media hashes match.')
