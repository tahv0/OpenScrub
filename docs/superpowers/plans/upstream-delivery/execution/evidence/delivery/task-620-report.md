# Task620: combined report/browser prerequisites

Completed locally on `integration/report-prerequisites` in the supplied native
worktree `/home/tahv0/.codex/worktrees/c832/OpenScrub`. No remote publication or
subagents. No Task621/lifecycle implementation was started. A fresh scoped
integration review remains the next gate.

## Commits and resolution

Verified the branch was clean at exact supplied base
`7063082ef2a2ff5e56d9aafacff9bd43363b05b3`, already containing the reviewed P06A,
P06D and test-only baseline prerequisites. Applied only these two commits, in
order, using `git cherry-pick -x`:

| Reviewed P07a donor | Local integration commit |
| --- | --- |
| `786990d9102d41c0ec698d6f31fe798de66a049a` | `7f82f3ac901b85bdb630ce4a006a3c4064c96a62` |
| `92124753736e287ac800af91f0ac96f3e96c01be` | `3795d49f6293baf7b8c35534862a4881447e1b16` |

Final range:
`7063082ef2a2ff5e56d9aafacff9bd43363b05b3..3795d49f6293baf7b8c35534862a4881447e1b16`.
Both commit messages retain their full donor provenance.

The sole conflict was the sdist include entry in `pyproject.toml`: the P06A/D
base already used `"tests"`, while P07a added equivalent `"tests/"`. Retained
the existing `"tests"` entry and the incoming `[tool.pytest.ini_options]`
`testpaths = ["test_openscrub.py", "tests"]`. No duplicate include was needed.
Contributor guidance already runs `python -m pytest test_openscrub.py tests/ -q`
and remained unchanged. No other manual resolution or implementation edit.

The range changes only `README.md`, `openscrub_web.py`, `pyproject.toml`, and
`tests/test_review_save_failures.py`. Author scope audit confirms the web-module
AST outside `APP_JS` equals the exact P06D base; evaluated `APP_JS` equals the
reviewed P07a fix head. Thus the server publication/roundtrip changes survive
without new transaction, lifecycle or replay behavior. Save As, P11A and donor
integration history were not imported.

## Fresh combined verification

Commands ran against this exact integration tree, using:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
```

Runtime: Python 3.12.16, `opencv-python` 4.14.0.94, NumPy 2.5.5, pytest 9.2.0,
build 1.6.1. The supplied isolation plugin prevents model autofetch and redirects
runtime paths. Browser/render fixtures and new scripts/logs live only in
`/tmp/openscrub-task620`; no new models or project dependencies were introduced.

| Exact command | Result | Log/evidence |
| --- | --- | --- |
| `python -m pytest -q --basetemp /tmp/openscrub-task620/pytest-tmp -o cache_dir=/tmp/openscrub-task620/pytest-cache` | Exit 0; actual full discovery **230 passed in 62.56s**, no failures/skips. Includes root tests, P06A atomic/vault cases, P06D roundtrip and all 62 P07a/fix actual-JS cases. | `/tmp/openscrub-task620/full-suite.log` |
| `PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PIP_CACHE_DIR=/tmp/openscrub-task620/pip-cache python -m build --outdir /tmp/openscrub-task620/dist` | Exit 0; sdist then wheel **from that sdist**, isolated Hatchling 1.33.0 builds. | `/tmp/openscrub-task620/build-offline.log` |
| `python /tmp/openscrub-task620/check_packaging.py` | Exit 0; all packaged Python parses with Python 3.9 grammar; evaluated `APP_JS` passes `node --check`; exact packaged source/test bytes checked. | `/tmp/openscrub-task620/parse-build.log`, `packaging.json`, `evaluated-app.js` |
| `python /tmp/openscrub-task620/serve.py` | Synthetic fixture, real Flask routes/worker and real engine on `http://127.0.0.1:18488/`; stopped after validation. | `/tmp/openscrub-task620/server.log`, `serve.py` |
| `PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu node /tmp/openscrub-task620/browser.cjs` | Exit 0; actual browser save and real worker render completed, 10 saved/10 rendered rows. | `/tmp/openscrub-task620/browser.log`, `browser-results.json`, `browser-done.png` |
| `python /tmp/openscrub-task620/check_integration.py` | Exit 0; fresh-process GET/reopen, full document equality and every output frame verified. | `/tmp/openscrub-task620/integration.log`, `integration-summary.json`, `fresh-reopened.json` |
| `git diff --check 7063082ef2a2ff5e56d9aafacff9bd43363b05b3..HEAD` | Exit 0. | Fresh command output |

