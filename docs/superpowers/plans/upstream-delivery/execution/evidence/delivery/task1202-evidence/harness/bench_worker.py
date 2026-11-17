"""One fresh base/candidate observation; no timing executes at import."""
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request

from task1202_isolation import configure
from fixtures.log_workload import JOBS, HTTP_REPETITIONS, message, retained

ROOT = Path(os.environ['TASK1202_ROOT'])

def digest(lines):
    return hashlib.sha256(json.dumps(lines, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()

def main():
    mode, case, count_s, sample = sys.argv[1:]
    count = int(count_s)
    web = configure()
    assert gc.isenabled()
    jobs = [web.new_job('', {}, 'calibration') for _ in range(JOBS)]
    callbacks = [web.WebCallbacks(job) for job in jobs]
    base, expected, payload = retained(case, count)
    expected_hash = digest(expected)
    instrumented = mode.endswith('-allocation')
    candidate = mode.startswith('candidate')
    if instrumented:
        import tracemalloc
        gc.collect()
        tracemalloc.start()
        for cb in callbacks:
            for i in range(count):
                cb.log(message(case, i))
        current, append_peak = tracemalloc.get_traced_memory()
        # Actual route snapshot/encoding, deliberately after all elapsed timing.
        with web.app.test_client() as client:
            result = client.get('/api/jobs/' + jobs[0]['id'] + '/log?from=0')
            output_bytes = len(result.data)
        snapshot_current, snapshot_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result_record = {'retained_traced_current': current, 'append_traced_peak': append_peak,
                         'snapshot_json_current': snapshot_current, 'snapshot_json_peak': snapshot_peak,
                         'output_bytes': output_bytes}
    else:
        inputs = tuple(message(case, i) for i in range(count))
        start = time.perf_counter_ns()
        for cb in callbacks:
            for value in inputs:
                cb.log(value)
        append_ns = time.perf_counter_ns() - start
        # The same immutable input sequence is supplied to each real callback.
        input_hash = digest(inputs)
        from werkzeug.serving import make_server, WSGIRequestHandler
        class QuietHandler(WSGIRequestHandler):
            def log_request(self, *args, **kwargs):
                pass
        server = make_server('127.0.0.1', 0, web.app, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        prefix = 'http://127.0.0.1:' + str(server.server_port)
        def request(index, cursor):
            with urllib.request.urlopen(prefix + '/api/jobs/' + jobs[index]['id'] + '/log?from=' + str(cursor), timeout=30) as response:
                return response.read()
        try:
            # Untimed correctness request makes exact matched-subset equivalence explicit.
            matched = json.loads(request(0, base))
            assert matched['lines'] == expected
            result_record = {'append_batch_ns': append_ns, 'append_us_per_entry': append_ns / (JOBS * count * 1000),
                             'input_hash': input_hash, 'http_full_ns': [], 'http_matched_ns': [],
                             'http_full_bytes': [], 'http_matched_bytes': []}
            for boundary, cursor in (('full', 0), ('matched', base)):
                for index in range(HTTP_REPETITIONS):
                    start = time.perf_counter_ns()
                    body = request(index % JOBS, cursor)
                    elapsed = time.perf_counter_ns() - start
                    result_record['http_' + boundary + '_ns'].append(elapsed)
                    result_record['http_' + boundary + '_bytes'].append(len(body))
                    decoded = json.loads(body)
                    expected_from = base if boundary == 'matched' or candidate else 0
                    assert decoded['from'] == expected_from
                    assert decoded['len'] == count
                    assert len(decoded['lines']) == count - expected_from
                    if boundary == 'matched' or candidate:
                        assert decoded['lines'] == expected
                        assert digest(decoded['lines']) == expected_hash
                    else:
                        assert decoded['lines'] == list(inputs)
                    if candidate:
                        assert decoded['base'] == base and decoded['dropped'] == base
                        assert decoded['truncated'] == 0
                        assert decoded['reset'] == ('stale' if cursor < base else None)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    owner = jobs[0]['log']
    if candidate:
        snap = owner.snapshot()
        assert snap['lines'] == expected
        state = {key: snap[key] for key in ('base', 'len', 'dropped', 'truncated', 'retained', 'bytes')}
    else:
        state = {'base': 0, 'len': len(owner), 'dropped': 0, 'truncated': 0,
                 'retained': len(owner), 'bytes': sum(len(value.encode()) for value in owner)}
    result_record.update(mode=mode, case=case, count=count, sample=sample, jobs=JOBS,
                         intended_base=base, intended_retained=count-base, intended_bytes=payload,
                         intended_subset_sha256=expected_hash, state=state, gc_enabled=gc.isenabled(),
                         frozen_manifest_sha256=os.environ['TASK1202_MANIFEST_HASH'],
                         source_web_sha256=os.environ['TASK1202_WEB_HASH'])
    print('OBSERVATION ' + json.dumps(result_record, sort_keys=True), flush=True)

if __name__ == '__main__':
    main()
