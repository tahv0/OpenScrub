"""Offline actual-PAGE/HTTP browser-log comparison (explicit isolated env only).

Requires existing OpenScrub Python dependencies and offline Playwright/Chromium.
See benchmark/README.md for isolated roots and frozen source/tool inputs.
The driver imports the real-route test fixture and serves the selected PAGE
with two narrowly asserted timing insertions. No product timing hook ships.
Run once per selected source with --phase timing, then instrumentation only
AFTER every timing source/case is complete. See the frozen task declaration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('timing', 'instrumentation'), required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--chromium', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--granted-sha', required=True)
    parser.add_argument('--check-setup', action='store_true', help='assert isolated imports/guards without browser, fixtures or timing')
    parser.add_argument('--label', choices=('base', 'candidate'), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    source = args.source.resolve()
    manifest = args.manifest.resolve()
    granted = args.granted_sha
    def verify_manifest():
        data = manifest.read_bytes()
        assert hashlib.sha256(data).hexdigest() == granted, 'granted manifest identity'
        return data
    frozen = json.loads(verify_manifest())
    assert str(source / 'openscrub_web.py') in frozen['sha256'], 'selected source path is not frozen'
    for tool in (args.node.resolve(), args.chromium.resolve(), Path(sys.executable).resolve()):
        assert str(tool) in frozen['sha256'], 'selected tool path is not frozen: ' + str(tool)
    expected = frozen['sha256'][str(source / 'openscrub_web.py')]
    def verify_frozen():
        verify_manifest()
        for name, digest in frozen['sha256'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    verify_frozen()
    sys.dont_write_bytecode = True
    from browser_logs_env import configure
    web = configure(root, source, frozen)
    if args.check_setup:
        verify_frozen()
        print('ISOLATED_SETUP_PASS: no browser, producer fixture or timing executed')
        return
    sys.path.insert(0, str(source / 'tests'))
    import pytest
    from test_job_polling_browser import polling_http
    assert hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest() == expected
    start = ('  document.getElementById("logStatus").textContent=[' if args.label == 'base'
             else ' RECENT_LOG.publish(nl,replace,!LOGINIT,modern);')
    end = (' LOGN=nl.len;LOGINIT=true;' if args.label == 'base'
           else ' LOGN=nl.len;LOGE=nextEpoch;LOGINIT=true;')
    assert web.PAGE.count(start) == web.PAGE.count(end) == 1
    begin = ' window.qaStart=performance.now();window.qaPublishing=true;\n'
    finish = '''
 const qaElement=document.getElementById("log"),qaHeight=qaElement.scrollHeight;
 const qaEnd=performance.now();window.qaPublishing=false;
 window.qaSamples.push({publicationStart:window.qaStart,publicationEnd:qaEnd,
  cycleStart:window.qaCycleStart,cycleEnd:qaEnd,publicationMs:qaEnd-window.qaStart,
  cycleMs:qaEnd-window.qaCycleStart,cursor:LOGN,height:qaHeight});
'''
    web.PAGE = web.PAGE.replace(start, begin + start).replace(end, end + finish)
    identity = {'label': args.label, 'phase': args.phase, 'source': expected,
                'instrumented_page': hashlib.sha256(web.PAGE.encode()).hexdigest()}
    fixture = root / ('measurement-' + args.label + '-' + args.phase)
    fixture.mkdir(exist_ok=True)
    monkeypatch = pytest.MonkeyPatch()
    generator = polling_http.__wrapped__(monkeypatch, fixture)
    base = next(generator)
    env = dict(os.environ, OPENSCRUB_LOG_BENCH_BASE=base, OPENSCRUB_LOG_BENCH_PHASE=args.phase,
               OPENSCRUB_LOG_BENCH_LABEL=args.label, OPENSCRUB_LOG_BENCH_ROOT=str(root),
               OPENSCRUB_LOG_BENCH_IDENTITY=json.dumps(identity),
               OPENSCRUB_LOG_BENCH_CHROMIUM=str(args.chromium.resolve()))
    try:
        log = root / 'logs' / ('measurement-' + args.label + '-' + args.phase + '.log')
        try:
            result = subprocess.run([str(args.node.resolve()), str(Path(__file__).with_suffix('.js'))], env=env,
                                    capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            log.write_text(decoded(error.stdout) + decoded(error.stderr) + '\nSUBPROCESS TIMEOUT\n')
            raise
        log.write_text(result.stdout + result.stderr)
        print(result.stdout, end='')
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)
    finally:
        generator.close()
        monkeypatch.undo()
        assert hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest() == expected
        verify_frozen()


if __name__ == '__main__':
    main()
