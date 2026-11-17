"""All predeclared samples, alternating paired orders, instrumentation last."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from fixtures.log_workload import CASES, COUNTS, WARMUPS, OBSERVATIONS
ROOT = Path(os.environ['TASK1202_ROOT'])
SOURCES = {'base': ROOT / 'base', 'candidate': Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')}
MANIFEST_PATH = ROOT / 'premeasurement-hashes.json'
MANIFEST_BYTES = MANIFEST_PATH.read_bytes()
FROZEN = json.loads(MANIFEST_BYTES)
MANIFEST_HASH = hashlib.sha256(MANIFEST_BYTES).hexdigest()
def verify_frozen():
    assert MANIFEST_PATH.read_bytes() == MANIFEST_BYTES
    for path, expected in FROZEN.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
verify_frozen()

def run(mode, case, count, sample):
    verify_frozen()
    source = SOURCES[mode.split('-')[0]]
    env = dict(os.environ, TASK1202_SOURCE=str(source),
               TASK1202_WEB_HASH=FROZEN[str(source/'openscrub_web.py')],
               TASK1202_MANIFEST_HASH=MANIFEST_HASH,
               PYTHONPATH=str(ROOT/'harness')+':'+str(source)+':'+str(ROOT))
    result = subprocess.run([sys.executable, str(ROOT/'bench_worker.py'), mode, case, str(count), sample],
                            env=env, cwd=ROOT, capture_output=True, text=True, timeout=240)
    with (ROOT/'logs/bench-processes.log').open('a') as output:
        output.write(result.stdout+result.stderr)
    assert result.returncode == 0, result.stdout+result.stderr
    verify_frozen()
    observation = next(json.loads(line[len('OBSERVATION '):]) for line in result.stdout.splitlines() if line.startswith('OBSERVATION '))
    with (ROOT/'measurements.jsonl').open('a') as output:
        output.write(json.dumps(observation,sort_keys=True)+'\n')
    print(mode,case,count,sample,flush=True)

for case in CASES:
    for count in COUNTS:
        for phase, repeats in (('warmup', WARMUPS), ('observed', OBSERVATIONS)):
            for index in range(repeats):
                order = ('base', 'candidate') if index % 2 == 0 else ('candidate', 'base')
                for mode in order:
                    run(mode,case,count,phase+'-'+str(index+1))
# Allocation/work instrumentation never interleaves with uninstrumented timing.
for case in CASES:
    for count in COUNTS:
        for mode in ('base-allocation','candidate-allocation'):
            run(mode,case,count,'instrumented')

verify_frozen()
print("FROZEN_MANIFEST_VERIFIED " + MANIFEST_HASH,flush=True)
