# Task72 / P07b: retry-safe ordinary manual additions

A committed ordinary manual-region save whose HTTP response is lost used to append a duplicate when retried. Identified additions now persist their ID and immutable effective creation record in the authoritative report transaction. A retry acknowledges the creation while preserving all later indexed geometry, time and Keep/Remove choices.

- Prerequisites: reviewed Task622/P06B.2 report transactions and the existing P07a draft ownership, deep submitted snapshots and identity-and-value acknowledgement behavior.
- Exact base: `f2cdf4813c86296644911f3f0b09bfc56d3e03c5`.
- Exact head: `12919c96c6f7558136b50d7b4d85e5e6b62f1971` (`Make ordinary manual additions safe to replay`).
- Branch/worktree: `pr/manual-addition-replay`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`. The clean branch and exact base were verified before editing.
- Local implementation/testing/commit only. No publication, pushes, remote writes, dependency/version/default changes, models, system tools, user data or original-checkout product changes. No subagents/reviewers were dispatched. These requested handoff documents are in the original SDD workspace.

## Contract and implementation

`manual_id` is an opaque case-sensitive ASCII `[A-Za-z0-9._:-]{1,128}` string scoped to the logical job report. An omitted ID retains legacy append behavior, including equal geometry. Explicit null/empty/non-string/invalid IDs receive JSON HTTP400 while the ordinary edit gate is open. Different valid IDs always represent different creations.

The server derives `manual_creation` with exactly `t_start`, `t_end`, `cbox`, `aoff`; client-provided creation metadata is ignored. Existing `float` time normalization, default `t_ref=t_start`, fps/cum offset selection and truncating integer content-space coordinate conversion are retained. Raw fractional coordinates or reference times with identical effective creation fields compare equal. Identified creations require finite times/coordinates/offsets, four box coordinates and two offsets. Existing interval and box-extent handling is retained. Server-derived category/text/confidence/enabled/last_seen defaults remain unchanged.

Under the existing single per-job report lock, each request reads the latest raw report, applies supplied indexed patches in its private document, builds the identity lookup, checks replays/appends and publishes once. Matching ID+valid immutable creation is a logical replay: no append, no resetting current fields. Within-request repeated IDs follow the same rule. Different creation, multiple matching imported rows, or a matching row with missing/invalid immutable creation returns JSON HTTP409. Local indexed changes/new rows preceding that rejection are never published. Unrelated malformed legacy/additive metadata does not block ordinary edits; nothing is reconstructed, retroactively identified, migrated or deduplicated. No second lock, identity store or durable journal was added. Existing response shape and raw-document render publication remain unchanged.

The actual ordinary Add box producer creates one UUID after both clicks and time prompts complete. `crypto.randomUUID` is preferred; `crypto.getRandomValues` supplies a UUID-v4 fallback. Missing secure randomness reports through existing save status and retains drafts rather than submitting unidentified additions. Compatibility additions acquire an ID once on the original object before their first snapshot. Original `BE.adds` IDs survive draft storage/revisits and explicit API field mapping. Deep submitted copies and P07a identity-and-value cleanup remain intact. No MAN producer/editor, ID-to-index acknowledgement mapping, retry loop, save deadline, UI mode or persistence layer was introduced.

## RED → GREEN and controlled schedules

All evidence is under `/tmp/openscrub-task72`. Commands ran from the isolated worktree. Initial sandbox-only HTTP execution could not bind loopback (`Operation not permitted`); that was a tooling error, not the regression RED. Authorized local-socket execution then observed the actual defect.

1. `python -m pytest tests/test_manual_addition_replay.py -q -o cache_dir=/tmp/openscrub-task72/cache --basetemp=/tmp/openscrub-task72/red2-tmp`: **27 failed in0.95s** before implementation (`red2.log`). The actual Cheroot HTTP lost-response test persisted one addition, deliberately discarded the completed response and retried the identical JSON; expected2 total rows but observed3. The other missing-contract cases also failed. This deliberately discarded acknowledgement is not a physical transport-disconnect experiment.
2. After server implementation the same27 cases were **27 passed in0.82s** (`green.log`). The deterministic overlapping schedule pauses the first actual publisher while a second same-ID request waits on the real report owner; after release both succeed and exactly one row exists. Conflict schedules assert byte-identical report retention despite unrelated supplied indexed/audio changes and verify subsequent successful edits/lifetime release.
3. `python -m pytest tests/test_review_save_failures.py -k 'manual_id or secure_randomness' -q ...`: **3 failed,80 deselected in2.42s** before browser implementation (`js-red.log`). IDs were missing and the old implementation attempted a request instead of surfacing missing randomness. After implementation, combined existing save tests/new route tests were **110 passed in10.78s** (`js-green.log`). UUID generation, distinct IDs, retained IDs across failure/job revisit, secure-random fallback, explicit serialization and actionable missing-randomness behavior use the actually emitted JavaScript.
4. Expanded imported-record probing found a real oversized-integer conversion failure: **1 failed,8 passed,28 deselected in0.24s** (`imported-red.log`). A stored offset integer outside finite floating conversion returned500. The validator now treats that malformed stored record as the required409; all final cases pass.

The new route regressions cover actual HTTP persistence/retry; duplicate/concurrent/same-payload IDs; distinct IDs/equal geometry/case sensitivity; legacy no-ID appends; ID boundary lengths and per-report scope; incompatible reuse/atomic rejection; explicit invalid IDs; finite creation validation; missing/invalid/multiple imported identities; effective normalization/default reference time; untrusted incoming metadata; reference offset identity; and previously committed current indexed changes across repeated replays. Actual FileOwners, report locks, admission/lifetime owners and atomic publication are used, not an isolated route body or miniature save endpoint.

### Actual browser delayed acknowledgement acceptance

The browser plugin was unavailable as recorded in the brief. Existing Playwright/Chromium and runtime libraries under `/tmp/openscrub-save-as-20261116` were reused without installation. `/tmp/openscrub-task72/serve_browser.py` serves the actual app with synthetic6-second160×120 videos and real job identities/reports. `/tmp/openscrub-task72/browser.cjs` runs the shipped page in actual headless Chromium; no editor/save function is replaced.

Both successful-ACK and lost-ACK schedules passed (`browser.log`, full request/row evidence in `browser-results.json`):

1. Actual canvas mouse clicks and FROM/TO prompt responses complete an Add box draft `[20,20,60,60]`, times `[0,4]`, with its retained UUID. Save goes through real HTTP and real publication.
2. Only the browser fetch return is held after the real server response arrives. Ordinary `beScrub` GET loads the committed indexed row while the save is awaiting its acknowledgement. Actual pointer selection/move/corner resize, Apply times and Remove blur produce `[30,30,80,90]`, `[.5,5]`, `enabled=false`. Original addition creation remains unchanged.
3. Releasing the original acknowledgement removes only its unchanged creation; rejecting it with an explicit injected browser response-loss Error retains that creation. Both retain newer indexed maps. This is response-failure injection after real HTTP persistence, not a claim of real transport disconnection.
4. A distinct equal-geometry addition is created through the actual producer with another UUID. Retry sends current maps plus pending original creations; its real commit is also followed by injected acknowledgement loss. Server report contains exactly one row per ID, the original immutable record and the latest current edited/disabled values.
5. Switching to another real job and back retains the drafts/IDs. A further identical retry is acknowledged while a newer Keep choice is created. Exactly two intentional rows remain; no replay resets their current values, acknowledged creations clear, and the newer choice stays pending. No browser page errors occurred.

Initial QA harness attempts exposed fixture issues (renaming synthetic job IDs broke source ownership; canvas visibility needed image-size/scroll readiness; an invented switch target caused a404). The harness was corrected to use real job-directory IDs, real alternate jobs and actual rendered canvas readiness; these were not product defects or claimed passing results. The final two schedules pass without response/route substitutions beyond the explicit acknowledgement boundary.

### Actual render and fresh process

`test_real_render_and_fresh_server_process_preserve_creation_and_current_choices` creates a synthetic30-frame video, makes real HTTP identified additions and indexed decisions, admits/runs the actual render worker/encoder, and asserts full row order/choices/ID/creation/additive fields survive raw report publication. Decoded output is black at the current moved box and unredacted at the original kept region. A fresh Python interpreter rehydrates the persisted job/report, starts a fresh Cheroot server, and replays the captured original creation request over HTTP; total/order/report document remain unchanged. No live identity registry crosses processes. The same test runs on Python3.12 and3.9. Output pixel assertions sample the first frame; this task does not add a general renderer validation suite.

## Stabilized validation/build evidence

Product source was frozen after the imported-record fix, before the final focused/full/build/floor set. `/tmp/openscrub-task72/verification-source.json` records SHA256 for30 source/test/metadata files. `committed-bytes.log` confirms exact committed bytes equal that tested manifest and the installed engine/web/private helper sources; the branch is clean. No product/test changes followed the stabilized set.

Python3.12 setup:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH="$PWD:/tmp/openscrub-task72:/tmp/openscrub-baseline-20261116"
export PYTEST_PLUGINS=task72_isolation
```

