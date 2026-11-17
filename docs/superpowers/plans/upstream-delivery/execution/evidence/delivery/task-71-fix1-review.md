### Finding Verdicts

- **Clean audio remains stale when an unrelated draft is pending — ADDRESSED.** `openscrub_web.py:2103` now evicts equal audio/current-baseline values independently of enabled/manual/box/time drafts and resets `audioLoaded`. Dirty audio remains retained. `openscrub_web.py:2993` pins audio only when this operation actually submits audio; the pin is released at acknowledgement (`openscrub_web.py:2998`) and in `finally` (`openscrub_web.py:3038`). An unacknowledged audio response marks the baseline uncertain (`openscrub_web.py:3034`), preserving a newer toggle-back for deliberate retry rather than evicting it as clean.
- **Regression coverage — verified.** The fix adds five clean-audio/non-audio-draft combinations, fifteen dirty add/remove/modify combinations, clean audio during an unrelated save, and successful/failed acknowledgement toggle-back cases in `tests/test_review_save_failures.py`. These exercise actual embedded JavaScript rather than a replacement implementation.

### New Breakage in the Fix Diff

- **None found.** The operation-owned flag and null baseline preserve dirty empty lists and toggle-back intent; non-audio requests do not pin clean loaded audio. No new Critical/Important issue was identified in the scoped diff.
- **Recorded checks inspected:** `fix1/red.log` shows the six original reproductions failing; `fix1/red-audio-retry.log` shows both unacknowledged toggle-back cases failing before their fix; `fix1/green.log` reports 62 passed. The browser script and results support twelve full-UI Chromium scenarios with no page exceptions and only intentionally injected 423/network console errors. The fresh-audio screenshot retains the editor, timeline spans and actionable failed-save status.
- **Recorded build checks inspected:** successful sdist/wheel build, Python 3.9 grammar, evaluated-JS parse and exact packaged source-byte comparisons. The parse/build script implements those checks. No test, browser or build rerun was needed for this review; the earlier 172-test full-suite run applies only to the initial reviewed head.

### Out-of-Scope Observations

- **Minor, previously recorded:** `CONTRIBUTING.md:25` still selects only the root test file. It is explicitly deferred outside this fix gate; no renewed inspection or additional finding was made.
- **Limits unchanged:** P07b lost-save-ack manual replay and the declared P06A/P06D server defects remain outside this fix. This review does not establish other-browser/platform behavior or the baseline status of the previously observed resize overlay.

### Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.** Exact fix range reviewed: `786990d9102d41c0ec698d6f31fe798de66a049a` → `92124753736e287ac800af91f0ac96f3e96c01be`. No product/Git mutation, Git command, subagent delegation or broad validation rerun was performed.
