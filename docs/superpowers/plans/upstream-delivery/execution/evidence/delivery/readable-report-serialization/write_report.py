from pathlib import Path
import json,hashlib,statistics,subprocess
ART=Path('/tmp/openscrub-task632'); DOC=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README'); ROOT=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
r=json.loads((ART/'measurement/results.json').read_text()); a=json.loads((ART/'attribution-10000-results.json').read_text()); verify=json.loads((ART/'committed-evidence.json').read_text()); large=json.loads((ART/'large-token-memory.json').read_text())
base=verify['base'];head=verify['head']
lines=[]
def add(s=''):lines.append(s)
def table(headers,rows):
 add('| '+' | '.join(headers)+' |');add('| '+' | '.join(['---']*len(headers))+' |')
 for row in rows:add('| '+' | '.join(str(v) for v in row)+' |')
 add()
def fmt(values):return ', '.join('%.6f'%v for v in values)
def mib(value):return '%.3f'%(value/1024)
add(f'''# Task632 — readable report serialization

Implementer disposition: **adopt the simple public-iterator/writelines candidate**, with the measured no-op-control regression retained as a review concern. Exact base **`{base}`**; clean committed head **`{head}`**, local branch `pr/readable-report-serialization`, native `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Independent supervisor review remains pending. No remote publication or messages, integration/docs branch pull, original-checkout product/runtime edits, subagents, new dependencies/models/toolchain, browser rerun or container work occurred. This report and task-632-pr.md are the requested handoff files in the supervisor SDD workspace. All raw evidence/scripts/logs and actual expected reports are under `/tmp/openscrub-task632`.

## Why, what and when

Reviewed Task631 established that changed publication remained material: its100k readable report is69,956,372bytes; changed-save medians5,370.674ms sparse and5,545.423ms bulk, versus1,189.387ms for its already-skipped no-op path. That difference includes route work as well as publication, and the12,460,177 separate Python stream-write observations are not syscalls or a speedup prediction. `report-noop-scope-research.md` and `task-631-report.md` were read before experimentation. No historical instrumented timings or no-op savings are reattributed to this change.

The only runtime change is in the existing private owner `openscrub_internal.reports.atomic_report`: replace `json.dump(report, stream, indent=1)` with `stream.writelines(json.JSONEncoder(indent=1).iterencode(report))`. Both use the public stdlib encoder with the same defaults. There is no encoder-private API, compact encoding, full dumps/join, cache/state, caller-specific path, buffer framework or changed persistence requirement. The shared owner still creates same-directory exclusive0600 staging, explicitly flushes/fsyncs, closes before replace, cleans temporary files and propagates failures. Engine/web callers, raw-report shape and insertion/list order, separators, ensure_ascii escapes, key handling, allow_nan/circular policy, no trailing newline, transaction/lifetime/replay/ACK behavior and Austin defaults are preserved.

The optimization removes the Python `json.dump` loop's per-token dispatch to the temporary wrapper. The public encoder still produces the same pieces, and TextIOWrapper still performs text encoding/buffering and internal writes. Fewer observable Python calls establish no syscall-count reduction. In particular, this change does not remove the large token produced when encoding a single large string.

## Bounded attribution and candidate selection

The first coordinated exclusive slot ran only `/tmp/openscrub-task632/attribution.py`, exact native base3457efa, prepared Python3.12.16. The retained script contains all three experimental bodies: unchanged dump, direct public iterator→writelines, and65536-character target aggregation using a list/join. Each uses the same atomic stage/flush/fsync/close/replace pattern over the deterministic10k fixture, with3warmups/5recorded publications per candidate, rotated order. GC, complete-output hashes, stats and memory-after snapshots are outside the publication timer. This is bounded publication attribution, not HTTP timing. All24 outputs were byte-identical6,955,571bytes, SHA256 `1942d80822b70f4527d81c879515421ae04a6f393b37a67626ed58238520148c`.
''')
table(['Candidate','Recorded median ms','Disposition'],[[k,'%.6f'%v,'selected for HTTP trial' if k=='writelines' else ('unchanged baseline' if k=='dump' else 'not adopted: essentially equal median with more retention/code')] for k,v in a['summary'].items()])
table(['Index','Kind','dump ms','writelines ms','aggregate65536 ms'],[[i,'warmup' if i<3 else 'recorded']+['%.6f'%next(s['milliseconds'] for s in a['samples'] if s['index']==i and s['candidate']==k) for k in ('dump','writelines','aggregate65536')] for i in range(8)])
add('''Direct writelines improved this median by23.96%; aggregation by24.29%. Their near-equal result favors the smaller direct candidate. The experimental aggregation list retains references to token strings plus joined output; its65536 target is not a hard cap when one token exceeds it. No failed/unused variant was added to runtime. A full dumps/join candidate was unnecessary once a simple streamed candidate justified the actual-route trial; no unmeasured full-materialization benefit or memory result is claimed.

Attribution memory is a cumulative in-process observation, **not** isolated per-candidate allocation: initial RSS43,016KiB/HWM44,920KiB, largest observed after-publication RSS43,432KiB/HWM45,288KiB, with fixture and previous candidates retained. Every individual memory snapshot, sample ordering, interpreter/source path and baseline helper SHA is retained in `attribution-10000-results.json`; final candidate memory is assessed separately below.

## Tests, verification and exact source provenance

`tests/test_report_serialization.py` adds16 real-publication compatibility/failure cases: literal golden readable bytes for nested additive fields, scalar distinctions including signed zero, Unicode/BMP/non-BMP/quote/backslash/control escapes, numeric/null/bool keys, explicit NaN/±Infinity default spellings; a large individually escaped string compared to public stdlib expected bytes; unsupported values/keys and circular references; injected streaming encoding, explicit flush, fsync and replace failures with both absent/existing destinations. Real partial staging bytes precede the encoding failure. Exact exception objects propagate, old files remain, and staging is cleaned. The unchanged private/complete-first-publication tests cover0600 permissions; existing reader/writer and actual-route suites cover atomic visibility and transaction/admission/lifetime behavior. The new bytes/error tests intentionally also pass baseline; they protect the unchanged contract.

A preliminary implementation-prescribing dispatch test was run RED against `json.dump` (16compatibility cases passed), then removed after review because it required one particular method. It is preserved in `add_tests.py` and `red.log`, not shipped. The owning performance RED is the bounded baseline attribution; the adopted change has no intended behavior delta to force into a failing compatibility test.

Two existing test-only instruments were adapted to the explicit public encoder: `test_large_report_io.py` retains its legacy internal `dump` counter as encoding-start count and now truthfully calls pieces `encoder_chunks`; the transaction serialization injection isolates `reports.json` so it cannot intercept client JSON. Route sparse/bulk/replay/no-op and P06 transaction/lifetime assertions were not removed or weakened.

Only the narrow reviewed Task651 driver corrections were carried from `ac6496810b03d8b062ab9da150aeea1e62285fed`: explicit supported tar `filter='data'` with capability fallback, historical baseline default1 and explicit already-optimized expectation0, plus reusable `count_operations`. No application/assembled source from Task651 was used. Task632 additionally adapts **separate counted workers** to observe both encoding entrypoints. `report_encode` counts actual publication encoding starts; `json_dump_calls` and `encoder_instances` retain method identity; `stream_writes`/`stream_writelines` count Python calls at the actual staging wrapper; `encoder_chunks` observes the explicit encoder iterator. Those counts do not instrument timed workers or measure syscalls. The historical default remains1 for before12919c9, while this run explicitly uses0 for before3457efa. Tiny six-row smoke asserts the preserved helper default and both exact pinned versions' actual HTTP counts before the timed comparison.
''')
table(['Check','Actual result','Evidence'],[
['Focused active-source reports/transactions/replay/reopen/response lifetime','168passed in12.60s','focused-final.log; task632_isolation.py asserts native imports'],
['Full discovered stable source','456passed in101.32s; zero skips/warnings','full.log, complete python -m pytest -q'],
['Actual Python3.9.25 affected cases','159passed in9.21s; zero skips/warnings','floor.log, floor-version.log, task-local audit/sitecustomize; public encoding, engine/route/replay/fresh-process tests'],
['Offline sdist→wheel','exit0, Hatchling1.33.0; wheel built from sdist','build.log; existing offline wheelhouse'],
['Exact archive contents/defaults/grammar','exit0; exact source/test/benchmark inclusion, Python3.9 grammar, metadata/defaults/JS','check_packaging.py, packaging.log/json'],
['Installed CLI/web entrypoints','exit0; installed CLI help, real Cheroot homepage/jobs, vault lock/unlock/allowlist, idle SIGTERM0','installed-startup-runtime.log; installed-startup.json; actual installed paths asserted'],
['Tiny separate count harness','6actual HTTP200; exact imports/bytes and zero-noop/one-changed encoding/stage/fsync/replace','count-smoke.py/log; count-smoke/results.json'],
['Pinned main benchmark','96uninstrumented+12counted HTTP200; complete final bytes, expected reports, exact exports','measurement.log; measurement/results.json; committed-evidence.json'],
['Source/commit self-review','127frozen blobs equal commit, clean head, diff --check passes','verification-source.json; committed-evidence.log/json']])
add('''Actual commands, working directories, environment, exact scripts and retained failed attempts are in `/tmp/openscrub-task632/evidence-commands.md`. The prepared3.12 executable is `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python`; actual3.9 is `/tmp/openscrub-python39-20261117/venv/bin/python` (3.9.25, Clang21.1.4). Runtime-source imports were asserted before final tests. Existing verified YuNet was reused only through the owning full-suite harness; no model was downloaded. The3.9 result covers affected active-source behavior and packaged grammar/floor metadata, not whole-app floor certification.

Full tests and packaging ran on stable source/test bytes before the local commit; the127-blob frozen manifest and later exact committed checks bind them to4a62e49. No source/test change followed those final tests. `packaging.json`'s captured precommit HEAD was3457efa and is not relabelled; archived and installed runtime bytes match the tested final commit. The real engine `write_report` success/failure and actual render/fresh interpreter report-reopen tests ran in the owning focused/full/3.9 sets. No additional broad browser matrix was justified: engine/web/JS/response sources are byte-identical between pinned versions and publication bytes remain exact.

Retained failures are not concealed or counted as passes:

- Initial `red.log`:1exploratory dispatch failure/16passes plus2read-only pytest cache warnings; cache redirected, dispatch test removed as above.
- Initial `focused.log`:132failed/27passed/10errors from original-cwd module shadowing and sandbox-denied loopback sockets. Native `sys.path` insertion/import assertions, native cwd and already-authorized escalation corrected the harness. This run provides no candidate correctness claim.
- Corrected `focused-active.log`:1failed/168passed; global JSONEncoder monkeypatch intercepted client request JSON before the intended lock schedule. Isolating the report module's JSON namespace corrected only the test injection; final168passed.
- `install.log`: prepared runtime had no pip. `installed-startup.log` therefore could not assert a missing installed module. Existing bootstrap pip then installed the wheel but generated dependency-less Python3.14 entrypoint shebangs (`install-bootstrap.log`, `installed-startup-final.log`). Running that existing pip code through the prepared3.12 interpreter installed identical wheel bytes with correct shebangs; `install-runtime.log` and final smoke passed. No new toolchain/dependencies/network.

## Final HTTP protocol, source identities and actual expected reports

The second coordinated exclusive slot compared only exact3457efa→4a62e49 exports. The supervisor confirmed no competing agent suite/browser/build/container/benchmark; only small source/docs IO occurred elsewhere. Own suite/build/install/server processes were stopped before the notice. The host was not reserved: user/system activity, CPU scheduling, storage and cache variation remain uncontrolled. Both timed slots were announced to the supervisor before/after; no own validation overlapped timing and no selective rerun was made to improve the noisy no-op control.

The committed driver ran10k/100k deterministic fixtures, each with dense/person/polygon tracks, manual creation metadata, three motion/band frames per row, audio/transcript/suggestions and nested unknown fields. Each operation/version receives3warmups then5recorded requests, alternating versions and which goes first. Sparse/bulk choices alternate every request;8total phases restore original choices. Timing is actual loopback Cheroot HTTP in the separate client from request construction/send through reading response bytes. Payload generation, reset/fixture construction, expected-output hashing, response decoding/statistics are outside the timer. Server module imports and fixture construction are outside request timing. No inference/media/download occurs. External5ms RSS sampling has no route-function wrappers. Fresh counted workers run only after timing and their recorded elapsed values are excluded from latency tables.

Reproduce from native cwd with a **fresh evidence/output directory**:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python benchmark/review_io.py --scenario saves --rows 10000 100000 \\
  --repository /home/tahv0/.codex/worktrees/c832/OpenScrub \\
  --before-ref 3457efac574d74a7d2377cbc0d44bb0b87462c3a \\
  --after-ref 4a62e49d2f0896b737081cc92e1f92e9bcaee93f \\
  --before-noop-publications 0 \\
  --evidence-dir /tmp/openscrub-task632/measurement \\
  --output /tmp/openscrub-task632/measurement/results.json
```

This exact command completed exit0. `measurement/results.json` retains Python3.12.16/Clang23.1.3, platform, all source SHA256 inventories, actual engine/web/report import paths and worker/client memory. All127before/after Git blobs were verified against pinned objects before import and after measurement. Engine/web source hashes are identical across versions; only the shared report helper's runtime bytes differ. Actual imports resolve under `/tmp/openscrub-task632/measurement/export-before` and `export-after`, never the original checkout. Helper SHA256 values:
''')
table(['Version','Exact revision','reports.py SHA256'],[[label,source['revision'],source['sha256']['openscrub_internal/reports.py']] for label,source in r['sources'].items()])
add('''All108main requests returned200/ok and released owners to0;96are uninstrumented (36warmups/60recorded),12separate counted. Every timed response has expected total/suggestions. Each scenario's complete final report SHA equals its deterministic expected full canonical report. Post-run `check_evidence.py` additionally writes the actual expected reports below, compares retained final timed files and counted final bulk-phase1 files byte-by-byte, checks every changed request replaced its inode and every no-op sample/final snapshot retained exact bytes/metadata. The benchmark records per-scenario final hashes before subsequent fixture resets; the retained physical worker file is the final bulk phase8 output. All scenarios'8phases finish at the same original document, rather than requiring differently named expected documents.
''')
table(['Rows','Actual expected final path','Complete bytes','SHA256'],[[rows,entry['path'],entry['bytes'],entry['sha256']] for rows,entry in verify['expected_final_reports'].items()])
add('''The separately retained `expected-counted-bulk-10000.json` and `expected-counted-bulk-100000.json` encode actual phase1 inverted enabled choices and match both remaining counted worker files byte-for-byte. Intermediate counted scenarios retain work/status/size observations; complete per-scenario final hashes belong to the uninstrumented run. Expected-fixture/client work is outside the measured requests and is not claimed as server serialization cost.

### All uninstrumented timing samples

Milliseconds below. Five observations per cell; nearest-rank p95 equals max and no confidence/population claim is made.
''')
rows=[]
for x in r['runs']:
 before=x['summary']['before'];after=x['summary']['after'];rows.append([x['rows'],x['operation'],' / '.join('%.3f'%before[k] for k in ('min_ms','median_ms','p95_ms')),' / '.join('%.3f'%after[k] for k in ('min_ms','median_ms','p95_ms')),'%+.2f%%'%(100*(after['median_ms']/before['median_ms']-1))])
