import ast, hashlib, json, pathlib, re, shutil, subprocess
ROOT=pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README'); OUT=ROOT/'task656-evidence'
SRC=pathlib.Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub'); RUNS=ROOT/'runtime/task656/runs'
def sha(b): return hashlib.sha256(b).hexdigest()
def save(n,o): (OUT/n).write_text(json.dumps(o,indent=2)+'\n')
def git(*args): return subprocess.check_output(['git',*args],cwd=SRC)
ident=json.loads((OUT/'source-identities.json').read_text()); prov=json.loads((OUT/'provenance.json').read_text())
assert git('rev-parse','HEAD').decode().strip()==ident['head']; assert not git('status','--porcelain=v1')
assert all(sha((SRC/p).read_bytes())==h for p,h in ident['files'].items())
refs=dict(line.split(' ',1) for line in git('for-each-ref','--format=%(refname) %(objectname)').decode().splitlines()); assert refs==prov['refs']
subprocess.run(['git','diff','--check',ident['base'],ident['head']],cwd=SRC,check=True)
results=[]; fixtures={}
helper='/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py'
controller='/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python'
for label,rid,seconds in [('312','task656-native-312-01',15.97),('39','task656-floor-39-01',17.08)]:
    run=RUNS/rid; dest=OUT/rid; dest.mkdir(exist_ok=False)
    cfg=json.loads((OUT/f'frozen-{label}.json').read_text())
    pre=json.loads((run/'preflight.json').read_text())
    log=(run/'logs/command.log').read_text()
    assert f'585 passed in {seconds}s' in log
    assert not re.search(r'\b(?:failed|skipped|warnings?|errors?)\b',log.splitlines()[-1],re.I)
    assert pre['head']==ident['head'] and pre['files']==ident['files']
    active=json.loads(next(line[len('ACTIVE_SOURCE '):] for line in log.splitlines() if line.startswith('ACTIVE_SOURCE ')))
    defaults=json.loads(next(line[len('DEFAULT_PATHS '):] for line in log.splitlines() if line.startswith('DEFAULT_PATHS ')))
    assert set(active['sources'])==set(ident['modules'])
    for mod,path in ident['modules'].items(): assert active['sources'][mod]=={'file':str(SRC/path),'sha256':ident['files'][path]}
    assert defaults['jobs']==str(SRC/'openscrub_jobs')
    shutil.copyfile(run/'preflight.json',dest/'preflight.json'); shutil.copyfile(run/'logs/command.log',dest/'command.log')
    for p in run.glob('runtime-*.json'): shutil.copyfile(p,dest/p.name)
    files={str(p.relative_to(run)):{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted((run/'pytest').rglob('*')) if p.is_file() and ('polygon-media' in str(p))}
    fixtures[rid]=files
    argv=[controller,helper,'--config',str(OUT/f'frozen-{label}.json'),'--run-id',rid,'run','--','-m','pytest',str(SRC/'tests/test_live_preview.py'),str(SRC/'tests/test_polygon_fallback.py'),'-q']
    actual=[cfg['python'],'-m','pytest',str(SRC/'tests/test_live_preview.py'),str(SRC/'tests/test_polygon_fallback.py'),'-q',f'--basetemp={run}/pytest','-o',f'cache_dir={run}/cache/pytest']
    results.append({'run_id':rid,'inner_helper_argv':argv,'actual_workload_argv':actual,'outer_environment':{'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','inheritance':'env -i; login:false'},'exit':0,'passed':585,'skipped':0,'failed':0,'seconds':seconds,'python':active['python'],'executable':active['executable'],'complete_owners':['tests/test_live_preview.py','tests/test_polygon_fallback.py'],'real_media_nodes':14,'media_prerequisite_contracts':9,'date_only_conditional_cases':2,'log_sha256':sha((run/'logs/command.log').read_bytes()),'default_paths':defaults,'run_bytes':sum(p.stat().st_size for p in run.rglob('*') if p.is_file())})
save('commands-results.json',results)
save('fixture-identities.json',{'policy':'Hashes and byte counts only; no media copies. tiny_media and observe_render AST identities are in static-checks.json. JPEG frame RNG seed/dimensions and complete owner assertions unchanged. Actual fixtures independently generated inside each owned run.','files':fixtures})
save('failures.json',{'unexpected_runtime_failures':[],'semantic_conflicts':[],'artificial_red':'Not run; exact previously reviewed whole commits imported. Original meaningful RED belongs to original tasks.','metadata_command_failures':[{'command':'cat /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task6521-evidence/config-native.json /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task655-evidence/config-native.json','exit':2,'output':'cat: /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task6521-evidence/config-native.json: No such file or directory\ncat: /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task655-evidence/config-native.json: No such file or directory','resolution':'Read actual named native-312.json and source-identities.json after bounded file discovery; no product/helper/environment changes.'}]})
save('self-review.json',{'head':ident['head'],'clean':True,'refs_unchanged_after_picks':True,'exact_four_whole_patch_ids_and_x_provenance':True,'only_four_files':True,'other_165_files_and_all_modes_equal':True,'complete_production_ast_docstrings_noncomment_tokens_equal':True,'all_existing_test_function_asts_preserved_except_reviewed_fixture_prerequisite_replacement':True,'combined_observer':'_render_into/_render_hdr_into; frame/buf locals preserved','metadata_and_recursive_inclusion_unchanged':True,'owning_native_and_floor':'585 passed each, 0 skips','findings':[],'next_gate':'Root fresh independent review; no working-ref advancement by implementer.'})
print(json.dumps({'head':ident['head'],'clean':True,'refs_preserved':True,'results':results},indent=2))
