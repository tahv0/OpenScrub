# Task654 compact evidence

Final source: `00480c7e42ddb329f4dde9599c256555f2dabcf0`, reviewed core base `117e41ac5ee857a6b367caf6ccbd479d78989ff2`. See [full report](../task-654-report.md) for behavior, truthful revision limits, every material failure and remaining platform/controlled-stub limits.

- [commands.md](commands.md) and [commands.json](commands.json): exact forwarded verification argv, real exits/results and each attempt's source/test pins. All17 verification invocations are retained, including supervisor initial preflight. Earlier config filenames evolved; per-run preflight/generated runtime configs bind their actual attempts.
- [source-identities.json](source-identities.json): final96 source/test/recipe hashes and selected package parent/leaf mapping.
- [assembly/](assembly/original-to-composed.json): seven exact original-to-composed `-x` mappings, all15 local commits, original conflict inputs, applied patches and actual cumulative resolution.
- [fixture-identities.json](fixture-identities.json) and `fixtures/`:69 exact old/new fixture snapshots across all meaningful source/test revisions. Missing files before their introduction are intentional.
- `runs/`: complete compact preflight/runtime manifests, owning logs (including failures), scoped child stdout/stderr, browser JSON and screenshots. No media, environment, installed/extracted/export/build trees are copied.
- `adapters/`: exact task-specific browser-directory creation, source/installed audit, source freeze/evidence collector and listening adapter. The stdout adapter is an unchanged copy of the reviewed Task16330 exact-child adapter.
- [package-identities.json](package-identities.json), [installed-audit.json](installed-audit.json), [environment312.json](environment312.json), [environment39.json](environment39.json): actual package membership/identities, source/installed default/PAGE agreement and distinct interpreter dependency versions.
- [self-review.json](self-review.json) and [static-recipes.json](static-recipes.json): clean source/unchanged core ref, helper identities, final runtime bytes and exact single-line runtime delta after the earlier floor selection. Docker/frozen/updater ownership is static inspection only.

Every allocating invocation used bounded external development admission. Private local code/config/state/policy/receipts are intentionally outside this archive. Prepared tools and shared verification launcher were unchanged. No timing, benchmark or full discovered suite was rerun, and no user data or upstream state was changed.

The17 runs retain: two genuine subtree regression failures→passes;346pass/9fixturefail and47pass/7fixturefail attempts→narrow fixes; actual3.9 355pass; one separate genuine phase-actions regression→37pass on each interpreter; browser9setupfail/1pass→8pass/1fixturefail→1paused-clock fixturefail→1pass; two source audits; and one final offline package/listening gate. The report identifies exact revisions rather than combining these into a fictitious final broad run.

The first browser setup's missing output directory masked six child startup outputs; all available parent diagnostics and raw library-launch failure are retained. The initial filename fixture's CalledProcessError did not expose child stderr; its complete parent failure remains. No such lost output is described as a successful check.
