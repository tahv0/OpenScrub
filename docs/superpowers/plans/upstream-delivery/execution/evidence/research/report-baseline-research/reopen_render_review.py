#!/usr/bin/env python3
"""Fresh-process Flask GET/reopen of the actual render output report snapshot."""
import argparse
import json
from pathlib import Path
import shutil
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--work-dir',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
sys.path.insert(0,str(a.source.resolve()))
import openscrub_web as web
root=a.work_dir/'reopened-review'
root.mkdir(parents=True,exist_ok=True)
web._data_root=lambda:str(root)
web.JOBS_DIR=str(root/'jobs')
shutil.copyfile(a.work_dir/'render-after.json',root/'report.json')
web.JOBS.clear()
web.JOBS['reopen']={'dir':str(root),'video':str(a.work_dir/'jobs/synthetic/input.avi')}
web.TOKEN=None
with web.app.test_client() as c:
 response=c.get('/api/jobs/reopen/detections')
 result={'scope':'Fresh module imports; real Flask test-client GET, no browser/socket',
         'status':response.status_code,'body':response.get_json()}
 assert result['status']==200
 assert len(result['body']['detections'])==7
 assert all(r['enabled'] for r in result['body']['detections'])
 before=json.loads((a.work_dir/'render-before.json').read_text())
 result['original_index_by_text']={r['text']:i for i,r in enumerate(before['detections'])}
 result['shifted_rows']=[{'text':r['text'],'before_index':result['original_index_by_text'][r['text']],
                          'after_index':r['i']} for r in result['body']['detections']
                         if result['original_index_by_text'][r['text']]!=r['i']]
 result['manual_rows_remaining']=[r for r in result['body']['detections'] if r['category']=='manual']
a.output.write_text(json.dumps(result,indent=2))
print('Fresh reopen:',response.status_code,len(result['body']['detections']),'rows;',len(result['shifted_rows']),'shifted')
