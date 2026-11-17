"""Behavior gates: refuse invalid setup before executing the caller's workload."""
import hashlib
import json
import os
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'verify.py'
SCRATCH = Path(os.environ['VERIFICATION_TEST_ROOT'])


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='fixture-', dir=SCRATCH))
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'sample.py').write_text('VALUE = 17\n')
        (self.source / '.verification-source.json').write_text(json.dumps({'head': 'fixture-head', 'base': 'fixture-base'}))
        self.config = {'task': 'test901', 'scratch': str(self.root / 'scratch'), 'source': str(self.source),
                       'source_kind': 'export', 'head': 'fixture-head', 'base': 'fixture-base', 'policy': 'frozen',
                       'files': {'sample.py': hashlib.sha256(b'VALUE = 17\n').hexdigest()},
                       'modules': {'sample': 'sample.py'}, 'python': sys.executable,
                       'python_version': list(sys.version_info[:3]), 'min_free_bytes': 1,
                       'environment': {}, 'prerequisites': [], 'configure_app': False}
        (self.root / 'scratch').mkdir()
        self.cfg = self.root / 'config.json'

    def invoke(self, args=(), command=None, config=None):
        self.cfg.write_text(json.dumps(config or self.config))
        invocation = [sys.executable, str(TOOL), '--config', str(self.cfg)] + list(args)
        if command is not None:
            invocation += ['run', '--'] + command
        else:
            invocation += ['preflight']
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run(invocation, cwd=self.root, env=env, capture_output=True, text=True)

    def assert_setup_failure(self, text, change):
        change()
        result = self.invoke(command=['-c', "raise Exception('WORKLOAD_STARTED')"])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(text, result.stderr)
        self.assertNotIn('WORKLOAD_STARTED', result.stderr)

    def test_refuses_wrong_source(self):
        self.assert_setup_failure('source head', lambda: self.config.update(head='wrong'))

    def test_refuses_wrong_hash(self):
        self.assert_setup_failure('hash mismatch', lambda: self.config['files'].update({'sample.py': '0' * 64}))

    def test_refuses_wrong_interpreter(self):
        self.assert_setup_failure('interpreter version', lambda: self.config.update(python_version=[1, 2, 3]))

    def test_refuses_unsafe_scratch_and_creates_nothing(self):
        self.config['scratch'] = str(self.source)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('scratch overlaps source', result.stderr)
        self.assertEqual(sorted(p.name for p in self.source.iterdir()), ['.verification-source.json', 'sample.py'])

    def test_refuses_symlink_scratch(self):
        link = self.root / 'linked'
        link.symlink_to(self.root / 'scratch', target_is_directory=True)
        self.config['scratch'] = str(link)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr)

    def test_refuses_missing_prerequisite_and_low_space(self):
        self.config['prerequisites'] = [{'path': str(self.root / 'absent')}]
        self.assertIn('prerequisite', self.invoke().stderr)
        self.config['prerequisites'] = []
        self.config['min_free_bytes'] = 10 ** 30
        self.assertIn('free space', self.invoke().stderr)

    def test_unique_runs_and_duplicate_run_preserves_existing_output(self):
        one = self.invoke(args=['--run-id', 'one'], command=['-c', "from pathlib import Path; Path('result.txt').write_text('owned')"])
        self.assertEqual(one.returncode, 0, one.stderr)
        duplicate = self.invoke(args=['--run-id', 'one'])
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn('already exists', duplicate.stderr)
        self.assertEqual((self.root / 'scratch/one/result.txt').read_text(), 'owned')
        two = self.invoke(command=['-c', 'pass'])
        self.assertEqual(two.returncode, 0, two.stderr)
        self.assertEqual(len([p for p in (self.root / 'scratch').iterdir() if p.is_dir()]), 2)

    def test_direct_child_isolation_and_result_persistence(self):
        script = """import os, subprocess, sys, socket
from pathlib import Path
import sample
assert sample.VALUE == 17
root = Path(os.environ['VERIFY_RUN'])
assert Path(os.path.expanduser('~')) == root / 'profile'
assert Path(os.environ['TMPDIR']) == root / 'tmp'
try:
    Path(sys.argv[1]).write_text('forbidden')
except RuntimeError:
    pass
else:
    raise AssertionError('outside write accepted')
try:
    socket.socket().connect(('192.0.2.1', 80))
except RuntimeError:
    pass
else:
    raise AssertionError('outside connect accepted')
subprocess.run([sys.executable, '-c', 'import sample; assert sample.VALUE == 17'], check=True)
print('SUCCESS_OUTPUT')
sys.stderr.write('FAILURE_OUTPUT\\n')
sys.exit(int(sys.argv[2]))
"""
        for number, code in enumerate((0, 7)):
            result = self.invoke(args=['--run-id', 'result' + str(number)], command=['-c', script, str(self.root / 'denied'), str(code)])
            self.assertEqual(result.returncode, code, result.stderr + result.stdout)
            log = (self.root / ('scratch/result' + str(number)) / 'logs/command.log').read_text()
            self.assertIn('SUCCESS_OUTPUT', log)
            self.assertIn('FAILURE_OUTPUT', log)
        self.assertFalse((self.root / 'denied').exists())

    def test_pytest_uses_owned_basetemp_and_same_hook(self):
        test = self.source / 'test_fixture.py'
        test.write_text("import os\nfrom pathlib import Path\ndef test_isolated(tmp_path):\n import sample\n assert sample.VALUE == 17\n assert tmp_path.is_relative_to(Path(os.environ['VERIFY_RUN']) / 'pytest')\n assert Path(os.path.expanduser('~')) == Path(os.environ['VERIFY_RUN']) / 'profile'\n")
        result = self.invoke(command=['-m', 'pytest', str(test), '-q'])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('1 passed', result.stdout)

    def test_installed_filters_editable_source_and_checks_target_bytes(self):
        target = self.root / 'target'
        target.mkdir()
        (target / 'sample.py').write_bytes((self.source / 'sample.py').read_bytes())
        self.config.update(installed_target=str(target), mode='installed', excluded_paths=[str(self.source)])
        script = """import os, sample, subprocess, sys
from pathlib import Path
assert Path(sample.__file__).parent == Path(sys.argv[1])
assert sys.argv[2] not in sys.path
env = dict(os.environ, PYTHONPATH=sys.argv[2] + os.pathsep + os.environ['PYTHONPATH'])
subprocess.run([sys.executable, '-c', 'import sample,sys; from pathlib import Path; assert Path(sample.__file__).parent == Path(sys.argv[1]); assert sys.argv[2] not in sys.path', sys.argv[1], sys.argv[2]], env=env, check=True)
"""
        result = self.invoke(command=['-c', script, str(target), str(self.source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        (target / 'sample.py').write_text('VALUE = 18\n')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hash mismatch', result.stderr)

    def file_origin_case(self, installed=False, child=False, module=False):
        selected = self.source
        if module:
            sample = self.source / 'sample.py'
            sample.write_text("VALUE = 17\nif __name__ == '__main__':\n from pathlib import Path\n import sys\n assert Path(__file__) == Path(sys.argv[1]) / 'sample.py'\n print('MODULE_SELECTED_17', __file__)\n")
            self.config['files']['sample.py'] = hashlib.sha256(sample.read_bytes()).hexdigest()
        if installed:
            selected = self.root / 'target'
            selected.mkdir()
            (selected / 'sample.py').write_bytes((self.source / 'sample.py').read_bytes())
            self.config.update(installed_target=str(selected), mode='installed', excluded_paths=[str(self.source)])
        adapter = self.root / 'adapter'
        adapter.mkdir()
        (adapter / 'sample.py').write_text('VALUE = 99\n')
        probe = """import sample, sys
from pathlib import Path
print('EXECUTED_IMPORT', sample.__file__, sample.VALUE, flush=True)
assert sample.VALUE == 17, (sample.__file__, sample.VALUE)
assert Path(sample.__file__) == Path(sys.argv[1]) / 'sample.py'
"""
        if child:
            children = adapter / 'children'
            children.mkdir()
            (children / 'sample.py').write_text('VALUE = 101\n')
            (children / 'probe.py').write_text(probe)
            if module:
                # -m normally adds the current directory after sitecustomize too.
                entry = """import subprocess, sys
from pathlib import Path
Path('sample.py').write_text('VALUE = 99\\n')
subprocess.run([sys.executable, '-m', 'sample', sys.argv[2]], check=True)
"""
            else:
                entry = "import subprocess, sys\nsubprocess.run([sys.executable, sys.argv[1], sys.argv[2]], check=True)\n"
            (adapter / 'main.py').write_text(entry)
            command = [str(adapter / 'main.py'), str(children / 'probe.py'), str(selected)]
        else:
            (adapter / 'main.py').write_text(probe)
            command = [str(adapter / 'main.py'), str(selected)]
        result = self.invoke(command=command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('MODULE_SELECTED_17 ' + str(selected / 'sample.py') if module else 'EXECUTED_IMPORT ' + str(selected / 'sample.py') + ' 17', result.stdout)

    def test_file_adapter_keeps_selected_source(self):
        self.file_origin_case()

    def test_file_adapter_keeps_installed_source(self):
        self.file_origin_case(installed=True)

    def test_file_child_keeps_selected_source(self):
        self.file_origin_case(child=True)

    def test_file_child_keeps_installed_source(self):
        self.file_origin_case(installed=True, child=True)

    def test_module_child_keeps_selected_source(self):
        self.file_origin_case(child=True, module=True)

    def test_module_child_keeps_installed_source(self):
        self.file_origin_case(installed=True, child=True, module=True)

    def test_prefixed_pytest_uses_owned_basetemp_and_cache(self):
        test = self.source / 'test_prefixed.py'
        test.write_text("import os\nfrom pathlib import Path\ndef test_owned(tmp_path, pytestconfig):\n root = Path(os.environ['VERIFY_RUN'])\n assert tmp_path.is_relative_to(root / 'pytest')\n assert pytestconfig.cache._cachedir == root / 'cache/pytest'\n")
        result = self.invoke(command=['-B', '-u', '-m', 'pytest', str(test), '-q'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 passed', result.stdout)

    def test_prefixed_pytest_refuses_workers_and_ownership_overrides(self):
        build_command = runpy.run_path(str(TOOL))['python_command']
        for options in (['-n', '2'], ['--numprocesses=2'], ['--dist', 'load'],
                        ['--basetemp', str(self.root / 'other')], ['-o', 'cache_dir=other']):
            with self.subTest(options=options):
                with self.assertRaisesRegex(ValueError, 'ownership overrides/parallel workers'):
                    build_command(self.config, self.root / 'scratch/run', ['-B', '-u', '-m', 'pytest', 'fixture.py'] + options)

    def test_unsupported_and_combined_interpreter_options_are_rejected(self):
        build_command = runpy.run_path(str(TOOL))['python_command']
        for options in (['-Es', '-c', 'pass'], ['-sE', '-m', 'pytest'], ['-IS', '-c', 'pass'],
                        ['-B', '-S', '-c', 'pass'], ['-Bu', '-c', 'pass'], ['-X', 'dev', '-c', 'pass']):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    build_command(self.config, self.root / 'scratch/run', options)

    def test_source_default_jobs_can_be_checkout_relative_before_retargeting(self):
        engine = self.source / 'openscrub.py'
        engine.write_text("import os\ndef _model_dir(): return os.path.expanduser('~/.openscrub/models')\ndef _fetch_model(url): pass\n")
        web = self.source / 'openscrub_web.py'
        web.write_text("from pathlib import Path\ndef _data_root(): return str(Path(__file__).parent)\nJOBS_DIR = str(Path(__file__).parent / 'openscrub_jobs')\n" +
                       "\n".join(name + " = 'example'" for name in ('ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR', 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH', 'CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY')))
        for name, path in (('openscrub', engine), ('openscrub_web', web)):
            self.config['modules'][name] = path.name
            self.config['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.config['configure_app'] = True
        result = self.invoke(command=['-c', "import os, openscrub_web; from pathlib import Path; assert Path(openscrub_web.JOBS_DIR).is_relative_to(Path(os.environ['VERIFY_RUN']) / 'app')"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_nested_import_path_rejection_does_not_execute_unselected_parent(self):
        package = self.source / 'unselected'
        package.mkdir()
        (package / '__init__.py').write_text("raise RuntimeError('UNSELECTED_PARENT_EXECUTED')\n")
        self.config['modules'] = {'unselected.child': 'sample.py'}
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('import path mismatch', result.stdout)
        self.assertNotIn('UNSELECTED_PARENT_EXECUTED', result.stdout)

    def test_conflicting_owner_is_not_removed(self):
        lock = self.root / 'scratch/.verification-active'
        lock.write_text('another owner')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('another invocation', result.stderr)
        self.assertEqual(lock.read_text(), 'another owner')

    def test_import_alias_and_prerequisite_hash_fail_before_workload(self):
        self.config['modules'] = {'absent_module': 'sample.py'}
        result = self.invoke(command=['-c', "print('WORKLOAD_STARTED')"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('import path mismatch', result.stdout)
        self.assertNotIn('WORKLOAD_STARTED\n', result.stdout)
        self.config['modules'] = {'sample': 'sample.py'}
        self.config['prerequisites'] = [{'path': str(self.source / 'sample.py'), 'sha256': '0' * 64}]
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('prerequisite hash mismatch', result.stderr)

    def test_git_frozen_rejects_dirty_but_development_is_explicit(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.source), *args], text=True).strip()
        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        head = git('rev-parse', 'HEAD')
        self.config.update(source_kind='git', head=head, base=head)
        (self.source / 'untracked').write_text('dirty')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('frozen checkout is dirty', result.stderr)
        self.config['policy'] = 'development'
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('"policy": "development"', result.stdout)

    def test_source_identity_is_rechecked_in_cli_child(self):
        script = "import os,subprocess,sys; from pathlib import Path; Path(sys.argv[1]).write_text('VALUE = 99\\n'); subprocess.run([sys.executable,'-c','import sample'],check=True)"
        # Runtime cannot alter frozen source: mutation itself must be rejected.
        result = self.invoke(command=['-c', script, str(self.source / 'sample.py')])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('outside run', result.stdout)
        self.assertEqual((self.source / 'sample.py').read_text(), 'VALUE = 17\n')


if __name__ == '__main__':
    unittest.main()
