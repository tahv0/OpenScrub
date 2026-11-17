# Task 3 / P03 — bounded recoverable job polling

Status: implemented, self-reviewed, committed and independently approved; see task-3-review.md. No publication or nested agents.

- Worktree: `/home/tahv0/.codex/worktrees/c832/OpenScrub`
- Branch: `pr/resilient-progress-polling`
- Exact reviewed P07a base: `92124753736e287ac800af91f0ac96f3e96c01be`
- Exact head: `6ae212a35b094fc9466f1616afb2c5bb5c0497f8`
- Commit: `Keep job polling single-flight, bounded and recoverable`
- Worktree clean after commit. P02 `2ae3257` and first C01 batch `aa07a06` were not imported or altered. Base intentionally excludes both.
- Artifacts: `/tmp/openscrub-task3/`.

## Change and ownership

`POLL_CYCLE` is one logical metadata→incremental-log cycle, captured against existing `(CUR, VIEW_GEN)` and guarded by cycle object identity. Repeated ordinary `refresh()` calls coalesce onto the current promise. Every existing `ownsView` publication fence remains. Old completion/catch/finally paths cannot clear a newer cycle, update its status or schedule its timer. No new view generation or draft store was introduced.

`POLL` owns one chained timeout by timer-object identity. Success schedules the next cycle **900 ms after completion**; request duration therefore adds to the start-to-start interval. Failure delays are exactly **900/1800/3600/7200/10000 ms**, capped at **10000 ms**, resetting after success or new view. Each metadata/log helper request has a **15000 ms** deadline over fetch headers, HTTP-status handling and complete JSON consumption. A cycle can contain two requests, or an additional existing-route log fetch after a server-length reset; 15000 ms is a per-request bound, not a combined-cycle bound.

`pollJson` races the whole request/body promise against deadline and cancellation, requests actual AbortController abort and removes its own timer/listener in finally. Promise.race attaches rejection handlers to losing work. UI publication happens only outside that helper after cycle/view checks. Even a synthetic transport/body ignoring abort releases its logical caller; late success/failure cannot control current ownership. No claim is made that uncooperative underlying work is forcibly terminated.

Switch, same-ID reopen and successful current-job deletion clear the timer and invalidate/cancel the old cycle before a new view is admitted. Hidden/pagehide stop cancels polling. Visible/focus/pageshow/online wakes replace obsolete work with one owned immediate timer, coalescing event bursts. None of these paths calls a scan, retry-scan or render mutation. Global job-list/model/update/extras/tracker scheduling remains unchanged, including the independent loadJobs behavior.

Polling errors get their own `pollStatus` live region in the existing detail area, also present before the first metadata success. HTTP/JSON/network/deadline failures retain valid metadata/progress/log DOM and show bounded-retry feedback. Successful cycles clear it. Repeated identical text is not assigned again. Save/pending-draft status is separate. HTTP error objects and malformed metadata do not build an undefined job shell.

The existing `{from,lines,len}` log protocol remains unchanged. Cursor length is authoritative even with empty lines. Shrink clears stale displayed lines/cursor and, when necessary, immediately rereads the existing route at `from=0` within the current cycle. Initial display still shows the last400 lines; later append and prior stick-to-bottom/manual-scroll semantics are preserved. No new limit, retention or log API.

`AUTO_REVIEW` is a **phase eligibility/initialization token**, not view identity. An observed entry into review creates it; an observed exit invalidates it. `REVIEW_REQUEST` is a **review initiation token**, allowing a newer initiation, including deliberate done-phase Re-open review, to supersede automatic publication. Automatic results check both tokens plus existing view ownership. A slow same-phase result remains eligible across healthy polls. Observed review→done→review cannot revive the old result. Automatic fetch failure is caught and returns initialization to an idle/retryable state on the next successful poll. Detections are fire-and-forget outside metadata/log occupancy; no review-fetch deadline was added. Request-supersession/phase checks apply to the automatic publication path, preserving manual done-phase review behavior.