The task-local plugin retains the existing no-model-fetch policy and redirects runtime data to `/tmp/openscrub-task72/runtime`. `imports.log` prints Python3.12.16 and active-worktree engine/web imports. OpenCV4-compatible environment and existing tool libraries were reused.

| Command / evidence | Actual result |
| --- | --- |
| `python -m pytest tests/test_manual_addition_replay.py tests/test_report_transactions.py tests/test_job_lifecycle.py tests/test_job_response_lifetime.py tests/test_job_source_allowlist_lifecycle.py tests/test_review_save_failures.py tests/test_report_roundtrip.py -q -o cache_dir=/tmp/openscrub-task72/cache --basetemp=/tmp/openscrub-task72/focused-final-tmp` | **239 passed in25.56s**, exit0; `focused-final.log`. |
| `python -m pytest -q -o cache_dir=/tmp/openscrub-task72/cache --basetemp=/tmp/openscrub-task72/full-final-tmp` | **394 passed in102.34s**, exit0; no failures/skips/warnings; `full-final.log`. One stabilized complete discovery run. |
| `TMPDIR=/tmp/openscrub-task72/build-tmp PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PIP_CACHE_DIR=/tmp/openscrub-task72/pip-cache python -m build --outdir /tmp/openscrub-task72/dist` | Exit0; `build-final.log`. Isolated Hatchling1.33.0, sdist then wheel from that sdist; existing offline wheelhouse only. |
| `python /tmp/openscrub-task72/check_packaging.py` | Exit0; `packaging-committed.log`/`packaging.json`: exact sdist source/tests and wheel source, every packaged Python file parses with3.9 grammar, actual emitted-JS Node syntax, unchanged CLI parser/source selection/settings/web defaults AST and project metadata, existing container/frozen inclusion. Final head recorded. |
| `/tmp/openscrub-baseline-20261116/bootstrap/bin/pip --python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python install --no-index --no-deps --target /tmp/openscrub-task72/installed/site-packages /tmp/openscrub-task72/dist/openscrub-1.0.96-py3-none-any.whl` | Exit0; only the built project wheel installed into task-local target; `install.log`. |
| `python /tmp/openscrub-task72/check_installed.py` | Exit0; `installed-startup.log`/`.json`: actual installed CLI help, unchanged CLI/web Austin defaults (`auto/auto/auto/blur/8/tight/archival`), actual Cheroot web entrypoint/homepage/jobs, allowlist and real vault lock/unlock/refusal, graceful idle SIGTERM0. Fresh task-local profile, no model downloads. |
| `node /tmp/openscrub-task72/browser.cjs` with existing `PLAYWRIGHT_BROWSERS_PATH` and existing library path | Exit0; actual Chromium two delayed/lost-ACK schedules passed; `browser.log`, `browser-results.json`. |

