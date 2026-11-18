### Finding Verdicts

- **T1004-R1 — error bodies escape the page-wide sample slot — ADDRESSED.** `openscrub_web.py:3418` checks HTTP status first; `:3420` now awaits `response.text()` before the HTTP-status error is thrown at `:3421`. Both body exhaustion and body-read failure therefore precede the slot release/latest-wanted pump at `:3432`. A stale mount still drains its issued response, and the existing owner check keeps its eventual error inert. The branch neither parses the refusal as JSON nor allocates decode work/URLs nor aborts an issued request.
- **Regression coverage verified:** `tests/test_review_save_failures.py:823` covers HTTP409/423/500 × exhaustion/read failure, holds non-JSON error bodies across A → B → new A mounts, replaces intermediate wanted requests, and verifies one fetch until settlement, no decode/URL allocation, stale-status isolation, latest-only launch and subsequent readiness. `:852` covers the same six combinations for a current owner, including retained active-slot ownership and useful HTTP/retry status after settlement. The fixture addition at `:44` supplies the normal Response `.text()` interface; shipped production functions remain under test.

### New Breakage in the Fix Diff

- **Critical:** None.
- **Important:** None.
- **Minor:** None.
- **Scope check:** the complete supplied `dcaa0e5..d1f056e` packet was read once. Its production change is confined to the non-success branch of `bePumpSamples`; successful body/decode/application, playback and backend behavior are untouched. Comparing old/final frozen file hashes independently yields only `openscrub_web.py` and `tests/test_review_save_failures.py`; all 136 final frozen checkout hashes match and the ten-module inventory is unchanged.

### Evidence Checks

- **Genuine RED verified:** `task1004-fix1-evidence/runs/task1004-fix1-84b494de56c24532929be706ceca4ae0/logs/command.log` records 12 failures/141 deselected in 1.70s: six premature-second-fetch assertions and six premature-slot-release assertions, rather than parser/harness errors. Its prospective metadata binds original dcaa web SHA `33cd9d19ff9ea9542d14408be7840929dafd2b9bc6c8ae240fc7aab410d8cc32` and the new test SHA `3ee8f7ab7a41639f85d6ad568aa4e5b01916a54424b4bbe7594ba908f506ecfb`. The wrapper records exit 1 and the focused `-k error_body` argv.
- **GREEN and attribution verified:** the two raw owner logs record 153 passed in 19.55s on actual Python 3.12.16 and 153 passed in 21.57s on actual Python 3.9.25. Wrapper argv and exit 0 agree with the appended report. Their development attribution remains explicit; both prospective web/test fingerprints match final d1f056e bytes, including web SHA `422ed86c602be624f17ac6f2ef7e607121552afcaff0801ce23ffc467dc02a09`. No 620-test, PAGE-success or floor-server result was relabeled as a fix-head rerun.
- **Frozen shipping evidence verified:** `task1004-fix1-evidence/runs/task1004-fix1-1cd1061244c54db38fb45c31b67aefde` contains successful sdist, extracted-sdist wheel, install, defaults, CLI and installed-adapter logs. The actual sdist is 626,648 bytes/SHA `770c2af3575d7e0ad05bc038ae0e6eeb1bf0de9803d9a00b524725493f723d74`; the actual wheel is 464,269 bytes/SHA `f23859d612b82c1036c05ddb837dccaccf70f77d863e65fc1b41ad8e93dedc7f`. Independently checked both artifact sizes/hashes. Installed logs retain ten product origins, final web/APP_JS identities, unchanged CSS, strict/legacy listening HTTP, PAGE substitutions and the updated owner-test/updater hash.
- **Archive/preservation verified:** all 38 new manifest rows and all 42 archive-index hashes match. The explicit `#byte17313` input is correctly handled as the report suffix, whose bytes equal archived `report-append.md`. The original report's 17,313-byte prefix, original review, saved pre-fix PR and original manifest/archive identities match their preserved hashes; all 181 old archive-index entries remain intact, accounting for 182 original files with the index itself. Original evidence was not overwritten.
- **Review limits:** no tests, browser, build, application runtime, Git commands or subagents were started. No unchanged source was re-reviewed; source access beyond the fix packet was file-hash bookkeeping. This remains the same reviewer's scoped fix round for BASE `dcaa0e5af6aedfca8685a3e64bea86ad0262f5c2` → HEAD `d1f056e86fcae2dcfaa01bbc7f97e79ca662faaa`.

### Out-of-Scope Observations

- None. The original full-task review and its stated verification/platform limits remain unchanged.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. T1004-R1 is closed; no findings remain open from the original task-scoped review.
