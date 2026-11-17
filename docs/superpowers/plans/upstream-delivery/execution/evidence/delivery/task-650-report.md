# Task 650 — first intermediate C01 batch assembly

Status: DONE for this bounded local integration gate. No product interaction defect was found. The combined branch is clean at `aa07a0664ec0b9d3d592adba19e5e1e473e906ac` on `integration/upstream-focused` in `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Starting point was exactly `12919c96c6f7558136b50d7b4d85e5e6b62f1971` (the already-reviewed report/lifetime/transaction/manual replay stack). This is the first meaningful-batch C01 smoke gate, **not** whole-plan C01 completion, C02 adoption, an umbrella upstream PR, or publication. Supervisor fresh task-scoped review follows; final selected application acceptance/default equivalence and whole-branch review remain open.

## Provenance and bounded scope

Only the six declared reviewed commits were cherry-picked, with `-x`, in the required order:

| Candidate | Original reviewed commit | Integrated commit |
| --- | --- | --- |
| P01 Save As | ca0f2ce7458347afd2e6156a97df580b6623767a | 6ccf4374c2269e600e2811cd85fddcf25ab2a688 |
| P11A dense smoothing | f19be5fe3b9176e568ea7bf761493bd267fee95e | 9cee49f383a083b4954fad657446d233c08db425 |
| N08 options validation | e34313e1b136254fb2777cabb385f2097a54935a | b76d1b2f13a2cf70a1a9ffe77ebb312000ebeeb5 |
| N08 integer decoding follow-up | b26b6685b237ba1c4caffaaefb47b029a3205b51 | 7635a67eaaa78f1da047e6542376447ca1652817 |
| P05 preview generations | b70d42011168192cdf7a9ef93a5e9419a92a1cdb | 51dbdeed0b91a3405d857241f875bef88234e6c9 |
| P04 recent ETA | d129e23e5fe144edb8bbd5675809c1877cfe4d0f | 7d2f812c1178601fc88618c5c4d736e77bbe0c0b |

The only subsequent commit is `aa07a0664ec0b9d3d592adba19e5e1e473e906ac` (`Verify the combined preview export and review lifetime contracts`), containing inherited test-fixture compatibility corrections plus `tests/test_batch_integration.py`. No additional product behavior was introduced by that commit. The original candidate refs remain: `pr/save-as-progress`, `pr/dense-smoothing-prefix`, `pr/scan-options-validation`, `pr/live-preview-snapshots`, `pr/recent-stage-eta`; original objects, checkout/data/archive were not changed. No remote commands, PR creation, optional models, new dependencies, global installs, new working-environment adoption, removed-system imports, or nested agents were used.

Raw artifacts are Task650-owned under `/tmp/openscrub-task650`. This report and `task-650-acceptance.md` are supervisor workspace evidence in the explicitly requested ignored SDD documentation directory, not upstream product documentation.

## Conflict decisions and corrections

1. P01: `CONTRIBUTING.md`, `pyproject.toml`, `openscrub_web.py` conflicted. Retained the base's complete root-plus-`tests/` contributor command and existing single `tests` sdist inclusion/discovery stanza; retained the incoming Node18+ requirement prose. Kept `job_report`'s per-job report lock and changed its filename expression to reviewed `export_filenames(job)[1]`. Kept the base's `VIEW_GEN`/`ownsView(id,gen)` guards at both refresh awaits and assigned `EXPORT_NAMES` only after the guarded status response.
2. P11A: `CONTRIBUTING.md`, `README.md`, `pyproject.toml` conflicted in shared discovery prose/list entries. Kept complete existing combined discovery and Node prose; did not duplicate `tests` or drop root tests. Engine and focused benchmark/test additions merged without conflict.
3. N08 first commit: only README discovery wording conflicted; retained the combined complete wording. The integer-limit follow-up applied cleanly. Actual admission validation remains before creating a job, with the base's request/queue lifetime ownership intact.
4. P05: contributor/readme/packaging discovery conflicts resolved identically. Preview publication/HTTP generation code merged without product conflict; base admission and response hooks retained.
5. P04: contributor/readme/packaging conflicts resolved as above; included incoming `CONTRIBUTING.md` sdist entry. Both `_publish_preview_jpeg` and ETA constants were retained at their shared insertion point. No helper was replaced by the other.

An initial setup command used unavailable `python` before sourcing an environment. Its draft resolution did not run; an accidental task-created draft commit `4880b09` was immediately discarded, its following pick aborted, and only this just-created integration draft was reset to the exact assigned base before recreating the chain above with `python3` and `set -e`. It is not part of the final history. No existing branch/data was reset. Final marker absence, tests, packaging and exact candidate comparisons all passed.

Initial focused assembly run: **34 failed, 99 passed** (`initial-focused.log`). Root causes were inherited fixture contracts predating P06B, not production failures: N08 expected a three-field queue ticket while the base correctly carries its lifetime lease as field four; P04 dictionaries and one P05 staging callback lacked the required cancellation event; P04's synthetic render job lacked current source/report admission. The separate integration commit:

- updates N08's synthetic ownership domain and asserts the first three fields **and** the real live fourth lease/queued mapping; its fixture drains/releases queued owners rather than resetting counts;
- supplies cancellation events in callback-only P04/P05 fixtures;
- runs P04's controlled pipeline through the real existing store/source/report admission and uses a mutable argument namespace for the base's source pin.

All original behavioral assertions remain. The adapted set passed **89/89** (`adapted-focused.log`). No production guards/counters were weakened. The new combined tests initially passed two schedules and hit the OS per-environment-value limit with the 1000-row expected document (`integration.log`); the harness now passes that expected document through its own temporary file. All three then passed (`integration-green.log`).

## Combined runtime contracts

### Actual scan callback → actual held HTTP preview → cancel/retry/lifetime

`test_actual_scan_preview_cancel_retry_and_held_response_ownership` creates a real 60-frame synthetic MJPEG video, admits a retry through HTTP, runs the actual worker/`run_scan`, decoder, callback, preview encoder/publication and configured Cheroot HTTP server. Only the OCR construction/read boundary is controlled (a fixed synthetic email word); no model was downloaded. Callback and response iteration events hold exact bounded boundaries rather than relying on timing.

The first completed JPEG snapshot is acquired by an actual GET whose first FileWrapper iteration is held. The real scan resumes and publishes a different second generation while that response remains held. Cancel is sent via HTTP, and DELETE, vault lock and retry all return409 while work is alive. After worker cancellation/cleanup, the completed in-memory JPEG response still owns its one existing lease: DELETE/vault remain409 until transfer completes. Its actual body, Content-Length and SHA256 ETag all match the original generation. Completion releases ownership to zero; real vault lock/unlock succeeds, then retry runs the actual scan to review. This verifies response-owned snapshot cleanup without a transfer-long filesystem/report lock or lock-order inversion. It makes no output-video atomicity claim; P16C remains separate.

### Actual emitted browser UI + HTTP + controlled picker / real OPFS

Browser plugin/skill is absent in this session, as verified in tool discovery; the already installed isolated Playwright/Chromium fallback was used. No browser/tool installation. `serve_browser.py` serves the actual integrated Flask app with Cheroot at `http://127.0.0.1:18650/`; imports assert the active native worktree. Two synthetic done jobs have valid tiny input videos/reports and real tiny preview JPEGs. For this browser-only download boundary the 4MiB output is a deterministic byte fixture, not a valid rendered MP4; actual rendered-video export is tested separately below. Optional release checking is replaced at the route boundary with a local no-update result.