P07a save/audio/editor ownership, draft cleanup, loaded-choice overlays and ACK reconciliation remain intact. In particular, the value-equality enabled-choice ACK rule was **not modified**: a matching ACK can satisfy an equal submitted repeat; a newer opposite choice remains pending. No save/download/render deadline or downstream editor rewrite.

## Before/after schedules

| Controlled schedule | Baseline | Head |
|---|---|---|
| Hold metadata; invoke refresh twice and advance1800 ms | Multiple same-view cycles can publish out of order | One metadata request; held log then also excludes duplicate cycles; next cycle starts900 ms after completion |
| Hold same-view logs across two nominal ticks | Repeated from=0 responses append duplicate lines | One current log request, one append |
| Actual HTTP metadata or log sends headers plus first JSON byte; hold rest | Body owns caller indefinitely while interval admits others | No second logical cycle; at fake15000 ms show retry, request abort, retry at+900 ms and recover; late body cannot publish |
| Ignore-abort headers/body, then late success/failure | No bound/cancellation race | Helper releases at15000 ms, losing operation cannot update DOM/timer |
| HTTP503, malformed JSON or network failure, then success | Unhandled rejection or undefined shell | Controlled polling status; preserved good DOM; no pageerror; success clears status |
| Fail repeatedly | Unbounded interval attempts despite in-flight work | 900/1800/3600/7200/10000/10000; success resets900 |
| A→B→A, same-ID reopen, or delete while old work held | Existing view fence suppresses late successful cross-view result | Existing fence retained; additionally abort old work, no obsolete finally/timer effect, immediate usable new view |
| Initial405 rows; later server5/405→1→0 | Initial400 works, but empty shrink leaves obsolete cursor/content | Initial400 preserved; shrink refetches from0; empty0 clears authoritative cursor |
| Review detections held; next metadata done; then return to review | Old detections can insert into newer phase | Old token stays ineligible after exit/return; same-phase slow load still succeeds |
| Failed review initialization | Fire-and-forget rejection; phase transition trigger already consumed | Failure caught; next successful same-phase cycle starts a fresh initialization |
| Hidden then visible/focus/pageshow/online burst | No lifecycle ownership | Stop/abort while hidden; one immediate replacement cycle after burst; no mutations |

## Test evidence

Actual evaluated `APP_JS` is executed in Node VM, with startup I/O suppressed and request/clock/DOM boundaries controlled; no miniature polling implementation is substituted. Full evaluated `PAGE` is served in Chromium. Browser plugin was **not available**, so the explicitly authorized existing Playwright/Chromium fallback was used. Viewport1280×950. Full PAGE assertions cover title/nonblank content, actual progress/log/review/actions DOM, no unhandled page errors, expected versus unrelated console errors, and interaction paths.

Real-body browser cases use stdlib HTTP serving full shipped PAGE and delegate metadata/log JSON generation to actual Flask production routes. Headers plus first JSON byte are flushed before an independently held body gate. These are distinct from Playwright complete-response route gates used for other network/review/error controls. The head exercises both real metadata/log deadlines and real body cancellation on view switch. Gates are released; browser/pages/server are closed. Synthetic jobs only.

RED evidence:

- `red-node.log`: baseline emitted JS, **18 failed /2 passed**. Two passing controls were inherited behavior (delete view suppression and slow same-phase review eligibility); no claim that P07a lacked them.
- `red-online.log`: additional held-request online-wake regression failed before replacement cancellation was added.
- `red-browser.log`: full PAGE with pinned baseline APP_JS, first overlap assertion observed **5 requests versus expected1**. This baseline substitution was test-process-only; no baseline product checkout was mutated.
- Two test-fixture corrections during GREEN: authoritative empty fixture len0 correctly resets content (retention assertion now uses unchanged server length); wake request count includes both metadata and log. Browser clock was explicitly paused before fake-deadline boundaries. Hidden Advanced help was opened before clicking. These were harness fixes, not concealed product failures.

Stabilized final set (no subsequent product/test changes):

