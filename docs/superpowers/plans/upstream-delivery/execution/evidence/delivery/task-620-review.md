### Spec Compliance

- ✅ **Spec compliant.** Reviewed `7063082ef2a2ff5e56d9aafacff9bd43363b05b3..3795d49f6293baf7b8c35534862a4881447e1b16` as prerequisite assembly. The prepared diff contains only the two requested P07a commits and four intended files. The server/publisher and P06D engine changes are not edited by this range; the browser's independent audio-eviction fix is present (`openscrub_web.py:2098`, `openscrub_web.py:2993`). No Save As, lifecycle/replay implementation, dependency/version change, training/workbench code or root helper was added.
- ✅ **Conflict resolution preserves both requirements.** `pyproject.toml:121` retains the existing `"tests"` sdist include; `pyproject.toml:124` adds default root-plus-`tests` discovery. `README.md:604` documents that command and optional Node coverage. The focused unchanged-file check confirms `CONTRIBUTING.md:25` already invokes both locations; the earlier standalone contributor-command finding does not apply to this base.
- ✅ **Actual combined evidence is retained.** `/tmp/openscrub-task620/full-suite.log:5` reports 230 passed with no warnings/skips; `/tmp/openscrub-task620/build-offline.log:16` confirms sdist then wheel completion. `packaging.json:2` names this exact head and records exact packaged source/test bytes, unchanged project/build requirements, all four test modules in the sdist, and no added wheel files. These satisfy the integration checks without repeating independent suites.
- ⚠️ **Scope of verification:** recorded final-head/clean-ref/original-checkout statements are in `task-620-report.md:118`; Git state was not re-queried in this read-only review. Linux/Python 3.12/Chromium and Python 3.9 grammar are the stated limits (`task-620-report.md:131`). Runtime Python 3.9, other platforms/browsers, installed-wheel execution, audible processing and lifecycle/concurrent-writer safety remain unverified and are not claimed by this prerequisite task.

### Strengths

- `openscrub_web.py:2978` retains captured job/view/draft ownership, acknowledged-only reconciliation, checked save/render responses and deliberate enabled deltas. `openscrub_web.py:2098` independently evicts clean audio while preserving dirty or in-flight audio. The new integration does not rewrite either reviewed implementation.
- `tests/test_review_save_failures.py:18` evaluates the shipped Python string rather than replacement save logic; its 62 cases add to the inherited 168 server/engine cases to explain the actual 230 count. `tests/test_review_save_failures.py:257` onward retains the independently reviewed clean-audio/non-audio-draft and toggle-back regressions.
- `/tmp/openscrub-task620/browser.cjs:26` forwards the actual intercepted POST through `route.fetch()` and returns its real response. It checks the saved full document before the real worker render; `/tmp/openscrub-task620/serve.py:6` points at the intended integration source and reuses the inherited synthetic fixture. `/tmp/openscrub-task620/check_integration.py:12` compares full non-provenance values, checks all 60 decoded frames and reopens both actual Flask routes in a fresh process. The retained browser/integration results show 10→10→10→10 rows, original indices/order, disabled/manual rows and all three audio metadata fields preserved, with no page exceptions or console warnings/errors.

### Issues

- **Critical:** None found.
- **Important:** None found.
- **Minor:** None found in this assembly scope. The first network-blocked build attempt and missing-name synthetic harness attempt are disclosed, retained and superseded by successful checks; they do not indicate a product defect or warning in the successful suite.

### Focused Checks

- **Risk: server/publisher preservation or browser-fix loss during assembly.** Ran one read-only Python AST/artifact comparison: current non-`APP_JS` AST equals the retained P06D wheel's module; evaluated `APP_JS` equals the retained P07a fix wheel's string. Also confirmed current web-module SHA-256 equals the exact-head `packaging.json` record and its Git blob hash begins `6e388ee`, matching the prepared diff's final index. All assertions passed. No Git command, build, browser, render or test rerun.
- **Risk: discovery/packaging dropped at the pyproject conflict.** Inspected the prepared `pyproject.toml:121`/`:124` hunk, retained successful build/parse logs, manifest/byte-check script and manifest results; read only the relevant unchanged contributor-command lines. Both root and directory tests are selected and packaged.
- **Risk: summaries describe a mocked or stale combined route.** Inspected retained harness source, raw successful logs, exact-source job metadata and result JSON. The harness uses this worktree's actual Flask routes/worker, forwards the save response, compares the saved report, checks real rendered output and imports this source in the fresh reopen process. No unanswered integration concern required another execution.

### Assessment

**Task quality: Approved.** The assembly preserves both reviewed implementations and resolves the sole package conflict without duplicate inclusion or lost discovery. Retained exact-head evidence and the narrow independent equality check support proceeding to the separately scoped lifecycle work; they do not extend the declared concurrency or replay guarantees.
