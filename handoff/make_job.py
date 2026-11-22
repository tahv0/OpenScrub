"""Synthetic 3000-card plate job for blur_all_check.sh. No real data."""
import sys,os,json,subprocess
root=sys.argv[1];sys.path.insert(0,root)
import openscrub as core
J=root+'/openscrub_jobs/aaaaaaaaaaaa';os.makedirs(J,exist_ok=True)
v=J+'/input.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=0xd7d7d7:s=160x96:r=1:d=1800','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',v],check=True)
class D:
    INPUT=640
    def __init__(s,*a,**k):s.n=0
    def available(s):return True
    def find(s,f,scale=1.):
        s.n+=1
        return [(30,20,100,60,.5)] if s.n<6 else []
core.PlateDetector=D
class Q(core.Callbacks):
    def log(s,m):pass
p=core.build_parser()
a=core._prep_args(p.parse_args([v,'--categories','plate','--no-vfr-fix','--tile','off','--uncertain-policy','manual_review','--plate-auto-cutoff','.8','--encoder','x264','--mode','box','--pad','0','--output',J+'/output.mp4','--report',J+'/report.json']),p)
s=core.run_scan(a,Q());d=core._report_document(a,s)
base=[r for r in d['detections'] if (r.get('policy_evidence') or {}).get('origin')=='detection'][0]
rows=[]
for k in range(3000):
    for j in range(90):
        r=dict(base);t0=k*.598+j*.02
        direct=j%3==0
        r.update(track=k,t_start=t0,t_end=min(1800,t0+1.2),last_seen=min(1800,t0+1.2),confidence=.9 if k%10==0 else .5,
          policy_evidence={'origin':'detection','frame':int(t0),'geometry_valid':True} if direct else {'origin':'interpolation','frame':None,'geometry_valid':False})
        r.pop('output_choice',None)
        rows.append(r)
for r,x in zip(rows,core.plate_policy.evaluate(rows,'manual_review',.35,.8,capable_off=True)):r['enabled']=x.enabled
d['detections']=rows
json.dump(d,open(J+'/report.json','w'))
print('rows',len(rows),'enabled before',sum(r['enabled'] for r in rows),'visible tracks',3000-len({r['track'] for r in rows if r['enabled']}))
