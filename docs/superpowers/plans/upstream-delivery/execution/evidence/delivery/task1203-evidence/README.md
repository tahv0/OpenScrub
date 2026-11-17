# Task1203 evidence

Exact base2c7f2530893cb2ecd20dfe7803b6301ea34f9f9f → candidate 4670641cb8e53e6daa6f77fb505397bfdb6733b8. Runtime web04af11cce1eaf4be0dc157ba5b4d78783a85bcbbb17596078c75d9df79f46c93; unchanged leaf63d08c124db019b120bb17efc64706d910f1d831f8ccfd9c1ba124368643d1b8. Full report: `../task-1203-report.md`.

This directory excludes media, browser screenshots, environments, model/cache/profile/job trees, installed packages and base/source exports. Those stay in ignored task scratch. Browser screenshots were inspected at1280×950 and390×844 with the actual log visible. No user callback content is present; all fixtures are synthetic.

## Identity and revision boundaries

- `source-identities.json`: base/final Git blobs, SHA-256 for all11 final changed files, unchanged runtime modules, and explicit full/calibration versus final test/portable recipe revisions.
- `package-identities.json`: exact sdist/wheel sizes/hashes and source-byte equality for runtime/private modules/tests/README/portable recipes; actual source updater output (34 files).
- `js-identity.json`: actual evaluated PAGE script118,533 bytes /SHA2562bfd1938…; Node parse accepting log.
- `environment312.json`, `environment39.json`: actual interpreter and dependency versions.
- `premeasurement-hashes*.json`, `measurement-plan.json`: source-only pregrant refinements plus final explicitly granted21-file manifest abeb6594…. No earlier recipe ran before grant. Declaration c1007da8… remained unchanged through the measured phases.
- `harness/measured_browser_logs.py` /`.js`: exact measured recipes (617b64b… /9d7e49c…), with task-local guards/env files. `harness/measured_test_browser_log_retention.py` is restored byte-for-byte and SHA-verified91540d4…: it binds full250 and calibration, not final tests.
- `harness/portable_*`, `portable-setup-manifest.json`: final shipped portable recipe/helper/recomputation bytes and non-timed setup manifest. Final owning testdfc32a0… binds strengthened6, floor59 and installed54. These delivery/test changes did not change runtime or repeat timing/full discovery.
- `browser/*.json`, `installed-browser.json`: actual PAGE scenarios, production-route requests and native browser layout/copy results. Final browser artifacts come from installed owning verification with exact same runtime/tests. Controlled lifecycle is explicitly distinct from failed native capability probes.

## Complete calibration data

Four lossless `measurement-{base,candidate}-{timing,instrumentation}.json.gz` files retain every raw record in declared order. `measurement-artifacts.json` gives compressed/uncompressed sizes/SHA-256 and verified decompression+JSON reparse. There are528 records per timing source (4 cases ×initial1+warmup5+observed125+case summary1) and132 per later instrumentation source (4 ×initial1+observed31+summary1). No measurement failed or was repeated/excluded.

`measurement-summary.json` and `logs/measurement-summary.log` are recomputed by the shipped `benchmark/browser_logs_summary.py`: all record counts/correctness/fixture hashes, observed median/nearest-rank p95, emission buckets, complete native fetch/body costs/bytes, initial observations, final retained state, timestamped long-task/frame overlap categories, idle wheel and publication-input/node instrumentation. Outside-observed-cycle intervals include initial/warmup/control/validation; overlap does not make an entire frame gap solely publication cost.

**Dense8,192/255LF fails16/50ms:** candidate44.8ms median /66ms p95 /82.8ms max,30 overlapping observed-publication long tasks (max whole task83ms). Root independently verified all four raw files and accepted unchanged caps/implementation. All four initial observations also regress. Other publication fixture budgets pass. No equal-work/universal speed, under-publication input latency, engine copy-count or RSS claim follows.

## Commands and logs

Native worktree `S=/home/tahv0/.codex/worktrees/c832/OpenScrub`; assigned scratch `R=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1203`. Runtime and all mutable paths were task-local before collection. Source `R/env.sh` or `R/env39.sh`; pin `TASK1203_WEB_HASH`; pytest invocations run serially with distinct `--basetemp` and local cache. Prepared tools remain read-only. Direct runners explicitly configure/assert source under task-local sitecustomize; they do not rely on a pytest plugin for standalone protection.

