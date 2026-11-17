#!/usr/bin/env python3
"""Explicit local verification setup; stdlib controller, no environment installation."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import uuid
import zipfile

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative_path(name):
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts and bool(path.parts), 'unsafe relative file: ' + name)
    return path


def check_files(root, files):
    require(bool(files), 'caller must supply frozen file hashes')
    for name, expected in files.items():
        path = root / relative_path(name)
        require(path.resolve().is_relative_to(root), 'file escapes selected source: ' + name)
        require(path.is_file() and digest(path) == expected, 'hash mismatch: ' + str(path))


def preflight(cfg):
    source = Path(cfg['source']).resolve()
    scratch_input = Path(cfg['scratch'])
    require(scratch_input.is_absolute(), 'scratch must be absolute')
    require(not any(p.is_symlink() for p in [scratch_input] + list(scratch_input.parents)), 'scratch symlink is unsafe')
    scratch = scratch_input.resolve()
    require(scratch.is_dir() and scratch != Path('/') and scratch != Path.home(), 'scratch must be an existing assigned directory')
    require(not scratch.is_relative_to(source) and not source.is_relative_to(scratch), 'scratch overlaps source')
    require(cfg['policy'] in ('frozen', 'development'), 'policy must be frozen or development')
    require(cfg.get('base') and cfg.get('head'), 'expected base/head are required')
    if cfg['source_kind'] == 'export':
        require(cfg['policy'] == 'frozen', 'exports require frozen policy')
        identity = json.loads((source / '.verification-source.json').read_text())
        require(identity['head'] == cfg['head'], 'source head differs from caller expectation')
        require(identity['base'] == cfg['base'], 'source base differs from caller expectation')
    else:
        require(cfg['source_kind'] == 'git', 'source_kind must be git or export')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
        require(git('rev-parse', 'HEAD') == cfg['head'], 'source head differs from caller expectation')
        require(git('merge-base', cfg['base'], cfg['head']) == cfg['base'], 'source base is not an ancestor')
        if cfg['policy'] == 'frozen':
            require(not git('status', '--porcelain'), 'frozen checkout is dirty; use development policy explicitly')
    check_files(source, cfg['files'])
    require(bool(cfg['modules']), 'explicit selected import modules are required')
    for module, name in cfg['modules'].items():
        require(name in cfg['files'], 'import file has no frozen hash: ' + module)
    selected = Path(cfg.get('installed_target', cfg['source'])).resolve() if cfg.get('mode') == 'installed' else source
    if cfg.get('mode') == 'installed':
        check_files(selected, {name: cfg['files'][name] for name in cfg['modules'].values()})
    # -I omits inherited floor/bootstrap/sitecustomize paths; it still identifies the actual venv interpreter.
    identity = json.loads(subprocess.check_output([cfg['python'], '-I', '-c',
        'import json,sys; print(json.dumps({"executable":sys.executable,"version":list(sys.version_info[:3])}))'], text=True))
    require(Path(identity['executable']).absolute() == Path(cfg['python']).absolute(), 'interpreter executable mismatch')
    require(identity['version'] == cfg['python_version'], 'interpreter version mismatch: ' + str(identity))
    prerequisites = []
    for item in cfg.get('prerequisites', []):
        path = Path(item['path'])
        require(path.exists(), 'missing prerequisite: ' + str(path))
        if item.get('executable'):
            require(os.access(path, os.X_OK), 'prerequisite not executable: ' + str(path))
        if item.get('sha256'):
            require(path.is_file() and digest(path) == item['sha256'], 'prerequisite hash mismatch: ' + str(path))
        prerequisites.append(dict(item))
    free = shutil.disk_usage(scratch).free
    require(free >= cfg['min_free_bytes'], 'insufficient scratch free space: ' + str(free))
    return {'source': str(source), 'base': cfg['base'], 'head': cfg['head'], 'policy': cfg['policy'],
            'files': cfg['files'], 'python': identity, 'free_bytes': free, 'prerequisites': prerequisites}


@contextlib.contextmanager
def owned_run(cfg, requested):
    scratch = Path(cfg['scratch']).resolve()
    name = requested or (cfg['task'] + '-' + uuid.uuid4().hex)
    require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name)) and name not in ('.', '..'), 'unsafe run id')
    lock = scratch / '.verification-active'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('another invocation owns runtime; inspect .verification-active; never remove an active owner')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'pid': os.getpid(), 'task': cfg['task'], 'run': name}, stream)
        root = scratch / name
        require(not root.exists() and not root.is_symlink(), 'run already exists: ' + str(root))
        root.mkdir()
        for child in ('hooks', 'logs', 'profile', 'tmp', 'cache', 'config', 'models', 'app', 'python'):
            (root / child).mkdir()
        (root / 'owner.json').write_text(json.dumps({'task': cfg['task'], 'pid': os.getpid(), 'run': name}) + '\n')
        yield root
    finally:
        lock.unlink()


def environment(cfg, root, mode=None, target=None, tools=False, configure=None):
    env = dict(os.environ)
    # Do not propagate old task guards, bootstrap imports, pytest selection or bytecode writes.
    for key in ('PYTHONPATH', 'PYTEST_PLUGINS', 'PYTEST_ADDOPTS', 'PYTHONHOME', 'VERIFY_CONFIG', 'VERIFY_RUN'):
        env.pop(key, None)
    env.update(cfg.get('environment', {}))
    require('HOME' not in cfg.get('environment', {}) and 'CODEX_HOME' not in cfg.get('environment', {}), 'HOME/CODEX_HOME must not be repurposed')
    paths = {'TMPDIR': 'tmp', 'XDG_CACHE_HOME': 'cache', 'XDG_CONFIG_HOME': 'config',
             'HF_HOME': 'cache/hf', 'TORCH_HOME': 'cache/torch', 'MPLCONFIGDIR': 'cache/mpl',
             'UV_CACHE_DIR': 'cache/uv', 'UV_PYTHON_INSTALL_DIR': 'python', 'POLLING_ARTIFACTS': 'browser',
             'OPENSCRUB_BASELINE_MODEL_DIR': 'models'}
    env.update({key: str(root / value) for key, value in paths.items()})
    env.update({'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                'OPENSCRUB_NO_AUTOFETCH': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'VERIFY_RUN': str(root)})
    runtime = dict(cfg, mode=mode or cfg.get('mode', 'source'), installed_target=str(target or cfg.get('installed_target', '')))
    if configure is not None:
        runtime['configure_app'] = configure
    config_path = root / ('runtime-' + uuid.uuid4().hex + '.json')
    config_path.write_text(json.dumps(runtime, indent=2) + '\n')
    env['VERIFY_CONFIG'] = str(config_path)
    for name in ('verification_hook.py', 'sitecustomize.py'):
        shutil.copyfile(HERE / name, root / 'hooks' / name)
    selected = runtime['installed_target'] if runtime['mode'] == 'installed' else cfg['source']
    pythonpath = [str(root / 'hooks'), selected]
    if tools:
        pythonpath += cfg['package']['tool_paths']
    env['PYTHONPATH'] = os.pathsep.join(pythonpath)
    env['PATH'] = str(Path(cfg['python']).parent) + os.pathsep + env.get('PATH', '')
    return env


def execute(command, root, env, label):
    log = root / 'logs' / (label + '.log')
    # Own the output directory before workload execution, including nonzero exits.
    log.parent.mkdir(parents=True, exist_ok=True)
    print('COMMAND ' + json.dumps(command), flush=True)
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
    print(log.read_text(errors='replace'), end='', flush=True)
    print('RESULT ' + json.dumps({'exit': result.returncode, 'log': str(log), 'sha256': digest(log)}), flush=True)
    return result.returncode


def python_command(cfg, root, args):
    require(bool(args), 'run requires Python arguments after --')
    require(not any(a in ('-I', '-E', '-S') or a.startswith('-I') for a in args), 'Python flags that bypass the startup guard are forbidden')
    if args[:2] == ['-m', 'pytest']:
        require(not any(a.startswith(('--basetemp', '-n', '--numprocesses', '--dist')) or 'cache_dir=' in a for a in args), 'pytest ownership overrides/parallel workers are forbidden')
        args = args + ['--basetemp=' + str(root / 'pytest'), '-o', 'cache_dir=' + str(root / 'cache/pytest')]
    return [cfg['python']] + args


def package(cfg, root):
    spec = cfg['package']
    required, wheel_files = spec['sdist_files'], spec['wheel_files']
    require(all(p in cfg['files'] for p in required + wheel_files), 'package file lists must have frozen hashes')
    env = environment(cfg, root, tools=True, configure=False)
    for name in ('dist', 'extracted', 'wheel', 'site-packages'):
        (root / name).mkdir()
    def run(args, label):
        code = execute([cfg['python']] + args, root, env, label)
        require(code == 0, label + ' failed; see raw log')
    run(['-m', 'build', '--sdist', '--no-isolation', '--outdir', str(root / 'dist'), cfg['source']], 'sdist')
    sdists = list((root / 'dist').glob('*.tar.gz'))
    require(len(sdists) == 1, 'expected exactly one sdist')
    with tarfile.open(sdists[0]) as archive:
        members = archive.getmembers()
        prefix = members[0].name.split('/')[0]
        for member in members:
            path = relative_path(member.name)
            require(not member.issym() and not member.islnk() and (member.isdir() or member.isfile()), 'unsafe archive member')
            require(path.parts[0] == prefix, 'multiple sdist roots')
        for name in required:
            require(hashlib.sha256(archive.extractfile(prefix + '/' + name).read()).hexdigest() == cfg['files'][name], 'sdist bytes differ: ' + name)
        archive.extractall(root / 'extracted')
    extracted = root / 'extracted' / prefix
    check_files(extracted, {p: cfg['files'][p] for p in required})
    run(['-m', 'build', '--wheel', '--no-isolation', '--outdir', str(root / 'wheel'), str(extracted)], 'wheel-from-sdist')
    wheels = list((root / 'wheel').glob('*.whl'))
    require(len(wheels) == 1, 'expected exactly one wheel')
    with zipfile.ZipFile(wheels[0]) as archive:
        for name in wheel_files:
            require(hashlib.sha256(archive.read(name)).hexdigest() == cfg['files'][name], 'wheel bytes differ: ' + name)
        metadata = archive.read(next(n for n in archive.namelist() if n.endswith('/METADATA'))).decode()
        require(('Requires-Python: ' + spec['requires_python']) in metadata.splitlines(), 'wheel Python floor differs')
    # Prepared pip is tool-only. Never expose its bootstrap path to installed runtime children.
    run(['-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile', '--target', str(root / 'site-packages'), str(wheels[0])], 'install')
    installed = environment(cfg, root, mode='installed', target=root / 'site-packages', configure=cfg.get('configure_app', False))
    code = execute([cfg['python'], '-c', 'print("INSTALLED_IDENTITY_DEFAULTS_OK")'], root, installed, 'installed-defaults')
    require(code == 0, 'installed identity/defaults failed')
    for index, args in enumerate(spec.get('installed_commands', [])):
        args = [a.replace('{target}', str(root / 'site-packages')) for a in args]
        code = execute(python_command(cfg, root, args), root, installed, 'installed-' + str(index))
        require(code == 0, 'installed command failed')
    result = {'sdist': {'file': str(sdists[0]), 'sha256': digest(sdists[0]), 'bytes': sdists[0].stat().st_size},
              'wheel': {'file': str(wheels[0]), 'sha256': digest(wheels[0]), 'bytes': wheels[0].stat().st_size},
              'sdist_files': required, 'wheel_files': wheel_files, 'requires_python': spec['requires_python']}
    (root / 'package-identities.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run-id')
    parser.add_argument('action', choices=('preflight', 'run', 'package'))
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        cfg = json.loads(args.config.read_text())
        record = preflight(cfg)
        with owned_run(cfg, args.run_id) as root:
            (root / 'preflight.json').write_text(json.dumps(record, indent=2) + '\n')
            summary = dict(record, run=str(root), files=len(record['files']), manifest_sha256=digest(root / 'preflight.json'))
            print('PREFLIGHT ' + json.dumps(summary, sort_keys=True), flush=True)
            if args.action == 'package':
                package(cfg, root)
                return 0
            env = environment(cfg, root)
            command = args.args[1:] if args.args[:1] == ['--'] else args.args
            if args.action == 'preflight':
                command = ['-c', 'print("IMPORT_PREFLIGHT_OK")']
            return execute(python_command(cfg, root, command), root, env, 'command')
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print('SETUP ERROR: ' + str(error), file=sys.stderr)
        return 78


if __name__ == '__main__':
    sys.exit(main())
