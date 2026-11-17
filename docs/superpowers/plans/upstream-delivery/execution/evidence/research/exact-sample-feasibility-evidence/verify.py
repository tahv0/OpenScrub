"""Verify this bounded probe's retained evidence; not a product test suite."""
import hashlib, json
from pathlib import Path
EVID=Path(__file__).resolve().parent
d=json.loads((EVID/'results.json').read_text())
assert d['source']['commit']=='12919c96c6f7558136b50d7b4d85e5e6b62f1971'
assert d['source']['verified_export_files']==125
assert len(d['samples'])==28 and d['captures']==28 and d['all_released']
passed=failed=0
for label,m in d['media'].items():
    assert hashlib.sha256(Path(m['path']).read_bytes()).hexdigest()==m['sha256']
    assert m['backend']=='FFMPEG'
for s in d['samples']:
    assert s['trace']['released']
    r=s['trace']['read'];m=d['media'][s['label']]
    if r['ok']:
        passed+=1
        assert s['expected_index_pixels_equal']
        assert s['selected_index'] in s['matches_sequential_indices']
        ref=m['sequential_reference'][s['selected_index']]
        assert r['sha256']==ref['sha256']
        assert abs(r['pos_msec']/1000-float(ref['pts_time'])) < .000001
        if 'odd_crop_matches_selected' in s:assert s['odd_crop_matches_selected']
    else:
        failed+=1
        assert s['selected_index']>=len(m['sequential_reference'])
        assert s['matches_sequential_indices']==[]
for label,t,idx in [('cfr24',.2,4),('cfr5',1.9,9),('normalized',.5,6)]:
    assert any(s['label']==label and s['requested_time']==t and s['selected_index']==idx
               and s['expected_index_pixels_equal'] for s in d['samples'])
dups=[s for s in d['samples'] if s['label']=='normalized' and s['selected_index'] in (2,3)]
assert len(dups)==2 and all(s['matches_sequential_indices']==[2,3] for s in dups)
assert dups[0]['trace']['read']['pos_msec'] != dups[1]['trace']['read']['pos_msec']
assert passed==22 and failed==6
print(f'PASS: 125 pinned export files; {passed} pixel/PTS agreements; {failed} natural EOF failures; 28 releases; duplicate ambiguity retained.')
