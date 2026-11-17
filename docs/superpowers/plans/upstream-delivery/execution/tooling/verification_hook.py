"""Task-local startup guard, reused by pytest, direct scripts and Python children.

Adapted from Task1202/1203 isolation and benchmark/browser_logs_env.py.
Python audit hooks are not an OS sandbox; native processes are not contained.
"""
import hashlib
from importlib.machinery import PathFinder
from importlib.util import spec_from_file_location
import json
import os
from pathlib import Path
import sys
import tempfile


def configure():
    cfg = json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())
    root = Path(os.environ['VERIFY_RUN']).resolve()
    source = Path(cfg['source']).resolve()
    installed = cfg.get('mode') == 'installed'
    selected = Path(cfg['installed_target']).resolve() if installed else source
    if installed:
        excluded = [source] + [Path(p).resolve() for p in cfg.get('excluded_paths', [])]
        def allowed(path):
            resolved = Path(path).resolve()
            if resolved == selected or resolved.is_relative_to(root / 'hooks'):
                return True
            # Discard editable checkout entries, including unknown native worktrees.
            if any(resolved == p or resolved.is_relative_to(p) for p in excluded):
                return False
            if '/worktrees/' in str(resolved) or '/src/OpenScrub' in str(resolved):
                return False
            return True
        sys.path[:] = [p for p in sys.path if p and allowed(p)]
    sys.dont_write_bytecode = True
    tempfile.tempdir = str(root / 'tmp')
    original = os.path.expanduser
    def expanduser(path):
        marker = b'~' if isinstance(path, bytes) else '~'
        sep = b'/' if isinstance(path, bytes) else '/'
        if path == marker or path.startswith(marker + sep):
            return (os.fsencode(root / 'profile') if isinstance(path, bytes) else str(root / 'profile')) + path[1:]
        return original(path)
    os.path.expanduser = expanduser

    def checked(path):
        if isinstance(path, (str, bytes)):
            resolved = Path(os.fsdecode(path)).resolve()
            if str(resolved) != os.devnull and not resolved.is_relative_to(root):
                raise RuntimeError('verification write outside run: ' + str(resolved))

    def audit(event, args):
        if event == 'socket.connect' and isinstance(args[1], tuple):
            if args[1][0] not in ('127.0.0.1', '::1', 'localhost'):
                raise RuntimeError('verification outward Python network disabled')
        if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            checked(args[0])
        if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
            checked(args[0])
        if event in ('os.rename', 'os.link', 'os.symlink'):
            checked(args[0]); checked(args[1])
    sys.addaudithook(audit)
    identities = {}
    for name, relative in cfg['modules'].items():
        expected = selected / relative
        search = sys.path
        spec = None
        parts = name.split('.')
        for index in range(len(parts)):
            spec = PathFinder.find_spec('.'.join(parts[:index + 1]), search)
            if spec is None:
                break
            search = spec.submodule_search_locations
            if index < len(parts) - 1 and search is None:
                spec = None
                break
        if spec is None or spec.origin is None or Path(spec.origin).resolve() != expected:
            raise RuntimeError('selected import path mismatch: ' + name + ' ' + str(getattr(spec, 'origin', None)))
        actual = hashlib.sha256(expected.read_bytes()).hexdigest()
        if actual != cfg['files'][relative]:
            raise RuntimeError('selected import hash mismatch: ' + str(expected))
        identities[name] = {'file': str(expected), 'sha256': actual}
    class SelectedSourceFinder:
        # CPython prepends a script/cwd path after sitecustomize. Keep declared
        # imports pinned when actually resolved, in this process and children.
        def find_spec(self, fullname, path=None, target=None):
            relative = cfg['modules'].get(fullname)
            if relative is None:
                return None
            expected = selected / relative
            if hashlib.sha256(expected.read_bytes()).hexdigest() != cfg['files'][relative]:
                raise ImportError('selected import hash mismatch: ' + str(expected))
            return spec_from_file_location(fullname, expected)

    sys.meta_path.insert(0, SelectedSourceFinder())
    if cfg.get('configure_app'):
        import openscrub
        import openscrub_web as web
        # Assert product defaults before applying explicit task paths, in installed mode too.
        defaults = [(web.JOBS_DIR, root / 'profile' if installed else source), (openscrub._model_dir(), root / 'profile')]
        for path, allowed_root in defaults:
            if not Path(path).resolve().is_relative_to(allowed_root):
                raise RuntimeError('default path escaped task profile: ' + str(path))
        print('DEFAULT_PATHS ' + json.dumps({'jobs': web.JOBS_DIR, 'models': openscrub._model_dir()}), flush=True)
        openscrub._model_dir = lambda: str(root / 'models')
        original_fetch = openscrub._fetch_model
        def offline(url, *args, **kwargs):
            if not url.startswith('file://'):
                raise RuntimeError('verification model downloads disabled')
            return original_fetch(url, *args, **kwargs)
        openscrub._fetch_model = offline
        web._data_root = lambda: str(root / 'app')
        for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR', 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
            setattr(web, name, str(root / 'app' / Path(getattr(web, name)).name))
        for name in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
            setattr(web, name, str(Path(web.CERT_DIR) / Path(getattr(web, name)).name))
        Path(web.JOBS_DIR).mkdir(exist_ok=True)
    print('ACTIVE_SOURCE ' + json.dumps({'python': sys.version, 'executable': sys.executable, 'sources': identities}, sort_keys=True), flush=True)
