import ast,hashlib,json,subprocess,tarfile,zipfile,tomllib
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task164')
manifest=json.loads((art/'verification-source.json').read_text())
for name,digest in manifest['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
sources=tomllib.loads((root/'pyproject.toml').read_text())['tool']['hatch']['build']['targets']['wheel']['include']
with tarfile.open(next((art/'dist').glob('*.tar.gz'))) as archive:
 names={n.split('/',1)[1]:n for n in archive.getnames() if '/' in n}
 for name in manifest['files']:assert archive.extractfile(names[name]).read()==(root/name).read_bytes(),name
 for name in names:
  if name.endswith('.py'):ast.parse(archive.extractfile(names[name]).read().decode(),feature_version=(3,9))
 archive.extractall(art/'sdist-extracted',filter='data')
with zipfile.ZipFile(next((art/'dist').glob('*.whl'))) as archive:
 for name in sources:assert archive.read(name)==(root/name).read_bytes(),name
 metadata=archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))).decode()
 assert 'Requires-Python: >=3.9' in metadata
for name in ['openscrub.py','pyproject.toml','requirements.txt']:
 assert (root/name).read_bytes()==subprocess.check_output(['git','-C',str(root),'show',manifest['base']+':'+name]),name
js=next(ast.literal_eval(n.value) for n in ast.parse((root/'openscrub_web.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))
(art/'app.js').write_text(js);subprocess.run(['node','--check',str(art/'app.js')],check=True)
result={'sdist_exact_sources_tests_and_browser_assets':True,'wheel_exact_product_sources':True,'python39_grammar':True,'evaluated_js_parse':True,'unchanged_engine_requirements_project_defaults':True,'files':manifest['files'],'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (art/'dist').iterdir()}}
(art/'packaging.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))
