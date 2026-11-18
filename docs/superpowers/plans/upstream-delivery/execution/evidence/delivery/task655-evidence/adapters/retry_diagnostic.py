"""Exact existing fixture retry/replacement ownership diagnostic; no browser."""
from pathlib import Path
import json
import os
import sys
import urllib.request
import pytest

source=Path(json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())['source'])
sys.path.insert(0,str(source/'tests'))
import test_job_polling_browser as fixture
import openscrub_web as web

root=Path(os.environ['VERIFY_RUN']); target=root/'fixture';target.mkdir()
patch=pytest.MonkeyPatch(); created=[]; actual=web.new_job
initial=web.FILES.count

def new_job(*args,**kwargs):
    job=actual(*args,**kwargs);created.append(job);return job
patch.setattr(web,'new_job',new_job)
generator=fixture.polling_http.__wrapped__(patch,target)
base=next(generator)
def control(data):
    request=urllib.request.Request(base+'/__qa__/control',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=5) as response:
        assert response.status==200
        return json.load(response)
record={'initial':initial,'steps':[]}
try:
    for data in [{'action':'retry'},{'action':'replace','count':1},{'action':'retry'}]:
        control(data)
        record['steps'].append({'action':data['action'],'count':web.FILES.count,'queued':[{'id':j['id'],'current':web.JOBS.get(j['id']) is j,'tickets':len(web.FILES.initialize(j).queued)} for j in created]})
    assert web.FILES.count==initial+2
    held=[(j,gen,owner) for j in created for gen,owner in web.FILES.initialize(j).queued.items()]
    assert len(held)==2 and len({id(owner) for _,_,owner in held})==2
finally:
    generator.close()  # actual old fixture teardown shuts down only its server
    record['after_old_fixture_teardown']=web.FILES.count
    held=[(j,gen,owner) for j in created for gen,owner in web.FILES.initialize(j).queued.items()]
    for job,generation,owner in held:
        files=web.FILES.initialize(job)
        with files.report_lock:
            assert files.queued.pop(generation) is owner
        web._finish_operation(job,owner)
        assert owner.released
    record['explicit_harness_tickets_released']=len(held)
    record['after_harness_release']=web.FILES.count
    assert web.FILES.count==initial
    patch.undo()
(root/'logs/retry-diagnostic.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
