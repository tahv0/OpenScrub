from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,tarfile,zipfile
ROOT=Path('/tmp/openscrub-task115');native=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
import openscrub as core
import openscrub_web as web
assert Path.cwd()==ROOT/'runtime'
assert Path(core.__file__).resolve()==ROOT/'installed/openscrub.py'
assert Path(web.__file__).resolve()==ROOT/'installed/openscrub_web.py'
assert not any(str(native)==p for p in sys.path)
products=['openscrub.py','openscrub_web.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py','zones_ui.py']
controls=['tests/test_first_scan_sanity.py','test_openscrub.py','pyproject.toml']
manifest={}
with tarfile.open(ROOT/'dist/openscrub-1.0.96.tar.gz') as tar, zipfile.ZipFile(ROOT/'dist/openscrub-1.0.96-py3-none-any.whl') as wheel:
 for name in products+controls:
  expected=(native/name).read_bytes()
  assert tar.extractfile('openscrub-1.0.96/'+name).read()==expected,name
  manifest[name]=hashlib.sha256(expected).hexdigest()
  if name in products:
   assert wheel.read(name)==expected,name
   assert (ROOT/'installed'/name).read_bytes()==expected,name
 metadata=wheel.read('openscrub-1.0.96.dist-info/METADATA').decode()
 assert 'Requires-Python: >=3.9' in metadata
spec=importlib.util.spec_from_file_location('default_base',ROOT/'base/openscrub.py');base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)
defaults=vars(core.build_parser().parse_args(['fixture.avi']))
assert defaults==vars(base.build_parser().parse_args(['fixture.avi']))
import task115_isolation
task115_isolation.configure('installed-smoke')
client=web.app.test_client();statuses={}
for path in ['/','/api/jobs','/api/models/face','/api/model_status','/api/vault']:
 r=client.get(path);assert r.status_code==200,(path,r.status_code);statuses[path]=r.status_code
assert client.get('/api/jobs').get_json()==[]
cli={}
for name in ['openscrub','openscrub-web']:
 result=subprocess.run([str(ROOT/'installed/bin'/name),'--help'],capture_output=True,text=True)
 assert result.returncode==0,(name,result.stderr)
 cli[name]=dict(exit_code=result.returncode,stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest())
report=dict(python=sys.version,executable=sys.executable,core_path=core.__file__,web_path=web.__file__,source_and_package_sha256=manifest,cli=cli,web_status=statuses,parser_defaults_equal=True,parser_defaults=defaults,artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'dist').iterdir()})
(ROOT/'evidence/package-smoke.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='parser_defaults'},indent=2))
