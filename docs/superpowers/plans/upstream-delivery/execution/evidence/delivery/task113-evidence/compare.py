"""Offline full-module reverse/finalization comparison; no model inference."""
import argparse, collections, dataclasses, gc, hashlib, importlib.util, inspect, json
import pathlib, random, statistics, sys, time, tracemalloc
from rapidfuzz import fuzz

def load(name, root):
    path = pathlib.Path(root).resolve() / 'openscrub.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert pathlib.Path(module.__file__).resolve() == path
    module.cv2.setNumThreads(1)
    return module


def fixture(module, mode, n):
    memory = module.PhiMemory()
    raw, scans, misses = [], [], []
    for i in range(n):
        rng = random.Random(83011 + (0 if mode == 'repeated' else i))
        size = 4 + (i * 17) % 77 if mode == 'heterogeneous' else 24
        text = ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(size)) + '@sample.invalid'
        miss = ('unmatched' if mode != 'same_length' else
                ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(len(text))))
        assert len(module.PhiMemory.norm(miss)) >= 4 and module.PhiMemory.norm(miss) not in module.STOPWORDS
        words = [(text, (8, 8, 150, 28), .99), (miss, (8, 40, 150, 60), .99)]
        t = i / 3
        found = module.detect_phi(words, module.group_lines(words), t, (0., 0.), None, None)
        assert len(found) == 1 and found[0].text == text and found[0].category == 'email'
        assert memory.recall(miss) is None
        raw.extend(found)
        for d in found:
            memory.add(d.text, d.category)
        scans.append((t, (0., 0.), words))
        misses.append(miss)
    assert len(memory.items) == (1 if mode == 'repeated' else n)
    assert all(memory.recall(w) is None for w in misses)
    return scans, memory, raw


def invoke(module, boundary, fixture_data):
    scans, memory, raw = fixture_data
    extra = module.reverse_pass(scans, memory, {'email'}, None)
    if boundary == 'reverse':
        return extra, extra
    return module.merge_detections(raw + extra, hold=1/3 + .3, scans=scans, fuzz=fuzz), extra


def values(result, extra, fixture_data):
    scans, memory, raw = fixture_data
    return dict(result=[dataclasses.asdict(d) for d in result],
                raw_after=[dataclasses.asdict(d) for d in raw],
                extra_after=[dataclasses.asdict(d) for d in extra],
                memory_items=list(memory.items.items()), counts=list(memory.counts.items()))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def measure_work(module, data):
    lines, start = inspect.getsourcelines(module.reverse_pass)
    candidate = next(start + i for i, line in enumerate(lines) if line.strip() == 'if cat not in cats:')
    construction = next((start+i for i,line in enumerate(lines)
                         if line.strip().startswith('if type(key) is not str')), None)
    counts = collections.Counter()
    retained = {}
    def trace(frame, event, arg):
        if frame.f_code is module.reverse_pass.__code__:
            if event == 'line':
                if frame.f_lineno == candidate: counts['candidate_visits'] += 1
                if frame.f_lineno == construction: counts['construction_entries'] += 1
            elif event == 'return':
                buckets = frame.f_locals.get('buckets')
                if buckets:
                    lists = [entries for by_length in buckets for entries in by_length.values()]
                    entries = [entry for bucket in lists for entry in bucket]
                    retained.update(entries=len(entries), buckets=len(lists),
                        index_bytes_shallow=(sys.getsizeof(buckets) +
                            sum(sys.getsizeof(d) for d in buckets) +
                            sum(sys.getsizeof(b) for b in lists) +
                            sum(sys.getsizeof(e) + sys.getsizeof(e[0]) for e in entries)))
        return trace
    sys.settrace(trace)
    try:
        result, extra = invoke(module, 'reverse', data)
    finally:
        sys.settrace(None)
    return dict(counts=counts, live_index_at_return=retained, output_sha256=digest(values(result, extra, data)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--scans', type=int, default=500)
    args = parser.parse_args()
    modules = {'base': load('reverse_base', args.base), 'head': load('reverse_head', args.head)}
    assert gc.isenabled()
    report = dict(python=sys.version, executable=sys.executable, gc_enabled=gc.isenabled(),
                  settings=dict(scans=args.scans, seed=83011, warmups=3, samples=5,
                                categories=['email'], hold=1/3+.3, lenient=76),
                  source_sha256={label: hashlib.sha256(pathlib.Path(m.__file__).read_bytes()).hexdigest()
                                 for label,m in modules.items()},
                  benchmark_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), cases=[])
    # Timing finishes for EVERY case before tracing/allocation instrumentation starts.
    for mode in ['heterogeneous', 'same_length', 'repeated']:
        row = dict(case=mode, boundaries={})
        data = fixture(modules['base'], mode, args.scans)
        row['input_scans'] = data[0]
        row['fixture'] = dict(scans=len(data[0]), words=sum(len(s[2]) for s in data[0]),
            memory=len(data[1].items), primary=len(data[2]), eligible_words=sum(1 for scan in data[0] for word,_,_ in scan[2] if len(modules['base'].PhiMemory.norm(word))>=4 and modules['base'].PhiMemory.norm(word) not in modules['base'].STOPWORDS),
            key_lengths=dict(collections.Counter(map(len,data[1].items))))
        for boundary in ['reverse', 'reverse_plus_merge']:
            runs = []
            expected = None
            for rep in range(8):
                order = ['base', 'head'] if rep % 2 == 0 else ['head', 'base']
                for label in order:
                    module = modules[label]
                    data = fixture(module, mode, args.scans)
                    start = time.perf_counter_ns()
                    result, extra = invoke(module, boundary, data)
                    elapsed = time.perf_counter_ns() - start
                    value = values(result, extra, data)
                    if expected is None: expected = value
                    assert value == expected, (mode, boundary, rep, label)
                    runs.append(dict(repetition=rep, warmup=rep<3, module=label,
                                     ns=elapsed, output_sha256=digest(value), value=value))
            medians = {label: statistics.median(r['ns'] for r in runs
                       if not r['warmup'] and r['module']==label) for label in modules}
            row['boundaries'][boundary] = dict(median_ns=medians, runs=runs)
            print(mode, boundary, medians, flush=True)
        report['cases'].append(row)
    for row in report['cases']:
        row['instrumentation'] = {}
        for label,module in modules.items():
            data = fixture(module,row['case'],args.scans)
            work = measure_work(module,data)
            data = fixture(module,row['case'],args.scans)
            tracemalloc.start()
            result, extra = invoke(module,'reverse',data)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            work['reverse_tracemalloc_bytes'] = dict(current=current,peak=peak)
            work['allocation_output_sha256'] = digest(values(result,extra,data))
            row['instrumentation'][label] = work
    pathlib.Path(args.output).write_text(json.dumps(report,indent=2)+'\n')

if __name__ == '__main__':
    main()
