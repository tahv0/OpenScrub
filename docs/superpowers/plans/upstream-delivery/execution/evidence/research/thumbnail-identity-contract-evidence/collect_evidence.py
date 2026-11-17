import ast, hashlib, json, pathlib, subprocess
root=pathlib.Path('/tmp/openscrub-thumbnail-identity-20261117/export')
out=pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/thumbnail-identity-contract-evidence')
repo=pathlib.Path('/home/tahv0/src/OpenScrub')
pin='12919c96c6f7558136b50d7b4d85e5e6b62f1971'
files=['openscrub_web.py','openscrub_internal/lifetimes.py','openscrub_internal/reports.py','pyproject.toml','Dockerfile','windows/openscrub.spec','openscrub_update.py']
manifest={'pin':pin,'export':str(root),'method':'git archive from original repository; static AST/text reads only; no product imports or schedules','files':{}}
for rel in files:
    content=(root/rel).read_bytes()
    pinned=subprocess.check_output(['git','show',pin+':'+rel],cwd=str(repo))
    assert content==pinned,rel
    manifest['files'][rel]={'sha256':hashlib.sha256(content).hexdigest(),'matches_git_show':True}
base=repo/'.superpowers/sdd/README/thumbnail-baseline-evidence/results.json'
manifest['reused_baseline']={'pin':'e21ebdf6e3ee46e6c65050dc956a9a3459152269','results_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'runtime_repeated':False}
assert manifest['reused_baseline']['results_sha256']=='b004cd653940fb6a828738baaa07c384cb5cafd4ff666f05aa329a6e1edf4f4b'
names={'_reserve_files_locked','_update_job_source','_own_files','_job_video','_report_current','_operation_valid','_begin_operation','_prepare_work','_run_job','enforce_vault_lock','_finish_file_response','_delete_job','job_cancel','_load_job_report','_frame_at','job_detections','job_detframe','job_boxes_at','job_thumb','job_save_edits','job_track_object','job_report','_vault_lock_locked','register_existing_jobs'}
lines=(root/'openscrub_web.py').read_text().splitlines()
tree=ast.parse('\n'.join(lines))
anchors=[]
for node in tree.body:
    if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names:
        anchors.append({'file':'openscrub_web.py','name':node.name,'start':node.lineno,'end':node.end_lineno})
manifest['anchors']=anchors
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
ranges=[(359,369),(430,464),(802,845),(965,1018),(1048,1068),(1176,1220),(1507,1519),(1541,1582),(1609,1662),(1720,1733),(1798,1807),(1876,1889),(1914,1923),(2241,2251),(2605,2642),(3250,3261),(3314,3326),(3340,3347),(3381,3387),(3396,3403),(3417,3423),(3501,3519),(3520,3547),(3920,3948)]
parts=['Pinned '+pin+'; excerpts, not runtime evidence.\n']
for start,end in ranges:
    parts.append('\nopenscrub_web.py:'+str(start)+'-'+str(end)+'\n'+ '\n'.join(str(i)+': '+lines[i-1] for i in range(start,end+1)))
for rel in ['openscrub_internal/lifetimes.py','openscrub_internal/reports.py','windows/openscrub.spec','openscrub_update.py']:
    ls=(root/rel).read_text().splitlines()
    if rel.endswith('lifetimes.py') or rel.endswith('reports.py'):
        parts.append('\n'+rel+'\n'+'\n'.join(str(i)+': '+line for i,line in enumerate(ls,1)))
    else:
        for i,line in enumerate(ls,1):
            if 'openscrub_internal' in line or 'collect_submodules' in line or ('copy' in line and 'tree' in line):
                parts.append('\n'+rel+':'+str(i)+'\n'+'\n'.join(str(k)+': '+ls[k-1] for k in range(max(1,i-3),min(len(ls),i+3)+1)))
(out/'pinned-source-excerpts.txt').write_text('\n'.join(parts)+'\n')
print(json.dumps({'status':'PASS','pin':pin,'export_files_match_git_show':len(files),'baseline_results_digest_matches':True,'product_imports':0,'runtime_schedules':0,'source_anchor_count':len(anchors)},indent=2))
