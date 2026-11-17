import ast,hashlib,json,os,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
runs=root.parent/'runtime/task653/runs'
manifest={}
for label in ['collect-312','discovery-312','acceptance-312','acceptance-39']:
    run=runs/label
    output=root/'runs'/label
    output.mkdir(parents=True,exist_ok=True)
    for p in [run/'preflight.json',*(run/'logs').glob('*.log')]:
        shutil.copyfile(p,output/p.name)
    fixtures={}
    for p in run.rglob('*'):
        if p.is_file() and p.suffix in ['.avi','.mp4','.mkv','.yuv']:
            fixtures[str(p.relative_to(run))]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    manifest[label]=dict(fixtures=fixtures,preflight_sha256=hashlib.sha256((run/'preflight.json').read_bytes()).hexdigest())
(root/'actual-fixture-identities.json').write_text(json.dumps(manifest,indent=2)+'\n')
source=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
recipes={}
for path,names in [('tests/test_batch_integration.py',['test_scan_reverse_onset_and_fragment_tail_preserve_partitioned_report','scan_setup']),('tests/test_first_scan_sanity.py',['scan_and_report']),('tests/test_polygon_fallback.py',['tiny_media']),('tests/test_manual_tracker_cancel.py',['make_video','media']),('tests/test_report_roundtrip.py',['review'])]:
    text=(source/path).read_text()
    for node in ast.parse(text).body:
        if getattr(node,'name',None) in names:
            recipes[path+'::'+node.name]=hashlib.sha256(ast.get_source_segment(text,node).encode()).hexdigest()
(root/'fixture-recipe-hashes.json').write_text(json.dumps(recipes,indent=2)+'\n')
# Environment metadata only: no product imports, -I ignores prepared editable paths.
code='''import importlib.metadata as m,json,sys
names=['numpy','opencv-python','opencv-python-headless','rapidfuzz','pytesseract','Flask','cryptography','onnxruntime','pytest','cheroot']
versions={}
for name in names:
 try: versions[name]=m.version(name)
 except m.PackageNotFoundError: versions[name]=None
print(json.dumps(dict(executable=sys.executable,version=sys.version,distributions=versions)))'''
versions={}
env=dict(os.environ)
for name in ['PYTHONPATH','PYTEST_PLUGINS','PYTEST_ADDOPTS','VERIFY_RUN','VERIFY_CONFIG']:env.pop(name,None)
for label in ['312','39']:
    cfg=json.loads((root/f'config-{label}.json').read_text())
    cmd=[cfg['python'],'-I','-B','-c',code]
    versions[label]=dict(command=cmd,metadata=json.loads(subprocess.check_output(cmd,env=env,text=True)))
(root/'prepared-interpreter-metadata.json').write_text(json.dumps(versions,indent=2)+'\n')
print('Collected compact logs for',len(manifest),'runs; generated fixture hashes for',sum(len(x['fixtures']) for x in manifest.values()),'media files; copied no media.')
