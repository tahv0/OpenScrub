from pathlib import Path
import sys
ROOT=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sys.path.insert(0,str(ROOT))
import python39_isolation
def pytest_configure(config):
    python39_isolation.configure('floor')
    import openscrub, openscrub_web, openscrub_internal.reports
    for module in (openscrub, openscrub_web, openscrub_internal.reports):
        assert Path(module.__file__).resolve().is_relative_to(ROOT), module.__file__
