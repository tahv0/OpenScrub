from pathlib import Path
import shutil
art=Path('/tmp/openscrub-task651')
for name in ['check_packaging.py','check_installed.py']:
 s=(Path('/tmp/openscrub-task650')/name).read_text().replace('task650','task651').replace('TASK650','TASK651').replace('12919c96c6f7558136b50d7b4d85e5e6b62f1971','aa07a0664ec0b9d3d592adba19e5e1e473e906ac')
 if name=='check_packaging.py':
  s=s.replace('assert project==previous',"previous['dependencies']=[d.replace('opencv-python', 'opencv-python<5') if d=='opencv-python' else d for d in previous['dependencies']]\n assert project==previous")
  s=s.replace("assert (root/name).read_text()==old(name)","assert (root/name).read_text()==old(name).replace('opencv-python\\n','opencv-python<5\\n')")
  s=s.replace("assert sorted(p.name for p in (root/'openscrub_internal').glob('*.py'))==expected_internal", "assert sorted(p.name for p in (root/'openscrub_internal').glob('*.py'))==sorted(expected_internal+['opencv_compat.py'])")
  s=s.replace("metadata_python_floor':'>=3.9'", "metadata_python_floor':'>=3.9','opencv_bound': 'opencv-python<5'")
  s=s.replace(" for name in sources:assert archive.read(name)==(root/name).read_bytes(),name", " for name in sources:assert archive.read(name)==(root/name).read_bytes(),name\n assert 'Requires-Dist: opencv-python<5' in archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))).decode()")
  s=s.replace("tests+['test_openscrub.py'", "tests+['benchmark/review_io.py','benchmark/README.md','test_openscrub.py'")
 (art/name).write_text(s)
shutil.copytree('/tmp/openscrub-task650/installed-hooks',art/'installed-hooks',dirs_exist_ok=True)
p=art/'installed-hooks/sitecustomize.py';p.write_text(p.read_text().replace('task650','task651').replace('TASK650','TASK651'))
p=art/'installed_compat.py';p.write_text(Path('/tmp/openscrub-task91/fix1/installed_smoke.py').read_text().replace('/tmp/openscrub-task91/fix1/installed','/tmp/openscrub-task651/installed/site-packages'))
