"""Freeze comparison inputs and isolate the optional synthetic browser recipe.

No product import occurs until configure() installs profile/write/network guards.
This helper is specific to browser_logs.py, not an application runtime feature.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

SOURCE_FILES = ('openscrub.py', 'openscrub_web.py', 'zones_ui.py',
                'openscrub_internal/__init__.py', 'openscrub_internal/job_logs.py', 'tests/test_job_polling_browser.py')
RECIPE_FILES = ('browser_logs.py', 'browser_logs.js', 'browser_logs_env.py',
                'browser_logs_summary.py', 'README.md')


def configure(root, source, frozen):
    root, source = root.resolve(), source.resolve()
    # Reject an unfrozen source selection before any product import.
    for relative in SOURCE_FILES:
        path = source / relative
        assert str(path) in frozen['sha256'], 'selected source path is not frozen: ' + str(path)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == frozen['sha256'][str(path)], str(path)
    for name in ('profile', 'tmp', 'cache', 'config', 'models', 'app'):
        (root / name).mkdir(parents=True, exist_ok=True)
    os.environ.update({'TMPDIR': str(root / 'tmp'), 'XDG_CACHE_HOME': str(root / 'cache'),
                       'XDG_CONFIG_HOME': str(root / 'config'), 'HF_HOME': str(root / 'cache/hf'),
                       'TORCH_HOME': str(root / 'cache/torch'), 'MPLCONFIGDIR': str(root / 'cache/mpl'),
                       'UV_CACHE_DIR': str(root / 'cache/uv'), 'UV_PYTHON_INSTALL_DIR': str(root / 'python'),
                       'OPENSCRUB_NO_AUTOFETCH': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                       'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'})
    sys.dont_write_bytecode = True
    tempfile.tempdir = str(root / 'tmp')
    original_expanduser = os.path.expanduser

    def expanduser(path):
        marker = b'~' if isinstance(path, bytes) else '~'
        separator = b'/' if isinstance(path, bytes) else '/'
        if path == marker or path.startswith(marker + separator):
            return (os.fsencode(root / 'profile') if isinstance(path, bytes) else str(root / 'profile')) + path[1:]
        return original_expanduser(path)

    os.path.expanduser = expanduser

    def checked(path):
        if isinstance(path, (str, bytes)):
            resolved = Path(os.fsdecode(path)).resolve()
            if str(resolved) != os.devnull and not resolved.is_relative_to(root):
                raise RuntimeError('browser-log recipe write outside root: ' + str(resolved))

    def audit(event, args):
        if event == 'socket.connect' and isinstance(args[1], tuple):
            if args[1][0] not in ('127.0.0.1', '::1', 'localhost'):
                raise RuntimeError('browser-log recipe outward Python network disabled')
        if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            checked(args[0])
        if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
            checked(args[0])
        if event in ('os.rename', 'os.link', 'os.symlink'):
            checked(args[0]); checked(args[1])

    sys.addaudithook(audit)
    os.chdir(root / 'app')
    sys.path.insert(0, str(source))
    import openscrub
    import openscrub_web as web
    import zones_ui
    import openscrub_internal.job_logs as job_logs
    identities = {}
    for module, relative in ((openscrub, 'openscrub.py'), (web, 'openscrub_web.py'),
                             (zones_ui, 'zones_ui.py'), (job_logs, 'openscrub_internal/job_logs.py')):
        path = Path(module.__file__).resolve()
        assert path == source / relative, (path, source / relative)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == frozen['sha256'][str(path)], str(path)
        identities[module.__name__] = {'file': str(path), 'sha256': digest}
    openscrub._model_dir = lambda: str(root / 'models')
    original_fetch = openscrub._fetch_model

    def offline(url, *args, **kwargs):
        if not url.startswith('file://'):
            raise RuntimeError('browser-log recipe model downloads disabled')
        return original_fetch(url, *args, **kwargs)

    openscrub._fetch_model = offline
    web._data_root = lambda: str(root / 'app')
    for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR', 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
        setattr(web, name, str(root / 'app' / Path(getattr(web, name)).name))
    for name in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
        setattr(web, name, str(Path(web.CERT_DIR) / Path(getattr(web, name)).name))
    Path(web.JOBS_DIR).mkdir(exist_ok=True)
    print('BROWSER_LOG_SOURCE ' + json.dumps({'python': sys.version, 'sources': identities}, sort_keys=True), flush=True)
    return web


def main():
    parser = argparse.ArgumentParser(description='Freeze exact source/recipe/existing-tool files; does not import the application or run timing.')
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--tool', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files = [source.resolve() / relative for source in args.source for relative in SOURCE_FILES]
    files += [Path(__file__).resolve().parent / relative for relative in RECIPE_FILES]
    files += [path.resolve() for path in args.tool]
    record = {'sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    print('Manifest SHA256: ' + hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