`browser.cjs` executes the full shipped page and real buttons, review controls, polling and fetch:

- holds the controlled File System picker across A→B, then verifies the captured A download route/name and no B feedback;
- holds the first real OPFS destination write; accepted progress remains zero until that write is accepted;
- reopens A review while export is pending, changes Keep, commits a real HTTP save but holds its returned fetch response, makes a newer edit, switches to B, then releases the acknowledgement; no render POST is sent and A's newer draft survives;
- revisits A and injects a publication-boundary OSError for a tagged real save request; actual HTTP500 preserves the server report and browser draft, with no unintended render POST;
- completes the real response→OPFS write stream, holds destination close, verifies `Finalizing…`, 4,194,304 accepted bytes and active state, switches jobs without cross-job feedback, releases close, and verifies `Saved` plus exact destination size/name and the first256 deterministic bytes. The browser harness does not compare the entire4MiB destination content; the separate rendered-video HTTP test compares its full response body.

Result: passed (`browser.log`, `browser-results.json`). URL/title `OpenScrub`, meaningful nonblank content, zero framework overlays, page exceptions `[]`. The only browser console warning is the deliberately injected HTTP500. Desktop1365×1000 and mobile390×844 screenshots were inspected: `browser-pending-desktop.png` shows finalizing beside retained failed-save draft; `browser-saved-mobile.png` shows saved export with readable controls/status. Native picker behavior itself is controlled, real OPFS writes/close are not. These checks supplement the retained P01/P07a/P07b standalone browser evidence; their broad matrices/large-file benchmarks were not repeated.

