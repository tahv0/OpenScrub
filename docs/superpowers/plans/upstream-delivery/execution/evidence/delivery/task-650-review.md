### Spec Compliance

- ✅ Spec compliant for the first intermediate C01 integration gate. The seven-commit package contains the six requested candidate subjects in the required order followed by the integration-test commit. The assembled source retains the report lock, guarded export-name refresh, complete preview publication/snapshot response, bounded ETA history, and admitted-options validation (`openscrub_web.py:517`, `openscrub_web.py:1324`, `openscrub_web.py:1526`, `openscrub_web.py:2304`, `openscrub_web.py:2777`). No unrelated product subsystem, dependency/default change, or product correction is visible in the diff.
- ✅ Conflict preservation matches the declared decisions: combined root/`tests/` contributor discovery and Node prerequisite remain (`CONTRIBUTING.md:24`), `CONTRIBUTING.md` is added to the existing sdist list without duplicate discovery entries (`pyproject.toml:112`), and report export keeps its existing per-job report lock (`openscrub_web.py:2304`). Fixture adaptations preserve the real queue lease rather than weakening admission (`tests/test_scan_options.py:1`); callback cancellation events and the existing store admission support the ETA/preview tests (`tests/test_scan_eta.py:1`, `tests/test_live_preview.py:1`).
- ✅ Combined-boundary requirements are represented by executable assertions, with actual versus controlled inputs accurately distinguished: held actual preview response through publication/cancellation/lifetime transitions, real pipeline/save/replay/render/download/fresh-process reopen, and a 1000-row HTTP save/reopen (`tests/test_batch_integration.py:1`). The inspected browser harness runs the shipped UI and real HTTP with a controlled picker and real OPFS, including newer edits/job switching, failed publication without render, accepted-write accounting, and held close (`/tmp/openscrub-task650/browser.cjs:1`; report:44–68).
- ⚠️ Cannot independently establish original refs/data/archive preservation, absence of remote operations, the exact `-x` commit messages, or current native branch cleanliness from this aggregate source diff. The report records these at `task-650-report.md:7` and `task-650-report.md:18`; `committed-bytes.json` records the assigned head and clean/native/frozen-byte results. Controller retains responsibility for repository-state/provenance verification; this reviewer performed no Git operations.

### Strengths

- Preview publication uses same-directory replacement, while HTTP derives body, length and content ETag from one immutable snapshot. The integrated response test verifies that an in-memory snapshot still retains and releases the existing response lease after worker cancellation (`openscrub_web.py:1526`; `tests/test_batch_integration.py:1`).
- Save As captures job/kind before picker/network awaits, counts only accepted destination writes, and delays success until destination close. The original view-generation guard remains before assigning export names (`openscrub_web.py:2777`). The browser evidence adds the pending review-save interaction that isolated candidate tests cannot establish (`/tmp/openscrub-task650/browser.cjs:1`).
- Dense smoothing changes only sequential retrieval and decoder cleanup; the marked-frame test checks complete detection output against a characterized pre-change digest, while focused error/cancellation cases cover release (`openscrub.py:1432`; `tests/test_dense_smoothing_io.py:1`).
- Acceptance explicitly keeps whole-C01/C02, physical-disconnect replay, optional models, video atomicity and general performance claims open (`task-650-report.md:108`, `task-650-report.md:116`, `task-650-acceptance.md:1`).

### Issues

#### Critical (Must Fix)

- None found.

#### Important (Should Fix)

- None found.

#### Minor (Nice to Have)

- **Clarify browser byte coverage.** `task-650-report.md:58` describes verification of deterministic destination bytes, but `/tmp/openscrub-task650/browser.cjs:84` retains and asserts only the first 256 bytes plus total size/name. Say “first 256 bytes” to make the evidence limit explicit. This does not block the integration gate: correct job routing, accepted byte count and close state are independently asserted, and the separate real rendered-video HTTP test compares its complete response body.

### Checks and Limits

- Read the supplied 119601-byte diff once, in sequential passes; did not re-read changed source files, rerun Git, mutate product/index/refs, or dispatch reviewers.
- Assessed raw successful results rather than relying on the report: `full-final.log` has **530 passed in 114.30s**; `python39-focused-final.log` has **136 passed in 17.71s**; `integration-green.log` has **3 passed in 3.84s**; `build-final.log` explicitly builds wheel from sdist. No warning/error summary appears in those successful suite/build logs. No suites/build/browser/media checks were repeated.
- Named risk: browser claims could describe mocked application behavior. Inspected `browser.cjs`, `serve_browser.py`, `browser-results.json` and `browser.log`. Actual UI/HTTP requests, real OPFS write/close, response-held save acknowledgement and real publication-boundary failure are implemented. Page exceptions are empty. The single browser warning is the deliberately injected HTTP500, as disclosed at `task-650-report.md:60`; no additional uncontrolled browser noise was evidenced.
- Named risk: packaging/default/candidate equality flags could lack meaningful assertions. Inspected `check_packaging.py`, `self_review.py` and their result artifacts. Assertions compare packaged source/test bytes, Python 3.9 grammar/metadata, defaults/project metadata/routes/private module set against the assigned base, selected candidate function ASTs/Save As text, and base lifetime hooks. Independently inspected archive membership and SHA256: wheel contains exactly nine Python sources; sdist contains all fifteen focused tests; both hashes match `committed-bytes.json`. This was archive inspection only, not a repeated build or executable smoke.
- Named risk: the integration test's imported preservation assertion could omit ordinary/additive report data. One focused outside-diff inspection of the `review` fixture and `assert_review_preserved` in unchanged `tests/test_report_roundtrip.py:23` and `tests/test_report_roundtrip.py:80` confirms mixed selected/kept/zone-dropped rows, audio/additive fields, and whole-document equality except provenance. The integrated fresh-process comparison also checks the complete rendered document. No broader source crawl was performed.
- Python 3.9 import evidence points to the designated native worktree; focused runtime plus packaged grammar checks support this gate, not whole-app floor certification (`/tmp/openscrub-task650/python39-imports.log`; `task-650-report.md:108`). Original readiness Minors remain separate as recorded at `task-650-report.md:118`. Screenshots were not re-inspected; visual QA is represented by the existing browser evidence and disclosed Linux/Chromium limits.

### Assessment

**Task quality:** Approved, with one nonblocking evidence-wording Minor.

**Reasoning:** The assembled changes preserve the visible overlapping ownership and report contracts, and the combined tests/evidence cover the task's critical interactions without weakening production guards. No integration blocker was identified; this approval is confined to Task650 and leaves final whole-branch/C01/C02 acceptance open.