| Command/check | Result/artifact |
|---|---|
| Active Python3.12 imports asserted to native worktree | `source-identity.log` |
| `python -m pytest tests/test_job_polling_node.py tests/test_job_polling_browser.py tests/test_review_save_failures.py -q` | **84 passed**,16.41 s; `final-focused.log` |
| `python -m pytest -q` | **218 passed**,92.29 s; `final-full.log` (one stabilized broad run) |
| Python3.9 active-source assertion + applicable selection below | **86 passed /131 deselected**,13.45 s; `final-python39.log` |
| AST parse edited Python; joined scripts from evaluated PAGE then `node --check` | Passed; `evaluated-page.js` |
| `python -m build --no-isolation --outdir /tmp/openscrub-task3/dist` using prepared Python3.9 Hatchling | Full **sdist→wheel passed**; `final-build.log` |
| Existing uv install of local wheel `--no-deps --no-index --target /tmp/openscrub-task3/installed` for prepared3.12 interpreter | Passed; `final-install.log` |
| Installed `openscrub --help`, `openscrub-web --help` | Passed; `installed-cli-help.log`, `installed-web-help.log` |
| Installed actual Cheroot HTTP `/`, `/api/jobs`, metadata/log; no-store header; exact installed/source equality; sdist tests inclusion; wheel source equality | Passed; `installed-smoke.log`, `installed_smoke.py` |
| Installed evaluated PAGE joined-script `node --check` | Passed; `installed-evaluated-page.js` |
| Self-review and `git diff --cached --check` | Passed before commit |

Python3.12 used `/tmp/openscrub-baseline-20261116/env-opencv4.sh`; Python3.9 used `/tmp/openscrub-python39-20261117/env.sh`. Python3.9 selection: `python -m pytest tests/test_job_polling_node.py tests/test_review_save_failures.py test_openscrub.py -k 'test_job_polling or test_review_save or help_tip or box_editor or progress_eta or worker_watchdog' -q`. Both asserted exact active module paths;3.9 version asserted explicitly. Initial attempted no-isolation build in3.12 reported missing Hatchling; reused existing3.9 build environment instead. No toolchain, dependency, inference or model installation.

Browser env: `NODE_PATH=/tmp/openscrub-save-as-20261116/node_modules`, `PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers`, and that tree's existing `tools/usr/lib/x86_64-linux-gnu` prepended to `LD_LIBRARY_PATH`. `POLLING_ARTIFACTS=/tmp/openscrub-task3` records `browser-results.json`, `browser-summary.log`, `polling-review-preview.png`. **18 browser schedules**, all `pageErrors=[]`. Deliberately aborted requests yield expected Chromium `net::ERR_FAILED`; injected503 yields expected503 console diagnostic. These are recorded in `expectedInjectedConsole`. Independent review found a nonblocking precision gap: the filter accepts ERR_FAILED/503 signatures across all scenarios, so another failure sharing either signature could be misclassified. Scenario-specific diagnostic/count checks remain a test-readiness follow-up. No scan/render POST occurred on wake/retry. Austin help, enlarged detection preview and box-editor opening are exercised; P07a62 save/audio/editor tests are included in focused/full checks.

## Self-review and limits

Reviewed cycle/timer object ownership, cancellation before same-ID reopen, obsolete finally/catch effects, deadline listener/timer cleanup, status validation before shell construction, log-reset await fences, phase-token eligibility across slow same-phase and leave/return schedules, automatic-only request checks, and untouched ACK/audio/editor code. Corrected owning contributor verification guidance in CONTRIBUTING.md and CLAUDE.md from the old single-file test command to full discovered pytest; existing P07a Node harness only gained a window event-listener stub.

A JavaScript timeout is not a wall-clock guarantee while the process is suspended. Controlled hidden/visible and focus/pageshow/online events are lifecycle evidence, **not native OS background/suspension timing evidence**; no new CDP/native-suspension claim. An underlying request/body that ignores abort may remain alive after its logical owner is released. Detections fetch remains outside polling's deadline and may stay pending, while metadata/log polling continues. Independent global-list and other existing network failures/scheduling were not rewritten. No production throughput, latency tuning, cross-browser/native mobile suspension, or real-media inference claim. Independent task review approved with the console-accounting Minor above; combined integration remains a separate gate.
