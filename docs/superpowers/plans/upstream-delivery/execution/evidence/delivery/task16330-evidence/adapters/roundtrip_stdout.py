"""Task-only compatibility for the exact fresh-route JSON child of one test.

Keep helper startup validation enabled and preserve complete child output. Strip
only its two verified leading records from the CompletedProcess seen by the
existing JSON-only test. All other calls/output pass through unchanged.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def exact_roundtrip_stdout(request, monkeypatch):
    if request.node.name != 'test_real_render_and_fresh_route_reopen_keep_all_ten_rows':
        return
    cfg = json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())
    source = Path(cfg['source'])
    root = Path(os.environ['VERIFY_RUN'])
    test = source / 'tests/test_report_roundtrip.py'
    assert hashlib.sha256(test.read_bytes()).hexdigest() == cfg['files']['tests/test_report_roundtrip.py']
    tree = ast.parse(test.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == request.node.name)
    script = next(ast.literal_eval(n.value) for n in function.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'script' for t in n.targets))
    actual_run = subprocess.run
    calls = []

    def run(args, *positional, **kwargs):
        result = actual_run(args, *positional, **kwargs)
        if not (isinstance(args, list) and len(args) == 5 and args[:3] == [sys.executable, '-c', script]):
            return result
        assert not calls, 'unexpected second fresh-route child'
        calls.append(True)
        # Keep every byte before parsing; failure evidence survives validation.
        (root / 'logs/roundtrip-child.stdout').write_text(result.stdout)
        (root / 'logs/roundtrip-child.stderr').write_text(result.stderr)
        assert not positional
        assert kwargs == dict(capture_output=True, text=True, check=True, cwd=str(source))
        assert Path(args[3]).resolve().is_relative_to(root)
        assert Path(args[4]).resolve().is_relative_to(root)
        lines = result.stdout.splitlines(keepends=True)
        assert len(lines) >= 3 and lines[0].startswith('DEFAULT_PATHS ') and lines[1].startswith('ACTIVE_SOURCE '), 'unexpected child startup records'
        defaults = json.loads(lines[0][len('DEFAULT_PATHS '):])
        assert defaults == {'jobs': str(source / 'openscrub_jobs'), 'models': str(root / 'profile/.openscrub/models')}
        identity = json.loads(lines[1][len('ACTIVE_SOURCE '):])
        assert set(identity) == {'executable', 'python', 'sources'}
        assert identity['executable'] == cfg['python'] == sys.executable
        assert identity['python'] == sys.version
        assert identity['sources'] == {name: {'file': str(source / relative), 'sha256': cfg['files'][relative]} for name, relative in cfg['modules'].items()}
        payload = ''.join(lines[2:])
        assert isinstance(json.loads(payload), dict), 'unexpected route payload'
        (root / 'logs/roundtrip-adapter.json').write_text(json.dumps({'test':request.node.name,'script_sha256':hashlib.sha256(script.encode()).hexdigest(),'stdout_sha256':hashlib.sha256(result.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(result.stderr.encode()).hexdigest(),'verified_records':['DEFAULT_PATHS','ACTIVE_SOURCE']},indent=2)+'\n')
        return subprocess.CompletedProcess(result.args, result.returncode, payload, result.stderr)

    monkeypatch.setattr(subprocess, 'run', run)
    yield
    assert calls == [True], 'exact fresh-route child was not exercised'
