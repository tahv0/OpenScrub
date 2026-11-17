import ast,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task652');base='ac6496810b03d8b062ab9da150aeea1e62285fed'
def imports(s):return [ast.dump(n) for n in ast.parse(s).body if isinstance(n,(ast.Import,ast.ImportFrom))]
files=['openscrub.py','openscrub_web.py','openscrub_setup.py','zones_ui.py']+[p.relative_to(root).as_posix() for p in (root/'openscrub_internal').glob('*.py')]
changes={}
for n in files:
 a=imports(subprocess.check_output(['git','-C',str(root),'show',base+':'+n],text=True));b=imports((root/n).read_text())
 removed=set(a)-set(b);added=set(b)-set(a)
 assert not removed,(n,removed)
 assert added==({"Import(names=[alias(name='math')])"} if n=='openscrub.py' else set()),(n,added)
 changes[n]={'removed':list(removed),'added':list(added)}
r={'runtime_source_count':len(files),'imports':changes,'only_reviewed_polygon_stdlib_math_addition':True,'no_removed_system_imports_added':True}
(art/'imports.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
