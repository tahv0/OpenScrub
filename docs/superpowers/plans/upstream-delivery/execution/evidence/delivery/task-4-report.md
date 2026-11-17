# Task 4 / P04: bounded recent-stage ETA

Long scans' early speed biases the previous whole-stage ETA long after throughput slows. This focused change makes server ETA follow recent stage progress. In a controlled 600-second fast prefix followed by a 180-second slow tail, upstream reports **476 seconds**, while this estimator reports **3,823 seconds** with **3,820 seconds** remaining at the synthetic tail rate. This compares estimators; it is not an inference-speed benchmark or a promise of prediction accuracy.

- Branch/worktree: `pr/recent-stage-eta`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
- Exact base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
- Exact committed head: `d129e23e5fe144edb8bbd5675809c1877cfe4d0f`.
- Commit: `Estimate stage ETA from bounded recent progress`.
- Worktree clean after commit; no publication or upstream acceptance claimed.
- Donor provenance only: `0b2e3d1d8ec702bfa1a3a26e2c278f15b3bc69aa` (recent-rate idea), `367148d54efaef7e49498d96ef17507f38408f64` (0.35/0.65 smoothing). Only callback ETA hunks were consulted; diagnostics and preview/cache changes were excluded.

## Result and scope

`WebCallbacks` owns the new state and constants. Throughput uses `time.monotonic()`, with a 120-second window, samples at least 5 seconds apart, and at most one predecessor before the cutoff to measure the crossing interval. Whole-stage startup requires at least 3 seconds and positive counter movement. A recent observation span of at least 20 seconds takes precedence, including when it has zero movement; a stalled mature window publishes `None` instead of reviving the historical average. Estimates use 0.35 previous / 0.65 new smoothing. Unusable/nonfinite observations or rates cannot publish negative/nonfinite ETA.

Stage change, completion, and counter regression reset samples and smoothing. Tracking the last counter separately catches regression between retained samples. A fresh worker attempt creates a fresh callback. The existing worker's terminal cleanup remains unchanged and is tested for done, cancellation and error.

Preserved: scan `(0, 0.45)`, post `(0.45, 0.05)`, render/other `(0.5, 0.5)` mapping; five-decimal public progress; callback signature; nullable public ETA seconds; `job_public`; client fallback and rendering; all inference, scheduling, defaults, dependencies and version. Unavailable totals use the existing **numeric zero sentinel**, as confirmed by the supervisor; `None` inputs were not added to the callback API.

Changed files:

| File | Change |
| --- | --- |
| `openscrub_web.py` | Private bounded estimator state, monotonic calculations, reset/finite guards; correct the UI comment from average to recent rate. |
| `tests/test_scan_eta.py` | 25 actual callback/worker cases with fake monotonic and independent wall clocks. |
| `pyproject.toml` | Minimal discovery of existing root suite plus `tests/`; include tests and contributor guidance in sdist. |
| `README.md`, `CONTRIBUTING.md` | Run the complete discovered suite with `python -m pytest`. |

## Controlled timeline

Total is 10,000 units. Callbacks arrive every 5 simulated seconds. Progress is 10 units/second through t=600, then 1 unit/second. `/tmp/openscrub-task4/timeline.py` executes the actual base callback class extracted from Git and the active changed callback against the same observations. The base is not rewritten or approximated.

| Elapsed seconds | Counter | Upstream ETA seconds | Recent ETA seconds | Remaining at 1 unit/s |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | null | null | — |
| 5 | 50 | 995 | 995 | — |
| 20 | 200 | 989 | 983 | — |
| 600 | 6000 | 415 | 403 | 4000 |
| 630 | 6030 | 411 | 495 | 3970 |
| 660 | 6060 | 423 | 673 | 3940 |
| 720 | 6120 | 450 | 2581 | 3880 |
| 725 | 6125 | 452 | 3422 | 3875 |
| 780 | 6180 | 476 | 3823 | 3820 |
| 900 | 6300 | 523 | 3703 | 3700 |

The 120-second window smooths bursty frame costs but takes roughly a full window to discard the fast prefix. The 5-second sampling interval bounds history to at most 26 retained samples (including the crossing predecessor), tested across 10,000 simulated seconds. Sparse callbacks can make the single crossing predecessor older than 120 seconds. The 20-second threshold avoids immediately extrapolating short recent intervals; 3-second startup provides an earlier whole-stage estimate. The 0.65 new-estimate weight responds faster than upstream's 0.25. As in the donor, smoothing is applied per callback, so its effective responsiveness also depends on callback cadence.

## Verification and actual commands

