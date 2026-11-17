"""Verify pinned-source immutability, complete-script identity and final evidence."""
from pathlib import Path
import ast, hashlib, json, subprocess, shutil
ROOT=Path('/tmp/openscrub-polling-baseline-20261117')
REPO=Path('/home/tahv0/src/OpenScrub')
OUT=REPO/'.superpowers/sdd/README/polling-baseline-evidence'
PIN='92124753736e287ac800af91f0ac96f3e96c01be'
def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
manifest=[]
for entry in git('ls-tree','-r','-z',PIN).split(b'\0'):
 if not entry:continue
 header,name=entry.split(b'\t',1);mode,typ,oid=header.split();name=name.decode()
 expected=git('cat-file','blob',oid.decode());actual=(ROOT/'pinned'/name).read_bytes()
 assert actual==expected,name
 manifest.append({'path':name,'git_blob':oid.decode(),'sha256':hashlib.sha256(actual).hexdigest()})
source=(ROOT/'pinned/openscrub_web.py').read_text()
app_js=next(ast.literal_eval(n.value) for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))
assert (ROOT/'app.js').read_text()==app_js
assert (ROOT/'emitted.html').read_text().count(app_js)==1
results=json.loads((ROOT/'browser-results.json').read_text())['results']
assert len(results)==17
assert all(r['unreleasedGates']==0 for r in results)
expected_errors={'transient-metadata-network-failure-then-success':['Failed to fetch'],'transient-log-network-failure-then-success':['Failed to fetch'],'http503-json-is-published-without-status-check':["Failed to set the 'value' property on 'HTMLProgressElement': The provided double value is non-finite."]}
for r in results:assert r['errors']==expected_errors.get(r['name'],[]),r['name']
body=next(r for r in results if r['name']=='metadata-headers-with-unfinished-body')
assert body['before']['headers']==3 and body['before']['bodyFinished']==2
assert body['after']['bodyFinished']==3
assert (ROOT/'server.log').read_text().strip()=='Pinned polling QA http://127.0.0.1:18513'
for name in ['browser.cjs','serve.py','verify.py','browser-results.json','server-identity.json','overlap-duplicate-log.png','browser.log','server.log']:
 shutil.copyfile(ROOT/name,OUT/name)
lines=source.splitlines()
ranges=[(1060,1072),(2080,2273),(2275,2288),(2324,2337),(2404,2436),(2548,2578),(2732,2755),(2777,2784),(2858,2865),(3190,3214)]
(OUT/'source-excerpts.txt').write_text('\n\n'.join(f'PIN {PIN} openscrub_web.py:{a}-{b}\n'+'\n'.join(f'{n+1}: {lines[n]}' for n in range(a-1,b)) for a,b in ranges)+'\n')
(OUT/'source-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
verification={'status':'passed','pin':PIN,'tracked_export_files_identical':len(manifest),'full_unmodified_app_js_in_emitted_page':True,'scenario_count':len(results),'all_browser_route_gates_released':True,'actual_http_body_gates_completed':True,'expected_fault_scenarios_only':True,'server_log_clean':True,'no_product_changes':True,'unavailable':'Native background-tab throttling/OS suspension timing; ignore-abort helper implementation (future tests)'}
(OUT/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
(OUT/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
print(json.dumps(verification,indent=2))
