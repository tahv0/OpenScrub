from pathlib import Path
import hashlib,json,subprocess,statistics
art=Path('/tmp/openscrub-task631'); root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
r=json.loads((art/'measurement/results.json').read_text());assert r['exports_verified_after']
base='12919c96c6f7558136b50d7b4d85e5e6b62f1971';head='3457efac574d74a7d2377cbc0d44bb0b87462c3a'
assert r['sources']['before']['revision']==base and r['sources']['after']['revision']==head
assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==head
assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True).strip()
manifest=json.loads((art/'verification-source.json').read_text())
for name,expected in manifest['files'].items():
 actual=hashlib.sha256((root/name).read_bytes()).hexdigest();assert actual==expected,name
 assert hashlib.sha256(subprocess.check_output(['git','-C',str(root),'show',head+':'+name])).hexdigest()==expected,name
for name in ['openscrub.py','openscrub_web.py','openscrub_internal/reports.py','openscrub_internal/lifetimes.py']:
 assert (art/'installed/site-packages'/name).read_bytes()==(root/name).read_bytes(),name
requests=0
for a in r['runs']:
 assert len(a['warmup'])==6 and len(a['recorded'])==10
 for label in ('before','after'):
  samples=sorted([s for s in a['warmup']+a['recorded'] if s['version']==label],key=lambda x:x['phase'])
  previous=a['files_before'][label]
  for s in samples:
   assert s['status']==200 and s['response']['total']==a['rows'];requests+=1
   if a['operation']=='noop' and label=='after':
    assert s['file_after']['inode']==previous['inode']
    assert s['file_after']['mtime_ns']==previous['mtime_ns']
   else: assert s['file_after']['inode']!=previous['inode']
   previous=s['file_after']
  assert a['files_after'][label]['sha256']==a['files_before'][label]['sha256'] # even final phase restores fixture
  c=a['instrumented'][label]['after']['counts'];assert c['report_parse']==c['request_json']==c['response_json']==1
  wanted=0 if a['operation']=='noop' and label=='after' else 1
  assert all(c[k]==wanted for k in ('report_dump','stage','fsync','replace'))
  assert a['instrumented'][label]['status']==200;requests+=1
assert requests==162
(art/'committed-bytes.log').write_text('Exact base/head exports verified after all measurements.32 frozen files match committed head; installed engine/web/report/lifetime bytes match head. Clean worktree.162/162 HTTP200;90 recorded/54 warmup/18 instrumented; all publication/content/identity assertions passed.\n')
lines=[(art/'report-prefix.md').read_text(), '\n## Measurement protocol and source identity\n',
'''The common benchmark driver at the committed head exported both pinned commits from Git into `measurement/export-before` and `measurement/export-after`. Every tracked blob was verified against its Git object before imports and rechecked after all measurements. Each fresh worker asserts actual imported engine/web/report paths and SHA256 against its export manifest. `results.json` retains complete source inventories, exact SHAs, Python executable/version/platform and all worker import paths. This is the reviewed P07b base, not an earlier instrumented research baseline. No timing is borrowed from earlier research.

The supervisor kept other agent-scheduled suites/browser/build/container/benchmark workloads absent. This did not reserve the host or control unrelated user/system activity. Our own suites, browser servers/Chromium, build, installed server and reopen process were finished/stopped before the boundary notice. Only this benchmark ran sustained work during its window; source/docs reads/writes continued. Shared-machine, scheduler, storage and filesystem-cache variation remain uncontrolled.

For each row count and operation, equal deterministic fresh fixtures contain motion and bands (three frames per row), dense tracks, manual rows/immutable creation metadata, person/polygon data, audio/transcript/suggestions and nested unknown fields. Both versions receive three warmups each, then five recorded samples each; calls alternate versions and which goes first. Sparse changes one enabled value and bulk changes every enabled value; both alternate choices every request and finish with the original choices restored. Every changed request's inode changes, while every after no-op retains its initial inode/mtime. Final SHA256 equals the expected complete canonical report, proving all unrelated content survives. No media or inference runs inside this benchmark; rendered-output compatibility is the separate small actual render/reopen evidence above.

Latency is actual loopback Cheroot HTTP through the registered save route, measured in the separate client from request construction/send through reading the response bytes; response decoding, payload generation, reset/fixture construction, complete expected-output hashing and statistics are outside the timer. An external client thread samples worker `/proc` RSS every5ms. Timing workers have no route wrappers. Fresh separate counted workers then instrument report work and request/response JSON. There are144 uninstrumented requests (54 warmups,90 recorded),18 separate instrumented requests, all162 HTTP200; all assertions and post-run export verification pass. The tiny10-row harness smoke is preserved separately and is not included in the main performance claim.

Reproduce in the prepared3.12 runtime (fresh evidence directory required):

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python benchmark/review_io.py --scenario saves --rows 1000 10000 100000 \\
  --repository /home/tahv0/.codex/worktrees/c832/OpenScrub \\
  --before-ref 12919c96c6f7558136b50d7b4d85e5e6b62f1971 \\
  --after-ref 3457efac574d74a7d2377cbc0d44bb0b87462c3a \\
  --evidence-dir /tmp/openscrub-task631/measurement \\
  --output /tmp/openscrub-task631/measurement/results.json
```

`measurement.log` and `measurement/results.json` preserve the actual run. The Python3.12 tarfile deprecation warning about Python3.14's future extraction-filter default appears during pinned local Git export, outside timing; no product/test warnings were observed. No repeated successful full suite, measurement set or build ran. The10-row smoke validated the harness before the required main sizes.
''', '\n### Latency distributions and every recorded sample\n\nAll times are milliseconds. With five observations, nearest-rank p95 equals max; no population-confidence claim is made. Raw warmups, sample ordering/statuses and RSS sample arrays remain in results.\n\n| Rows | Operation | Before min / median / p95=max | After min / median / p95=max | Median change |\n| ---: | --- | --- | --- | ---: |']
for a in r['runs']:
 b=a['summary']['before'];f=a['summary']['after'];change=(f['median_ms']/b['median_ms']-1)*100
 lines.append(f"| {a['rows']} | {a['operation']} | {b['min_ms']:.3f} / {b['median_ms']:.3f} / {b['p95_ms']:.3f} | {f['min_ms']:.3f} / {f['median_ms']:.3f} / {f['p95_ms']:.3f} | {change:+.2f}% |")
