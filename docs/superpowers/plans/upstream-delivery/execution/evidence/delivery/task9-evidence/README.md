# Task 9 compact evidence

Candidate `0c2b98e9e136abcd472bdda59cecaf546775ea4e` from exact reviewed P02/P07a `2ae3257b9752e2d976ff7a0d39955a13c133273a`. See [report](../task-9-report.md) and [PR draft](../task-9-pr.md). This archive contains synthetic verification evidence, not original user data, runtime/media/environment/install/source-export trees or package binaries.

## Read first

- [identity.json](results/identity.json): exact source/PAGE/base/head identities. The commit was made only after the tested and packaged source hashes were checked unchanged.
- [browser-results.json](results/browser-results.json): final bounded main UI matrix. `browser-qa-final-2.log` passed; earlier similarly named logs contain failures and must not be substituted.
- [route-body-counts.json](results/route-body-counts.json): separate tiny actual PAGE/Flask observer. Six browser fetch/body settlements and image loads; six route entries/WSGI body exhaustions/closes; three JPEG hits, three cold misses, three thumbnail decoder opens. No client-receipt/native-cancellation claim.
- [final-observations.json](results/final-observations.json): exact-base small count, final large DOM/heap diagnostics, actual narrow control, authoritative terminal render `done`. Its original call-on-close zero count is retained as ineffective instrumentation, not server noncompletion.
- [pre-render-verified.json](results/pre-render-verified.json), [post-render-report.json](results/post-render-report.json), [output-check.json](results/output-check.json): raw saved choices/fields and actual decoded output. Standalone after-render row loss 21→18 remains P06D/C01.
- [failure-browser-results.json](results/failure-browser-results.json): four attempts, 283px card height before/after exhaustion, editing and zone keyboard action remain usable.
- [touch-lifecycle.json](results/touch-lifecycle.json): real touch scroll +615px, no marquee, actual enlarged original and Escape, actual owned synthetic-job deletion teardown.
- [package-check.json](results/package-check.json), [installed-http.json](results/installed-http.json), native/installed defaults: offline build/install and actual HTTP boundaries.
- [cleanup.json](results/cleanup.json): no held/pending gates; only four verified owned servers stopped; ports 18509–18512 closed.

## Verification commands

Commands ran from the native worktree unless a script is explicitly task-root based. Mutable paths were all under the authorized task root; shared prepared tools/environments were reused read-only. `scripts/env.sh`, `sitecustomize.py` and `task9_isolation.py` show the actual protections. Direct server/client Python processes used the actual task-local hook, not an inert pytest plugin variable. Node scripts set `TMPDIR` before importing Playwright. Browser plugin was absent.

```bash
. /home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/env.sh
python -m pytest test_openscrub.py tests/test_thumbnail_scheduling.py tests/test_review_choices.py tests/test_review_save_failures.py -q -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/required-final"
python -m pytest -q -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/full-final"
# Sequential after the above; keep the same task-local hooks and paths.
export PATH=/tmp/openscrub-python39-20261117/venv/bin:$PATH
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export UV_PYTHON_INSTALL_DIR="$TASK9_ROOT/runtime/python"
python -m pytest tests/test_thumbnail_scheduling.py tests/test_review_choices.py tests/test_review_save_failures.py -q -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/floor39-final"
```

Results: required/full each **212 passed**; actual Python 3.9 ownership **78 passed**. `floor39-compile.log` separately records 3.9 active-source parsing. `js-parse.log` is the successful `node --check` of the AST-evaluated final `APP_JS`; `source-identities.json`/package assertions bind it to shipped source. Eight new owning tests are in the candidate; the first four had missing-feature RED then GREEN. Legacy choice/save mounting adapters do not supply admission/decision logic.

Offline build used actual 3.12, pip supplied through the prepared bootstrap **module path**, and cached wheelhouse `/tmp/openscrub-task620/build-wheelhouse`. Cached hatchling/packaging/pathspec/pluggy/trove-classifiers/tomlkit were installed only to task-local `build-tools`. Build commands were:

```bash
python -m build --no-isolation --sdist --outdir "$TASK9_ROOT/dist" "$TASK9_ROOT/build-source"
# Extract that exact sdist into TASK9_ROOT/sdist before this command.
python -m build --no-isolation --wheel --outdir "$TASK9_ROOT/dist" "$TASK9_ROOT/sdist/openscrub-1.0.96"
python -m pip install --no-index --no-deps --target "$TASK9_ROOT/installed" "$TASK9_ROOT/dist/openscrub-1.0.96-py3-none-any.whl"
```

See build/install logs and `scripts/check_package.py`; final package hashes are in the result record. The installed CLI/web/actual listening HTTP checks removed editable checkout paths. Default comparison is JSON equality (71 options); the first byte comparison differed only by one final newline.

