import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

root = Path('/tmp/openscrub-task91/installed-release')
network_events = []
def audit(event, args):
    if event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo'):
        network_events.append(event)
        raise AssertionError('network forbidden during installed check')
sys.addaudithook(audit)
import openscrub
import openscrub_setup
from openscrub_internal import opencv_compat
for module in (openscrub, openscrub_setup, opencv_compat):
    assert Path(module.__file__).is_relative_to(root), module.__file__
assert importlib.metadata.metadata('OpenScrub')['Requires-Python'] == '>=3.9'
result = opencv_compat.probe_opencv(sys.executable)
assert opencv_compat.assess_opencv(result)['state'] == 'healthy', result
assert openscrub_setup.main(['--check']) == 0
spec = importlib.util.spec_from_file_location('standalone_installer', '/home/tahv0/.codex/worktrees/c832/OpenScrub/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
assert installer.probe_opencv.__module__ == 'openscrub_internal.opencv_compat'
assert installer.PYTHON == sys.executable
installer.step_core(check=True, yes=False)
assert all(ok for _,ok,_ in installer.RESULTS), installer.RESULTS
assert not network_events
print(json.dumps(dict(python=sys.version, executable=sys.executable,
    imports={m.__name__:m.__file__ for m in (openscrub, openscrub_setup, opencv_compat)},
    opencv=result, network_events=network_events, installer_results=installer.RESULTS), indent=2))
