### Finding Verdicts

1. **Mounted rows lose logical DOM/Tab order after an upward window move. — ADDRESSED.** `openscrub_web.py:2937` now reconciles sibling order from the end, moving other siblings around the actual focused subtree. `:3028` applies this to cards within each row; `:3031` applies it to ordered rows after removing old spacers. This repairs the original retained-later/new-earlier insertion defect and the corresponding width-repartition case without reusing descriptor identities. The emitted-JS regression at `tests/test_thumbnail_scheduling.py:212` asserts the original concrete upward sequence and exact focused-control retention across both repartition directions. Retained actual Chromium evidence (`task9-fix1-evidence/results/browser.json`) shows ordered IDs 63–118 after the overlapping upward move, with 42 retained IDs, exact native Tab sequences at seven and five columns, and the same focused control after resize.

2. **Page-hide restoration abandons old row/spacer nodes in the live review root. — ADDRESSED.** `openscrub_web.py:3138` removes every owned row and spacer, clears the row maps and spacer arrays, and retains the section's explicit height while suspended. Fresh restoration therefore cannot orphan the old structural set. The regression at `tests/test_thumbnail_scheduling.py:225` checks both actual primitive DOM counts and owned maps across three cycles. Actual PAGE/Flask Chromium evidence records 6 rows/4 spacers/42 cards before and after each of three controlled transitions, and zero structure while hidden; final permanent cleanup is zero throughout. `results/anchor-last.json` additionally records group 77 at −199px, scrollY 4445 and document height 8478 before/during/after the focused controlled case.

3. **The same restored view receives a fresh retry budget. — ADDRESSED.** `openscrub_web.py:2913` marks page hide as suspension. `:3145` preserves freshly copied numeric failure/deadline records with `timer:0`; `:3154` requires a suspended owner with the same job/view/root before restoration; `:3156` transfers retry history and empties the retired owner's map. Permanent disposal clears history and disables restoration (`:3131`). Binding/controller/timer objects are not transferred. The emitted-JS tests at `tests/test_thumbnail_scheduling.py:237` and `:251` cover exhausted history across three restores, fresh-view reset, deadline preservation, stale timer fencing and normal-queue timer recreation. Actual browser evidence records exactly four failure attempts across all three restores, no fifth attempt, fresh metadata resetting the history to zero, and zero abandoned work.

### New Breakage in the Fix Diff

- **None found.** Reviewed the complete one-commit fix diff (`0c2b98e9e136abcd472bdda59cecaf546775ea4e..fe20dff7b73efb5afdbf3130e75a19c8b35ecba3`). The ordering helper operates on the bounded mounted siblings; disposal is still idempotent, and suspended retry transfer retains no asynchronous target references. No new Critical, Important or Minor finding arose from this fix.

### Out-of-Scope Observations

- **None.** No new unchanged-code issue was identified or added to this loop.

### Evidence and Limits

- **Checked:** the appended fix1 section of `task-9-report.md`, the complete `task-9-fix1-report.md`, the supplied fix diff once, the four-test RED output, final native/floor logs, actual browser/anchor records, source/package/installed HTTP records and cleanup evidence. No separate changed-source read or unrelated source inspection was needed.
- **Checked:** `logs/red.log` reproduces the exact original DOM order, abandoned structure, missing exhausted retry record and lost 600ms deadline, with 8 passed/4 failed. Final retained `logs/focused-green.log` reports 82 passed; actual Python 3.9.25 `logs/floor39.log` reports 82 passed. Neither contains unexpected warnings. Browser JS errors are zero; the four recorded network failures are deliberately injected retry failures. The earlier cleanup-counter harness failure is disclosed and corrected in the retained final run.
- **Checked:** independent read-only hash comparison matched all six source files in `results/identity.json` against the frozen native tree, including web SHA `435ee74b112635a9694333fafc9460b3f454d371760f3aba1c4d4fa4875e4563`. AST-evaluated final APP_JS matches `1d0608598dfd24cd912c90cf810ded4942ba50f918fe82074413827c9ef39d94`. Retained installed HTTP output asserts exact embedded final APP_JS and successful `/` and `/api/jobs` responses. Package records bind exact final runtime/test bytes to the rebuilt sdist→wheel.
- **Cannot verify beyond the stated boundary:** lifecycle browser evidence replays `PageTransitionEvent`; actual BFCache/history navigation was not observed. The anchor result is one measured controlled viewport. This does not leave the three concrete code defects open: their original structural/order/retry failures are directly repaired and covered by the named regressions.
- **Unchanged validation boundaries:** original full/required 212 and real save/fresh-reopen/render evidence remain bound to `0c2b98e`, not relabeled as final-head runs. P06D after-render preservation, P16D ordinary Play startup and combined C01 gates remain as recorded in the original review. No new speed, total-memory or native-cancellation claim is made.
- **Review checks performed:** hash/AST equality only. No suites, builds, browser matrices, timing, product/Git mutations, nested agents or external actions were performed in this re-review.

### Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.** No findings remain open in this scoped round.

**SpecCompliance: ✅ Spec compliant within the reviewed standalone Task9 scope, with the unchanged integration/verification boundaries above.**

**TaskQuality: Approved.** The changes repair the exact three defects locally and add meaningful emitted-JS regressions plus focused actual UI evidence; no whole-branch or C01 integration approval is implied.
