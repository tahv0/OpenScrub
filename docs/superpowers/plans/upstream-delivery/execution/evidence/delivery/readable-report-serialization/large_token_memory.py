"""Separate fresh-process publication RSS evidence; no HTTP latency claims."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ART = Path('/tmp/openscrub-task632')

def memory(pid):
    result = {}
    for line in Path('/proc/%d/status' % pid).read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:')):
            key, value, _ = line.split()
            result[key[:-1] + '_kib'] = int(value)
    return result

def worker(label):
    source = ART / 'measurement' / ('export-' + label) / 'openscrub_internal/reports.py'
    spec = importlib.util.spec_from_file_location('task632_reports', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    imported = memory(os.getpid())
    doc = {'future': {'large': '☃"\n\\' * 1000000}, 'tail': [False, 0, 1.0, None]}
    print(json.dumps(dict(pid=os.getpid(), source=str(source), import_memory=imported,
                          ready_memory=memory(os.getpid()))), flush=True)
    assert sys.stdin.readline().strip() == 'publish'
    module.atomic_report(ART / ('large-token-' + label + '.json'), doc)
    print(json.dumps(dict(after_publication_memory=memory(os.getpid()))), flush=True)
    assert sys.stdin.readline().strip() == 'tokens'
    # This token observation is after the publication RSS observation window.
    count = maximum = characters = 0
    for chunk in json.JSONEncoder(indent=1).iterencode(doc):
        count += 1
        maximum = max(maximum, len(chunk))
        characters += len(chunk)
    print(json.dumps(dict(encoder_chunks=count, largest_token_characters=maximum,
                          serialized_characters=characters)), flush=True)

def main():
    results = dict(python=sys.version, executable=sys.executable, samples={})
    for label in ('before', 'after'):
        child = subprocess.Popen([sys.executable, __file__, '--worker', label],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        ready = json.loads(child.stdout.readline())
        child.stdin.write('publish\n'); child.stdin.flush()
        import threading
        done = threading.Event()
        samples = [memory(ready['pid'])]
        def sample():
            while not done.wait(.001): samples.append(memory(ready['pid']))
        observer = threading.Thread(target=sample); observer.start()
        publication = json.loads(child.stdout.readline())
        done.set(); observer.join()
        samples.append(publication['after_publication_memory'])
        child.stdin.write('tokens\n'); child.stdin.flush()
        tokens = json.loads(child.stdout.readline())
        assert child.wait(timeout=15) == 0
        results['samples'][label] = dict(ready=ready, publication=publication,
                                        rss_samples=samples, tokens=tokens)
    import hashlib
    digests = {}
    with (ART/'large-token-before.json').open('rb') as before, (ART/'large-token-after.json').open('rb') as after:
        digest = hashlib.sha256()
        while True:
            left, right = before.read(1024*1024), after.read(1024*1024)
            assert left == right
            if not left: break
            digest.update(left)
    results.update(complete_bytes_equal=True, sha256=digest.hexdigest(),
                   bytes=(ART/'large-token-before.json').stat().st_size)
    (ART/'large-token-memory.json').write_text(json.dumps(results, indent=2))
    print(json.dumps({k:{'ready':v['ready'], 'publication':v['publication'],
                          'peak_rss_kib':max(s['VmRSS_kib'] for s in v['rss_samples']),
                          'peak_hwm_kib':max(s['VmHWM_kib'] for s in v['rss_samples']),
                          'tokens':v['tokens']} for k,v in results['samples'].items()}, indent=2))

if __name__ == '__main__':
    if len(sys.argv)>1: worker(sys.argv[2])
    else: main()
