"""Recompute all declared browser-log records; no application imports/timing."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


def distribution(values):
    values = sorted(values)
    return {'n': len(values), 'min': values[0], 'median': statistics.median(values),
            'p95_nearest_rank': values[math.ceil(.95 * len(values)) - 1], 'max': values[-1]}


def overlaps(start, end, windows):
    return any(start < b and end > a for a, b in windows)


def attribution(rows, observed):
    publication = [(x['sample']['publicationStart'], x['sample']['publicationEnd']) for x in observed]
    cycle = [(x['sample']['cycleStart'], x['sample']['cycleEnd']) for x in observed]
    result = {}
    for name, items in (
        ('long_tasks', [t for x in rows for t in x['longTasks']]),
        ('raf_gaps', [t for x in rows for t in x['frames']]),
    ):
        groups = {'overlaps_observed_publication': [], 'overlaps_other_observed_cycle': [], 'outside_observed_cycles': []}
        for item in items:
            start, end = item['start'], item.get('end', item['start'] + item['duration'])
            key = ('overlaps_observed_publication' if overlaps(start, end, publication)
                   else 'overlaps_other_observed_cycle' if overlaps(start, end, cycle)
                   else 'outside_observed_cycles')
            groups[key].append(item['duration'])
        result[name] = {k: {'count': len(v), 'max_whole_interval_ms': max(v, default=0)} for k, v in groups.items()}
    result['interpretation'] = 'Interval overlap is not sole-cause attribution; outside includes initial/warmup/control/async validation. A frame gap can include work outside its overlapping publication.'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    summary = {'cases': {}, 'raw_files': {}, 'method': '125 observed accepted batches per source/case; median and empirical nearest-rank p95 sorted[118]. Initial has one observation only.',
               'limitations': ['fixed base→candidate source order', 'intentionally differing retained histories', 'idle post-batch wheel is not input latency during publication', 'represented units/node creation are not engine copies/heap/RSS']}
    fixture_hashes = {}
    for phase in ('timing', 'instrumentation'):
        for label in ('base', 'candidate'):
            path = args.root / ('measurement-' + label + '-' + phase + '.json')
            data = json.loads(path.read_text())
            assert len(data) == (528 if phase == 'timing' else 132)
            summary['raw_files'][path.name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'records': len(data)}
            for kind in ('short', 'multiline', 'long', 'dense-multiline'):
                rows = [x for x in data if x['kind'] == kind and 'sample' in x]
                assert all(x['correct'] for x in rows)
                initial = [x for x in rows if x['stage'] == 'initial']
                observed = [x for x in rows if x['stage'] == 'observed']
                assert len(initial) == 1 and len(observed) == (125 if phase == 'timing' else 31)
                identity = next(x for x in data if x['kind'] == kind and 'fixtureHash' in x)
                key = (phase, kind)
                if key in fixture_hashes:
                    assert identity['fixtureHash'] == fixture_hashes[key]
                fixture_hashes[key] = identity['fixtureHash']
                case = summary['cases'].setdefault(kind, {}).setdefault(label, {})
                if phase == 'timing':
                    assert len([x for x in rows if x['stage'] == 'warmup']) == 5
                    case.update({'identity': identity, 'initial_publication_ms': initial[0]['sample']['publicationMs'],
                                 'initial_cycle_ms': initial[0]['sample']['cycleMs'], 'initial_entries': initial[0]['expectedEntries'],
                                 'publication_ms': distribution([x['sample']['publicationMs'] for x in observed]),
                                 'cycle_ms': distribution([x['sample']['cycleMs'] for x in observed]),
                                 'emission_buckets': {}, 'transport': {}, 'attribution': attribution(rows, observed),
                                 'idle_post_batch_wheels': [x['idlePostBatchWheel'] for x in observed if 'idlePostBatchWheel' in x]})
                    for end, begin in ((1000, 500), (2000, 1000), (3000, 2000)):
                        bucket = [x['sample']['publicationMs'] for x in observed if begin < x['emitted'] <= end]
                        case['emission_buckets'][str(end)] = {'n': len(bucket), 'publication_median_ms': statistics.median(bucket)}
                    for route in ('meta', 'log'):
                        transports = [t for x in observed for t in x['transport'] if ('/log?' in t['url']) == (route == 'log')]
                        assert len(transports) == 125
                        case['transport'][route] = {field: distribution([t[field] for t in transports]) for field in ('headersMs', 'bodyMs', 'totalMs', 'bytes')}
                    last = observed[-1]
                    case['final'] = {k: last[k] for k in ('emitted', 'cursor', 'expectedEntries', 'entries', 'contentNodes', 'delimiters', 'units')}
                    case['final']['represented_bytes'] = 2 * last['units']
                    case['budget_exceeded'] = label == 'candidate' and (case['publication_ms']['median'] > 16 or case['publication_ms']['p95_nearest_rank'] > 50)
                else:
                    previous_entries = previous_nodes = previous_units = 0
                    bounds = []
                    for row in rows:
                        bounds.append({'entry_objects_nodes': previous_entries + row['counts']['spans'],
                                       'text_nodes': previous_nodes + row['counts']['textNodes'],
                                       'represented_node_input_bytes': 2 * (previous_units + row['counts']['units'])})
                        previous_entries, previous_nodes, previous_units = row['entries'], row['contentNodes'] + row['delimiters'], row['units']
                    case['instrumentation'] = {'final_publication': observed[-1]['counts'], 'maximum_passed_units': max(x['counts']['units'] for x in rows),
                                               'conservative_transient_maxima': {k: max(x[k] for x in bounds) for k in bounds[0]},
                                               'note': 'old referenced state plus created publication inputs; engine allocation/copy counts are unmeasured. Baseline implicit textContent nodes are not counted by createTextNode hooks.'}
    (args.root / 'measurement-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({kind: {label: {'publication': case['publication_ms'], 'initial_ms': case['initial_publication_ms'], 'final': case['final'], 'budget_exceeded': case['budget_exceeded']} for label, case in labels.items()} for kind, labels in summary['cases'].items()}, indent=2))


if __name__ == '__main__':
    main()