table(['Rows','Operation','Before min / median / p95=max','After min / median / p95=max','Median change'],rows)
for kind in ('warmup','recorded'):
 add('**Every '+kind+' sample, per-version request order:**\n')
 table(['Rows','Operation','Before ms','After ms'],[[x['rows'],x['operation']]+[fmt([s['milliseconds'] for s in x[kind] if s['version']==label]) for label in ('before','after')] for x in r['runs']])
add('''All four changed-save median comparisons improve18.37–23.12%; every recorded candidate changed-save sample is faster than every baseline sample in its matching cell. At100k this saves1,016.918ms sparse and1,025.885ms bulk median in this local run. That reproducible effect across sparse/bulk and both sizes, together with bounded measured memory below, justifies adopting the simpler candidate.

The **100k no-op median regresses9.97%** (1,029.429→1,132.037ms); its spreads and warmups are retained above, including before max2,524.512ms and after max1,563.412ms. The10k no-op median is−1.19%. No-op route sources are unchanged and separate counts still show zero publication, which defines the optimization's scope but **does not establish the cause** of the observed control difference. The control was not selectively rerun. This PR claims changed-publication benefit in these fixtures, not no-op improvement, overall capacity or latency guarantees.

### Separate actual publication work

Every row below has report parse1, request JSON parse1, response JSON serialization1, owners0. `Encode/publish` is the count of each report_encode/staging/fsync/replace. `write`/`writelines` are Python calls at the staging wrapper, never syscalls; `pieces` comes from the explicit public iterator in the candidate (baseline JSON dump owns its iterator internally). Serialized characters equal bytes here because default ensure_ascii output is ASCII. Fresh counted workers' elapsed values and every count/RSS snapshot are retained under each run's `instrumented` key and are excluded from uninstrumented timing.
''')
table(['Rows','Operation','Version','Encode/publish each','dump calls','encoder instances','Python write','Python writelines','Observed pieces','Characters'],[[x['rows'],x['operation'],label]+[x['instrumented'][label]['after']['counts'][key] for key in ('report_encode','json_dump_calls','encoder_instances','stream_writes','stream_writelines','encoder_chunks','serialized_characters')] for x in r['runs'] for label in ('before','after')])
add('''At100k changed publication still encodes12,460,177pieces; Python staging `write` dispatches become0 and one `writelines` invocation consumes the real iterable. Encoding/staging/fsync/replace remain exactly1. Internal TextIOWrapper writes and OS syscalls were not counted. No-op retains its Task631 skip with one fresh report parse and no encoding/publication.

### RSS/high-water observations and retention limits

RSS tables are MiB (KiB/1024); exact KiB and every sampled5ms array remain in `measurement/results.json`, separate from timing claims. Import RSS follows actual module imports. Fixture HWM includes fixture construction/serialization; ready RSS is after fixture release/GC/server startup. Request-start RSS is the median first sample of the five recorded requests; during max is the largest recorded sampled RSS. HWM is the largest observed cumulative counter across samples and after snapshots, not per-request temporary allocation. Some post-GC kernel HWM readings are lower than in-flight RSS/counter observations on this host; the table retains the maximum observed value, not only the last reading. Sampling may miss shorter peaks and allocator retention/prior scenarios confound attribution.
''')
workers=[]
for rows in (10000,100000):
 x=next(x for x in r['runs'] if x['rows']==rows)
 for label,w in x['workers'].items():workers.append([rows,label,mib(w['imported_memory']['VmRSS_kib']),mib(w['fixture_memory']['VmHWM_kib']),mib(w['ready_memory']['VmRSS_kib'])])
