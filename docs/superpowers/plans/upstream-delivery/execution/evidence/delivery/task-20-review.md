### Spec Compliance

- ✅ Spec compliant for Task 20 / P02. Reviewed base `92124753736e287ac800af91f0ac96f3e96c01be` → head `2ae3257b9752e2d976ff7a0d39955a13c133273a` using the supplied one-commit diff. Ordinary and zone cards emit explicit native setters; aggregate status, pressed attributes and dimming use every existing member; category/selection scopes and grouping construction remain intact (`openscrub_web.py:2799`, `openscrub_web.py:2836`, `openscrub_web.py:2875`, `openscrub_web.py:2887`, `openscrub_web.py:2898`). The two contributor commands now discover standalone tests (`CONTRIBUTING.md:25`, `CLAUDE.md:1025`). No extra product scope found.
- ⚠️ Complete preservation on a fresh review **after render** remains the explicitly deferred P06D/C01 combination gate. `/tmp/openscrub-task20/output-check.json` records 13 rows before and 8 afterward, with the known disabled-row loss explicitly identified. This task's diff changes no server lifecycle functions; do not interpret this approval as approval of that combined roundtrip.

### Strengths

- `openscrub_web.py:2875`–`openscrub_web.py:2907`: one output setter continues to record deliberate same-value intent in the existing draft. No duplicate acknowledgement code, decision baseline or per-action versions were added. The new emitted-JS tests exercise same-value ACK satisfaction, newer opposite intent, failed saves and job ownership through the existing save entrypoint (`tests/test_review_choices.py:1`; `/tmp/openscrub-task20/green.log`).
- `openscrub_web.py:2868`, `openscrub_web.py:2898`: derived row-to-card membership makes a nonrepresentative edit refresh its containing card without scanning other groups. Group actions refresh each affected card once; the 600-row/200-group regression bounds enabled-value reads rather than making an unsupported latency claim (`tests/test_review_choices.py:1`).
- `openscrub_web.py:2877`, `openscrub_web.py:2887`: contextual native action groups, in-place status/attribute changes and a local focus-visible outline preserve focus and convey mixed state without dimming the card. Saved desktop/mobile screenshots show readable paired controls; `/tmp/openscrub-task20/browser.cjs` checks actual pointer, Tab, Enter, Space, retained focus, pressed state, 390px bounds, marquee/Escape, original preview, touch scrolling and the existing help tap guard. Its saved result records 8 scenarios with no page errors or console warnings/errors.
- `/tmp/openscrub-task20/real.cjs`: backend evidence has a clear boundary. Only the first render request is gated; actual UI choices are saved by the real backend, all non-output report fields are compared, a fresh page reopens all 13 rows before render, then the real worker renders. `/tmp/openscrub-task20/output-check.json` records eight selected black regions, five textured kept regions and an unchanged unrelated region, while exposing the known post-render row loss.

### Issues

#### Critical (Must Fix)

- None found.

#### Important (Should Fix)

- None found.

#### Minor (Nice to Have)

- None found.

### Checks and limits

- Changed source was reviewed from the supplied diff once. Only the initially truncated documentation hunks were recovered afterward. No Git commands, source/index/ref mutations, suite/build/browser/render reruns, or nested agents were performed. This requested review report is the only file written.
- Named concrete outside-diff risk: removing `toggleDet` or introducing membership-derived refresh could strand a mutation caller or change editor scope. A focused enabled-write/setter-call search in the candidate found no remaining `toggleDet` call; the only row output assignment paths are review loading and `applyDet`. Inspection of unchanged `openscrub_web.py:2730`–`openscrub_web.py:2736` confirms `beRemove()` still calls `applyDet(BE.sel,false)`, clears selection and hides the existing controls. The diff's `TRKMEM[i] || [i]` mutation contract preserves representative fan-out and nonrepresentative row locality.
- Read the raw evidence rather than relying solely on the report: `green.log` reports 70 passed; `full.log` reports 204 passed; `build.log` records successful sdist→wheel; `packaging.json` records exact source/test inclusion, Python 3.9 grammar and unchanged server/engine/zones; `installed-startup.json` records actual installed CLI/web startup, defaults and idle SIGTERM exit 0. `committed-source.json` ties the validated packaged source to the reviewed head. No focused new test was necessary because the code and existing evidence answered the identified risks.
- The initial Python 3.9 run's one failure is transparently attributable to its write-audit temp-root restriction (`python39.log`); the focused retry under its allowed root passed (`python39-report-retry.log`). The final focused/full logs are clean. Saved browser assertions and `mixed-accessibility.txt` support the accessibility claims; this review does not establish Safari/Firefox behavior, screen-reader user testing or large-list latency, and the task does not claim those.

### Assessment

**Task quality:** Approved.

**Reasoning:** The change implements explicit repeatable output choices and truthful all-member feedback with a small, view-derived index and existing setter/ACK ownership. Behavioral, browser and real backend/output evidence cover the task's material edges; the separate after-render lifecycle prerequisite remains clearly bounded and unchanged.
