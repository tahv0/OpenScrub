#!/usr/bin/env python3
"""Check recorded baseline evidence; findings are expected baseline failures."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
r=json.loads((root/'results.json').read_text())
s=json.loads((root/'source-verification.json').read_text())
assert r['upstream_sha']==s['sha']=='5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f'
assert all(v['matches_git_object'] for v in s['files'].values())
for key in ('test-client-encoding','test-client-write','socket-encoding','socket-write'):
 x=r['regressions'][key]
 assert x['status']==500 and not x['previous_bytes_preserved'] and not x['valid_json_after_failure']
x=r['regressions']['socket-overlapping-sparse-saves']
assert x['statuses']=={'1':200,'2':200} and x['errors']==[]
assert x['actual_enabled']==[True,False] and x['expected_enabled']==[False,False]
x=r['regressions']['socket-identical-manual-replay']
assert x['row_counts']==[10,11,12] and x['statuses']==[200,200]
assert x['duplicate_added_rows_equal'] and x['existing_rows_preserved'] and x['other_fields_preserved']
x=r['regressions']['socket-ordinary-combined-edit']
assert x['status']==200 and all(x[k] for k in ('enabled_applied','box_applied','time_applied','audio_applied','suggest_allowlist_preserved'))
x=r['render_preservation']
assert x['actual_render_completed'] and x['output_frames']==60 and x['before_rows']==10 and x['after_rows']==7
assert len(x['disabled_rows_lost'])==3 and x['enabled_track_person_preserved']
assert x['audio_redactions']['equal'] and not x['audio_suggestions']['present_after'] and not x['audio_transcript']['present_after']
reopen=json.loads((root/'reopened-review.json').read_text())
assert reopen['status']==200 and len(reopen['body']['detections'])==7 and len(reopen['shifted_rows'])==7
assert len(reopen['manual_rows_remaining'])==2
assert [m['rows'] for m in r['measurements']]==[1000,10000,100000]
for m in r['measurements']:
 assert m['preservation']['all_other_fields_equal']
 for name,x in m['scenarios'].items():
  assert x['warmups']==3 and x['measured_repetitions']==len(x['samples'])==5
  if name=='no_op': assert x['identical_report_bytes']
  for sample in x['samples']:
   assert sample['status']==200
   assert all(sample['counts'][k]==1 for k in ('parses','serializations','report_write_opens'))
print('PASS: pinned source, route failures/race/replay, actual render + fresh reopen, and 30 measured socket samples verified.')
