from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/benchmark/review_io.py');s=p.read_text()
a=s.index('        # Fresh workers keep instrumentation entirely out of timed request paths.')
b=s.index('    # Revalidate exports after all measurements;',a)
old=s[a:b]
helper='''def count_operations(sources, rows, evidence, before_noop_publications=1):
    """Run only fresh counted workers; no latency sample from here is a timing result.

    Historical pre-optimization baselines publish once for no-op saves. A pinned
    baseline that already skips publication must explicitly request zero.
    """
    if before_noop_publications not in (0, 1):
        raise ValueError('before_noop_publications must be 0 or 1')
    counted = {scenario: {} for scenario in ('noop', 'sparse', 'bulk')}
    for label, source in sources.items():
        item = Worker(source, rows, evidence/('%d-counted-%s' % (rows,label)), True)
        try:
            for scenario in counted:
                item.command('reset')
                result = request(item, json.dumps(payload(rows, scenario, 1)).encode())
                result.update(version=label, worker=item.info)
                counts = result['after']['counts']
                writes = (before_noop_publications if label == 'before' else 0) if scenario == 'noop' else 1
                assert counts['report_parse'] == counts['request_json'] == counts['response_json'] == 1
                assert all(counts[k] == writes for k in ('report_dump','stage','fsync','replace')), counts
                counted[scenario][label] = result
        finally:
            item.close()
    return counted


'''
s=s[:a]+'''        # Fresh workers keep instrumentation entirely out of timed request paths.
        counted = count_operations(sources, rows, evidence, args.before_noop_publications)
        for scenario, observations in counted.items():
            record = next(r for r in results['runs'] if r['rows']==rows and r['operation']==scenario)
            record['instrumented'] = observations
        save()
'''+s[b:]
s=s.replace('def run(args):',helper+'def run(args):')
s=s.replace("platform=platform.platform(), warmups=args.warmups, samples=args.samples,", "platform=platform.platform(), warmups=args.warmups, samples=args.samples,\n                   before_noop_publications=args.before_noop_publications,")
s=s.replace("    parser.add_argument('--warmups', type=int, default=3)","    parser.add_argument('--before-noop-publications', type=int, choices=[0, 1], default=1,\n                        help='expected baseline no-op publications; use 0 for an already optimized baseline')\n    parser.add_argument('--warmups', type=int, default=3)")
p.write_text(s)
p=p.with_name('README.md');s=p.read_text();s+='''
For a pinned baseline that already skips unchanged-save publication, pass
`--before-noop-publications 0`; the default `1` retains the historical
pre-optimization comparison. This changes only counted-work expectations.
To recover a completed timing set after a count-expectation error, import
`count_operations(sources, rows, evidence_dir, before_noop_publications=0)`
with the original pinned source manifests and a fresh evidence directory.
Keep its result separate, reverify every exported source hash, and prove
runtime-byte equality before relating timings to a tooling-only follow-up.
Never relabel existing timing samples as another commit.
''';p.write_text(s)
