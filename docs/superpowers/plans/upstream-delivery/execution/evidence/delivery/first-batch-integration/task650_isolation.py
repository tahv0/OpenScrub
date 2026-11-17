from pathlib import Path
import baseline_isolation

def pytest_configure(config):
    baseline_isolation.ROOT=Path('/tmp/openscrub-task650')
    web=baseline_isolation.configure('runtime')
    source=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
    import openscrub
    assert Path(web.__file__).resolve()==source/'openscrub_web.py'
    assert Path(openscrub.__file__).resolve()==source/'openscrub.py'
