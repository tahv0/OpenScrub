# Task1202 evidence

Candidate `2c7f2530893cb2ecd20dfe7803b6301ea34f9f9f`, exact base `6ae212a35b094fc9466f1616afb2c5bb5c0497f8`. [Report](../task-1202-report.md) and [PR draft](../task-1202-pr.md) state behavior, results, failed attempts and limits. This directory contains compact recipes, identities, complete result records and logs; it excludes runtime/model/media/browser-profile/environment/build/install/source-export trees and generated callback payload bodies.

- `source-identities.json`: base/head/blob/SHA identities and clean candidate status.
- `package-identities.json`: sdist/wheel hashes, sizes, exact packaged source/test/private files and actual updater result.
- `artifact-identities.json`: emitted-JS parse artifact, existing copied model identity and raw measurement identity.
- `environment312.json`, `environment39.json`: actual interpreter/dependency versions, including different NumPy/pytest versions.
- `measurement-plan.json`, `premeasurement-hashes-original.json`, `premeasurement-hashes.json`: declaration, original/revised harness identities, final frozen17-file manifest. Original declaration/worker never ran; supervisor requested stronger output/source checks before grant.
- `measurements.jsonl`: all216 observations in declared order:192 timing observations including warmups, followed by24 allocation observations. No sample was discarded or rerun. No raw callback contents are recorded.
- `measurement-summary.json`: complete derived medians/ratios, absolute states, response sizes, separate allocation observations and budget flags. Append medians use five observed batches; main HTTP medians pool30 individual observed responses per mode/case. Median of five observation means is separately labeled.
- `bounded-browser.json`, `browser-results.json`, `browser-summary.log`: actual both-production-route bounded-history scenarios and complementary P03 schedule/deadline/review scenarios. Browser plugin unavailable; existing Playwright/Chromium fallback.
- `harness/`: copied executable recipes and guards. Paths deliberately retain assigned scratch/prepared-tool identities; these are evidence recipes, not product helpers.
- `logs/`: complete RED/setup-failure/GREEN/full/floor/package/installed/measurement outputs. Screenshots stay in ignored task scratch because media/runtime artifacts are excluded here.

## Commands and boundaries

Shared task root `R=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1202`; native `S=/home/tahv0/.codex/worktrees/c832/OpenScrub`. All pytest invocations were serial. Native commands source `$R/env.sh`, set task-local cache and unique `--basetemp`, and run from `$S`. Floor commands source `$R/env39.sh`. Local socket/browser operations used already-authorized sandbox escalation after the recorded loopback denial.

| Log | Command / result |
| --- | --- |
| `red.log` | `python -m pytest tests/test_job_logs.py tests/test_job_polling_node.py::test_new_contract_stale_clamp_replaces_and_advances -q --basetemp=$R/red`; two expected behavior failures on exact base. |
| `green1.log` | `python -m pytest tests/test_job_logs.py tests/test_job_polling_node.py -q --basetemp=$R/green1`;33 pass. |
| `thumbnail-red.log` | `python -m pytest tests/test_job_logs.py::test_thumbnail_and_tracking_callbacks_stay_with_their_job -q --basetemp=$R/thumbnail-red`; expected old-job ownership failure. |
| `focused2.log` | New store/Node/browser plus existing producer selection;48 pass, one fixture mutation error, two loopback permission setup errors. |
| `focused3.log` | Corrected fixture / socket escalation;49 pass, two Chromium shared-library loader failures. |
| `browser4.log` | Prepared browser library directory added to LD_LIBRARY_PATH; `python -m pytest tests/test_job_polling_browser.py -q --basetemp=$R/browser4`;2 pass. |
| `full.log` | `python -m pytest -q --basetemp=$R/full -o cache_dir=$R/cache/pytest`;244 pass in95.06s. |
| `floor39.log` | `python -m pytest tests/test_job_logs.py tests/test_job_polling_node.py tests/test_job_polling_browser.py test_openscrub.py -k 'job_logs or job_polling or web_worker or watchdog or bad_web_settings or plate_threshold_exposed or phrase_category_wired' -q --basetemp=$R/floor39 -o cache_dir=$R/cache/pytest39`;53 pass /129 deselected. |
| `split-read-control.log` | `$R/split_read_control.py`, isolated cwd/PYTHONPATH to exact archived base, explicit configure; events force real append between actual `job_public` slice/len reads and prove tail1/next2 mismatch. No sleeps/timing inference. |
| `build-tools.log` | Actual3.12 `python -m pip install --no-index --no-deps --target $R/build-tools /tmp/openscrub-task620/build-wheelhouse/*.whl`; cached tools only, bootstrap supplies pip while task guard remains active. |
| `build-sdist.log` | `python -m build --sdist --no-isolation --outdir $R/dist $S`; succeeds. |
| `build-wheel.log` | Extract sdist under `$R/extracted`, then `python -m build --wheel --no-isolation --outdir $R/wheel $R/extracted/openscrub-1.0.96`; succeeds. |
| `package-check.log` | `$R/package_check.py`; exact runtime/private/test bytes, Python floor and real updater nested delivery verified. |
| `install-wheel.log` | Cached/bootstrap pip `--no-index --no-deps --target $R/installed/site-packages` exact built wheel. |
| `installed-cli.log`, `installed-startup.log`, `installed-http.log` | Installed-only PYTHONPATH and `TASK1202_INSTALLED=1`; `installed_entry.py` asserts imports/hashes/defaults before generated CLI/main. `installed_http.py` launches actual installed web main/cheroot and queries loopback page/metadata/log. Server exit0. |
| `installed-tests.log` | Extracted sdist's three owning test files, strict installed source target, `$R/installed-tests` basetemp;48 pass. |
| `js-parse.log` | Evaluated PAGE script extracted after source assertion; `node --check $R/evaluated-page.js` succeeds (empty output). |
| `docker-static.log` | Exact application install line matched; all three private-package COPY paths precede it. Static inspection only. |
| `measurement-driver.log`, `bench-processes.log` | Root-granted exclusive run `python $R/bench_driver.py`; exactly192 timing then24 allocation observations; final frozen-manifest check, no failures. Full process logs contain source assertion records and complete scalar observation results. |
| `measurement-summary.log` | `python $R/summarize_measurements.py`;216 records verified and summarized without selecting samples. |

Standalone benchmark/control scripts explicitly call configure and run under task-local sitecustomize. Installed entrypoint runners assert installed identities and leave the real task-profile defaults in place; pytest plugin configuration alone is not represented as standalone isolation. Node inherits task-local TMPDIR/XDG paths before Playwright starts. Source/base/floor/installed imports and hashes are printed in owning logs. Auxiliary metadata-name / exploratory Docker-print corrections are described in the report and did not alter runtime code or require equivalent suite repeats.

No Docker image, native Windows/frozen or GPU execution claim is supported by these artifacts. No p95, browser/global memory or faster-append claim is supported. Root independently verified the raw record structure/medians and ruled to retain the original limits after the exclusive slot was released.
