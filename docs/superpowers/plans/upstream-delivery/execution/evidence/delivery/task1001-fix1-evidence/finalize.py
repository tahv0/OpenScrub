"""Compact fix evidence only; preserve all original Task1001 payloads/indexes."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import zipfile

root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
task=root/'runtime/task1001/fix1';out=root/'task1001-fix1-evidence'
source=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
base='5acb655f98cc4699d4a05a5670e4e7ab33b477d6'
head='335435e1e1120de9e6773656b7dfdfabf220e27b'
def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(path.read_bytes())
def git(*args):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false',*args],cwd=source)
assert git('rev-parse','HEAD').decode().strip()==head and not git('status','--porcelain')
for name in ['original-task-1001-report.md','original-task-1001-pr.md']:
    old=out/name;new=out/(name+'.txt')
    if old.exists():old.rename(new)
    assert new.is_file()
old_evidence=root/'task1001-evidence'
old_manifest=json.loads((old_evidence/'manifest.json').read_text())
assert len(old_manifest)==132
for name,value in old_manifest.items():
    p=old_evidence/name
    assert p.stat().st_size==value['bytes'] and sha(p)==value['sha256']
old_indexes={name:dict(bytes=(old_evidence/name).stat().st_size,sha256=sha(old_evidence/name)) for name in ['manifest.json','SHA256SUMS','final-integrity.json']}
assert (old_evidence/'SHA256SUMS').read_text()==''.join(v['sha256']+'  '+k+'\n' for k,v in old_manifest.items())
original_integrity=json.loads((old_evidence/'final-integrity.json').read_text())
assert sha(out/'original-task-1001-report.md.txt')==original_integrity['report_sha256']
assert sha(out/'original-task-1001-pr.md.txt')==original_integrity['pr_sha256']
original=dict(payloads_checked=132,index_files=old_indexes,report_sha256=sha(out/'original-task-1001-report.md.txt'),pr_sha256=sha(out/'original-task-1001-pr.md.txt'))
(out/'original-evidence-integrity.json').write_text(json.dumps(original,indent=2)+'\n')
config=json.loads((task/'frozen-312.json').read_text())
assert len(config['files'])==130
for name,value in config['files'].items():
    assert sha(source/name)==value and digest(git('show',head+':'+name))==value
assert set(git('diff','--name-only',base,head).decode().splitlines())=={'openscrub_web.py','tests/test_exact_recovery_races.py'}
unchanged=['openscrub.py','openscrub_internal/exact_samples.py','openscrub_internal/lifetimes.py','openscrub_internal/reports.py','pyproject.toml','tests/test_job_response_lifetime.py']
for name in unchanged:assert git('show',base+':'+name)==(source/name).read_bytes()
def ui(text):
    result={}
    for node in ast.parse(text).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('APP_JS','APP_CSS'):
                    result[target.id]=ast.literal_eval(node.value)
    return result
assert ui(git('show',base+':openscrub_web.py').decode())==ui((source/'openscrub_web.py').read_text())
for line in (out/'pre-fix-refs.txt').read_text().splitlines():
    ref,value=line.split()
    assert git('rev-parse',ref).decode().strip()==(head if ref=='refs/heads/pr/exact-editor-samples' else value)
def without_messages(path):
    tree=ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node,ast.Assert):node.msg=None
    return ast.dump(tree,include_attributes=False)
assert without_messages(out/'red-test_exact_recovery_races.py')==without_messages(source/'tests/test_exact_recovery_races.py')
(out/'static-integrity.json').write_text(json.dumps(dict(base=base,head=head,source_files=130,runtime_modules=config['modules'],unchanged_owner_source=unchanged,unchanged_ui=['APP_JS','APP_CSS'],other_refs_preserved=True,test_diagnostic_only_ast_equivalence=True),indent=2)+'\n')
paths=[source/'tests'/name for name in ['test_exact_recovery_races.py','test_exact_samples.py','test_exact_adoption.py','test_exact_media.py','test_report_transactions.py','test_manual_addition_replay.py','test_job_response_lifetime.py']]
selection=['-m','pytest',*[str(p) for p in paths],'-q','-k','not test_configured_wsgi_closes_stream_owner_exactly_once or video']
records=[]
transform=None
for name,exit_code in [('fix1-red-002',1),('fix1-green-004',0),('fix1-native-006',0),('fix1-floor-007',0),('fix1-package-008',0)]:
    run=task/'runs'/name;destination=out/'runs'/name;destination.mkdir(parents=True,exist_ok=True)
    preflight=json.loads((run/'preflight.json').read_text())
    shutil.copyfile(run/'preflight.json',destination/'preflight.json')
    configs=sorted(run.glob('runtime-*.json'))
    for p in configs:shutil.copyfile(p,destination/p.name)
    for p in sorted((run/'logs').iterdir()):
        if name=='fix1-red-002' and p.name=='command.log':
            raw=p.read_bytes();text=raw.decode();replacements=[]
            pattern=r'"base64":"([A-Za-z0-9+/=]+)"'
            def replace(match):
                encoded=match.group(1).encode('ascii');jpeg=base64.b64decode(encoded,validate=True)
                record=dict(original_character_span=[match.start(),match.end()],matched_field_bytes=len(match.group(0).encode()),matched_field_sha256=digest(match.group(0).encode()),base64_characters=len(encoded),base64_sha256=digest(encoded),jpeg_bytes=len(jpeg),jpeg_sha256=digest(jpeg))
                replacements.append(record)
                return '"base64":"[image bytes omitted; JPEG bytes='+str(len(jpeg))+'; SHA256='+digest(jpeg)+']"'
            transformed=re.sub(pattern,replace,text)
            assert len(replacements)==3
            compact=('TRANSFORMED COMPACT DIAGNOSTIC COPY; NOT LOSSLESS. Only JPEG base64 values replaced by size/hash. Original runtime log remains unchanged.\n'+transformed).encode()
            (destination/'command.compact.log').write_bytes(compact)
            transform=dict(original_path=str(p),original_bytes=len(raw),original_sha256=digest(raw),archive_copy='runs/'+name+'/command.compact.log',archive_bytes=len(compact),archive_sha256=digest(compact),pattern=pattern,replaced_values=replacements,lossless=False)
        else:shutil.copyfile(p,destination/p.name)
    if (run/'package-identities.json').exists():shutil.copyfile(run/'package-identities.json',destination/'package-identities.json')
    log=run/'logs/command.log';text=log.read_text() if log.exists() else ''
    summary=next((line for line in reversed(text.splitlines()) if re.search(r'\d+ (passed|failed)',line)),None)
    workload=(['-m','pytest',str(source/'tests/test_exact_recovery_races.py'),'-q'] if name in ('fix1-red-002','fix1-green-004') else selection if name in ('fix1-native-006','fix1-floor-007') else None)
    records.append(dict(run=name,head=preflight['head'],policy=preflight['policy'],python=preflight['python'],actual_exit=exit_code,summary=summary,workload_argv=workload,controller_action='package' if name=='fix1-package-008' else 'run',runtime_configs=[p.name for p in configs],original_log_sha256=sha(log) if log.exists() else None))
(out/'red-diagnostic-transformation.json').write_text(json.dumps(transform,indent=2)+'\n')
(out/'commands-results.json').write_text(json.dumps(records,indent=2)+'\n')
selected=[]
for name in ['fix1-native-006','fix1-floor-007']:
    ids=json.loads((task/'runs'/name/'cache/pytest/v/cache/nodeids').read_text())
    assert len(ids)==157
    (out/(name+'-selected-ids.json')).write_text(json.dumps(ids,indent=2)+'\n')
    selected.append(ids)
manual_path=source/'tests/test_manual_addition_replay.py'
manual_text=manual_path.read_text()
assert "'x'*129" in manual_text and "'A0._:-'+'x'*122" in manual_text
prefix='tests/test_manual_addition_replay.py::'
aliases={
    prefix+'test_explicit_invalid_id_is_json_400_and_atomic['+'x'*129+']':prefix+'test_explicit_invalid_id_is_json_400_and_atomic[identity7]',
    prefix+'test_valid_id_boundaries_and_report_local_scope['+'A0._:-'+'x'*122+']':prefix+'test_valid_id_boundaries_and_report_local_scope[identity1]',
}
assert set(selected[1])-set(selected[0])==set(aliases)
assert set(selected[0])-set(selected[1])==set(aliases.values())
assert sorted(aliases.get(value,value) for value in selected[1])==selected[0]
collector_versions={}
for label,env in [('native','/tmp/openscrub-baseline-20261116/venv-opencv4'),('floor','/tmp/openscrub-python39-20261117/venv')]:
    metadata=list(Path(env).glob('lib/python*/site-packages/pytest-*.dist-info/METADATA'))
    assert len(metadata)==1
    version=next(line.split(': ',1)[1] for line in metadata[0].read_text().splitlines() if line.startswith('Version: '))
    collector_versions[label]=dict(version=version,metadata_file=str(metadata[0]),metadata_sha256=sha(metadata[0]))
assert collector_versions['native']['version']=='9.2.0' and collector_versions['floor']['version']=='8.4.2'
(out/'collector-id-aliases.json').write_text(json.dumps(dict(total_selected=157,verbatim_matching_ids=155,collector_versions=collector_versions,source_file='tests/test_manual_addition_replay.py',source_sha256=sha(manual_path),source_parameter_evidence=[dict(function='test_explicit_invalid_id_is_json_400_and_atomic',parameter='identity',parameter_index=7,expression="'x'*129",value='x'*129),dict(function='test_valid_id_boundaries_and_report_local_scope',parameter='identity',parameter_index=1,expression="'A0._:-'+'x'*122",value='A0._:-'+'x'*122)],exact_floor_to_native_display_aliases=aliases,all_other_ids_unchanged=True),indent=2)+'\n')
stream_prefix='tests/test_job_response_lifetime.py::test_configured_wsgi_closes_stream_owner_exactly_once'
deselected=[stream_prefix+'['+ending+'-'+endpoint+']' for ending in ['complete','iterator_error','disconnect'] for endpoint in ['download','report']]
(out/'selection.json').write_text(json.dumps(dict(workload_argv=selection,selected_count=157,deselected_count=6,selected_source_video_ids=[v for v in selected[0] if 'test_configured_wsgi' in v],deselected_ids=deselected,unchanged_permutation_evidence='Original full471 at5acb655; unchanged test/stream owner bytes'),indent=2)+'\n')
package=json.loads((task/'runs/fix1-package-008/package-identities.json').read_text())
new_test='tests/test_exact_recovery_races.py'
assert new_test in package['sdist_files']
with tarfile.open(package['sdist']['file']) as archive:
    members=archive.getmembers();prefix=members[0].name.split('/')[0]
    actual=archive.extractfile(prefix+'/'+new_test).read()
    assert digest(actual)==config['files'][new_test]
    sdist_total=sum(m.isfile() for m in members)
with zipfile.ZipFile(package['wheel']['file']) as archive:
    assert digest(archive.read('openscrub_web.py'))==config['files']['openscrub_web.py']
    wheel_total=sum(not name.endswith('/') for name in archive.namelist())
(out/'package-counts.json').write_text(json.dumps(dict(validated_sdist_files=len(package['sdist_files']),total_sdist_regular_files=sdist_total,validated_wheel_files=len(package['wheel_files']),total_wheel_regular_files=wheel_total,new_race_test=new_test,new_race_test_sha256=digest(actual),requires_python=package['requires_python'],sdist=package['sdist'],wheel=package['wheel']),indent=2)+'\n')
for p in [task/'prepare.py',task/'finalize.py',task/'frozen-312.json',task/'frozen-39.json']:
    shutil.copyfile(p,out/p.name)
print('Verified original132 payloads/index formats, repaired130 source files, diagnostic-only test edit, other refs, selected157 IDs, and new race-test sdist bytes')
print('Package byte assertions/regular totals:',len(package['sdist_files']),sdist_total,len(package['wheel_files']),wheel_total)