| Logs | Command / meaning |
| --- | --- |
| `red.log`, `red-layout.log` | Owning browser regressions on exact P12B webda40c171…; actual1,000 displayed versus expected800; complementary layout/count/selection RED. |
| `green1.log`, `green2.log`, `selection-red.log`, `selection-red2.log` | Initial iteration, native blank-final-entry selection probe and retained-container-selection RED;38 affected owning+Node pass after initial fixes. |
| `green3.log`, `green4.log`, `focused-final.log`, `cleanup-green.log` | Affected store/Node/P03/P12B checks plus preserved fixture syntax, native capability and queued-delete409 attempts; actual cancel-before-delete and cleanup/blank anchors2 pass. |
| `lifecycle-probe.log`, `lifecycle-full.log` | Headless shell remains native visible/no freeze events; one full-Chromium launch fails Unix socket path length. Root accepted explicit native-suspension limitation; no install/product accommodation. Exact probe source remains in ignored scratch. |
| `full.log` | `python -m pytest -q --basetemp=$R/full -o cache_dir=$R/cache/pytest`;250 pass /106.67s, one normal discovered suite, measured owning test91540d4…. |
| `strengthened-browser.log`, `clamp-probe.log`, `clamp-native-flush.log`, `strengthened-green.log` | Later test-only expansion; initial fake-clock/native-event fixture races preserved with exact geometry, final native-scroll completion/observer flush and wrapped-prefix fixture;6 pass /11.74s. |
| `floor39.log` | Source `env39.sh`, unset `POLLING_ARTIFACTS`; `tests/test_job_logs.py tests/test_job_polling_node.py tests/test_job_polling_browser.py tests/test_browser_log_retention.py test_openscrub.py -k 'job_logs or job_polling or browser_log_retention or web_worker or watchdog or bad_web_settings or plate_threshold_exposed or phrase_category_wired'`;59 pass /129 deselected /25.74s. Actual3.9.25, exact final source/tests. |
| `measurement-base-process.log`, `measurement-candidate-process.log` | Exclusive granted timing. Set `TASK1203_FROZEN=$R/frozen.json`, literal `TASK1203_GRANTED_HASH=abeb6594…`; run exact archived Python recipe with `--phase timing --label base` then candidate. Base selected `$R/base` with explicit PYTHONPATH and cwd `$R/app`; candidate native.4cases ×125 observed each, final frozen-file checks pass. |
| `instrumentation-base-process.log`, `instrumentation-candidate-process.log` | Only after all timing and root dense-cost disposition, exact archived recipe `--phase instrumentation --label base` then candidate. No timing rerun. Final immutable manifest/all21 files pass before explicit release. |
| `portable-setup.log`, `portable-wrong-*.log` | Initial portable setup checks under inherited outer task guard; retained separately from the independence smoke below. No timing. |
| `portable-clean-setup.log`, `portable-clean-wrong-*.log` | Final public CLI with `PYTHONPATH= PYTEST_PLUGINS=`; selected root/source/Node/Chromium/manifest/granted-sha args and `--check-setup`; pass0, wrong hash1, wrong path1. Guards/imports work without private module dependency. |
| `build-tools.log`, `build-sdist.log`, `build-wheel.log` | Cached `--no-index --no-deps` backend wheels to `$R/build-tools`; actual3.12 `python -m build --sdist --no-isolation`; extract sdist; `--wheel --no-isolation` from extracted source. No environment/dependency download. |
| `package-check.log`, `install-wheel.log` | Exact runtime/private/test/README/portable recipe archive equality, Python>=3.9, actual updater nested delivery; `pip --no-index --no-deps --target $R/installed/site-packages` exact built wheel. |
| `installed-cli.log`, `installed-startup.log`, `installed-http.log`, `installed-browser.log` | Installed-only source filtering and asserted paths/hashes/default profile; generated CLI help; actual installed web main/Cheroot listening server; real routes and browser initial400→800/cursor2700. No page/console errors, server exit0. Test-only synthetic append endpoint lives only in the evidence runner. |
| `installed-tests.log` | Extracted-sdist four owning test files against installed-only module paths/hashes, distinct installed-tests basetemp;54 pass /25.00s. |
| `js-parse-source.log`, `js-parse.log` | Assert actual source, extract evaluated PAGE script, `node --check`; pass. |

No native Windows/frozen, Docker/GPU/media-throughput or cross-browser/native-suspension acceptance is claimed. P12B producer and packaging evidence retains its original Task1202 identities; final optional-artifact unset behavior is newly verified here.