table(['Rows','Version','Import RSS MiB','Fixture HWM MiB','Initial ready RSS MiB'],workers)
memrows=[]
for x in r['runs']:
 for label in ('before','after'):
  samples=[s for s in x['recorded'] if s['version']==label];observations=[p for s in samples for p in s['rss_samples']]
  memrows.append([x['rows'],x['operation'],label,mib(statistics.median(s['rss_samples'][0]['VmRSS_kib'] for s in samples)),mib(max(p['VmRSS_kib'] for p in observations)),mib(max([p['VmHWM_kib'] for p in observations]+[s['after']['memory']['VmHWM_kib'] for s in samples]))])
table(['Rows','Operation','Version','Request-start RSS median','During RSS max','Cumulative HWM max'],memrows)
client=[]
for rows in (10000,100000):
 s=[s['client_memory'] for x in r['runs'] if x['rows']==rows for s in x['recorded']]
 client.append([rows,mib(min(p['VmRSS_kib'] for p in s))+'–'+mib(max(p['VmRSS_kib'] for p in s)),mib(max(p['VmHWM_kib'] for p in s))])
table(['Rows','Separate client RSS range MiB','Client cumulative HWM max MiB'],client)
add('''At100k sampled sparse peak441.938→442.043MiB is+108KiB; bulk458.719→455.152MiB is−3,652KiB. These are measured paired observations, not proof of zero allocation cost or an allocation bound. Worker retained raw parsed report and existing bulk touched-field storage dominate; client fixture/hash/payload/response/result arrays and imports are separate costs, outside request timing where specified. No full document encoding/join is introduced in the runtime.

A separate fresh-process probe (`large_token_memory.py`) imports only each pinned real report helper, then retains a4,000,000-character Unicode/control string inside nested additive metadata. External1ms RSS observations cover publication only; token counting occurs afterward and is excluded from those observations. Actual encoded largest token is**12,000,002characters**,22pieces total, complete report12,000,076bytes; baseline and candidate files compare byte-for-byte, SHA256 `'''+large['sha256']+'''`. This demonstrates why streamed pieces do not provide a hard memory ceiling for individually large tokens. No latency measurement is claimed for this probe.
''')
large_rows=[]
for label,x in large['samples'].items():
 large_rows.append([label,mib(x['ready']['import_memory']['VmRSS_kib']),mib(x['ready']['ready_memory']['VmRSS_kib']),mib(max(p['VmRSS_kib'] for p in x['rss_samples'])),mib(max(p['VmHWM_kib'] for p in x['rss_samples'])),mib(x['publication']['after_publication_memory']['VmRSS_kib'])])
