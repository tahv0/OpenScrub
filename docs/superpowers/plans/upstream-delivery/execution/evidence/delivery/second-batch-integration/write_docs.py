from pathlib import Path
import subprocess,json,hashlib
repo=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');docs=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README');art=Path('/tmp/openscrub-task651')
head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
text=f'''# Task651 — second intermediate C01 assembly

Status: awaiting final benchmark and supervisor review. Exact base `aa07a0664ec0b9d3d592adba19e5e1e473e906ac`; head `{head}` on local `integration/upstream-focused`, native `/home/tahv0/.codex/worktrees/c832/OpenScrub`. This is bounded second-batch evidence, not whole-C01 approval, C02 adoption, an umbrella upstream PR or publication. The original checkout/product/data and individual branch refs were not edited. No remote commands, subagents, dependency/model installation, optional stack migration or platform build occurred. Artifacts `/tmp/openscrub-task651`; existing prepared3.12/3.9, offline build wheelhouse and Playwright/Chromium were reused.

## Provenance and conflict decisions

All exact declared picks retain `-x`:

| Original reviewed commit | Integrated commit | Contract |
| --- | --- | --- |
| 2ae3257b9752e2d976ff7a0d39955a13c133273a | da2ac2d1712eeb3d8490263ac00894b737dba1d2 | Explicit Blur/Keep choices |
| 6ae212a35b094fc9466f1616afb2c5bb5c0497f8 | 93a5e304299148e3926fe10a741e392109877ac2 | Bounded recoverable polling |
| 3457efac574d74a7d2377cbc0d44bb0b87462c3a | 686607e9b5554d9efa711587acfccb893c4eb022 | Unchanged report saves |
| a4f064f1b12cb0a22e5090d7fddfa3fc6055b5d7 | 4467a91c1d85cc251768bb18c48f7931f106eede | OpenCV core bound/diagnosis |
| a10e485962571a566f99225541735ab1ada1f4c0 | e29d5251bfd11a90bdd65b2948d2a52c39c984e2 | Runtime/wheel agreement for repair advice |

P02 and P03 conflict in shared contributor commands: retain complete root+tests discovery and Node18 prerequisite. CLAUDE full-discovery guidance retained. At P03's actual `refresh` intersection, keep all existing Save As helper functions, insert the incoming `refreshCycle`, set `EXPORT_NAMES` after successful guarded/validated metadata, and keep `renderExportProgress` plus incoming automatic-review retry initialization. The original view fences/cycle identity, draft/value ACK and export ownership are retained. P06C.1 packaging overlap keeps both CONTRIBUTING and benchmark entries. B02b private namespace add/add is equivalent docstring only; keep existing namespace docstring, recursive private-module packaging and all tests/discovery/benchmark entries. Both original B02b provenance commits retained. No merges/squashes.

A separate final integration commit contains only test/tooling corrections, no production/runtime correction:

- P03 Node VM lacked `performance.now`, now called by preexisting P01 progress rendering. Initial focused run: **15 failed/168 passed** (`initial.log`). Adding the VM's own controlled clock gives **21 passed** (`node-green.log`), with original assertions retained.
- P01's test extraction ended at `async function refresh()`, renamed by P03. First complete run: **21 failed/677 passed in139.69s** (`full.log`), all failures were `emptyEditor is not defined` from overextracting unrelated later JS. End extraction at the actual `refreshCycle` boundary. Affected set: **45 passed in4.53s** (`extraction-green.log`). No product function is stubbed or lifecycle guard weakened.
- P03 browser diagnostics now record actual injected kind+URL per scenario. Each warning/error must consume at most one matching injection in that scenario and exact URL. Healthy scenarios accept zero. Controlled diagnostics are reported separately; no global ERR_FAILED/503 suppression. Affected actual PAGE browser check passed (`poll-browser.log`,18 schedules in `polling-browser-results.json`).
- Benchmark trusted local Git extraction uses explicit supported `filter='data'` when available, retaining Python3.9 older-patch compatibility via capability check. Historical logs remain intact.
- Existing batch render test checks selected/kept pixels on all60 decoded frames and all report route indices/flags, extending its previous first-frame observation.

## Actual combined UI, persistence and media boundaries

Browser plugin not available (tool/skill discovery); prepared isolated Playwright/Chromium fallback, Linux only. Flow: actual emitted PAGE and real Cheroot HTTP → review/draft → polling failure/deadline/recovery → Save As → actual worker render → explicit mixed/zone setters → save/render → fresh browser and fresh interpreter HTTP reopen. No app implementation substitute. QA title `OpenScrub`, meaningful full content, zero framework overlays and page errors. Desktop1365x1000 and mobile390x844 screenshots inspected: readable paired controls, truthful mixed/group/zone state, retained save error beside completed export, no clipping found. Screenshots `browser-draft-desktop.png` and `browser-after-render-mobile.png`.

`serve_browser.py` creates synthetic60-frame160x96 clips. Alpha runs actual `_run_job`/`run_scan`, decoder/callback/report pipeline with only OCR creation/read controlled to one synthetic email word. `actual-scan.json` records it. The subsequent ordinary imported-report boundary is explicitly controlled: thirteen mixed person/track/singleton/zone rows from P02's synthetic fixture, precise geometry/timing, per-row additive data, audio spans/suggestions/transcript and additive provenance/state/top data. Detection accuracy is not evaluated. Beta supplies a deterministic4MiB download fixture, not valid video; actual alpha render output is separately decoded.

`browser.cjs` performs:

1. Deliberately clicks Blur on already-true row10 and holds delivery of the actual successful HTTP acknowledgement. Exact report bytes/inode remain unchanged; publisher was never called. Newer opposite Keep remains pending.
2. Starts actual Save As with a controlled picker returning a real OPFS writable. First write is held: accepted bytes remain0. Injects actual HTTP503 on metadata (server request header boundary), observes separate polling retry status while review-save status and draft remain. Holds actual HTTP headers+first body byte beyond shipped15s deadline, then observes retry and recovery. No duplicate log lines or draft clearing. Switches A→B, releases ACK, returns A: newer false draft survives and no render POST occurred.
3. Injects OSError at actual changed-save publisher. Real HTTP500 retains exact old report and pending false draft; no render. Completing OPFS writes yields4,194,304 accepted bytes and exact **whole destination bytes**, with status separate from polling. This is controlled failure injection, not real disk failure.
4. Restores stored true through explicit Blur and saves: no successful save publication occurs, yet ordinary actual render admission/worker/encoder/publication completes. The only publisher events are the deliberately failed save and actual render publication; skip does not block rendering.
5. Reopens review; deliberate repeated Keep on person group `[0,1,11]`, repeated Blur on track `[4,5]`, independent repeated zone-row8 Blur, and identified manual addition `batch651:replay`. Real save and render finish. All thirteen raw rows except intended enabled changes are deeply equal, all audio/state/top additive data remain equal; appended manual makes14. Identical identified replay appends nothing.
6. A new browser view requests real detections/report after render: indices0..13, all flags and full raw report match, grouped/zone feedback truthful. `check_output.py` decodes **all60 frames**; all14 region centers independently match saved choices (selected means0..1, kept176.33). This closes **P02's historical standalone13→8 after-render prerequisite on this combined P06D head**. It does not change or retroactively approve that standalone server branch.
7. `check_fresh.py` starts a fresh interpreter, rehydrates persisted jobs and serves actual HTTP. Complete14-row report equality, indices/flags, same-ID manual replay with exact bytes/inode retained, and owners released to0 pass (`fresh.log`). No live registry crosses processes.

Browser final result `browser-final.log`, `browser-results.json`: passed; page exceptions empty, exactly two controlled resource diagnostics (actual503 and publication500). No unrelated console warning/error. P03's18 affected browser schedules separately passed with scenario/URL accounting. Existing native keyboard/help/enlarged-preview/mobile-touch broader matrices remain the candidates' evidence; this batch does not repeat or expand all of them.

Harness attempts retained: initial browser helper's10s wait could not cover actual15s body deadline; increased only its bound to24s. A server restart first hit the still-running task process; stopped that exact process and reset only task-owned fixture flags. A later render-completion poll initially sampled old done before its POST was accepted; final helper **awaits actual render HTTP200 first**, then explicitly awaited HTTP phase polling, and separately observes real completed publisher events. This is distinct from Task631's prior truthy-async-predicate issue. No early-done lifecycle defect was demonstrated or patched. Task-only server stopped after validation.

## Verification evidence

Active3.12 setup: source `/tmp/openscrub-baseline-20261116/env-opencv4.sh`, `PYTHONPATH=/tmp/openscrub-task651:/home/tahv0/.codex/worktrees/c832/OpenScrub:$PYTHONPATH`, `PYTEST_PLUGINS=task651_isolation`. Plugin asserts active imports and redirects all runtime data to Task651. Python3.12.16/OpenCV4.14.0. Existing cached verified YuNet only; no new models. Audit-isolated3.9 uses `/tmp/openscrub-python39-20261117/env.sh`, Task651 copied `sitecustomize`/plugin and task-local TMPDIR/cache/config.

| Check | Observed result |
| --- | --- |
| Focused combined integration/review/poll/save/lifetime/transaction/replay/core | **376 passed in24.57s**, `focused.log`; includes bounded existing held-preview/cancel/retry overlap, full real scan/render/fresh-process report and1000-row save smoke. Nine-stream old schedule not repeated. |
| Affected P03 actual full PAGE browser helper | **1 passed in6.73s**, `poll-browser.log`,18 schedules; actual held HTTP bodies, controlled transport failures, recovery/phase/view fences, help/editor. |
| Amended P01+P03 VM extraction/clock | **45 passed in4.53s**, `extraction-green.log`. |
| Complete stabilized discovery | FINAL_SUITE |
| Python3.9 active-source focused set | **264 passed,2 skipped in25.06s**, `python39-final.log`. Skips were cached-YuNet fixture path absent in inherited floor isolation. `python39-amended.log`: **28 passed/60 deselected in2.18s**, covering all amended Save As checks plus all4 real face fallback/cache cases using existing verified cached model via explicit `OPENSCRUB_COMPAT_YUNET`; closes skipped coverage without downloading. |
| Final offline sdist→wheel | Exit0, `build-final.log`; Hatchling1.33.0, wheel explicitly built from final sdist. Refreshed because shipped extraction test changed; first build/log retained. |
| Package exact content/metadata/defaults | Exit0, `packaging-final.log/json`; exact10 wheel sources (all private helpers),20 focused test files plus root tests and benchmark/docs in sdist;3.9 grammar/metadata, JS syntax, expected sole core `opencv-python<5` delta, unchanged defaults/routes, no removed-system imports. |
| Installed CLI/web/HTTP | Exit0, `installed-startup.log/json`: actual installed CLI help, web entrypoint/Cheroot homepage/jobs, vault setup/lock/refusal/unlock, allowlist recovery and idle SIGTERM0. Final wheel SHA is byte-identical to the initially installed wheel, so source-corrected sdist test change needed no redundant reinstall. |
| Installed stdlib compatibility helper/read-only consumers | Exit0 on both3.12 and3.9, `installed-compat.log`, `installed-compat39.log`; installed paths/bytes asserted, real normal4 capability, actual setup --check and standalone core check, controlled mismatch/positive agreeing controls, zero pip/network. |
| Self-review/frozen source | `self-review.json`, `verification-source.json`: engine byte-identical base, reviewed no-op route exact AST, unchanged base lifecycle/work/preview routes, corrected helper exact bytes, core consumers/declarations exact candidate bytes; diff check clean. Final committed-byte/package checks below. |

Python3.9 checks are active-source focused runtime plus package grammar/floor metadata, **not whole-app floor certification**. First floor attempt lacked the copied plugin and failed before collection; plugin copied into task-only harness. No successful broad matrix was repeated without a concrete source/test change/failure. Source/test manifest frozen before final suite/build.

## Largest-report interaction measurement

BENCHMARK_PENDING

## Scope and limits

Reviewed defaults remain `auto/auto/auto/blur/8/tight/archival`; engine source exact base. No no-op routing shortcut bypasses admission/fresh parse/vault/busy/deleting/conflict: reviewed route exact AST and lifecycle/transaction/replay focused/full checks retain those gates and release paths. Core source/built declarations match corrected Task91; reuse its named Linux3.12/3.9 metadata-only resolver evidence when declarations unchanged, no fresh resolution. Optional Paddle coexistence, alternate/source-built environments, Windows/macOS/frozen/container/GPU validation, Safari/Firefox/native picker dialogs, inference accuracy, physical-disconnect replay, audio-output waveform, output-video atomicity, general long/4K/performance claims remain outside this gate. No claim of untouched-feature speed improvement.

Self-review found only the documented fixture/tooling corrections; product corrections beyond actual conflict preservation: **none**. Supervisor reviews entire exact base→head independently. Final whole-branch/C01/C02 remain open.
'''
(docs/'task-651-report.md').write_text(text)
(docs/'task-651-pr.md').write_text('''# Local Task651 second-batch integration draft

Explicit Blur/Keep choices, resilient polling, no-op report saves and corrected core compatibility diagnosis are assembled on the reviewed first batch. Review drafts survive polling failures and newer edits; unchanged saves skip publication while preserving actual render/lifecycle admission. P02 choices now survive post-render P06D reopen with every raw row/index and audio/additive fields intact.

Five exact reviewed commits retain `-x`, including both B02b commits. Only overlap resolution plus separately described fixture/tooling corrections follow. Validation and exact base/head/provenance, real browser/media/package/floor evidence and one100k interaction measurement are in task-651-report.md.

Local intermediate C01 draft only. No remote PR/publication, umbrella upstream PR, final C01 approval or C02 adoption. Supervisor independent base→head review required.
''')
(docs/'task-651-acceptance.md').write_text(f'''# Task651 batch acceptance draft

Exact base `aa07a0664ec0b9d3d592adba19e5e1e473e906ac`; exact head `{head}`. Second local intermediate C01 assembly on `integration/upstream-focused`; supervisor review pending.

- Five declared reviewed `-x` picks, both Task91 provenance commits, original candidate refs intact.
- Actual PAGE/HTTP newer draft through503/held-body deadline/recovery and switch, failed real publication, accepted-byte Save As and no-op save→actual render pass.
- Repeated explicit mixed-group and independent zone choices survive actual render and fresh browser/interpreter HTTP reopen: all14 rows/indices, raw metadata, meaningful geometry/audio/additive data, manual replay ID preserved. All60 frames'14 selected/kept region centers match choices. This closes P02's historical standalone after-render13→8 prerequisite for the combined P06D head.
- Transaction/lifetime/cancellation/streaming/vault/fresh-parse/conflict gates retained, bounded overlap and focused/full checks recorded.
- Complete suite/floor/package/installed checks and exact one100k benchmark evidence: see task-651-report.md; final results pending here until benchmark finishes.
- No C02 adoption, final whole-C01 approval, umbrella upstream PR or publication. Optional/platform/detection/long-media limits remain explicit.
''')
print('wrote requested drafts')