The first normal `python -m build` attempt could not resolve PyPI in the sandbox;
it failed before producing distributions (`build.log`). Reused wheel bytes
already cached by Task64 to populate the task-local offline build wheelhouse;
the successful retry installed the same build backend, with no network or
dependency/version changes. The first fresh-route harness omitted the synthetic
job's `name`, which the report download route requires. The real error was
`KeyError: 'name'`; added that fixture field and reran successfully. This was a
task-local harness correction, not a product fix or claimed behavioral RED.
The initial failed run remains in `integration-initial.log`.

## Combined synthetic route

Reused Task64's ten-row synthetic 60-frame MJPEG fixture from the integration
branch. Full OpenScrub page → select `synthetic-task620.avi` → click the first
row's Blur/Keep toggle twice → actual Save edits & render → real HTTP save →
real queued worker/FFmpeg render → fresh Python process's actual Flask GET
`/api/jobs/reopen/detections` and `/api/jobs/reopen/report`.

The browser submitted exactly the deliberate `enabled:{"0":false}` delta,
empty manual/box/time deltas, and no untouched audio payload. Its intercepted
save response was forwarded through the real route, and the saved full report
equaled the pre-save document. The actual browser save/snapshot code executed;
none of the save/render responses were fabricated. Full-suite Node VM cases
also exercised the evaluated shipped JS, including failed acknowledgements,
newer drafts, view changes and the reviewed independent audio-eviction fix.

Result: **10 → 10 → 10 → 10** rows before/save/render/fresh reopen, unchanged
original order and indices. All non-provenance report values compare equal,
including disabled ordinary row 0, disabled zone-dropped row 4, disabled manual
polygon row 8, enabled manual polygon/rectangle rows 3/9, precision/additive
metadata, and `audio_redactions`, `audio_suggestions`, `audio_transcript`.
Fresh full-report GET equals the rendered document exactly. All 60 decoded
frames have seven black enabled regions and three visible disabled regions.
Output path/hash provenance was refreshed by the actual render.

Browser QA followed the frontend-testing-debugging skill. Browser plugin was
not available; reused installed Playwright 1.65.1/isolated Chromium without
installing dependencies. Desktop 1365×1000, intended URL/title `OpenScrub`,
nonblank true, framework overlays 0, page exceptions `[]`, console warnings/errors
`[]`. Screenshot inspected: app and actionable render status present. The
screenshot reflects the submitted rendering status; completion is established
by fresh job API `phase:done, has_output:true` and decoded output, not by the
stale displayed phase badge.

## Distribution/scope and remaining limits

Wheel bytes match `openscrub.py`, `openscrub_web.py`, and both
`openscrub_internal` files in this exact worktree. Sdist bytes also match all
four `tests/test_*.py` files, root `test_openscrub.py`, `pyproject.toml`, and
`README.md`. Relative to Task64's P06D build, the sole newly included sdist file
is `tests/test_review_save_failures.py`; wheel manifest has no new files.
Project/build requirements and Python web imports are unchanged. No new
custom-training/workbench files, imports, dependencies, version changes or root
helpers. Full manifests/hashes are recorded in `packaging.json`; AST/ancestry
checks in `scope-audit.txt` confirm the reviewed P06A and baseline commits
remain ancestors.

Integration worktree is clean on final head
`3795d49f6293baf7b8c35534862a4881447e1b16`. Individual refs remain
`pr/report-roundtrip-preservation` at `7063082ef2a2ff5e56d9aafacff9bd43363b05b3`
and `pr/review-save-snapshots` at `92124753736e287ac800af91f0ac96f3e96c01be`.
Original checkout remains on `main` at
`5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`; its observed untracked `docs/`
was not touched. Original product files/Git, individual PR branches/reports and
user runtime data were not modified; only this requested SDD report was written
there.

No new product issue identified during this assembly. The fresh independent
integration review has not yet run. This does not establish lifecycle/concurrent
writer safety or lost-save-ack manual replay idempotence (P06B/P07b boundaries).
Only Linux/Python 3.12/OpenCV 4 and one Chromium desktop route were freshly
exercised; Python 3.9 is grammar-checked, not runtime-tested. No Windows/macOS,
other browsers/mobile, installed-wheel runtime, model inference/download,
production concurrency, audible mute/bleep quality or performance claim. Existing
root-suite audio tests ran; this combined fixture itself has no audio stream.
