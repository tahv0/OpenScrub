import ast
import os
import subprocess
import sys
from pathlib import Path
from baseline_isolation import configure
web=configure('save-as-browser')
for name,suffix,size in [('alpha','.mkv',256*1024*1024),('beta','.mp4',1024)]:
    job=web.new_job('',{},'synthetic.'+name+'.mov')
    web.JOBS.pop(job['id'])
    job['id']=name
    job['phase']='done'
    job['output']=str(Path(job['dir'])/('result'+suffix))
    with open(job['output'],'wb') as f:f.truncate(size)
    (Path(job['dir'])/'report.json').write_bytes(b'{"synthetic":true}')
    web.JOBS[name]=job
if '--donor' in sys.argv:
    source=subprocess.check_output(['git','show','2900930f:openscrub_web.py'],text=True)
    donor_js=next(ast.literal_eval(n.value) for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))
    web.PAGE=web.PAGE.replace(web.APP_JS,donor_js)
    original=web.job_public
    def public(job):
        result=original(job)
        result.update(download_name='synthetic.'+job['id']+'_redacted'+Path(job['output']).suffix,report_name='synthetic.'+job['id']+'_audit.json')
        return result
    web.job_public=public
# Prevent optional remote release checks during isolated UI validation.
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
from cheroot.wsgi import Server
print('Synthetic Save As QA server http://127.0.0.1:18484',flush=True)
Server(('127.0.0.1',18484),web.app,numthreads=8).start()
