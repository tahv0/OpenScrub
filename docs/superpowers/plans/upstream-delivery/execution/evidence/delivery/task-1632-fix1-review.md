# Task1632 fix round 1 — scoped independent re-review

## Finding Verdicts

- **Track a render-local primary exception** — **ADDRESSED**. Both renderers initialize their own `primary = None` and assign it only when their owned work raises, then immediately re-raise the same exception (`openscrub.py:3953`, `openscrub.py:4115`, `openscrub.py:4163`, `openscrub.py:4387`). Finally no longer reads ambient `sys.exc_info()`. Expanded SDR/HDR controls execute inside and outside a caller's handled exception and assert the caller remains unannotated; callback primaries retain identity (`tests/test_render_resources.py:327`, `tests/test_render_resources.py:360`). Actual 3.12 and 3.9 retained records show all caller annotations false, successful-work cleanup errors raised, and callback sentinel identity true where applicable (`task1632-fix1-evidence/runs/fix1-focused312/logs/command.log:18`, `task1632-fix1-evidence/runs/fix1-focused39/logs/command.log:18`).

- **Retain independent encoder stdin-close failures** — **ADDRESSED**. Both EOF paths now retain an `OSError` from owned stdin close and bound the exceptional status wait to two seconds (`openscrub.py:4094`, `openscrub.py:4098`, `openscrub.py:4364`, `openscrub.py:4368`). Observed encoder exit zero re-raises the original close error; independently observed nonzero exit retains useful `_ffmpeg_failure` diagnostics and records the close error as secondary. Timeout invokes owned abort and preserves the original close error instead of presenting a forced exit as an encoder cause. Ordinary status-wait failure is secondary to that close error. Successful close still uses the existing unbounded healthy wait. Real-resource tests cover after-real-close success/nonzero status and undelivered EOF, including a bounded status-wait failure (`tests/test_render_resources.py:431`, `tests/test_render_resources.py:485`). Both interpreters' retained records show actual zero exits with original close-error identity, encoder rejection rc 254 with useful stderr, and abort rc -9/-15 with the original close error remaining primary (`task1632-fix1-evidence/runs/fix1-focused312/logs/command.log:27`, `task1632-fix1-evidence/runs/fix1-focused39/logs/command.log:27`).

## New Breakage in the Fix Diff

- **None.** The fix adds no deletion activation, changes neither existing removal guard/block nor the shared child helper, and introduces no timeout on healthy completion. The renderer-local exception handlers only record/re-raise. The tests still assert production closure/reaping before unconditional harness containment. No new Critical or Important issue was found in the scoped diff.

## Out-of-Scope Observations

- None newly identified. The earlier nonblocking offline pip-cache warning remains deferred; unchanged ownership code was not re-reviewed. Native interruption, universal OS reaping, Windows/GPU behavior, G composition and P publication remain outside this scoped acceptance.

## Checks and Evidence

- Read the scoped re-review template, task brief, appended fix report and standalone fix report. Read the complete 372-line supplied fix diff in two bounded, nonoverlapping chunks: `8e70af446caa5ed37e0e36c029925d5caf08f943` → `70ec464ca70b5e49751d778890f56029dced0b8a`. No Git diff regeneration, source/index/branch mutation, new product execution, suites, builds or servers were performed.
- Verified all **12 indexed retained logs** against recorded sizes/SHA256. Retained RED names the eight owning failures and reports **8 failed / 6 passed / 37 deselected** on the original engine hash. Preserved RED test bytes hash to `9a84ba41c90dd0458e9ccd70184884d97c098d9a6432cfd0ec6b0d9e88fe67a1`, matching the RED preflight. Retained primary-only GREEN is **8 passed / 43 deselected** and both-fix GREEN is **14 passed / 37 deselected**.
- Checked the final focused preflights and structured actual-resource records. Actual **Python 3.12.16 development** and frozen **Python 3.9.25** each show **64 passed / 126 deselected**, no skips (`task1632-fix1-evidence/runs/fix1-focused312/logs/command.log:55`, `task1632-fix1-evidence/runs/fix1-focused39/logs/command.log:55`). Their engine/test hashes match the final frozen inventory and current native bytes: engine `9365c47bdc74bf5fc7496ffca62600861367fd968530664dc58f6710ca00037d`, resource tests `0d93b9eec719a73cc30a36332ef0758af767c604f6518e7f1c945cdb52a44607`. All **23 selected native files** match the final frozen manifest. These were byte-identity checks, not rereading unchanged product code.
- Independently hashed the retained final sdist (**534037 bytes**, SHA256 `755c0f147dbb3d2eaa915471f591bd92c42b07fe9335841ef98d3edd631eac81`) and wheel (**435567 bytes**, SHA256 `153237d7023b13f3b1372cc93feba9b20f9be52916e2a74709e9fdb78fbdb6a8`). All **11 selected sdist members**, **six wheel members** and **six installed runtime files** match final frozen source hashes. Retained package commands explicitly build the wheel from extracted sdist, install offline without dependencies, and show all six phases exiting zero. Installed default paths are owned; actual listening `/api/jobs` and `/` return HTTP 200 and the server is reaped with rc 0 (`task1632-fix1-evidence/runs/fix1-package/logs/installed-1.log:3`). No completed gate was rerun to corroborate these records.
- `final-check.json` and `retained-acceptance-check.json` keep final acceptance distinct from the historical **174 passed / 5 skipped** full suite at `e9fd0d3`; that earlier full result was not treated as a full-suite run of this fix head. This review verifies the fix's covering evidence and does not broaden its platform/native guarantees.

## Verdict

**Spec compliance:** Approved for this scoped fix; both original Important findings are addressed and the carried constraints are preserved.

**Task quality:** Approved.

**Fix round:** All findings addressed, no new Critical/Important breakage.
