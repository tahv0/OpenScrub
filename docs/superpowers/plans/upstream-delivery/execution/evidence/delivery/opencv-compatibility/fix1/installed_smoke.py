import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

root = Path('/tmp/openscrub-task91/fix1/installed')
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

# Exercise the installed helper and both real consumers with controlled ownership boundaries.
import contextlib
import io
source = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
assert Path(opencv_compat.__file__).read_bytes() == (source/'openscrub_internal/opencv_compat.py').read_bytes()
assert Path(openscrub_setup.__file__).read_bytes() == (source/'openscrub_setup.py').read_bytes()
controlled = []
def no_pip(*args, **kwargs):
    raise AssertionError('no pip is allowed for an ownership mismatch')
installer.pip = no_pip
for runtime, wheel in [('5.0.0', '4.14.0.94'), ('4.14.0', '5.0.0.93')]:
    data = dict(status='ok', version=runtime, path='/controlled/shadow/cv2.so',
                distributions={'opencv-python':wheel}, capability='ok', detail='')
    hint = opencv_compat.opencv_repair_hint(data, sys.executable)
    assert '--force-reinstall' not in hint and 'Reconcile cv2 ownership' in hint
    installer.probe_opencv = lambda executable, data=data: data
    openscrub_setup.probe_opencv = lambda executable, data=data: data
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        installer.step_core(check=False, yes=True)
        openscrub_setup.main(['--check'])
    assert '--force-reinstall' not in output.getvalue()
    assert output.getvalue().count('Reconcile cv2 ownership') == 2
    controlled.append(dict(runtime=runtime, wheel=wheel, consumers='installer+setup', output=output.getvalue()))
for runtime, wheel, capability in [('5.0.0','5.0.0.93','missing_api'), ('4.14.0','4.14.0.94','missing_xml')]:
    data = dict(status='ok', version=runtime, path='/controlled/normal/cv2.so',
                distributions={'opencv-python':wheel}, capability=capability, detail='')
    assert '--force-reinstall' in opencv_compat.opencv_repair_hint(data, sys.executable)
assert not network_events
print(json.dumps(dict(installed_controlled_mismatch_checks=controlled,
    positive_agreeing_unsupported_and_broken_controls=True,
    exact_installed_helper_source_bytes=True, network_events=network_events), indent=2))
