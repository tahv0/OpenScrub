"""Offline actual-PAGE/HTTP browser-log comparison (explicit isolated env only).

Requires TASK1203_ROOT, TASK1203_SOURCE and the task's source/write guards.
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
    parser.add_argument('--label', choices=('base', 'candidate'), required=True)
    args = parser.parse_args()
    root = Path(os.environ['TASK1203_ROOT'])
    source = Path(os.environ['TASK1203_SOURCE'])
    frozen = json.loads(Path(os.environ['TASK1203_FROZEN']).read_text())
    def verify_frozen():
        for name, digest in frozen['sha256'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    verify_frozen()
    from task1203_isolation import configure
    web = configure()  # Direct-script source/hash/model/job guard, not a pytest hook.
    sys.path.insert(0, str(source / 'tests'))
    import pytest
    from test_job_polling_browser import polling_http
    expected = os.environ['TASK1203_WEB_HASH']
    assert hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest() == expected
    start = ('  document.getElementById("logStatus").textContent=[' if args.label == 'base'
             else ' RECENT_LOG.publish(nl,replace,!LOGINIT,modern);')
    end = (' LOGN=nl.len;LOGINIT=true;' if args.label == 'base'
           else ' LOGN=nl.len;LOGE=nextEpoch;LOGINIT=true;')
    assert web.PAGE.count(start) == web.PAGE.count(end) == 1
    begin = ' window.qaStart=performance.now();window.qaPublishing=true;\n'
    finish = '''
 const qaElement=document.getElementById("log"),qaHeight=qaElement.scrollHeight;
 window.qaPublishing=false;
 window.qaSamples.push({publicationMs:performance.now()-window.qaStart,
  cycleMs:performance.now()-window.qaCycleStart,cursor:LOGN,height:qaHeight});
'''
    web.PAGE = web.PAGE.replace(start, begin + start).replace(end, end + finish)
    identity = {'label': args.label, 'phase': args.phase, 'source': expected,
                'instrumented_page': hashlib.sha256(web.PAGE.encode()).hexdigest()}
    fixture = root / ('measurement-' + args.label + '-' + args.phase)
    fixture.mkdir(exist_ok=True)
    monkeypatch = pytest.MonkeyPatch()
    generator = polling_http.__wrapped__(monkeypatch, fixture)
    base = next(generator)
    env = dict(os.environ, POLLING_BASE=base, MEASURE_PHASE=args.phase, MEASURE_LABEL=args.label,
               MEASURE_IDENTITY=json.dumps(identity))
    try:
        result = subprocess.run(['node', str(Path(__file__).with_suffix('.js'))], env=env,
                                capture_output=True, text=True, timeout=1800)
        log = root / 'logs' / ('measurement-' + args.label + '-' + args.phase + '.log')
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