lines += ['\n| Rows | Operation | Before recorded samples (request order) | After recorded samples (request order) |\n| ---: | --- | --- | --- |']
for a in r['runs']:
 vals={label:', '.join(f"{s['milliseconds']:.6f}" for s in a['recorded'] if s['version']==label) for label in ('before','after')}
 lines.append(f"| {a['rows']} | {a['operation']} | {vals['before']} | {vals['after']} |")
lines += ['\nThe no-op median reductions are88.60% (1k),87.16% (10k) and78.03% (100k). Sparse medians vary from−0.78% to+1.30%; bulk from−4.45% to+4.38%. The100k bulk control is slower by232.76ms median (4.38%), consistent with the additional bounded ledger work; this small sample does not isolate causality. This PR claims demonstrated no-op savings only, not changed-save acceleration or general latency guarantees.\n', '\n### Separate report work and sizes\n\nEach row below has exactly one report parse, one request-JSON parse and one response-JSON serialization. `publish` means each of report dump, staging creation, explicit fsync and replacement has that count. Stream writes are Python calls, **not OS syscalls**. Instrumented timings are retained for audit but are excluded from the latency table.\n\n| Rows | Operation | Version | Publish | Python stream writes | Serialized characters |\n| ---: | --- | --- | ---: | ---: | ---: |']
for a in r['runs']:
 for label in ('before','after'):
  c=a['instrumented'][label]['after']['counts']
  lines.append(f"| {a['rows']} | {a['operation']} | {label} | {c['report_dump']} | {c['stream_writes']} | {c['serialized_characters']} |")
lines += ['\n| Rows | Canonical report bytes (initial/final) | No-op payload bytes | Sparse payload bytes | Bulk payload bytes |\n| ---: | ---: | ---: | --- | --- |']
for rows in (1000,10000,100000):
 aa=[a for a in r['runs'] if a['rows']==rows];sizes=[]
 for a in aa:
  vals=sorted({s['payload_bytes'] for s in a['recorded']});sizes.append('–'.join(map(str,vals)))
 lines.append(f"| {rows} | {aa[0]['files_before']['before']['bytes']} | {' | '.join(sizes)} |")
lines += ['\n### RSS, high-water and observer boundaries\n\nMiB below are KiB/1024; exact KiB and every external5ms observation are retained in results. Import RSS is measured after actual module imports. Fixture high-water includes fixture generation/serialization; ready RSS is after fixture release/GC and server readiness. Timed `before` is the median first RSS observation of recorded requests; `during max` is the largest sampled RSS, and HWM is the largest observed kernel VmHWM counter across in-flight and post-request snapshots. HWM may already be dominated by fixture construction or prior scenarios; it is not per-request temporary allocation. Some post-GC VmHWM reads are lower than in-flight RSS/counter observations on this host, so the table retains the maximum observed counter rather than only the final read. Sampling may miss shorter peaks.\n\n| Rows | Version | Import RSS | Fixture HWM | Initial ready RSS |\n| ---: | --- | ---: | ---: | ---: |']
for a in r['runs']:
 if a['operation']!='noop':continue
 for label in ('before','after'):
  w=a['workers'][label]
  lines.append(f"| {a['rows']} | {label} | {w['imported_memory']['VmRSS_kib']/1024:.1f} | {w['fixture_memory']['VmHWM_kib']/1024:.1f} | {w['ready_memory']['VmRSS_kib']/1024:.1f} |")