All generated scripts, logs, build output, runtime fixtures and screenshots for this task are under `/tmp/openscrub-task4`. Existing prepared environments/tools were reused, with no global installs or dependency/version edits.

Commands below run from the worktree unless another directory is specified. Python 3.12 commands source `. /tmp/openscrub-baseline-20261116/env-opencv4.sh`. Python 3.9 commands source `. /tmp/openscrub-python39-20261117/env.sh`. Explicit import assertions confirmed `openscrub` and `openscrub_web` came from the active worktree, with Python 3.12.16 and Python 3.9.25 respectively.

| Check | Actual command / evidence | Result |
| --- | --- | --- |
| Controlling RED | `python -m pytest tests/test_scan_eta.py -q -o cache_dir=/tmp/openscrub-task4/pytest-cache`; `red.log` | 1 expected failure against upstream: `3815 <= 476` fails for slow tail. |
| Extended RED | Same focused command, `red-all.log` | 15 failed / 9 passed, including expected unsupported behavior. This exploratory run also exposed a missing `name` in the worker test fixture, corrected before GREEN. |
| Stabilized focused GREEN | Same focused command, `green.log` | **25 passed in 0.06 s**. |
| Full discovered suite, once after stabilization | `python -m pytest -q -o cache_dir=/tmp/openscrub-task4/pytest-cache`; `full.log` | **159 passed in 56.03 s**, no failures. |
| Active-source Python 3.9 floor | `python -m pytest tests/test_scan_eta.py -q`; `python39.log` | **25 passed in 0.08 s**; active imports asserted separately. |
| Isolated offline sdist→wheel | `PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PIP_CACHE_DIR=/tmp/openscrub-task4/pip-cache python -m build --outdir /tmp/openscrub-task4/dist`; `build-offline.log` | Built `openscrub-1.0.96.tar.gz` and `openscrub-1.0.96-py3-none-any.whl`, wheel explicitly from sdist, using cached hatchling 1.33.0. |
| Archive inclusion and exact source | `python /tmp/openscrub-task4/check_package.py`; `package.log` | Exact sdist copies of callback, old/new tests, pyproject and guidance; exact wheel callback; Python `>=3.9` preserved; tests stay in sdist, not wheel. 27 sdist / 17 wheel entries. |
| Extracted-source execution | In `/tmp/openscrub-task4/source/openscrub-1.0.96`: active-source assertion, then `python -m pytest tests/test_scan_eta.py -q -o cache_dir=/tmp/openscrub-task4/sdist-pytest-cache`; `sdist-focused.log` | **25 passed in 0.05 s**. |
| Isolated wheel install | `PIP_NO_INDEX=1 PIP_CACHE_DIR=/tmp/openscrub-task4/pip-cache /tmp/openscrub-baseline-20261116/bootstrap/bin/python -m pip install --no-deps --target /tmp/openscrub-task4/site /tmp/openscrub-task4/dist/openscrub-1.0.96-py3-none-any.whl`; `install-final.log` | Installed wheel into task-local target; did not mutate shared runtime environment. |
| Installed CLI/web | From `/tmp/openscrub-task4`, prepared 3.12 env: `python /tmp/openscrub-task4/check_installed.py`; `installed-smoke.log` | Both wheel-installed entry scripts `--help` exit 0 under 3.12; actual web entry starts, `/` returns emitted UI and no-store, `/api/jobs`, `/api/models/face`, `/api/model_status`, `/api/vault` all 200 JSON; clean server shutdown 0. |
| Timeline | `PYTHONPATH=$PWD:$PYTHONPATH python /tmp/openscrub-task4/timeline.py`; `timeline.log`, `timeline.json` | Actual upstream versus new callback values shown above. |
| Scope/whitespace review | `git diff --check`, final diff review, post-commit `git status --short` | Clean; only five intended files; no worker, polling, inference or preview behavior edits. |

Installed smoke uses `installed_entry.py` to run the wheel-installed console scripts with the prepared 3.12 interpreter and dependency environment. It asserts both module imports resolve to `/tmp/openscrub-task4/site` and substitutes a task-local synthetic profile in-process before import, so installed application data does not touch the user's profile. The installer itself runs from the already available bootstrap environment; this is not a claim of Python 3.14 runtime validation.

Focused cases cover startup, exact smoothing examples, steady rate, zero movement and mature stall, slow tail, 20-second maturity, crossing predecessor, repeated/subsample callbacks, independent backward wall-clock jump, between-sample regression, stage transitions and all mappings/precision, completion, fresh callbacks, zero/unavailable numeric totals, nonfinite inputs and overflowed estimates, bounded storage, plus real worker done/cancel/error cleanup and new attempts. External scanning/report loading is replaced only at the worker integration boundary; the callback, worker control flow and metadata are real.

