import ast, hashlib, json, pathlib, subprocess, tomllib
root=pathlib.Path('/tmp/openscrub-opencv-resolution-20261117')
pin='e21ebdf6e3ee46e6c65050dc956a9a3459152269'
def git(*args): return subprocess.check_output(['git',*args],cwd='/home/tahv0/src/OpenScrub')
manifest={'commit':pin,'tree':git('rev-parse',pin+'^{tree}').decode().strip(),'sources':{}}
for name in ['pyproject.toml','requirements.txt','install.py']:
    raw=git('show',pin+':'+name)
    (root/('source-'+name)).write_bytes(raw)
    manifest['sources'][name]={'blob':git('rev-parse',pin+':'+name).decode().strip(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
data=tomllib.loads((root/'source-pyproject.toml').read_text())
core=data['project']['dependencies']
assert core.count('opencv-python')==1
candidate=['opencv-python<5' if r=='opencv-python' else r for r in core]
(root/'core-original.in').write_text('\n'.join(core)+'\n')
(root/'core-candidate.in').write_text('\n'.join(candidate)+'\n')
manifest['requires_python']=data['project']['requires-python']
manifest['core_original']=core
manifest['core_candidate']=candidate
manifest['requirements_txt']=(root/'source-requirements.txt').read_text().splitlines()
tree=ast.parse((root/'source-install.py').read_text())
manifest['installer_core']=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CORE_PKGS' for t in n.targets))
manifest['candidate_delta']={'removed':'opencv-python','added':'opencv-python<5','other_core_changes':False}
for name in ['core-original.in','core-candidate.in']:
    raw=(root/name).read_bytes()
    manifest[name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
(root/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