Browser/server scripts are test instrumentation around actual product routes. Ports: candidate 18509, exact-base small control 18510, installed smoke 18511, separate tiny WSGI counts fixture 18512. The final `serve.py` includes a body-iterator observer and rejects an expired render gate. Earlier server logs predate those harness-only changes, while retaining the same product source hash. `qa.cjs` handles main cardinality/ownership; `anchor.cjs` reproduces the zoom anchor defect; `failures.cjs`, `output.cjs`, `final-observations.cjs`, `counts.cjs`, and `touch-lifecycle.cjs` cover the named remaining gates. The final output reproduction script uses authoritative HTTP terminal polling; that exact updated script was not rerun after the complete pre-render/fresh-page sequence passed and terminal status/pixels were independently established.

Source-only base export, fixtures, builds, installed target and media remain in ignored task scratch, not this archive. Reproduction requires the supervisor to pin the native branch/head first; do not run scripts against an arbitrary later checkout. Do not invoke all browser scripts indiscriminately against a previously mutated/deleted fixture: `output.cjs` expects a clean small fixture and `touch-lifecycle.cjs` deliberately deletes its owned synthetic beta.

## Boundaries and failed attempts

- `red-descriptors.log`: expected missing complete descriptor feature.
- `red-network.log`: expected missing scheduler feature; `green-network.log`: four passed.
- `focused-1.log`: 73 passed/one legacy save-only adapter lacked ResizeObserver; `focused-2.log`: 78 passed after adapter correction.
- `layout-zoom-before.log`: actual implicit columns under 125% zoom; source corrected to native computed grid tracks and coordinate scaling.
- `anchor-red.log` / `anchor-green.log`: actual group 866 was lost; now −54px → −54.25px.
- `browser-qa-1.log`: marquee probe targeted an offscreen focus pin and sticky scroll coordinate. Corrected to an actual visible card/nonsticky target.
- `browser-qa-2.log`: editor probe waited for detections at t=0, before fixture start. Native slider moved into its valid interval.
- `browser-qa-3.log` / `browser-qa-final.log` / `playback-diagnostic.log`: retained P02 preload-none start wait. Initial mp4v decoding diagnosis was unconfirmed; replacing it with H264 did not resolve the wait. Actual readyState=0/networkState=1/paused=true/error=null isolated the metadata-start deadlock. Supervisor confirms P16D already owns its fix. `browser-qa-final-2.log` passes subsequent playback ownership after explicit native `video.load()`; ordinary Play startup is not passed on this base.
- `browser-failures.log`: initially unscoped details locator matched settings and review. Scoped final probe passed.
- `browser-output.log`: raw last_seen correctly clamped when changing time; initial expectation was wrong. Its saved document is retained in `output-attempt1-saved.json`.
- `browser-output-final.log`: all raw pre-render and fresh-page assertions passed; a subsequent immediate terminal sample saw `rendering`. Independent authoritative HTTP `done` and actual pixel verification passed. These are separate evidence boundaries, not one uninterrupted green script.
- `build-sdist.log`: cached tomlkit initially missing; added offline to task-local build tools, final sdist/wheel passed.
- `installed-cli.log`: initial installed-only path filter also excluded the authorized task scratch nested under the original checkout. Exact task-root exception corrected the harness, final installed boundaries passed.
- `failed-attempt-notes.txt`: initial non-escalated socket bind denial was observed, but its raw log was overwritten by the authorized retry; this is explicitly a transcribed note. It also records the harmless default newline comparison and script-version boundaries.
- Initial server `call_on_close` completion zeros are retained in compressed server observations and final diagnostics. The separate WSGI observer records its actual exhaustion/close boundary successfully.

No baseline 1k/10k rerun or latency benchmark was performed. Counts do not establish speedup. Browser heap/DOM and separate process RSS are bounded point observations with normal GC, not constant-memory or decoder-termination guarantees. CSS zoom, the exact desktop/narrow viewports, Chromium and synthetic media were tested; other platforms/browser engines/toolbar zoom/audible audio and combined-candidate gates were not. P03/P08/P15/P01/P06/P16D integration belongs to C01.

## Screenshots and raw data

Screenshots show desktop review, actual narrow control, failed preview, actual editor edits, and decoded input/output. They complement assertions and real input; they are not standalone mobile-interaction proof. The two decoded PNGs are useful region evidence rather than video artifacts.

`server-observations.json.gz` is lossless; `compression.json` records raw/compressed hashes/sizes and successful decode/reparse verification. All other compact result records remain JSON. Large duplicate fixture/report bodies and the evaluated source export are omitted; fixture recipes, hashes/counts, small raw reports and the source/package identities remain. All log failures are retained; the one overwritten initial bind log is disclosed above.
