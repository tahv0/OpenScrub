from pathlib import Path
import sys
ROOT=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sys.path.insert(0,str(ROOT))
import baseline_isolation
def pytest_configure(config):
    baseline_isolation.configure('/tmp/openscrub-task632/runtime')
    import openscrub, openscrub_web, openscrub_internal.reports
    for module in (openscrub, openscrub_web, openscrub_internal.reports):
        assert Path(module.__file__).resolve().is_relative_to(ROOT),module.__file__