### Actual scan → review → save/replay → render → export → fresh-process reopen

`test_actual_scan_review_save_render_export_and_fresh_reopen` uses actual scan with controlled OCR only, then seeds the ordinary imported-report fixture boundary with ten mixed name/plate/face/manual/person selected/kept/zone-dropped rows, precise/additive row metadata, audio redactions/suggestions/transcript and additive top/provenance/render-state fields. Actual scanned email rows are retained too. It saves decisions and an identified manual addition over real HTTP, deliberately discards the completed first acknowledgement and replays the identical request; one manual row is appended. This is controlled application-level acknowledgement loss, **not** a physical transport-disconnect experiment.

The real admitted worker/x264 box render completes. All saved detection rows/audio/additive fields outside legitimate provenance updates remain equal. Both report and rendered output are downloaded over HTTP with correct audit/video names and exact bytes. A decoded selected pixel is black while a kept pixel remains bright. A new Python process asserts active source imports, rehydrates persisted storage, starts a fresh actual Cheroot HTTP server, replays the captured creation request and reads the report over HTTP; the complete rendered report remains identical and ownership returns to zero. No live identity registry crosses processes.

`test_thousand_row_actual_http_save_and_fresh_reopen` performs a real HTTP sparse save over1000 synthetic ordinary rows and a fresh-interpreter/server HTTP report reopen. Row999 changes, other999 and audio/additive fields remain intact. This is a modest correctness smoke, not a save-performance benchmark.

The three combined integration tests passed on Python3.12 and Python3.9. Existing standalone smoothing/frame/cancellation/performance evidence is preserved; no new dense timing, general long/4K performance or model-accuracy claim is made.

## Stabilized checks and commands

