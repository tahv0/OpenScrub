import subprocess,pathlib,runpy,sys
p=pathlib.Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub/openscrub_web.py');green=p.read_text()
old=subprocess.check_output(['git','-C',str(p.parent),'show','07cfaa9539a2561c26b6f7280fae6702eb07137c:openscrub_web.py'],text=True)
a=green.index('async function saveAndRender()');z=green.index('function persistFailure',a);oa=old.index('async function saveAndRender()');oz=old.index('function persistFailure',oa)
try:
 p.write_text(green[:a]+old[oa:oz]+green[z:])
 subprocess.run(['/usr/bin/python3','/tmp/task1004-freeze.py','development-save-red'],check=True)
 with open('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1004/save-red.log','w') as out:
  r=subprocess.run(['/usr/bin/python3','/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py','--config','/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1004/development-save-red.json','run','--','-m','pytest',str(p.parent/'tests/test_review_save_failures.py'),'-q','--tb=short','-k','geometry_ack or lost_ack or ack_clear'],stdout=out,stderr=subprocess.STDOUT)
 print('Accepted07cf save owner transplanted onto new sample prerequisite, actual exit',r.returncode)
finally:p.write_text(green)