## Browser QA

**Browser plugin not available** in this session; the brief explicitly authorized existing Playwright/Chromium fallback. The flow tested is: actual `/` page → click synthetic job → real job metadata from `/api/jobs/<id>` → emitted ETA text → transition from scan to render → completion. A temporary test-only route advances the real callback's fake monotonic clock; no production QA endpoint was added.

Server command: `PYTHONPATH=$PWD:$PYTHONPATH python /tmp/openscrub-task4/qa_server.py` after sourcing the prepared 3.12 environment. Browser command:

```sh
LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers node /tmp/openscrub-task4/browser.cjs
```

Local URL `http://127.0.0.1:18487/`, Chromium, desktop 1365×950 and mobile 390×844. Server and browser required the already-authorized local-process escalation due sandbox socket restrictions. Server stopped after QA.

| Check | Result |
| --- | --- |
| Identity / meaningful content | URL and `OpenScrub` title asserted; meaningful page content and job link present. |
| No overlay / screenshots | Desktop and mobile screenshots inspected; real progress bar, phase and ETA visible without overlay/clipping. Mobile ETA wraps legibly. |
| Interaction / actual metadata | Clicked job link; JSON from real job route exactly matches callback result; emitted refresh renders the values below. |
| Console | No JavaScript page errors. Four expected preview-image 404s because no synthetic video frames were generated; all recorded failed responses are preview URLs. No other final HTTP/browser errors. |

| Synthetic observation | Public ETA / progress | Rendered text |
| --- | --- | --- |
| scan t=0, 0/100 | null / 0 | empty |
| scan t=5, 10/100 | 45 / 0.045 | `~45 s left` |
| scan t=20, 40/100 | 35 / 0.18 | `~35 s left` |
| render t=21, 0/100, phase rendering | null / 0.5 | empty |
| render t=24, 3/100 | 97 / 0.515 | `~2 min left` |
| render t=30, 100/100 | null / 1 | empty |

Evidence: `browser-results.json`, `browser-final.log`, `server-fixed.log`, `scan.png`, `render.png`, `render-mobile.png`. Browser interval polling was stopped by the temporary harness after opening the job to exercise deterministic snapshots of the existing refresh consumer; P03 request-race behavior was intentionally not tested or changed.

## Tooling/harness corrections and limits

Initial temporary-script execution used an unavailable bare `python`; rerunning with available `python3` created the test, and the controlling RED then ran correctly in the prepared environment. An earlier pytest invocation before that creation collected no tests; it is not counted as RED evidence.

The first build with `--no-isolation` could not import hatchling; a normal isolated attempt could not resolve PyPI in the restricted network. The existing offline wheelhouse completed the full isolated build. The runtime environment has no pip or bare uv, so initial target-install attempts failed before installation; the existing bootstrap pip completed the local install. No tooling changes were committed. Archive extraction printed the standard future tar-filter deprecation warning for the locally built archive.

The first local web bind was denied by the sandbox; the authorized escalated server succeeded. Initial browser launch omitted its prepared shared-library directory (`libnspr4.so`); adding the supplied tools path fixed startup. The first browser run passed ETA assertions but exposed an incomplete temporary certificate-path override, causing `/api/certinfo` 500; the temporary harness was corrected to redirect every certificate path and browser QA was rerun. Final browser results contain only expected missing-preview 404s. These were harness/tooling corrections, not product regressions.

Self-review checked the estimator equations and concrete expected values, source/archive identity, exact unchanged progress expression, bounded predecessor pruning, monotonic owner scope, absence of new rate fields/threads/dependencies, and unchanged worker cleanup. Supervisor review is still independent and pending.

Estimation limits: stage ETA measures that stage's remaining units, not total end-to-end job time; future throughput changes, long pauses, callbacks that stop arriving and sparse observations can make estimates stale or inaccurate. The retained crossing interval and EMA intentionally trade responsiveness for stability. No background timer advances the estimator during callback silence. The existing browser fallback can independently estimate from progress when server ETA is null and retains its existing phase-based history behavior; this work does not redesign that consumer or introduce public stage metadata. Numeric invalid-input guards protect ETA only; progress input handling/mapping was deliberately preserved, including the pre-existing numeric input contract. Testing used Linux x86_64 and synthetic observations, Chromium only; no Windows/macOS, other-browser, GPU/real-model or prediction-accuracy claim is made.
