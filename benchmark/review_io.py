#!/usr/bin/env python3
"""Compare pinned report-save sources over loopback HTTP, without inference.

Example (run in a prepared runtime with Flask, Cheroot and engine dependencies):
  python benchmark/review_io.py --scenario saves --rows 1000 10000 100000 \
    --before-ref BASE_SHA --after-ref HEAD_SHA --repository . \
    --evidence-dir /tmp/review-io --output /tmp/review-io/results.json

Exports are verified against every pinned Git blob before import. Timing workers
have no route instrumentation. Separate workers count report/request/response
operations. RSS sampling is external via Linux /proc; high-water includes fixture
construction/imports, and all raw samples, identities and boundaries are retained.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request


def fixture(rows):
    """Deterministic realistic shape; no media, models, random state or user data."""
    frames = max(1800, rows * 3)
    cum = [[round((i % 240) * .1, 1), round((i % 300) * .2, 1)] for i in range(frames)]
    detections = []
    for i in range(rows):
        t = i * 3 / 30
        category = ('name', 'plate', 'face', 'manual', 'person')[i % 5]
        row = dict(t_start=t, t_end=t + .15, cbox=[10., 12., 44., 36.],
                   category=category, text='synthetic-%06d' % i, confidence=.85,
                   aoff=list(cum[i * 3]), last_seen=t + .1, enabled=i % 11 != 0,
                   dense=i % 5 >= 2, track=i // 5 if i % 5 >= 2 else -1,
                   person=i // 25 if category == 'face' else -1,
                   poly=[[[10.,12.],[44.,12.],[44.,36.],[10.,36.]]] if category == 'person' else [],
                   future={'ordered': [None, True, 1, 1.], 'label': 'synthetic'})
        if category == 'manual':
            row.update(manual_id='fixture:%d' % i, manual_creation={
                't_start': t, 't_end': t + .15, 'cbox': [10,12,44,36],
                'aoff': list(row['aoff'])})
        detections.append(row)
    for i in (0,5):
        if i < rows: detections[i].update(category='name', text='synthetic-recurring', enabled=False)
    return dict(provenance={'tool': 'openscrub', 'input': '/synthetic/input.avi',
                            'settings': {'categories': 'name,plate,face,person'}},
                render_state={'fps': 30, 'cum': cum,
                              'bands': [[round(i % 17 * .2, 1), round(i % 19 * .2, 1)] for i in range(frames)]},
                detections=detections,
                audio_redactions=[{'t0': .2, 't1': .4, 'mode': 'mute'}, {'t0': .5, 't1': .7, 'mode': 'bleep'}],
                audio_suggestions=[{'t0': .1, 't1': .3, 'text': 'synthetic audio', 'category': 'name'}],
                audio_transcript=[{'start': 0., 'end': 1., 'text': 'synthetic audio', 'future': [1,False]}],
                future={'nested': {'motion': [[1,2],[3,4]]}, 'ordered': [False,0,0.]})


def memory(pid):
    result = {}
    try:
        for line in Path('/proc/%d/status' % pid).read_text().splitlines():
            if line.startswith(('VmRSS:', 'VmHWM:')):
                key, value, _ = line.split()
                result[key[:-1] + '_kib'] = int(value)
    except FileNotFoundError:
        pass
    return result


def sha_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest.update(chunk)
    return digest.hexdigest()


def metadata(path):
    stat = path.stat()
    return dict(bytes=stat.st_size, inode=stat.st_ino, device=stat.st_dev,
                mtime_ns=stat.st_mtime_ns, mode=stat.st_mode, sha256=sha_file(path))


def export_source(repository, revision, destination):
    revision = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', revision + '^{commit}'], text=True).strip()
    if destination.exists():
        raise ValueError('Evidence/export directory already exists: %s' % destination)
    destination.mkdir(parents=True)
    archive = subprocess.check_output(['git', '-C', str(repository), 'archive', revision])
    import io
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(destination)
    entries = subprocess.check_output(['git', '-C', str(repository), 'ls-tree', '-r', '-z', revision]).split(b'\0')
    manifest = {}
    for entry in entries:
        if not entry: continue
        spec, name = entry.split(b'\t', 1)
        mode, kind, expected = spec.split()
        if kind != b'blob' or mode == b'120000':
            raise ValueError('Only regular pinned source blobs are supported')
        name = name.decode()
        contents = (destination / name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(contents)).encode() + b'\0' + contents).hexdigest()
        assert actual == expected.decode(), name
        manifest[name] = hashlib.sha256(contents).hexdigest()
    return {'revision': revision, 'export': str(destination), 'sha256': manifest}


def instrument(web):
    """Separate counters; stream writes count Python calls, never syscalls."""
    from types import SimpleNamespace
    from openscrub_internal import reports
    counts = dict(report_parse=0, report_dump=0, stage=0, fsync=0, replace=0,
                  stream_writes=0, serialized_characters=0, request_json=0, response_json=0)
    def wrap(owner, name, key):
        original = getattr(owner, name)
        def counted(*args, **kwargs):
            counts[key] += 1
            return original(*args, **kwargs)
        setattr(owner, name, counted)
    wrap(web, '_load_job_report', 'report_parse')
    dump = reports.json.dump
    def encode(doc, stream, **kwargs):
        counts['report_dump'] += 1
        class Stream:
            def write(self, value):
                counts['stream_writes'] += 1
                counts['serialized_characters'] += len(value)
                return stream.write(value)
        return dump(doc, Stream(), **kwargs)
    reports.json = SimpleNamespace(dump=encode)
    wrap(reports.tempfile, 'NamedTemporaryFile', 'stage')
    wrap(reports.os, 'fsync', 'fsync')
    wrap(reports.os, 'replace', 'replace')
    wrap(web.app.request_class, 'get_json', 'request_json')
    wrap(web.app.json, 'dumps', 'response_json')
    return counts


def worker(config):
    root = Path(config['source']['export']).resolve()
    sys.path.insert(0, str(root))
    os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
    import openscrub
    import openscrub_web as web
    import openscrub_internal.reports as reports
    from cheroot.wsgi import Server
    imported = {}
    for module in (openscrub, web, reports):
        path = Path(module.__file__).resolve()
        name = path.relative_to(root).as_posix()  # fails if wrong import
        assert sha_file(path) == config['source']['sha256'][name]
        imported[module.__name__] = str(path)
    imported_memory = memory(os.getpid())
    runtime = Path(config['runtime']); runtime.mkdir(parents=True)
    web._data_root = lambda: str(runtime)
    for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR',
                 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
        setattr(web, name, str(runtime / Path(getattr(web, name)).name))
    Path(web.JOBS_DIR).mkdir()
    web.TOKEN = None
    job = web.new_job('', {}, 'synthetic.avi')
    path = Path(job['dir']) / 'report.json'
    video = Path(job['dir']) / 'input.avi'; video.write_bytes(b'synthetic placeholder')
    job.update(video=str(video), phase='review')
    def reset():
        with path.open('w', encoding='utf-8') as stream:
            json.dump(fixture(config['rows']), stream, indent=1)
        gc.collect()
    reset()
    fixture_memory = memory(os.getpid())
    counts = instrument(web) if config['instrument'] else None
    ready = threading.Event()
    server = Server(('127.0.0.1', 0), web.app, numthreads=2)
    original = server.prepare
    def prepare():
        original(); ready.set()
    server.prepare = prepare
    thread = threading.Thread(target=server.start)
    thread.start()
    assert ready.wait(15)
    def emit(value):
        print(json.dumps(value), flush=True)
    emit(dict(pid=os.getpid(), url='http://127.0.0.1:%d/api/jobs/%s/detections' %
              (server.socket.getsockname()[1], job['id']), path=str(path), imported=imported,
              imported_memory=imported_memory, fixture_memory=fixture_memory,
              ready_memory=memory(os.getpid()), initial_file=metadata(path)))
    try:
        for line in sys.stdin:
            command = json.loads(line)
            if command == 'stop': break
            if command == 'reset': reset()
            if command in ('reset', 'clear') and counts:
                for key in counts: counts[key] = 0
            emit(dict(memory=memory(os.getpid()), counts=counts, owners=web.FILES.count))
    finally:
        server.stop(); thread.join(15)
        assert not thread.is_alive()


class Worker:
    def __init__(self, source, rows, directory, counted):
        directory.mkdir(parents=True)
        config = directory / 'config.json'
        config.write_text(json.dumps(dict(source=source, rows=rows, runtime=str(directory/'runtime'), instrument=counted)))
        self.log = (directory/'stderr.log').open('w')
        self.process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(config)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True)
        self.info = json.loads(self.process.stdout.readline())
    def command(self, value):
        self.process.stdin.write(json.dumps(value)+'\n'); self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('"stop"\n'); self.process.stdin.flush()
        assert self.process.wait(timeout=25) == 0
        self.log.close()


def payload(rows, scenario, phase):
    if scenario == 'noop': return {}
    if scenario == 'sparse': return {'enabled': {'0': bool(phase % 2)}}
    return {'enabled': {str(i): (not (i % 11 != 0 and i not in (0,5)) if phase % 2
                                else i % 11 != 0 and i not in (0,5)) for i in range(rows)}}


def request(worker, encoded):
    stop = threading.Event()
    samples = [memory(worker.info['pid'])]
    def observe():
        while not stop.wait(.005): samples.append(memory(worker.info['pid']))
    observer = threading.Thread(target=observe); observer.start()
    start = time.perf_counter_ns()
    req = urllib.request.Request(worker.info['url'], data=encoded, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    finally:
        elapsed = (time.perf_counter_ns()-start)/1e6
        stop.set(); observer.join()
    samples.append(memory(worker.info['pid']))
    stat = Path(worker.info['path']).stat()
    result = dict(milliseconds=elapsed, status=status, response_bytes=len(body),
                  file_after=dict(bytes=stat.st_size, inode=stat.st_ino, mtime_ns=stat.st_mtime_ns),
                  response=json.loads(body), payload_bytes=len(encoded), rss_samples=samples,
                  client_memory=memory(os.getpid()), after=worker.command('stats'))
    assert status == 200 and result['response']['ok'] is True, result
    assert result['after']['owners'] == 0
    return result


def expected_hash(rows, scenario, phase):
    doc = fixture(rows)
    for key, value in payload(rows, scenario, phase).get('enabled', {}).items():
        doc['detections'][int(key)]['enabled'] = value
    class HashStream:
        digest = hashlib.sha256()
        def write(self, value): self.digest.update(value.encode('utf-8'))
    stream = HashStream(); json.dump(doc, stream, indent=1)
    return stream.digest.hexdigest()


def distribution(values):
    ordered = sorted(values)
    return dict(n=len(values), min_ms=min(values), median_ms=statistics.median(values),
                p95_ms=ordered[max(0, (95*len(values)+99)//100-1)], max_ms=max(values))


def run(args):
    evidence = args.evidence_dir.resolve(); evidence.mkdir(parents=True, exist_ok=True)
    sources = {label: export_source(args.repository, revision, evidence/('export-'+label))
               for label, revision in [('before', args.before_ref), ('after', args.after_ref)]}
    results = dict(scenario='saves', sources=sources, python=sys.version, executable=sys.executable,
                   platform=platform.platform(), warmups=args.warmups, samples=args.samples,
                   client_initial_memory=memory(os.getpid()), runs=[],
                   limits=['Linux /proc RSS sampled every 5ms may miss peaks.',
                           'VmHWM includes imports/fixture construction; process counters are cumulative.',
                           'Client fixture hashing/payload generation are outside latency; client RSS recorded separately.',
                           'Loopback Cheroot HTTP on one host; warm filesystem cache; no inference/media/downloads.',
                           'Python stream writes are not syscalls. Timing workers have no operation wrappers.'])
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2))
    save()
    for rows in args.rows:
        workers = {}
        try:
            workers = {label: Worker(source, rows, evidence/('%d-timed-%s' % (rows,label)), False)
                       for label, source in sources.items()}
            assert workers['before'].info['initial_file']['sha256'] == workers['after'].info['initial_file']['sha256']
            for scenario in ('noop','sparse','bulk'):
                record = dict(rows=rows, operation=scenario, workers={k:v.info for k,v in workers.items()},
                              warmup=[], recorded=[], files_before={}, files_after={}, summary={})
                results['runs'].append(record)
                for label, item in workers.items():
                    item.command('reset'); record['files_before'][label] = metadata(Path(item.info['path']))
                for index in range(args.warmups+args.samples):
                    encoded = json.dumps(payload(rows, scenario, index+1), separators=(',',':')).encode()
                    # Alternate both across versions and which version goes first.
                    order = ('before','after') if index % 2 == 0 else ('after','before')
                    for label in order:
                        result = request(workers[label], encoded)
                        result.update(version=label, phase=index+1)
                        assert result['response']['total'] == rows
                        assert result['response']['suggest_allowlist'] == (['synthetic-recurring'] if scenario == 'noop' or (index+1) % 2 == 0 else [])
                        record['warmup' if index < args.warmups else 'recorded'].append(result)
                    save()
                expected = expected_hash(rows, scenario, args.warmups+args.samples)
                for label, item in workers.items():
                    record['files_after'][label] = metadata(Path(item.info['path']))
                    assert record['files_after'][label]['sha256'] == expected
                    record['summary'][label] = distribution([s['milliseconds'] for s in record['recorded'] if s['version']==label])
                save()
                print(json.dumps(dict(rows=rows, operation=scenario, summary=record['summary'])), flush=True)
        finally:
            for item in workers.values(): item.close()
        # Fresh workers keep instrumentation entirely out of timed request paths.
        for label, source in sources.items():
            item = Worker(source, rows, evidence/('%d-counted-%s' % (rows,label)), True)
            try:
                for scenario in ('noop','sparse','bulk'):
                    item.command('reset')
                    result = request(item, json.dumps(payload(rows, scenario, 1)).encode())
                    result.update(version=label, worker=item.info)
                    counts = result['after']['counts']
                    writes = 0 if label == 'after' and scenario == 'noop' else 1
                    assert counts['report_parse'] == counts['request_json'] == counts['response_json'] == 1
                    assert all(counts[k] == writes for k in ('report_dump','stage','fsync','replace'))
                    record = next(r for r in results['runs'] if r['rows']==rows and r['operation']==scenario)
                    record.setdefault('instrumented', {})[label] = result
                    save()
            finally: item.close()
    # Revalidate exports after all measurements; unexpected source writes fail.
    for source in sources.values():
        for name, expected in source['sha256'].items():
            assert sha_file(Path(source['export'])/name) == expected
    results['exports_verified_after'] = True
    save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['saves'], default='saves')
    parser.add_argument('--rows', type=int, nargs='+', default=[1000,10000,100000])
    parser.add_argument('--repository', type=Path, default=Path.cwd())
    parser.add_argument('--before-ref')
    parser.add_argument('--after-ref')
    parser.add_argument('--evidence-dir', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--warmups', type=int, default=3)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker.read_text())); return
    if not all((args.before_ref,args.after_ref,args.evidence_dir,args.output)):
        parser.error('--before-ref, --after-ref, --evidence-dir and --output are required')
    if min(args.rows) < 6 or args.warmups < 3 or args.samples < 5:
        parser.error('rows >=6, warmups >=3 and samples >=5 are required')
    run(args)


if __name__ == '__main__':
    main()