table(['Version','Import RSS MiB','Document-ready RSS MiB','Sampled publication max MiB','Observed cumulative HWM MiB','After-publication RSS MiB'],large_rows)
add('''The68KiB observed peak difference is small relative to the same token's allocation in both versions; one fresh process per version and sampled RSS do not establish a worst-case bound. Public encoder traversal/circular-detection state remains proportional to nesting; the chosen candidate adds no aggregate token list, index or full encoded report copy. Individually large encoded tokens and their UTF-8 encoding/buffering remain possible allocations. Raw1ms observations and source paths are in `large-token-memory.json`; these are separate from the main benchmark worker/client arrays.

## Self-review and handoff limits

Self-review checked exact public encoder defaults and3.9/3.12 bytes/errors; the unchanged shared atomic publication scaffold and cleanup; same consumer aliases; unchanged full raw engine/web source, defaults and response bytes; no publication/no-op/transaction/replay/lifetime/ACK bypass; no runtime test-only hooks or experimental aggregation. Production diff is the single encoding expression plus three explanatory comments. Test/harness changes are scoped to this owner and truthful separate measurement. Complete content preservation is supported by golden/stdout expected bytes, actual route/engine/render/fresh-reopen regressions, full deterministic report expectations, cryptographic whole-file hashes and remaining physical-file byte comparison.

Adoption is limited to measured local changed-report publication benefit18.37–23.12% with acceptable observed RSS, not a general JSON performance claim. The retained100k no-op median regression, uncontrolled shared-host activity, five samples/cell, warm filesystem caches, loopback Cheroot, no load/concurrency/inference/media, cumulative/sampled rather than allocation-traced memory, and Linux/WSL-only platform evidence remain explicit review concerns. Fewer Python calls are not fewer syscalls. Atomic replacement and directory durability/platform limits remain the unchanged helper's documented limits.

Final post-timing commands were prepared3.12 `python /tmp/openscrub-task632/large_token_memory.py` and `python /tmp/openscrub-task632/check_evidence.py`, each exit0, writing `large-token-memory.log/json` and `committed-evidence.log/json`. No final latency/suite/build/browser repetition followed stable successful evidence. The supervisor owns independent review and any future publication; this implementation does not imply assembled-application or umbrella approval.
''')
(DOC/'task-632-report.md').write_text('\n'.join(lines))
pr=f'''# Stream readable report publication through the public encoder iterator

Changed review saves still publish the complete readable report atomically, but `json.dump` dispatches one Python staging-stream write per JSON piece. Consume the same public `JSONEncoder(indent=1).iterencode` iterator through `writelines` in the existing shared owner. Preserve readable bytes/default encoder errors, private staging, flush/fsync/close/replace/cleanup and all caller/transaction/no-op contracts.

Exact base `{base}` → head `{head}`. A bounded10k stdlib comparison favored direct writelines over equally fast65536-target aggregation because the direct candidate needs no token-list buffering. Pinned, uninstrumented real HTTP comparison (10k/100k; sparse/bulk;3warmups/5alternating recorded samples) reduces changed-save medians18.37–23.12%. Separate counts still show one complete encoding/stage/fsync/replace per change and zero publication for no-ops. Actual expected complete reports and byte/hash verification are retained.

Validation:168focused,456full discovered and159actualPython3.9 affected cases pass; exact readable/error/atomic fixtures; actual engine writer/render/fresh reopen; offline sdist→wheel/exact package/defaults and installed CLI/Cheroot smoke pass. Main108HTTP200 plus6tiny counted smoke. All127frozen blobs match clean final commit. No JS/response change or broad browser rerun.

Measured limits:100k no-op median regresses9.97% (1029.429→1132.037ms); retain full spread and do not infer its cause from unchanged skip/counts. Sampled100k peak RSS is+108KiB sparse and−3652KiB bulk; a separate12-million-character-token probe is+68KiB, with no hard token-memory bound. Shared-host scheduling/storage, five samples/cell and cumulative/sampled RSS limit conclusions; fewer Python calls are not fewer syscalls. All failures and exact commands/source inventories/raw samples are in [task-632-report.md](task-632-report.md) and `/tmp/openscrub-task632`. Independent review pending; no publication.
'''
(DOC/'task-632-pr.md').write_text(pr)
# Preserve hashes of human-readable handoff and all task scripts/logs; raw worker
# outputs and source inventories are referenced in results, not duplicated here.
manifest={str(p.relative_to(ART)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ART.glob('*') if p.is_file() and p.name!='handoff-manifest.json'}
manifest['task-632-report.md']=hashlib.sha256((DOC/'task-632-report.md').read_bytes()).hexdigest();manifest['task-632-pr.md']=hashlib.sha256((DOC/'task-632-pr.md').read_bytes()).hexdigest()
(ART/'handoff-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Wrote task-632-report.md and task-632-pr.md; base',base,'head',head)
