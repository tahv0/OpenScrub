from pathlib import Path
import json,hashlib
art=Path('/tmp/openscrub-task652');workspace=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
r=json.loads((art/'measurement/results.json').read_text());e=json.loads((art/'committed-evidence.json').read_text());c=json.loads((art/'committed-bytes.json').read_text())
summary=[];samples=[];warm=[];mem=[]
for rec in r['runs']:
 op=rec['operation'];b=rec['summary']['before'];a=rec['summary']['after'];change=100*(a['median_ms']/b['median_ms']-1)
 summary.append(f"| {op} | {b['min_ms']:.3f} / {b['median_ms']:.3f} / {b['p95_ms']:.3f} | {a['min_ms']:.3f} / {a['median_ms']:.3f} / {a['p95_ms']:.3f} | {change:+.2f}% |")
 pairs=[]
 for group,dst in [('recorded',samples),('warmup',warm)]:
  values={label:', '.join(f"{x['milliseconds']:.6f}" for x in rec[group] if x['version']==label) for label in ('before','after')}
  dst.append(f"| {op} | {values['before']} | {values['after']} |")
 peaks={label:max(m['VmRSS_kib'] for x in rec['warmup']+rec['recorded'] if x['version']==label for m in x['rss_samples']) for label in ('before','after')}
 mem.append(f"| {op} | {peaks['before']} | {peaks['after']} |")
