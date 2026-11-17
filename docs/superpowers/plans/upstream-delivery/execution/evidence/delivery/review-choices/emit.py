import ast,re
from pathlib import Path
from types import SimpleNamespace
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub'); ns={}
for fn in ['zones_ui.py','openscrub_web.py']:
 for n in ast.parse((root/fn).read_text()).body:
  if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
   try:ns[n.targets[0].id]=ast.literal_eval(n.value)
   except (ValueError,TypeError):
    if n.targets[0].id=='PAGE':
     ns['zones_ui']=SimpleNamespace(ZONES_PAGE=ns['ZONES_PAGE'])
     page=eval(compile(ast.Expression(n.value),fn,'eval'),{'__builtins__':{}},ns)
page=page.replace('%%MAXUP%%','0').replace('%%FREEDISK%%','0').replace('%%VERSION%%','1.0.96')
Path('/tmp/openscrub-task20/current.html').write_text(page)
Path('/tmp/openscrub-task20/evaluated.js').write_text('\n'.join(re.findall(r'<script>(.*?)</script>',page,re.S)))
