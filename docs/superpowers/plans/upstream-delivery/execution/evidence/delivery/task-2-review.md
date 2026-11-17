# P01 independent review

Reviewed 2026-11-16. Base `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`; candidate
`ca0f2ce7458347afd2e6156a97df580b6623767a`. Read-only product checkout:
`/home/tahv0/.codex/worktrees/c832/OpenScrub`.

**Spec verdict: PASS. Quality verdict: APPROVE.** No actionable P01 correctness,
compatibility, or maintainability findings identified. This approval does not
represent an entirely passing repository suite; the known baseline failure remains
visible below.

## Scope and findings

Read the supplied diff once, the current brief, implementation report and PR
draft. Inspected the changed Python/JavaScript and contributor/README/package
changes. Followed unchanged job-selection/polling and download/report call sites
only to assess captured-job behavior, export persistence and HTTP attachment
compatibility. No product or Git changes, browser rerun, full suite rerun, or
build rerun were performed.

- `openscrub_web.py:350`: filename calculation preserves the real output suffix
  and fallback, exposes additive metadata, and supplies both existing attachment
  routes. No report schema or route shape changes were found.
- `openscrub_web.py:2216`: the clicked job, kind, filename and route are captured
  before the picker await. Cancellation restores earlier feedback without a
  fetch. The stream awaits each destination write before counting bytes or
  fetching its next chunk, validates a reliable total before close, and awaits
  close before Saved. Failure paths retain actionable feedback and perform
  reader/writable cleanup.
- `openscrub_web.py:2243`: totals come from a valid safe-integer response length
  only when no content encoding, or identity encoding, is present. Unknown,
  invalid and decoded-transfer lengths remain indeterminate. No job-size total
  or fabricated percentage/countdown is used.
- `openscrub_web.py:2169`: progress is keyed by captured job/export and rendered
  only into the matching selected job's controls. The timer keeps elapsed time
  visible during pending reads/writes/close. Visual updates have a 250 ms guard;
  live announcements have a separate two-second cadence. The ten-second rate
  history, three-second ETA threshold, five-second waiting threshold, stale-ETA
  suppression, finalizing state and consistent decimal byte units match the
  brief. Saved elapsed time freezes at completion. Direct download hides the
  bar and reports only browser-download initiation.
- `tests/test_export_save_as.py`: new tests execute the actual evaluated embedded
  JavaScript, with independently controlled picker/read/write/close promises and
  clock. They cover the required named regressions, failure paths and timing
  behavior; an unresolved asynchronous scenario cannot silently pass. Flask
  response tests verify actual names, payloads and lengths for video/report.
- `CONTRIBUTING.md:25` and `pyproject.toml`: contributor collection includes the
  existing root suite and `tests/`; new tests enter the sdist. No runtime module,
  dependency/framework/version change or CI workflow was introduced. This
  follows the supervisor's explicit CI ruling.

## Verification evidence and limits

Checked the preserved final focused log (`green-harness.log`: **24 passed**),
required combined-suite log (`full-required.log`: **157 passed, 1 failed**) and
full sdist-to-wheel log (`build-final.log`: successful). The suite failure is the
unchanged `test_track_person_size_jump_handoff` log assertion at
`test_openscrub.py:2335`, already identified in the baseline. Its separate test-only
correction is outside this candidate and was not assumed complete.

Inspected the preserved browser harness and `browser-results.json`, rather than
accepting the implementation narrative alone. They support the reported real
HTTP-to-OPFS 268,435,456-byte transfer, exact final size/progress totals, one
in-flight write, at most one fetched-but-unaccepted chunk (maximum 2,097,152
bytes), visible waiting/finalizing states, polling/job switches, retries,
cancellation and direct-download fallback. The harness blocks `.blob()` and
samples browser memory; the report appropriately limits its memory claims to
those measurements. The PR draft accurately identifies the donor's static
feedback as the trigger and does not claim an upstream filename regression or
download-speed improvement.

The picker boundary is injected in headless Chromium; actual OS-native picker
interaction, Windows permissions, other browser engines, multi-GB exports and
physical-disk durability remain unverified. Runtime evidence uses Python 3.12 and
the documented OpenCV 4 environment, not Python 3.9 or unconstrained OpenCV 5.
These limits are disclosed in the implementation report/PR draft. No concrete
unanswered correctness doubt warranted an additional focused execution.
