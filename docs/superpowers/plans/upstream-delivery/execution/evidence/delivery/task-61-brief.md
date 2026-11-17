# Task 61: P06A atomic report publication

## Global constraints

Preserve upstream defaults, report compatibility, entry points, existing face margins and job/vault lifecycle. New tests go in `tests/`. Every PR runs the existing suite and full build plus its own tests. Research probes are not production regressions. Package a new runtime module in every applicable distribution in the owning PR.


## P06 — report correctness and measured save cost

**What:** Separate atomic publication, overlapping-edit preservation and serialization performance into reviewable changes.

**Why:** R05/R06 show concrete correctness problems, while the original fork throughput explanation does not directly describe upstream. A correct report is more valuable than merely acknowledging the request sooner.

**When:** Begin regressions in W1, deliver in W2 as ready. P06A/B/C are potential separate PRs within the P06 family. P06C is conditional on measured benefit. P07 may follow the shared transaction contract.

**Files / contract:** `job_save_edits` and all actual report writers it can overlap; `tests/test_large_report_io.py`; `benchmark/review_io.py`. Keep a one-owner helper local initially. When shared, use `openscrub_internal.reports.atomic_report(path, report) -> None`: same-directory publication, raise on failure, never acknowledge incomplete persistence. A per-job transaction covers **read → apply → publish**, not just the final write. Do not introduce a database, training fields or a general repository layer.

**B03 extraction follow-ups:** Include ordinary tracking publication in the writer inventory: mixed section donor `08f432b` reloads the latest report before appending tracked rows, but allocates a track ID earlier, so collision/revision tests still matter. Also reproduce scan → Keep some detections → render → reopen: training donor `db9a142` restores original review rows after rendering, while upstream's load/render/write path may discard disabled rows and stable indices. Preserve that generic requirement under a separate report-round-trip fix if confirmed; do not import `learning_session` to obtain it.


### P06A — atomic report publication

**What / why / when:** Prevent an interrupted write from replacing a valid report with partial JSON; first P06 correctness PR after the full handler reproducer exists.

- [ ] **E/I:** Port the probe into real Flask/HTTP tests `test_failed_report_write_preserves_previous_bytes` and `test_save_acknowledges_only_after_publish`. Inject encoding, write, flush and replace failures; assert the previous report remains parseable/unchanged where publication has not succeeded, and the client sees failure.
- [ ] **I:** Implement same-directory temporary writing, explicit flush/fsync policy and replacement with cleanup. Preserve existing report fields and deterministic JSON meaning. Document Windows/filesystem limits; rename atomicity alone is not a blanket power-loss guarantee.
- [ ] **V/D:** Run `python -m pytest test_openscrub.py tests/test_large_report_io.py -q`, full build and restart/rehydration after injected failure. PR lead: interrupted review save should preserve the last complete report. Include the probe only as initial evidence; report actual route-test results.



## Supervisor scope and interfaces

This is a separate upstream branch based on Austin main, not on Save As. The dispatch will provide exact branch/base and any test-only prerequisite. Do not include P06B locking, P06C serialization/no-op optimization, P07 replay/browser changes or P06D render-round-trip retention in this patch. Their concrete baseline bugs remain intentionally separate.

Confirmed before evidence is in `report-baseline-research/README.md`, raw results and scripts in the same SDD workspace: real socket handler encoding/write failures corrupt the previous valid report. Use that as evidence, adapting minimal real-app regressions into tests rather than committing the whole research harness or instrumentation.

Source inspection found three report publication owners: engine `write_report` (openscrub.py), web `job_save_edits`, and web `job_track_object`'s background append. All use JSON indent=1; engine currently chmods its report to 0600 after writing. Scan/render invoke the engine owner. Introduce only a cohesive stdlib private helper `openscrub_internal/reports.py::atomic_report(path, report) -> None`, with `__init__.py`, and route these three publishers through it. This shared boundary is justified by real reuse and the user's module-structure requirement. No Flask/global job/model imports in this package.

Keep JSON meaning/fields and existing response behavior. Same-directory temporary file with a `.tmp` suffix (existing vault crash-cleanup convention), restrictive report permissions, flush/file-fsync before replace, close before replace (Windows compatibility), cleanup on failure; raise rather than acknowledge failed persistence. Document the durability boundary honestly; successful atomic replacement is not a universal power-loss guarantee. No broad config/model/batch-summary writer refactor. Tests must cover real route failure response and original bytes, failed encode/write/flush/replace, acknowledgement timing, clean first publication, temp cleanup, engine writer and background tracking publication. Verify readers observe complete old/new reports, not partial JSON; do not claim overlapping edits are solved before P06B.

Packaging belongs in this PR: include private package in Hatch wheel/sdist and each existing app image's COPY (`Dockerfile`, `Dockerfile.intel`, root `Dockerfile.cuda`—not docker/Dockerfile.cuda). PyInstaller should discover static imports; change hidden imports only if needed. Existing updater supports nested paths; verify inclusion/preserved-data behavior without rewriting updater. Test installed wheel/source startup and package contents. Record unavailable Docker/Windows hardware checks, do not claim them executed. Extend contribution test collection and sdist tests inclusion minimally on this independent branch (no test CI exists).

Use environment `/tmp/openscrub-baseline-20261116/env-opencv4.sh` and its synthetic isolation, with task-specific pytest/artifact locations. No models/training, user data, remote writes or subagents. Native-worktree writes may need escalation. Run focused RED/GREEN and meaningful failure tests, full suite/build and real synthetic engine report/render validation before local commit. Read source before editing; report a concrete incompatibility to supervisor rather than expanding scope silently.

Full report: `task-61-report.md`; PR title/body draft: `task-61-pr.md` under this SDD workspace. Include actual failure/restart/HTTP results, packaging evidence/limits, exact commands, tested SHA/env and self-review. Return concise status, commits, tests and concerns.