lines += ['\n| Rows | Operation | Version | Before RSS median | During RSS max | Cumulative HWM |\n| ---: | --- | --- | ---: | ---: | ---: |']
for a in r['runs']:
 for label in ('before','after'):
  ss=[s for s in a['recorded'] if s['version']==label]
  first=statistics.median(s['rss_samples'][0]['VmRSS_kib'] for s in ss)/1024
  peak=max(m['VmRSS_kib'] for s in ss for m in s['rss_samples'])/1024
  hwm=max([m['VmHWM_kib'] for s in ss for m in s['rss_samples']]+[s['after']['memory']['VmHWM_kib'] for s in ss])/1024
  lines.append(f"| {a['rows']} | {a['operation']} | {label} | {first:.1f} | {peak:.1f} | {hwm:.1f} |")
lines += ['\nClient RSS/high-water is separate from worker RSS. The client owns preencoded payloads, response buffers, result samples and expected-fixture hashing outside timed requests; no extra full-report copy was added inside the timed route. The server retains parsed raw data, and bulk assignment tracking additionally retains O(touched destinations) references/tuples.\n\n| Rows | Client RSS range in recorded requests | Client cumulative HWM max |\n| ---: | ---: | ---: |']
for rows in (1000,10000,100000):
 mm=[s['client_memory'] for a in r['runs'] if a['rows']==rows for s in a['recorded']]
 lines.append(f"| {rows} | {min(m['VmRSS_kib'] for m in mm)/1024:.1f}–{max(m['VmRSS_kib'] for m in mm)/1024:.1f} | {max(m['VmHWM_kib'] for m in mm)/1024:.1f} |")
a=r['runs'][-1]
peaks={label:max(m['VmRSS_kib'] for s in a['recorded'] if s['version']==label for m in s['rss_samples'])/1024 for label in ('before','after')}
lines += [f"\nAt100k bulk, sampled worker peak is{peaks['before']:.1f}MiB before and{peaks['after']:.1f}MiB after (delta{peaks['after']-peaks['before']:+.1f}MiB). This is a measured cost/control, not a claim that the ledger has zero memory cost. Import/fixture baselines, allocator retention, previous scenarios and sampled rather than continuous peaks limit attribution.\n", '''
## Self-review, limits and handoff

Self-review confirmed no full-document copy/encoding/digest on the no-op route; unchanged encoder and ordering; full validation before the publication decision; correct missing/type/signed-zero and alias handling; exact replay/conflict semantics; and unchanged browser/defaults. The existing web module is large; this change stays within the existing save route plus one small private comparator, without restructuring it. Benchmark driver complexity is isolated from runtime and packaged as source, not imported by the app.

Known costs/limits: bulk touched-field storage and measured control overhead; no no-op directory-mtime retention refresh; nonfinite touched values may conservatively publish; mandatory report parsing and existing full-row traversals remain. Report/file preservation was exercised on Linux/WSL only. Timing uses one shared host, local warm-cache Cheroot HTTP, five recorded samples per pair, no concurrency/load/inference/media and no controlled unrelated host activity. RSS is sampled and cumulative high-water includes fixture/import costs. The benchmark makes no production capacity, alternate platform, compact-serialization or general sparse/bulk speed claim.

All requested implementation, validation and measurement gates completed. No correctness concerns were found in self-review; the measured bulk/memory and retention limitations are explicit review considerations. The supervisor owns independent review and any future publication. Exact final verification is in `committed-bytes.log`; all source/export inventories, raw samples, counter runs and evidence paths are retained under `/tmp/openscrub-task631`.
''']
text='\n'.join(lines)
out=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task-631-report.md');out.write_text(text)
pr='''# Skip publication for effectively unchanged report saves

An empty, same-value or replay-only review save currently re-encodes, fsyncs and replaces the complete report. Compare only the final effective assignment destinations after existing normalization/replay validation, then skip publication when nothing changed. No-ops retain exact bytes and file metadata; real edits keep one existing atomic readable publication and the same acknowledgement response.

Preserves Task622/P06B transaction/lifetime gates, Task72/P07b immutable manual creation/replay/conflicts and P07a deliberate same-value/newer-edit acknowledgement behavior. No browser/default/dependency/version or serializer change. Nonfinite touched values conservatively publish; no-op saves do not refresh retention's directory mtime.

Validation:440-test combined suite;96 Python3.9 focused cases; actual browser acknowledgement/newer-edit/failed-publication/no-op save-and-render and fresh-process reopen; offline sdist→wheel/source/tests/benchmark inclusion and installed CLI/web smoke. All pass.

Pinned alternating loopback HTTP (three warmups/five recorded samples each, uninstrumented routes): no-op medians46.24→5.27ms at1k,481.03→61.75ms at10k,5,413.88→1,189.39ms at100k. Separate counts:one fresh report parse, zero report dump/stage/fsync/replace after a no-op; true sparse/bulk changes publish once.100k sparse median+1.3%, bulk+4.4%; no changed-save speed claim. Shared Linux host/warm-cache/sampled-RSS limits and all samples/costs are in task-631-report.md.

Base:`12919c96c6f7558136b50d7b4d85e5e6b62f1971`; head:`3457efac574d74a7d2377cbc0d44bb0b87462c3a`. Local draft only; not published.
'''
Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task-631-pr.md').write_text(pr)
print('Report and local PR draft written; exact committed/installed/export checks passed.162/162 HTTP200.')
print('100k bulk sampled peak MiB:',peaks)
