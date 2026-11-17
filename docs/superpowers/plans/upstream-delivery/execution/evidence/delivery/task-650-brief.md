## Task 650: assemble the reviewed reliability, progress and smoothing candidates

### Global constraints

This is the first intermediate C01 integration gate, not completion of C01/C02, an umbrella upstream PR or adoption of a new working environment. Preserve individual PR refs and original checkout/data/archive. No publication, remote operations, custom training/workbench/Findings/journal/section imports, changed defaults, optional models or nested agents. Product assembly only in the designated native worktree. Keep conflicts and necessary integration corrections small and documented.

### What, why and when

The report prerequisites were previously combined and reviewed at3795d49, then lifetime/transaction/manual replay changes were reviewed at12919c9. Independently reviewed Save As, preview, ETA, options validation and dense-smoothing changes now need a combined runtime check, particularly preview callbacks/response ownership and browser save/download state. Run this local integration before expanding UI features. It fulfills C01's meaningful-batch smoke gate; final selected application acceptance and optional default equivalence still follow later.

Supervisor creates `integration/upstream-focused` from exact `12919c96c6f7558136b50d7b4d85e5e6b62f1971` before dispatch. It already includes B02a, P06A/D, P07a, P06B.1/2 and P07b. Apply only these individually reviewed commits with provenance, in order:

1. P01 Save As: `ca0f2ce7458347afd2e6156a97df580b6623767a`.
2. P11A dense smoothing: `f19be5fe3b9176e568ea7bf761493bd267fee95e`.
3. N08 options validation: `e34313e1b136254fb2777cabb385f2097a54935a`, then `b26b6685b237ba1c4caffaaefb47b029a3205b51`.
4. P05 live-preview snapshots: `b70d42011168192cdf7a9ef93a5e9419a92a1cdb`.
5. P04 recent ETA: `d129e23e5fe144edb8bbd5675809c1877cfe4d0f`.

Use the source/diff of those explicit commits; only read their task reports as needed for interfaces/evidence, not the whole plan or unbounded history. If a product correction beyond a routine conflict is needed, reproduce it, describe the owning contract and keep it separate from provenance-preserving cherry-picks. Do not copy unrelated candidates. Keep tests/ discovery and complete documentation commands rather than retaining conflict markers or duplicate entries.

### Integration contract and verification

1. Preserve P05 whole-generation preview publication/response together with P06B admission/lifetime protection. Exercise actual scan callback→preview HTTP while publishing, cancelling and attempting delete/vault transitions at bounded held-response/work boundaries. A response-owned completed in-memory preview still needs its existing request ownership correctly released. No long transfer lock or lock-order inversion; no output video atomicity claim (P16C remains separate).
2. Preserve P01 per-job/kind streaming-download ownership, accepted-byte progress and final close state alongside P07a save drafts/acknowledgements. Exercise real emitted UI with actual HTTP and the already-used controlled File System picker/real OPFS boundary; include newer edits/job switching while response/save pending, failed save and held download close, without repeating all standalone browser cases. Verify correct job/file and no unintended render after failed save.
3. Use a small synthetic actual scan→review→save→render→export→fresh-process reopen flow, keeping all ordinary rows/audio/additive fields and selected/kept pixels. Controlled OCR/model inputs at existing boundaries are allowed and must be labelled; use no new models. Exercise cancellation/retry, file ownership and replay after a committed response loss at their actual boundaries. Run a modest1000-row real save/reopen smoke, not a new save-performance benchmark.
4. Verify unchanged default settings and no removed-system module/routes/dependencies in the combined source/package. Preserve Austin's queue/watchdog/parser/fallback/ordinary review behaviour; external dependency OpenCV5 remains the separate B02b candidate, validation environment constraint only here.
5. Run the full discovered suite once after stable conflict resolution, sdist→wheel and exact packaged source/test/JS/Python-floor metadata checks; fresh installed CLI/web/real server smoke. Run focused active-source Python3.9 integration checks, accurately distinguish them from whole-app floor certification. Reuse passed standalone benchmarks; no repeat dense-smoothing timing or general long/4K performance claim unless a new conflict concern requires it. Existing tests cover its default/frame/cancellation contract.
6. Keep final readiness Minors separate unless this integration directly touches their owners: P04 missing-preview/extraction-harness noise (use a real tiny preview and explicit supported archive filter here), P05 date-validator test suggestion, P06A evidence-script deprecation, standalone P07a contributor-command omission and P11A publication evidence attachment are tracked. Do not claim those PRs changed merely because assembly docs are correct.

### Delivery

Artifacts `/tmp/openscrub-task650`; use prepared env-opencv4.sh, Python3.9 env and isolated Playwright/Chromium fallback (browser plugin unavailable), all imports asserted. Native/Git writes may use already-authorized require_escalated. No global installs or user data. Record all conflict decisions, exact before/after/cherry-pick mapping, changed integration-only behaviour, actual versus controlled runtime boundaries, commands/results and limits in `task-650-report.md`; write concise local acceptance record `task-650-acceptance.md` rather than an umbrella PR draft. Commit and self-review. Return short status/head/tests/concerns. Supervisor performs a fresh task-scoped integration review; final whole-branch review/C01 and C02 remain open.
