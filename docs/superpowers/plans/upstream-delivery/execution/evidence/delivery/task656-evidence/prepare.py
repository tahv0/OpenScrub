import ast, hashlib, io, json, os, pathlib, subprocess, sys, tokenize
ROOT=pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
OUT=ROOT/'task656-evidence'; SRC=pathlib.Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
BASE='c205ef5379778f63313b519411a2d5e37d07cba5'
def git(*args): return subprocess.check_output(['git',*args],cwd=SRC)
def sha(b): return hashlib.sha256(b).hexdigest()
def save(n,v): (OUT/n).write_text(json.dumps(v,indent=2)+'\n')
def obj(ref,p): return git('show',f'{ref}:{p}')
head=git('rev-parse','HEAD').decode().strip()
assert git('branch','--show-current').decode().strip()=='integration/upstream-focused-readiness'
assert not git('status','--porcelain=v1')
allowed={'tests/test_live_preview.py','openscrub_internal/render_delivery.py','tests/test_first_scan_sanity.py','tests/test_polygon_fallback.py'}
changed=set(git('diff','--name-only',BASE,head).decode().splitlines()); assert changed==allowed
subprocess.run(['git','diff','--check',BASE,head],cwd=SRC,check=True)
tracked=git('ls-tree','-r','--name-only',head).decode().splitlines()
base_tree=git('ls-tree','-r',BASE).decode().splitlines(); new_tree=git('ls-tree','-r',head).decode().splitlines()
assert len(base_tree)==len(new_tree)
unchanged=[]
for old,new in zip(base_tree,new_tree):
    a,p=old.split('\t'); b,q=new.split('\t'); assert p==q
    assert a.split()[:2]==b.split()[:2]
    if p not in allowed: assert old==new; unchanged.append(p)
files={p:sha(obj(head,p)) for p in tracked}
assert all(sha((SRC/p).read_bytes())==h for p,h in files.items())
modules={p[:-3].replace('/','.') if not p.endswith('/__init__.py') else p[:-12].replace('/','.') :p for p in tracked if p in {'openscrub.py','openscrub_web.py','zones_ui.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py'} or (p.startswith('openscrub_internal/') and p.endswith('.py'))}
assert len(modules)==12
production=[p for p in tracked if p.endswith('.py') and ('/' not in p or p.startswith('openscrub_internal/')) and not p.startswith('test_')]
def tokens(b): return [(t.type,t.string) for t in tokenize.tokenize(io.BytesIO(b).readline) if t.type not in {tokenize.COMMENT,tokenize.NL}]
def dump(b): return ast.dump(ast.parse(b, type_comments=True),annotate_fields=True,include_attributes=False)
ast_checks={}
for p in production+['tests/test_first_scan_sanity.py']:
    a,b=obj(BASE,p),obj(head,p); da,db=dump(a),dump(b); assert da==db; assert tokens(a)==tokens(b)
    ast_checks[p]={'old_source':sha(a),'new_source':sha(b),'ast_sha256':sha(da.encode()),'noncomment_tokens_sha256':sha(repr(tokens(b)).encode()),'tokens':len(tokens(b))}
