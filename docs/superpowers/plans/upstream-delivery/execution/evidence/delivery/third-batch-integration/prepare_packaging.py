from pathlib import Path
import shutil
art=Path('/tmp/openscrub-task652')
for name in ['check_packaging.py','check_installed.py']:
 s=(Path('/tmp/openscrub-task651')/name).read_text().replace('task651','task652').replace('TASK651','TASK652').replace('aa07a0664ec0b9d3d592adba19e5e1e473e906ac','ac6496810b03d8b062ab9da150aeea1e62285fed').replace('dist-amended','dist')
 if name=='check_packaging.py':
  s=s.replace("sorted(expected_internal+['opencv_compat.py'])",'expected_internal')
 (art/name).write_text(s)
shutil.copytree('/tmp/openscrub-task651/installed-hooks',art/'installed-hooks',dirs_exist_ok=True)
p=art/'installed-hooks/sitecustomize.py';p.write_text(p.read_text().replace('task651','task652').replace('TASK651','TASK652'))
for name in ['installed_compat.py']:
 (art/name).write_text((Path('/tmp/openscrub-task651')/name).read_text().replace('task651','task652'))
