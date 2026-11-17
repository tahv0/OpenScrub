"""Freeze task16330 Git-owned acceptance identities and static ownership checks."""
import ast, hashlib, json, subprocess
from pathlib import Path
repo=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
out=Path(__file__).resolve().parent.parent
scratch=out.parent/'runtime/task16330'
base='4a62e49d2f0896b737081cc92e1f92e9bcaee93f'
r='70ec464ca70b5e49751d778890f56029dced0b8a'
def git(*args): return subprocess.check_output(['git','-C',str(repo),*args])
def blob(ref,path): return git('show',ref+':'+path)
def sha(b): return hashlib.sha256(b).hexdigest()
def dump(name,value): (out/name).write_text(json.dumps(value,indent=2)+'\n')
head=git('rev-parse','HEAD').decode().strip()
assert head=='8768e86dc1cd57720fd1c22eb6b539ae6bda6cde'
assert not git('status','--porcelain')
commits=git('rev-list','--reverse',base+'..'+head).decode().split()
originals=['ded411cbec308333d1416ae3d58b4f6e918d7849','e9fd0d39bd9c10ddbaa121e9c91cc504921c5afb','cb7b7ff8577aa4e7c0db48916179a1521fb4b412','8e70af446caa5ed37e0e36c029925d5caf08f943',r]
assert len(commits)==len(originals)
for old,new in zip(originals,commits): assert '(cherry picked from commit '+old+')' in git('show','-s','--format=%B',new).decode()
dump('commit-map.json',dict(base=base,head=head,map=dict(zip(originals,commits))))
owned={'render','render_hdr','_stop_render_children'}
def parts(ref):
 text=blob(ref,'openscrub.py').decode(); tree=ast.parse(text); lines=text.splitlines(keepends=True)
 funcs={n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in owned}
 tree.body=[n for n in tree.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name not in owned]
 return funcs,ast.dump(tree,include_attributes=False)
f,other=parts(head); approved,_=parts(r); _,inherited=parts(base)
assert f==approved and other==inherited
tracked=git('ls-tree','-r','--name-only',head).decode().splitlines()
modules={p[:-3]:p for p in ['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py']}
modules.update({'openscrub_internal':'openscrub_internal/__init__.py','openscrub_internal.reports':'openscrub_internal/reports.py','openscrub_internal.lifetimes':'openscrub_internal/lifetimes.py'})
private=list(p for p in tracked if p.startswith('openscrub_internal/'))
rt=list(modules.values())
sdist=sorted(set(rt+['pyproject.toml','CONTRIBUTING.md','test_openscrub.py']+[p for p in tracked if p.startswith(('tests/','benchmark/'))]))
recipes=['Dockerfile','Dockerfile.cpu','Dockerfile.intel','requirements.txt']
recipes=[p for p in recipes if p in tracked]
files={p:sha(blob(head,p)) for p in sorted(set(sdist+recipes))}
checks={p:{'owner':base,'sha256':sha(blob(head,p)),'git_blob':git('rev-parse',head+':'+p).decode().strip()} for p in rt if p!='openscrub.py'}
for p in checks: assert blob(head,p)==blob(base,p)
for p in ['tests/test_render_resources.py','tests/test_hdr_decoder_cleanup.py']: assert blob(head,p)==blob(r,p)
dump('static-ownership.json',dict(renderer={k:sha(v.encode()) for k,v in f.items()},renderer_owner=r,other_engine_ast_equal_base=True,other_runtime=checks))
dump('source-manifest.json',dict(head=head,files={p:{'sha256':v,'git_blob':git('rev-parse',head+':'+p).decode().strip()} for p,v in files.items()}))
prereqs=[]
for name in ['ffmpeg','ffprobe','tesseract']:
 p=Path('/tmp/openscrub-baseline-20261116/tools/usr/bin')/name
 prereqs.append(dict(path=str(p),sha256=sha(p.read_bytes()),executable=True))
for name in ['prepare.py','environment.py','listening_smoke.py']:
 p=out/'adapters'/name;prereqs.append(dict(path=str(p),sha256=sha(p.read_bytes())))
for p in (Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling')).glob('*.py'):
 prereqs.append(dict(path=str(p),sha256=sha(p.read_bytes())))
cfg=dict(task='task16330',scratch=str(scratch/'runs'),source=str(repo),source_kind='git',base=base,head=head,policy='frozen',files=files,modules=modules,python='/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python',python_version=[3,12,16],min_free_bytes=2000000000,configure_app=True,prerequisites=prereqs,environment=dict(LD_LIBRARY_PATH='/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu/pulseaudio',TESSDATA_PREFIX='/tmp/openscrub-baseline-20261116/tools/usr/share/tesseract-ocr/5/tessdata',PATH='/tmp/openscrub-baseline-20261116/tools/usr/bin:/usr/bin:/bin'))
dump('frozen312.json',cfg)
cfg39=dict(cfg,python='/tmp/openscrub-python39-20261117/venv/bin/python',python_version=[3,9,25]);dump('frozen39.json',cfg39)
selection=[p for p in tracked if p.startswith('tests/') and p.endswith('.py') and p!='tests/test_review_save_failures.py']
assert len(selection)==11
(out/'selected-tests.txt').write_text('\n'.join(str(repo/p) for p in selection)+'\n')
(out/'selection-rationale.txt').write_text('Complete N09/R resource/finalization controls; raw document roundtrip, shared serializer/atomic failures, report transaction/cancellation/replay/no-op; selected-source and FILES lifetime, actual configured streamed response, and vault cleanup owners. Select all 11 owning files, excluding browser/JS review-save owner and unrelated test_openscrub.py general suite. Synthetic media generated by exact hashed test fixtures. No model-seeding adapter needed: selected real cases render existing reports and mock detector/tracker admission where appropriate. No G/P/C01 feature tests.\n')
print(head,len(files),'frozen files;',len(selection),'owning test files; static ownership PASS')