python_files=[p for p in tracked if p.endswith('.py')]
for p in python_files: ast.parse(obj(head,p),feature_version=(3,9),type_comments=True)
# Existing test/fixture/oracle definitions are complete AST-identical except the tiny_media prerequisite preamble.
existing={}
for p in ['tests/test_live_preview.py','tests/test_polygon_fallback.py']:
    before=ast.parse(obj(BASE,p)); after=ast.parse(obj(head,p))
    old={n.name:n for n in before.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    new={n.name:n for n in after.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    checked=[]
    for name,n in old.items():
        m=new[name]
        if name=='tiny_media':
            assert isinstance(n.body[0],ast.If) and ast.unparse(n.body[0].test)=='not shutil.which(\'ffmpeg\')'
            assert ast.unparse(m.body[0])=='require_media_tools()'
            n.body=n.body[1:]; m.body=m.body[1:]
        assert ast.dump(n,include_attributes=False)==ast.dump(m,include_attributes=False),name
        checked.append(name)
    existing[p]=checked
poly=ast.parse(obj(head,'tests/test_polygon_fallback.py'))
fixtures={n.name:sha(ast.dump(n,include_attributes=False).encode()) for n in poly.body if isinstance(n,ast.FunctionDef) and (n.name in ['tiny_media','observe_render','require_media_tools','ffmpeg'] or n.name.startswith('test_report_to_actual'))}
pyproject=obj(head,'pyproject.toml'); assert pyproject==obj(BASE,'pyproject.toml')
import tomllib
meta=tomllib.loads(pyproject.decode()); assert meta['project']['requires-python']=='>=3.9'
assert 'tests' in meta['tool']['hatch']['build']['targets']['sdist']['include']
for target in ['sdist','wheel']: assert 'openscrub_internal' in meta['tool']['hatch']['build']['targets'][target]['include']
refs=dict(line.split(' ',1) for line in git('for-each-ref','--format=%(refname) %(objectname)').decode().splitlines())
assert refs['refs/heads/integration/upstream-focused']==BASE
assert refs['refs/heads/docs/upstream-delivery-plan']=='6f055a4604563d1adc79da8264c3e56abd953fc2'
sources=['ac0f5e4661701e954e04dbc95eb00d9317c04cc6','af862c8c9700b7b2b06426e4c4287e469fe28038','bb4e129ae620f72a691971de1010d38d8cf661ad','c7f9dcc29affe5da363094b8646b3064966e52ed']
composed=git('rev-list','--reverse',f'{BASE}..{head}').decode().splitlines(); assert len(composed)==4
mapping=dict(zip(sources,composed))
for original,current in mapping.items():
    assert f'(cherry picked from commit {original})' in git('show','-s','--format=%B',current).decode()
    def patchid(c): return subprocess.check_output(['git','patch-id','--stable'],input=git('show','--format=',c)).decode().split()[0]
    assert patchid(original)==patchid(current)
save('source-identities.json',{'base':BASE,'head':head,'files':files,'modules':modules})
save('static-checks.json',{'interpreter':sys.version,'executable':sys.executable,'ast_options':{'type_comments':True,'annotate_fields':True,'include_attributes':False},'grammar':{'feature_version':[3,9],'files':len(python_files)},'changed':sorted(changed),'unchanged_tracked_files':unchanged,'production_ast_docstrings_noncomment_tokens':ast_checks,'existing_owner_definitions_preserved':existing,'fixture_ast_identities':fixtures,'metadata':{'requires_python':'>=3.9','recursive_tests_sdist':True,'private_package_sdist_wheel':True},'clean':True,'diff_check':True,'mode_file_inventory_equal':True})
save('provenance.json',{'base':BASE,'head':head,'branch':'integration/upstream-focused-readiness','mapping':mapping,'patch_ids_equal':True,'conflicts':[],'refs':refs})
old=json.loads((ROOT/'task6521-evidence/native-312.json').read_text())
prereqs=old['prerequisites'][:-1]
for item in prereqs: assert sha(pathlib.Path(item['path']).read_bytes())==item['sha256']
assert prereqs[0]['sha256']=='354cf49b0c83d11f3945137fbdffc3ac6b2793f1217ac39a9b62270097940067'
for label,exe,version in [('312','/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python',[3,12,16]),('39','/tmp/openscrub-python39-20261117/venv/bin/python',[3,9,25])]:
    actual=subprocess.check_output([exe,'-I','-c','import sys;print(sys.version);print(sys.executable)']).decode()
    config={'task':'task656','scratch':str(ROOT/'runtime/task656/runs'),'source':str(SRC),'source_kind':'git','base':BASE,'head':head,'policy':'frozen','files':files,'modules':modules,'python':exe,'python_version':version,'min_free_bytes':2000000000,'configure_app':True,'prerequisites':prereqs+[{'path':exe,'sha256':sha(pathlib.Path(exe).read_bytes()),'executable':True}],'environment':old['environment']}
    save(f'frozen-{label}.json',config)
    save(f'interpreter-{label}.json',{'actual':actual,'executable_sha256':sha(pathlib.Path(exe).read_bytes())})
save('recipe-identities.json',{'prepare.py':sha(pathlib.Path(__file__).read_bytes()),'tooling':prereqs,'review_reports':{n:sha((ROOT/n).read_bytes()) for n in ['task-51-review.md','task-16331-review.md','task-116-review.md','task-6521-review.md']},'fixture':fixtures,'no_adapter':True,'no_model_seed':True})
print(json.dumps({'head':head,'changed':sorted(changed),'unchanged_count':len(unchanged),'production_count':len(production),'grammar_count':len(python_files),'modules':modules,'mapping':mapping,'status':'PASS'},indent=2))