perf='''One approved exclusive slot compared exact `ac6496810b03d8b062ab9da150aeea1e62285fed` → exact `4b9bd7e576a8ae30369672b4b4722fc9752e233f`. Supervisor and implementer exchanged start/end notices; all other own servers/suites/build/install work stopped. Supervisor avoided competing workloads. The host itself was not reserved. No source change or amendment followed measurement; all samples remain attributed to their actual commits. No selective rerun.

Exact native command (prepared3.12/env.sh):

```sh
python benchmark/review_io.py --scenario saves --rows 100000 \\
  --repository /home/tahv0/.codex/worktrees/c832/OpenScrub \\
  --before-ref ac6496810b03d8b062ab9da150aeea1e62285fed \\
  --after-ref 4b9bd7e576a8ae30369672b4b4722fc9752e233f \\
  --before-noop-publications 0 --warmups 3 --samples 5 \\
  --evidence-dir /tmp/openscrub-task652/measurement \\
  --output /tmp/openscrub-task652/measurement/results.json
```

Command completed **exit0**. `measurement.log/results.json` retain every warmup/sample/status/RSS array/client observation/import/export hash. Actual loopback Cheroot requests include complete response reads. Payload/fixture/reset/expected hashing are outside timing; instrumented workers are separate after timing. Before and after both skip no-op publication; the common counter works with both serializers. Tiny6-row counted smoke ran first and passed. Only the required100k interaction set ran: **48uninstrumented HTTP200 requests (18warmup/30recorded), six separate counted HTTP200**, all owners0. No1k/10k, attribution, large-token or old matrix rerun.

All times ms, five observations per cell; nearest-rank p95=max, no confidence/population claim.

| Operation100k | Before min / median / p95=max | After min / median / p95=max | Median change |
| --- | --- | --- | --- |
'''+ '\n'.join(summary)+'''

Every recorded sample, in per-version request order:

| Operation | Before ms | After ms |
| --- | --- | --- |
'''+ '\n'.join(samples)+'''

Every warmup, in per-version request order:

| Operation | Before ms | After ms |
| --- | --- | --- |
'''+ '\n'.join(warm)+'''

Peak observed worker RSS KiB across warmup/recorded samples:

| Operation | Before | After |
| --- | --- | --- |
'''+ '\n'.join(mem)+'''

RSS is sampled5ms and can miss peaks; VmHWM includes imports/reset/fixtures and prior operations. It is not request-only memory or a hard allocation bound. Full worker/client memory and per-sample timing order remain in JSON. Changed-save improvements17.22–18.87% are a bounded local interaction observation. **No-op median regressed11.46%** (1026.342→1143.987ms); retain this measured concern, alongside the prior standalone Task632 +9.97% control observation. Zero-publication counts and unchanged no-op route bytes establish scope, not cause or repeatability. No scheduling/GC attribution or general untouched-feature speed claim.

Separate counts, per request: both versions parse/report request JSON/response JSON1; no-op report_encode/stage/fsync/replace/write/writelines0. Sparse/bulk encode/stage/fsync/replace1 each. Before uses one json.dump call,12,460,177 Python staging writes,0explicit encoder instances/writelines/chunks. After uses0json.dump/0Python staging writes, one public encoder instance and one writelines call,12,460,177 iterator chunks. Serialized characters agree across versions:69,956,371 sparse,70,038,188 bulk. These are Python dispatch/piece counts, **not OS syscalls or an output-format change**.

`check_evidence.py` independently checked all54statuses/owners, every no-op bytes/inode/mtime observation and exact final metadata/hash, every changed-request inode replacement, every expected complete final hash, retained actual final timed bytes and separate counted bulk phase1 bytes. `expected-final-100000.json` is69,956,372bytes, SHA256 `74f6909e2997cc763ecdbd8601986a5ae784217a4a7270e2863b3ffb7b814681`; expected counted changed output is retained separately. All3scenarios finish their8phases at the original choices; final physical timed files are last bulk phase8. No intermediate physical file is falsely labelled as still retained. `committed-evidence.json` records complete-output checks.

Both exported subject inventories were verified before imports and after measurement:139before/144after Git blobs; actual engine/web/report imports resolve within their pinned export roots. The final driver intentionally runs both source versions with its common counters; tooling identity is the measured-after `benchmark/review_io.py`, distinct from subjects' serializer implementations. `check_committed.py` proves all144frozen files match final Git/native bytes, all10wheel Python sources equal installed/native/commit, all five -x markers/candidate refs intact, clean head. No runtime-identity amendment or SHA relabelling was needed.
'''
report=workspace/'task-652-report.md';s=report.read_text().replace('PERFORMANCE_PENDING',perf)
s=s.replace('sdist contains all25 focused test files','sdist contains all25 test files')
s=s.replace('before **every** test run','before **every** test run')
s=s.replace('No runtime integration correction was needed.', 'No runtime integration correction was needed.')
s+='\nFinal package hashes: wheel `'+c['artifacts']['openscrub-1.0.96-py3-none-any.whl']+'`; sdist `'+c['artifacts']['openscrub-1.0.96.tar.gz']+'`. Final runtime import ASTs equal base for all10runtime Python sources (new helper/function bodies contain no new imports).\n'
report.write_text(s)
short='Single100k interaction: no-op median +11.46% (retained concern); sparse −18.87%, bulk −17.22%. 48uninstrumented+6separate counted HTTP200; complete reports/no-op metadata/export/commit/package identities verified. Exact SHAs retained; no selective rerun or general speed claim.'
for n in ['task-652-pr.md','task-652-acceptance.md']:
 p=workspace/n;p.write_text(p.read_text().replace('PERFORMANCE_PENDING',short))
identity={'before':r['sources']['before']['revision'],'after':r['sources']['after']['revision'],'measured_after_equals_final_head':True,'driver_sha256':hashlib.sha256((art/'measurement/export-after/benchmark/review_io.py').read_bytes()).hexdigest(),'measurement_log_sha256':hashlib.sha256((art/'measurement.log').read_bytes()).hexdigest(),'measurement_results_sha256':hashlib.sha256((art/'measurement/results.json').read_bytes()).hexdigest(),'source_manifests':{k:len(v['sha256']) for k,v in r['sources'].items()},'timing_and_counts_completed_exit0':True,'complete_reports_verified':True,'no_selective_rerun':True,'no_after_measurement_source_changes':True}
(art/'runtime-identity.json').write_text(json.dumps(identity,indent=2))
(art/'progress.md').write_text((art/'progress.md').read_text()+'\nTask652 implementation complete at '+r['sources']['after']['revision']+'. Five provenance picks and one test-only correction. Focused3.12/3.9 1242pass each; full1643pass/1optional browser skip; actual PAGE/HTTP/worker/native tracker/package/install complete. Exclusive100k run completed exit0 with no-op+11.46% control concern retained. Independent supervisor review pending.\n')
print('Final three handoff files and measured/runtime identity written.')
