from pathlib import Path
import ast,hashlib,json,subprocess
E=Path(__file__).parent;S=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub');B='d1eeebd2b12645a7284344fb16ec589c8aba0ce7'
def git(*a):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false',*a],cwd=S)
def sha(b):return hashlib.sha256(b).hexdigest()
def obj(r,p):return git('show',r+':'+p)
head=git('rev-parse','HEAD').decode().strip();tracked=git('ls-files').decode().splitlines();changed=git('diff','--name-only',B,head).decode().splitlines()
assert not git('status','--porcelain');assert set(changed)=={'openscrub_web.py','tests/test_review_filters.py','tests/review_filters_browser.cjs','tests/review_filters_browser.py','tests/review_filters_http.cjs','tests/review_filters_http.py'}
production=[p for p in tracked if p.endswith('.py') and ('/' not in p or p.startswith('openscrub_internal/')) and not p.startswith('test_')]
for p in production:
 if p!='openscrub_web.py':assert obj(B,p)==obj(head,p),p
old,new=ast.parse(obj(B,'openscrub_web.py')),ast.parse(obj(head,'openscrub_web.py'))
def backend(t):
 t.body=[n for n in t.body if not(isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in ('APP_CSS','APP_JS') for x in n.targets))];return ast.dump(t,include_attributes=False)
assert backend(old)==backend(new)
for p in ['pyproject.toml','requirements.txt','face_models.json','person_models.json','plate_models.json']:assert obj(B,p)==obj(head,p)
py=[p for p in tracked if p.endswith('.py')]
for p in py:ast.parse((S/p).read_bytes(),feature_version=(3,9))
git('diff','--check',B,head)
record=dict(base=B,head=head,changed=changed,unchanged_production={p:sha(obj(head,p)) for p in production if p!='openscrub_web.py'},web_backend_ast_equal=True,python39_grammar_files=len(py),web_sha256=sha(obj(head,'openscrub_web.py')),metadata_dependencies_registries_equal=True,clean=True,diff_check=True,provenance={'ac28a2ac981f2612cbaeadedddbfac8db1efeefb':'e8b9611','c0ebcc7a8c3121330730bea3619bbfea8add7992':'7950ddd'},source_blobs={'reviewed_base':git('rev-parse',B+':openscrub_web.py').decode().strip(),'reviewed_P15':git('rev-parse','c0ebcc7:openscrub_web.py').decode().strip()})
(E/'static-checks.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