Python3.9 setup:

```sh
. /tmp/openscrub-python39-20261117/env.sh
export PYTHONPATH="$PWD:/tmp/openscrub-task72/py39-harness"
export PYTEST_ADDOPTS='-o cache_dir=/tmp/openscrub-task72/python39/cache'
export TMPDIR=/tmp/openscrub-task72/python39/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task72/python39/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task72/python39/config
python -m pytest tests/test_manual_addition_replay.py -q \
  --basetemp=/tmp/openscrub-task72/python39/audited-final-tmp
```

**37 passed in2.96s**, exit0 (`python39-audited-final.log`). `python39-imports-audited.log` asserts both engine and web resolve to the active worktree, records Python3.9.25, and verifies the retained task-local `sitecustomize` audit. The first floor run also passed37 cases but omitted that audit hook when copying the harness; the harness was corrected and the floor set repeated once under its outbound-network/write restrictions. No source change or full-suite repetition was involved. The complete suite and installed-wheel smoke are3.12 checks; only focused new cases and full packaged grammar were checked at the3.9 floor.

## Changed files and self-review

- `openscrub_web.py`: immutable finite creation validator; identified manual replay checks inside existing report transaction; UUID creation/fallback/error path; retained draft identity serialization.
- `tests/test_manual_addition_replay.py`:37 parameterized actual-route/runtime cases, bounded concurrency, real render and fresh-process HTTP replay.
- `tests/test_review_save_failures.py`:3 evaluated shipped-JS identity/fallback/error cases; harness secure randomness/assertion availability. Existing P07a acknowledgement and job/view schedules remain passing.

Self-review checked latest-read/lookup/append/publication stay under the reviewed single report lock; validation/conflict mutates only unpublished request-local data; all rejection paths release existing owners; identity lookup never compares or resets mutable current row fields; repeated payload IDs enter the lookup immediately; immutable lists are separately copied; unrelated malformed metadata is preserved; legacy normalization/append and exact success shape remain; UUIDs attach once before snapshots; explicit mapping retains IDs; P07a deep copies/identity+value cleanup and separate newer indexed maps stay intact. `git diff --check` passed before commit. The supervisor performs independent review after this handoff.

## Limits and scope boundaries

Replay is a logical creation no-op; unchanged report serialization/edited-state optimization belongs to P06C and was not implemented. IDs do not resolve stale indexed requests across replacement scans/reports. Browser reload still loses current in-memory drafts; server-side durable report replay is proven only when the caller retained the original identified request. No general report revision protocol, ID-to-row protocol, source-bound quad/tracker feature, P16C render validation, Findings/journal/sections workbench, training, database or dependency work was added. Runtime evidence uses synthetic small media, bounded schedules and sampled output checks; no performance or throughput claim is made.
