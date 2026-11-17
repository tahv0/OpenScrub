import ast,hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
src=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
base='4b9bd7e576a8ae30369672b4b4722fc9752e233f'; head='117e41ac5ee857a6b367caf6ccbd479d78989ff2'
def git(*args): return subprocess.check_output(['git',*args],cwd=src)
def blob(ref,p): return git('show',ref+':'+p)
def digest(b): return hashlib.sha256(b).hexdigest()
def status(command): return subprocess.run(['git',*command],cwd=src,stdout=subprocess.PIPE,stderr=subprocess.PIPE).returncode
pairs=[('e96deb59e1b3c36585672be4c74d90eb6d0a49b5','9999f25af550f14b9971131d1f76bf2767c9c595'),('952af20da205133886ba69799e134b86d1654137','77e51306eea8467bb2607d9df2b29eb2ec9b8cf8'),('9d888708d08cccf6e5f0ec8c9cf81740d3868fa1','afe0fd414736df4efca2586dc5147d20fabb4753'),('17dfe5d575306dea395b680205038e606ad598a2','3a1dc0bd5aa864cec85d463f51a12168a04e0687')]
prev=base; provenance=[]
for original,composed in pairs:
    assert git('rev-parse',composed+'^').decode().strip()==prev
    assert f'(cherry picked from commit {original})' in git('show','-s','--format=%B',composed).decode()
    assert status(['merge-base','--is-ancestor',original,base])==1
    provenance.append(dict(original=original,composed=composed,parent=prev,original_parent=git('rev-parse',original+'^').decode().strip()))
    prev=composed
assert git('rev-parse',head+'^').decode().strip()==prev
assert status(['merge-base','--is-ancestor',base,head])==0
for ref in ['e21ebdf6e3ee46e6c65050dc956a9a3459152269','9cee49f383a083b4954fad657446d233c08db425','533919313d293d2fab8fc15407c8a30d4dbca1a6','5408f87b965dcd66089677385b9ac9c0f4e24a3b','fe4b22f17b35c12ad2f35c95c0d7b89cd37faf37']:
    assert status(['merge-base','--is-ancestor',ref,base])==0
(root/'provenance.json').write_text(json.dumps(dict(base=base,head=head,picks=provenance,refs=git('branch','--format=%(refname:short) %(objectname)').decode().splitlines()),indent=2)+'\n')
# Preserve exact donor/composed differences: includes and prior guidance remain C01-owned.
patch=[]
for original,composed in pairs:
    patch.append('ORIGINAL '+original+' -> COMPOSED '+composed+'\n')
    patch.append(git('range-diff','--no-color',original+'^..'+original,composed+'^..'+composed).decode())
(root/'resolution.patch').write_text('\n'.join(patch))
(root/'combined.diff').write_bytes(git('diff',base,head))
# Runtime owners unchanged except the three approved definitions.
old=blob(base,'openscrub.py').decode();new=blob(head,'openscrub.py').decode()
def owners(text):
    return {n.name:digest(ast.get_source_segment(text,n).encode()) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
a,b=owners(old),owners(new)
changed=[name for name in sorted(a) if a[name]!=b[name]]
assert changed==['merge_detections','reverse_pass','run_scan'],changed
for ref,name in [(pairs[0][0],'merge_detections'),(pairs[2][0],'reverse_pass')]:
    assert owners(blob(ref,'openscrub.py').decode())[name]==b[name]
unchanged_files=['openscrub_web.py','zones_ui.py','openscrub_internal/__init__.py','openscrub_internal/lifetimes.py','openscrub_internal/reports.py','openscrub_internal/opencv_compat.py','pyproject.toml','tests/test_hdr_chroma_coverage.py','tests/test_polygon_fallback.py','tests/test_dense_smoothing_io.py','tests/test_manual_tracker_cancel.py','tests/test_report_roundtrip.py','tests/test_report_transactions.py']
for p in unchanged_files: assert blob(base,p)==blob(head,p),p
(root/'owner-hashes.json').write_text(json.dumps(dict(changed_definitions=changed,base_definitions=a,head_definitions=b,unchanged_files={p:digest(blob(head,p)) for p in unchanged_files}),indent=2)+'\n')
# Static recursive recipe membership, not a build or installed-startup claim.
meta=blob(head,'pyproject.toml').decode()
def include(section):
    text=meta.split('['+section+']',1)[1].split('\n[',1)[0]
    return ast.literal_eval(text.split('include =',1)[1].strip())
sdist=include('tool.hatch.build.targets.sdist');wheel=include('tool.hatch.build.targets.wheel')
assert {'openscrub_internal','tests','benchmark'}.issubset(sdist)
assert 'openscrub_internal' in wheel
assert 'requires-python = ">=3.9"' in meta
paths=git('ls-tree','-r','--name-only',head).decode().splitlines()
required=[p for p in paths if p.startswith(('openscrub_internal/','tests/','benchmark/'))]
assert all(any(p==i or p.startswith(i+'/') for i in sdist) for p in required)
dockers=[p for p in paths if p.startswith('Dockerfile')]
for p in dockers:
    assert blob(base,p)==blob(head,p)
    assert 'COPY openscrub_internal' in blob(head,p).decode()
(root/'static-package.json').write_text(json.dumps(dict(requires_python='>=3.9',metadata_sha256=digest(meta.encode()),metadata_equal_base=True,sdist=sdist,wheel=wheel,recursive_members={p:digest(blob(head,p)) for p in required},docker_unchanged={p:digest(blob(head,p)) for p in dockers},built=False),indent=2)+'\n')
# Assert the canonical helper is still the reviewed081 bytes.
helper=Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling')
for name in ['README.md','verify.py','verification_hook.py','sitecustomize.py']:
    assert (helper/name).read_bytes()==blob('081816d93d6aaa18944fc88f251040cf11d4135f',str(helper.relative_to(Path('/home/tahv0/src/OpenScrub'))/name))
assert not git('status','--porcelain')
subprocess.run(['git','diff','--check',base,head],cwd=src,check=True)
print(json.dumps(dict(base=base,head=head,changed_definitions=changed,unchanged_runtime_files=len(unchanged_files),sdist_recursive_files=len(required),dockerfiles=dockers,helper_matches_reviewed081=True,status='clean'),indent=2))
