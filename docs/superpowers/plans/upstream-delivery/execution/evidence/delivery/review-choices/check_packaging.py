import ast,json,re,tarfile,zipfile,subprocess,hashlib
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task20')
sources=['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py'];tests=['test_openscrub.py']+[p.relative_to(root).as_posix() for p in sorted((root/'tests').glob('*.py'))]
with tarfile.open(next((art/'dist').glob('*.tar.gz'))) as z:
 members={n.split('/',1)[1]:n for n in z.getnames() if '/' in n}
 for p in sources+tests:assert z.extractfile(members[p]).read()==(root/p).read_bytes(),p
 for p in members:
  if p.endswith('.py'):ast.parse(z.extractfile(members[p]).read().decode(),feature_version=(3,9))
with zipfile.ZipFile(next((art/'dist').glob('*.whl'))) as z:
 for p in sources:assert z.read(p)==(root/p).read_bytes(),p
 for p in z.namelist():
  if p.endswith('.py'):ast.parse(z.read(p).decode(),feature_version=(3,9))
base='92124753736e287ac800af91f0ac96f3e96c01be'
def old(name):return subprocess.check_output(['git','-C',str(root),'show',base+':'+name])
assert old('openscrub.py')==(root/'openscrub.py').read_bytes();assert old('zones_ui.py')==(root/'zones_ui.py').read_bytes()
# Exclude only the two UI literal assignments; every server function is unchanged.
def server_tree(data):
 tree=ast.parse(data)
 return ast.dump(ast.Module(body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ['APP_JS','APP_CSS'] for t in n.targets))],type_ignores=[]),include_attributes=False)
assert server_tree(old('openscrub_web.py'))==server_tree((root/'openscrub_web.py').read_bytes())
result={'base':base,'exact_source_and_test_inclusion':True,'packaged_python39_grammar':True,'unchanged_engine_and_zones':True,'all_server_functions_unchanged':True,'sdist_tests':tests,'source_hashes':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sources}}
(art/'packaging.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
