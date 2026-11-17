import ast,subprocess,tarfile,zipfile
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
for filename in ('openscrub.py','openscrub_web.py','zones_ui.py'):
 tree=ast.parse((root/filename).read_text(),filename=filename,feature_version=(3,9));print(filename,'Python3.9 parse OK')
tree=ast.parse((root/'openscrub_web.py').read_text());js=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets));p=Path('/tmp/openscrub-task71/evaluated-app.js');p.write_text(js);subprocess.run(['node','--check',str(p)],check=True);print('evaluated APP_JS Node parse OK')
with tarfile.open('/tmp/openscrub-task71/dist-final/openscrub-1.0.96.tar.gz') as tf:
 names=tf.getnames();assert any(x.endswith('/tests/test_review_save_failures.py') for x in names);assert any(x.endswith('/test_openscrub.py') for x in names);assert tf.extractfile(next(x for x in names if x.endswith('/openscrub_web.py'))).read()==(root/'openscrub_web.py').read_bytes();assert tf.extractfile(next(x for x in names if x.endswith('/tests/test_review_save_failures.py'))).read()==(root/'tests/test_review_save_failures.py').read_bytes();print('sdist root + tests regression sources included; exact final source bytes verified')
with zipfile.ZipFile('/tmp/openscrub-task71/dist-final/openscrub-1.0.96-py3-none-any.whl') as z:
 assert 'openscrub_web.py' in z.namelist();assert z.read('openscrub_web.py')==(root/'openscrub_web.py').read_bytes();print('wheel exact final source bytes verified')
