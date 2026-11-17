### Finding Verdicts

- **Render does not reserve the original input that the engine actually reads — ADDRESSED.** `openscrub_web.py:369` selects provenance input under an existing primary lifetime, reserves its live containing job before checking source existence, and deduplicates self/alias ownership. `openscrub_web.py:800`, `openscrub_web.py:812`, and `openscrub_web.py:2008` transfer the selected canonical source into the queue reservation without an ownership gap, including the automatic skip-review handoff. `openscrub_web.py:892` retains worker ownership and passes the private input pin; `openscrub.py:8542` honors that pin instead of following later provenance into an unowned source. The default unpinned engine selection remains in the else branch, and `openscrub.py:6054` excludes the pin from persisted settings.
  - Actual-route regressions cover source ownership from queued state through normalization/cleanup, delete/retention refusal, direct/symlink originals, missing-original fallback, self deduplication, orphan/deleting rejection, and late provenance replacement (`tests/test_job_source_allowlist_lifecycle.py:144`, `:195`, `:228`, `:252`). The automatic normalized scan→render reservation is exercised at `:292`, ordinary engine behavior at `:324`, and real report rendering/private-state exclusion at `:272`.
  - The existing `/tmp/openscrub-task621/fix1/review-repros.log` confirms the verbatim reproduction now selects A's actual input while DELETE A returns **409**, the source still exists, and B is rendering. This addresses the original Important defect.
- **The shared allowlist bypasses admission and can create plaintext after lock — ADDRESSED.** `openscrub_web.py:1085` now admits both GET and POST through a store-wide lifetime before entering the route; `openscrub_web.py:1980` closes each read handle within that lifetime. The existing response/teardown ownership paths handle release. Locked/failed transitions reject admission, while an active write makes lock busy.
  - Actual-route regressions cover locked GET/POST, an Event-paused real write through close/encrypt/reopen, waiters behind encryption, exact committed bytes and partial-encryption recovery (`tests/test_job_source_allowlist_lifecycle.py:46`, `:55`, `:97`, `:127`). The existing reproduction log confirms **423**, locked state true and no recreated plaintext file.
  - The authorized consumer correction is narrow: `persistFailure`, `loadPersist`, `clearPersist` and `rmPersist` (`openscrub_web.py:3376`, `:3383`, `:3406`, `:3413`) preserve displayed words, report refusal/network errors in the existing note, and reload only after an acknowledged mutation. Evaluated emitted-JS tests cover refusal and ready success (`tests/test_review_save_failures.py:353`, `:372`). This addresses the original Important defect without introducing another mode or unrelated UI change.

### New Breakage in the Fix Diff

- None identified at Critical or Important severity. No additional finding is raised.
- The new selection preparation performs report JSON I/O outside VAULT_LOCK, retains only short source-admission decisions under it, releases unused provisional owners, and acquires no job/report mutex around queue submission (`openscrub_web.py:369`, `:800`, `:812`, `:2008`). The one absence check for an unregistered original stays within the guarded store boundary and never opens that source.
- Missing/invalid-report asynchronous behavior and private-state exclusion receive explicit controls (`tests/test_job_source_allowlist_lifecycle.py:345`, `:272`). The new engine branch is limited to the private selected-input contract (`openscrub.py:8542`); there is no report cache, transaction/publication callback, new dependency or unrelated helper package in the fix diff.

### Out-of-Scope Observations

- None added. The documented in-process, external-filesystem, platform/container/frozen/TLS and deferred report-transaction/cancellation limits remain applicable; this scoped re-review does not reopen unchanged implementation.

### Checks and Evidence

- Fix base `4479b57612f4e5c463d31900f76277a5fcebb8a9`; reviewed head `c697d5a686d4dccbdf4f474567628d5d24e75a03`. Read the five-file fix package once in two bounded passes, plus the task brief, verbatim two findings, re-review template and appended fix report. Line references are relative to the frozen native worktree at that head.
- Read existing `/tmp/openscrub-task621/fix1/targeted.log`: **188 passed in 41.15s**, clean output. Its reported matrix includes prior lifecycle/socket cases, all new route and emitted-JS controls, real report roundtrip/failure behavior and selected existing engine/worker regressions.
- Read existing `review-repros.log`: **10 passed in 0.21s**, including both verbatim reviewer reproductions and eight vault-cleanup cases, with explicit corrected statuses/source ownership output. Read `python39.log`: **36 passed in 2.63s**, clean output for all new route and consumer cases.
- Read retained RED evidence: `red.log` records the seven initial route failures and `js-red.log` records nine emitted-JS refusal failures before the relevant fixes. The appended report distinguishes intermediate mixed selections from final passing runs.
- Read existing `build.log`, `packaging-final-head.log`, `installed-startup.log` and `installed-source-equality.log`: sdist→wheel success; exact amended-head artifact/source checks; Python 3.9 grammar/default-engine-branch/limited-JS-change checks; installed CLI/web/allowlist/vault/shutdown success; and installed-source byte equality. These are retained evidence, not newly executed validation.
- No tests, builds, socket schedules or startup checks were rerun: the diff and existing focused evidence resolved both findings without a specific unanswered execution doubt. No Git commands, native-tree product edits or subagents were used; only this requested review report was written.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
