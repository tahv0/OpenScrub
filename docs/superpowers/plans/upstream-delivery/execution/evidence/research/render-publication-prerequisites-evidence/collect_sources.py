"""Source-only Git-object inventory. Never imports or executes product code."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/home/tahv0/src/OpenScrub')
OUT = ROOT / '.superpowers/sdd/README/render-publication-prerequisites-evidence'
REFS = {
 'test_baseline': 'e21ebdf6e3ee46e6c65050dc956a9a3459152269',
 'p06a': 'c7cf1f02d98742e93a728e4b1e94d8c6bd02c318',
 'p06a_vault_fix': '66787aa09a958154e81e75f9bdc54d9788feb843',
 'p06d': '7063082ef2a2ff5e56d9aafacff9bd43363b05b3',
 'p07a_composed': '7f82f3ac901b85bdb630ce4a006a3c4064c96a62',
 'p07a_audio_fix_composed': '3795d49f6293baf7b8c35534862a4881447e1b16',
 'p06b1': '4479b57612f4e5c463d31900f76277a5fcebb8a9',
 'p06b1_source_fix': 'c697d5a686d4dccbdf4f474567628d5d24e75a03',
 'p06b2': 'f2cdf4813c86296644911f3f0b09bfc56d3e03c5',
 'p07b': '12919c96c6f7558136b50d7b4d85e5e6b62f1971',
 'p06c1': '3457efac574d74a7d2377cbc0d44bb0b87462c3a',
 'p06c2': '4a62e49d2f0896b737081cc92e1f92e9bcaee93f',
 'n09': 'ded411cbec308333d1416ae3d58b4f6e918d7849',
 'r_initial_pending': 'e9fd0d39bd9c10ddbaa121e9c91cc504921c5afb',
 'r_test_selection_pending': 'cb7b7ff8577aa4e7c0db48916179a1521fb4b412',
 'r_old_review_head_pending': '8e70af446caa5ed37e0e36c029925d5caf08f943',
 'r_fix_pending_review': '70ec464ca70b5e49751d778890f56029dced0b8a',
 'g_reviewed_c01_only': '83af23b5fd3c5922d0d476ba2a6ae21a3598ced2',
 'c01_validation_target_only': '4b9bd7e576a8ae30369672b4b4722fc9752e233f',
}

def git(*args):
 return subprocess.check_output(['git', '-C', str(ROOT), *args])

def blob(ref, path):
 return git('show', ref + ':' + path)

manifest = {'kind': 'source-only; no product imports/tests/runtime probes', 'refs': {}, 'files': [], 'local_files': []}
for name, ref in REFS.items():
 assert git('cat-file', '-t', ref).strip() == b'commit'
 manifest['refs'][name] = {'sha': ref, 'parents_subject': git('show', '-s', '--format=%P %s', ref).decode().strip()}
files = ['openscrub.py','openscrub_web.py','openscrub_vault.py','openscrub_internal/lifetimes.py','openscrub_internal/reports.py','pyproject.toml','CONTRIBUTING.md','Dockerfile','Dockerfile.intel','Dockerfile.cuda','openscrub_update.py']
for label in ['p06c2','r_old_review_head_pending','r_fix_pending_review','n09','g_reviewed_c01_only','c01_validation_target_only']:
 ref = REFS[label]
 for path in files:
  result = subprocess.run(['git','-C',str(ROOT),'cat-file','-e',ref+':'+path],capture_output=True)
  if result.returncode:
   continue
  data = blob(ref,path)
  manifest['files'].append({'ref':ref,'path':path,'git_blob':git('rev-parse',ref+':'+path).decode().strip(),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
local_paths = ['docs/superpowers/plans/upstream-delivery/03-packaging-and-review-features.md','.superpowers/sdd/README/render-delivery-contract-research.md','docs/superpowers/plans/upstream-delivery/execution/tooling/README.md','docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py','docs/superpowers/plans/upstream-delivery/execution/tooling/verification_hook.py','docs/superpowers/plans/upstream-delivery/execution/tooling/sitecustomize.py']
for path in local_paths:
 data = (ROOT/path).read_bytes()
 manifest['local_files'].append({'path':path,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
(OUT/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

excerpts = {
 'engine-and-report-excerpts.txt': [('p06c2','openscrub.py',[(6286,6346),(8451,8465),(8488,8520),(6052,6061)]),('p06c2','openscrub_internal/reports.py',[(1,43)]),('r_fix_pending_review','openscrub.py',[(3887,3894),(3937,3962),(4090,4145),(4358,4416)])],
 'web-owner-and-reader-excerpts.txt': [('p06c2','openscrub_internal/lifetimes.py',[(10,70),(73,104)]),('p06c2','openscrub_web.py',[(344,367),(418,441),(802,871),(965,978),(1087,1117),(1181,1223),(1469,1504),(1661,1699),(2265,2285),(4331,4349),(4482,4505),(4546,4565)])],
 'vault-package-excerpts.txt': [('p06c2','openscrub_vault.py',[(158,204)]),('p06c2','pyproject.toml',[(90,126)]),('p06c2','openscrub_update.py',[(157,181)]),('p06c2','Dockerfile',[(60,64)]),('p06c2','Dockerfile.intel',[(94,98)]),('p06c2','Dockerfile.cuda',[(132,136)])],
}
for outname, entries in excerpts.items():
 blocks=[]
 for label,path,ranges in entries:
  ref=REFS[label]; lines=blob(ref,path).decode().splitlines()
  for first,last in ranges:
   blocks.append(f'=== {ref}:{path}:{first}-{last} ===\n'+'\n'.join(f'{i}: {lines[i-1]}' for i in range(first,min(last,len(lines))+1)))
 (OUT/outname).write_text('\n\n'.join(blocks)+'\n')

parts=[]
for a,b,paths in [('test_baseline','p06c2',['openscrub.py']),('test_baseline','r_old_review_head_pending',['openscrub.py']),('r_old_review_head_pending','r_fix_pending_review',['openscrub.py']),('test_baseline','p06c2',['pyproject.toml','CONTRIBUTING.md']),('test_baseline','n09',['pyproject.toml','CONTRIBUTING.md'])]:
 d=git('diff','--unified=0',REFS[a],REFS[b],'--',*paths).decode()
 if paths==['openscrub.py'] and a=='test_baseline':
  d='\n'.join(line for line in d.splitlines() if line.startswith(('diff ','---','+++','@@')))+'\n'
 parts.append(f'=== {a}..{b} ===\n'+d)
parts.append('=== Serializer whole-commit dependencies ===\n'+git('show','--format=','--stat',REFS['p06c2']).decode())
(OUT/'overlap-map.txt').write_text('\n'.join(parts))

parts=[]
for path in ['tests/test_report_transactions.py','tests/test_job_response_lifetime.py','tests/test_job_source_allowlist_lifecycle.py','tests/test_report_roundtrip.py','tests/test_report_serialization.py','tests/test_vault_cleanup.py']:
 tree=ast.parse(blob(REFS['p06c2'],path));parts.append(f'=== {REFS["p06c2"]}:{path} ===')
 parts.extend(f'{n.lineno}: {n.name}' for n in tree.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test'))
(OUT/'existing-test-owners.txt').write_text('\n'.join(parts)+'\n')
print('Wrote compact source manifests/excerpts only to', OUT)
print('Verified',len(REFS),'commit objects;',len(manifest['files']),'source blob identities')
