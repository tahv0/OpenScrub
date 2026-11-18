from pathlib import Path
import hashlib,json,re,shutil,subprocess
E=Path(__file__).parent;R=E.parent;RUNS=R/'runtime/task657/runs';S=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub');B='d1eeebd2b12645a7284344fb16ec589c8aba0ce7'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false',*args],cwd=S)
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
commands=[]
for run in sorted(RUNS.iterdir()):
 if not run.is_dir() or not (run/'preflight.json').exists():continue
 dest=E/'runs'/run.name;dest.mkdir(parents=True,exist_ok=True)
 for p in [*run.glob('runtime-*.json'),run/'preflight.json',*sorted((run/'logs').glob('*.log')),*[run/n for n in ['browser-results.json','touch-precondition.json','http-results.json','output-check.json','initial-report.json','pre-render-report.json','package-identities.json']]]:
  if p.is_file():shutil.copyfile(p,dest/p.name)
 pre=json.loads((run/'preflight.json').read_text())
 entry=dict(run=run.name,head=pre.get('head'),python=pre.get('python'),command_log=str((dest/'command.log').relative_to(E)) if (dest/'command.log').exists() else None)
 matches=[]
 for p in E.glob('*launch.log'):
  text=p.read_text()
  if str(run) in text:
   matches.append(dict(log=p.name,commands=[json.loads(line[8:]) for line in text.splitlines() if line.startswith('COMMAND ')],results=[json.loads(line[7:]) for line in text.splitlines() if line.startswith('RESULT ')]))
 entry['launch_records']=matches
 commands.append(entry)
save(E/'commands-results.json',commands)
for n,src in [('mobile-controls.png',RUNS/'task657-browser-06/mobile.png'),('mobile-help.png',RUNS/'task657-touch-02/filtered.png')]:shutil.copyfile(src,E/n)
commits=git('rev-list','--reverse',B+'..HEAD').decode().splitlines()
save(E/'provenance.json',dict(base=B,head=git('rev-parse','HEAD').decode().strip(),branch=git('branch','--show-current').decode().strip(),mapping={'ac28a2ac981f2612cbaeadedddbfac8db1efeefb':commits[0],'c0ebcc7a8c3121330730bea3619bbfea8add7992':commits[1]},followups=[dict(commit=c,subject=git('show','-s','--format=%s',c).decode().strip()) for c in commits[2:]],conflicts=['openscrub_web.py: metadata/render/lifecycle block; batch/setters; marquee setup/completion; selected bulk'],resolution='Retain current C01 metadata Map, scheduler shells/queue/lifetime, captured-owner visibility seam, openJob/loadReview teardown/request guards, one batch and scheduler selectionCleanup; graft P15 category/section/filter/count UI and live eligibility.',escape_fix='5b9241b: global Escape auto-pick referenced removed donor cancelReviewMarquee; actual listener RED then sole current scheduler cleanup invocation.',source_export=False,publication=False,ref_advance=False))
(E/'final.diff').write_bytes(git('diff','-U0',B,'HEAD','--','openscrub_web.py','tests'))
# Exact reuse boundary: final-head product + owning tests equal both final native/floor executed head.
prior='5b9241b';names=['openscrub_web.py','tests/test_review_filters.py','tests/test_review_choices.py','tests/test_review_save_failures.py','tests/test_thumbnail_scheduling.py','tests/test_job_polling_node.py','test_openscrub.py']
comparison={}
for p in names:
 a=git('show',prior+':'+p);b=git('show','HEAD:'+p);assert a==b;comparison[p]=hashlib.sha256(b).hexdigest()
save(E/'acceptance-identities.json',dict(native_floor_head=git('rev-parse',prior).decode().strip(),browser_http_head=git('rev-parse','4162e56').decode().strip(),final_touch_package_head=git('rev-parse','HEAD').decode().strip(),native_floor_files_identical_at_final_head=comparison,product_sha256=comparison['openscrub_web.py'],screenshots={n:sha(E/n) for n in ['mobile-controls.png','mobile-help.png']}))
save(E/'self-review.json',dict(author_review=True,fresh_independent_review='root assigns next; not claimed',checks=['complete P15 donor and current C01 source mapping','one metadata Map and pending EN overlay; zone singleton/category grouping/order','current scheduler/queue/layout/focus teardown and owner fences retained','single batch, complete hidden category/zone scopes, explicit matching selected ID scope','no filter-induced I/O/editor/save/render mutation','actual Escape listener RED/current selectionCleanup GREEN','native/floor final product and owning tests identical to final head','complete real saved/post-render raw document and decoded pixels','offline extracted-sdist wheel/installed source origins','Python3.9 grammar, unchanged backend AST/other production/defaults/dependencies'],blocking_findings=[],limits=['author self-review; root independent review pending','controlled pagehide/pageshow lifecycle dispatch, not native BFCache navigation certification','virtual native touch in headless Chromium, not physical touch-device certification','Linux CPU/headless Chromium only; no cross-platform/browser/GPU/performance/memory claim']))
files={str(p.relative_to(E)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(E.rglob('*')) if p.is_file() and p.name not in ['manifest.json','SHA256SUMS']}
save(E/'manifest.json',files)
(E/'SHA256SUMS').write_text(''.join(v['sha256']+'  '+p+'\n' for p,v in files.items()))
print(json.dumps(dict(files=len(files),bytes=sum(v['bytes'] for v in files.values()),head=git('rev-parse','HEAD').decode().strip()),indent=2))