Product/test source was frozen before the complete suite/build/floor set. `verification-source.json` records SHA256 of39 source/test/metadata files. No product/test change followed that manifest. Common3.12 setup:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/tmp/openscrub-task650:/home/tahv0/.codex/worktrees/c832/OpenScrub:$PYTHONPATH
export PYTEST_PLUGINS=task650_isolation
```

The Task650 plugin isolates runtime data under `/tmp/openscrub-task650` and asserts engine/web imports from the active worktree. Environment: Python3.12.16, OpenCV4.14.0, NumPy2.5.5. OpenCV4 is a validation-environment constraint; project dependency metadata remains the original unbounded `opencv-python`. B02b/OpenCV5 is separate and was not adopted.

| Command/check | Observed result/evidence |
| --- | --- |
| `python -m pytest tests/test_batch_integration.py -q -s -o cache_dir=/tmp/openscrub-task650/cache --basetemp=/tmp/openscrub-task650/integration-green-tmp` | **3 passed in3.84s**; `integration-green.log`. |
| `python -m pytest -q -o cache_dir=/tmp/openscrub-task650/cache --basetemp=/tmp/openscrub-task650/full-final-tmp` | **530 passed in114.30s**, exit0; `full-final.log`. Exactly one stabilized complete discovery run, no failures/skips/warnings. Includes Austin queue/watchdog/parser/fallback/review tests and all prior report/lifetime/save/replay contracts plus candidates. |
| `TMPDIR=/tmp/openscrub-task650/build-tmp PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PIP_CACHE_DIR=/tmp/openscrub-task650/pip-cache python -m build --outdir /tmp/openscrub-task650/dist` | Exit0; isolated Hatchling1.33.0, sdist then wheel **from that sdist**, existing offline wheelhouse only; `build-final.log`. |
| `python /tmp/openscrub-task650/check_packaging.py` | Exit0; `packaging.log`, `packaging.json`. Exact9 declared wheel Python sources and all15 focused test files/root suite/docs/metadata/requirements in sdist; exact wheel sources; all packaged Python parses with3.9 grammar; `Requires-Python: >=3.9`; emitted `APP_JS` passes `node --check`. Explicit supported `filter='data'` used for archive extraction. Initial evidence-script glob included unshipped developer helper `fetch_plate_models.py`; corrected to the declared wheel include list (artifact-only harness correction). |
| `/tmp/openscrub-baseline-20261116/bootstrap/bin/pip --python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python install --no-index --no-deps --target /tmp/openscrub-task650/installed/site-packages /tmp/openscrub-task650/dist/openscrub-1.0.96-py3-none-any.whl` | Exit0; only built project wheel in a new task-local target; `install.log`. |
| `python /tmp/openscrub-task650/check_installed.py` | Exit0; `installed-startup.log`/`.json`. Fresh installed imports, real CLI help, real installed web entrypoint/Cheroot/homepage/jobs, allowlist/vault setup/lock/refusal/unlock/recovery and graceful idle SIGTERM0; fresh task-local profile, no model fetch. |
| `PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu node /tmp/openscrub-task650/browser.cjs` | Exit0; combined actual UI/HTTP/OPFS schedules passed; browser artifacts described above. Server command uses prepared env plus active-source `PYTHONPATH` and `python /tmp/openscrub-task650/serve_browser.py`. Localhost server/browser runs used authorized escalation because sandbox binding is blocked. |
| `python3 /tmp/openscrub-task650/self_review.py` | Exit0; `self-review.json`. Exact AST equality to reviewed dense smoother/export filenames/preview helper/preview route/ETA progress; exact Save As JS block; base lifetime/admission/response/render/retry hooks unchanged; report lock and refresh generation guards retained; no conflict markers. |
| `python /tmp/openscrub-task650/check_packaging.py` after self-review, before commit | Exit0; `frozen-bytes-final.log`. Same manifest/build bytes confirmed. `git diff --check` also clean. |

Python3.9 active-source checks:

```sh
. /tmp/openscrub-python39-20261117/env.sh
export PYTHONPATH=/tmp/openscrub-task650/py39-harness:/home/tahv0/.codex/worktrees/c832/OpenScrub
export PYTEST_ADDOPTS='-o cache_dir=/tmp/openscrub-task650/python39/cache'
export TMPDIR=/tmp/openscrub-task650/python39/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task650/python39/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task650/python39/config
python -m pytest tests/test_batch_integration.py tests/test_export_save_as.py tests/test_dense_smoothing_io.py tests/test_scan_options.py tests/test_live_preview.py tests/test_scan_eta.py -q --basetemp=/tmp/openscrub-task650/python39/focused-final-tmp
```

**136 passed in17.71s**, exit0 (`python39-focused-final.log`). `python39-imports.log` records Python3.9.25/OpenCV4.14.0, asserts engine/web imports from the native active worktree and the Task650 `sitecustomize` hook. The copied existing audit isolation blocks outward connects and writes outside Task650 while reusing existing3.9 runtime/dependencies/models boundary; no model/download/install. This focused floor run plus packaged grammar/metadata checks is **not whole-app Python3.9 runtime certification**. The complete suite/build/installed smoke used3.12.

`packaging.json` also confirms unchanged complete project metadata/dependencies/entrypoints, unchanged `requirements.txt`, unchanged parser/CLI settings/run_pipeline/web build_args AST, identical web route declarations and private module set to the assigned base, and no removed workbench/Findings/journal/section/training modules in the wheel. Installed ordinary defaults remain `auto/auto/auto/blur/8/tight/archival` and report publisher remains optional. No new defaults were introduced.

## Self-review and remaining boundaries

Self-review of the assembled production diff, fixture adaptations and new integration tests found no unresolved important/critical issue. There is no product correction beyond routine preservation of overlapping reviewed changes; the separate integration commit is tests only. Supervisor fresh-context task-scoped integration review remains required. The clean Git head above is the exact frozen source/test build tested here; no publish/remote operation was performed. Final post-commit `committed-bytes.json` verifies all39 manifest files against committed bytes, installed engine/web/private helper bytes against that commit, and records sdist/wheel SHA256. The task-owned browser server was stopped after validation. No source/test change required a repeat full run.

Linux/Chromium only; Safari/Firefox, real native File System picker dialogs and native Windows/macOS were not exercised. Synthetic controlled OCR, imported mixed-row fixture, injected report-publication failure and acknowledgement loss are identified above. No new models, detection quality certification, physical network-disconnect replay claim, output-video atomicity claim, long/4K performance expansion or broad browser matrix repetition.

Existing readiness Minors remain separate and unchanged: P04 missing-preview/extraction-harness noise (this browser used actual tiny previews and packaging extraction explicitly uses supported data filter), P05 date-validator test suggestion, P06A evidence-script deprecation, standalone P07a contributor-command omission, and P11A publication-evidence attachment. Assembly docs/discovery do not retroactively fix or change those standalone PRs. Final whole-branch C01/C02 acceptance remains open.

Supervisor review note: task-650-review.md independently approved spec and quality with no blockers. Its one nonblocking wording suggestion is corrected above: browser content coverage is first256bytes plus total size/name, while the separate rendered-video HTTP assertion compares full bytes. No product/test changes or checks were repeated for this documentation correction. Final whole-branch/C01/C02 gates remain open.
