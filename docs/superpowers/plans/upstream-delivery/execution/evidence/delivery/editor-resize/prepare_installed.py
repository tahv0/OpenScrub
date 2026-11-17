from pathlib import Path
art=Path('/tmp/openscrub-task164');site=art/'installed/site-packages'
(art/'installed-hooks').mkdir(exist_ok=True)
s=Path('/tmp/openscrub-task652/installed-hooks/sitecustomize.py').read_text().replace('task652','task164').replace('TASK652','TASK164')
(art/'installed-hooks/sitecustomize.py').write_text(s)
s=(art/'task164_isolation.py').read_text().replace("ROOT = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')", "ROOT = Path('/tmp/openscrub-task164/installed/site-packages')").replace("ART = Path('/tmp/openscrub-task164')", "ART = Path('/tmp/openscrub-task164/installedqa')").replace('assert Path.cwd() == ROOT, Path.cwd()', "assert Path.cwd() == ART / 'cwd', Path.cwd()")
(art/'task164installed_isolation.py').write_text(s)
(art/'installedqa/cwd').mkdir(parents=True,exist_ok=True)
