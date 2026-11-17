from pathlib import Path
art=Path('/tmp/openscrub-task632'); prior=Path('/tmp/openscrub-task631')
(art/'check_installed.py').write_text((prior/'check_installed.py').read_text().replace('task631','task632').replace('TASK631','TASK632'))
(art/'installed-hooks').mkdir(exist_ok=True)
(art/'installed-hooks/sitecustomize.py').write_text((prior/'installed-hooks/sitecustomize.py').read_text().replace('task631','task632').replace('TASK631','TASK632'))
s=(prior/'check_packaging.py').read_text().replace('task631','task632').replace('12919c96c6f7558136b50d7b4d85e5e6b62f1971','3457efac574d74a7d2377cbc0d44bb0b87462c3a').replace("assert (root/'pyproject.toml').read_text().replace('    \\\"benchmark\\\",\\n','')==old('pyproject.toml')", "assert (root/'pyproject.toml').read_text()==old('pyproject.toml')")
(art/'check_packaging.py').write_text(s)
floor=art/'floor-harness';floor.mkdir(exist_ok=True)
for name in ('sitecustomize.py','python39_isolation.py'):
    s=(Path('/tmp/openscrub-python39-20261117/harness')/name).read_text().replace('/tmp/openscrub-python39-20261117','/tmp/openscrub-task632')
    (floor/name).write_text(s)
(floor/'task632_floor.py').write_text('''from pathlib import Path
import sys
ROOT=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sys.path.insert(0,str(ROOT))
import python39_isolation
def pytest_configure(config):
    python39_isolation.configure('floor')
    import openscrub, openscrub_web, openscrub_internal.reports
    for module in (openscrub, openscrub_web, openscrub_internal.reports):
        assert Path(module.__file__).resolve().is_relative_to(ROOT), module.__file__
''')
(art/'tmp').mkdir(exist_ok=True)
