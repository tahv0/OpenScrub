"""Confirm the adopted exact-route admission/body compatibility boundary."""
import json
import os
from pathlib import Path
import openscrub_web as web

web.TOKEN=None
web.JOBS={}
results=[]
with web.app.test_client() as client:
    response=client.get('/api/jobs/missing-exact-job/edit_sample?t=0.2')
    assert response.status_code==404
    assert response.headers['Cache-Control']=='private, no-store'
    assert not response.is_json and b'404' in response.data
    results.append(dict(boundary='pre-route missing job',status=response.status_code,headers=dict(response.headers),body=response.get_data(as_text=True)))
    response.close()
    job=web.new_job('',{},'synthetic-missing-report.mp4');job['phase']='review'
    response=client.get('/api/jobs/'+job['id']+'/edit_sample?t=0.2')
    assert response.status_code==404 and response.json['error']=='missing_report'
    assert response.headers['Cache-Control']=='private, no-store'
    results.append(dict(boundary='route-managed missing report',status=response.status_code,headers=dict(response.headers),body=response.get_data(as_text=True)))
    response.close()
assert web.FILES.count==0
(Path(os.environ['VERIFY_RUN'])/'logs/admission-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('EXACT_ADMISSION_BODY_COMPATIBILITY_OK',flush=True)
