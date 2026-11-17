# B01/B02 baseline preparation review

Reviewed 2026-11-16 against `task-1-brief.md`, the complete `task-1-report.md`
(including the OpenCV 4 compatibility section), `baseline-review-package.md`,
retained artifacts, and the unchanged native worktree.

**Spec verdict: PASS for the authorized preparation scope.** B01 is complete;
B02 has established a usable comparison environment and captured the required
baseline checks with existing failures visible. This does not establish a green
upstream baseline or Python 3.9 runtime compatibility.

**Preparation/evidence quality verdict: PASS WITH A MINOR DOCUMENTATION CONCERN.**
No blocking findings and no product changes to review. The retained evidence
supports the reported outcomes and appropriately separates setup errors,
dependency/model limitations, and the remaining tracking assertion failure.

## Verified evidence

- Independently inspected native-worktree Git state: HEAD/local `main` are
  `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`, status/diff are empty, the donor
  archive reference resolves to `b4d0c75f25d91510fe1692f901d11853dc7db005`, and
  `origin` remains the user's configured remote. No checkout or branch mutation
  was performed during this review.
- The isolation plugin redirects app data/model paths and blocks network model
  fetches while delegating local-file verification tests to the real fetch
  implementation (`task-1-artifacts/baseline_isolation.py:7`). It does not modify
  collection, assertions, skips, or outcomes. This is a disclosed test-environment
  intervention, not shipped code.
- All 134 tests are accounted for: `pytest.log:2382` records 116 passed,
  14 failed, 4 errors; `pytest-opencv4.log:74` records 133 passed, 1 failed.
  The retained tracebacks support the missing `CascadeClassifier` explanation.
  `environment.json` and `environment-opencv4.json` record the differing API
  availability. The report correctly avoids treating a simultaneous OpenCV/model
  change as an isolated causal experiment.
- The permitted pretrained YuNet manifest records the upstream hash pin and
  separate synthetic model path (`task-1-artifacts/yunet-manifest.json`). No
  evidence reviewed indicates custom training or workbench dependencies.
- The handoff diagnostics in both versions record the same held-state log
  suppression, size ratios/correlations, and 20 late samples of area 7,200.
  These observations agree with unchanged `openscrub.py:2243` and the assertion
  at `test_openscrub.py:2335`. The report's narrow conclusion is supported;
  the failure remains reported rather than silently repaired.
- `build.log` explicitly shows sdist followed by wheel-from-sdist. Independently
  hashed both retained distributions; their SHA256 values match the report.
  `syntax.log` records the two evaluated script blocks and successful Node
  check. `http_smoke.py`, `run_web.py`, `http-smoke.log`, and `startup.log`
  support the real main/startup, loopback endpoint, separate job-root and clean
  shutdown claims.
- The report explicitly records missing browser/GPU/optional models and lack of
  Python 3.9 verification. Deferring new test collection changes until an owning
  product PR is consistent with this task's empty product diff.

## Nonblocking concern

**Low — the reproduction block is not sufficient to bootstrap a fresh task
root verbatim.** `task-1-report.md:83` calls a helper at its `/tmp` location
without recording how the preserved helpers are staged there;
`task-1-artifacts/get_tools.py:8` assumes `root/debs` already exists; and
`task-1-report.md:88` checks an evaluated JavaScript file without recording the
command that creates it. The syntax artifact supplies the observed outcome but
not that missing generation command. Record the helper-copy/staging commands,
`mkdir -p .../debs`, and evaluated-PAGE extraction/AST command in a follow-up
evidence-only edit. This affects replay convenience and completeness, not the
credibility of the retained baseline results; no full test/build rerun is needed
to address it.

Review was read-only for the native checkout. No full suite/build rerun, browser
installation, broad web search, product edits, or publication was performed.
