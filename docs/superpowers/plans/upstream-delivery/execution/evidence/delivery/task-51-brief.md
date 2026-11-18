## Task 51: pin preview cache headers over real configured HTTP

### Global constraints, what, why and when

Test-only follow-up after reviewed P05. Preserve Austin defaults, all production bytes, Python>=3.9, actual preview complete-generation/ETag/Range semantics and existing fixture assertions. No training/workbench, dependency, helper/environment change, benchmark, user-data change, publication or nested agents. This closes Task5's explicit missing Last-Modified/If-Modified-Since controls before focused upstream submission.

Root creates pr/live-preview-cache-regressions from exact b70d42011168192cdf7a9ef93a5e9419a92a1cdb. Preserve original pr/live-preview-snapshots, integration/upstream-focused and every old candidate. Assigned managed source worktree is /home/tahv0/.codex/worktrees/bde3/OpenScrub; keep documentation worktree /home/tahv0/.codex/worktrees/c832/OpenScrub intact; mutable scratch is /home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task51/runs, created by root.

### Exact scope and interfaces

Modify only tests/test_live_preview.py. Reuse its actual preview/publish/http/assert_jpeg fixtures. The http fixture runs production _serve and actual configured Cheroot sockets, returning status, response headers and body and owning stop/join. Do not replace it with a test-client shortcut. Existing test_http_missing_conditional_range_and_changed_etag remains intact.

Add test_http_ignores_modified_since_without_last_modified(preview, http, modified_since), parameterized over the two dates below, proving a successful published preview has no Last-Modified header, compared case-insensitively, and that If-Modified-Since alone produces complete status200, exact JPEG bytes, correct length and same content ETag. Cover both a valid old HTTP date (Thu, 01 Jan 1970 00:00:00 GMT) and a valid future HTTP date (Fri, 01 Jan 2100 00:00:00 GMT). Retain existing ETag304/Range/If-Range behavior; do not add or change production cache policy. The existing behavior is correct: this is missing regression coverage, so no artificial failing runtime mutation/RED is required. A newly exposed actual product failure must be reported to root before expanding beyond tests.

### Verification and delivery

- [ ] Inspect exact base, existing owner fixtures and prepared source-isolation handoff; declare actual base/module/test/adapter hashes rather than copying C01 private-module inventory.
- [ ] Add the two bounded header cases, using actual complete expected JPEG bytes and no timing/performance claim.
- [ ] Freeze a clean source/test commit and run the complete owning tests/test_live_preview.py on actual prepared3.12.16, serial helper-owned scratch, original-call socket escalation, login:false.
- [ ] Run the new exact header cases on actual prepared3.9.25 (whole owner file only if within the same declared allowance). Retain real source/interpreter/exit identities and all failures. Do not rerun unrelated full suites, browser matrices, media or models.
- [ ] Verify only this test file changed, all production/metadata/recipe bytes equal base, Python3.9 grammar, git diff --check and existing recursive sdist inclusion for the same test path. No new package artifact/build/startup claim is needed for a test-only follow-up with unchanged runtime and recipe; original P05 package evidence remains at its original ref.
- [ ] Self-review, commit and write task-51-report.md, task-51-pr.md and compact task51-evidence (commands/logs/source/fixture identities; no media/env/export/install or private local guard material). Explain what/why/upstream timing and test-only scope. Root assigns fresh independent review; no working integration-ref change or publication by implementer.

Use the unchanged canonical verification launcher and separately supplied local execution instructions; keep those private notes outside product evidence. No downloads or shared environment/helper edits.

