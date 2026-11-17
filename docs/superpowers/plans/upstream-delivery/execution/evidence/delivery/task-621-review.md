### Spec Compliance

- ❌ Issues found: P06B.1 does not yet cover every operation within the vault tree, and render's secondary ownership can protect a different source from the one actually selected by the engine. Both are Important blockers below.
- Reviewed base `3795d49f6293baf7b8c35534862a4881447e1b16`, head `4479b57612f4e5c463d31900f76277a5fcebb8a9`, using the supplied eight-file diff package. Product references below are relative to the frozen `/home/tahv0/.codex/worktrees/c832/OpenScrub` head.
- ✅ The implementation otherwise follows the selected scope: a small existing-namespace helper (`openscrub_internal/lifetimes.py:17`), guarded admissions and live identity checks (`openscrub_web.py:331`), ownership-aware deletion (`openscrub_web.py:1206`), closed transition/recovery state (`openscrub_web.py:3615`, `openscrub_web.py:3703`), and an engine capture-finally extension (`openscrub.py:2469`, `openscrub.py:2715`). No transaction/generation-publication system or unrelated runtime package is added in the diff.
- ⚠️ Cannot verify from diff: actual Windows/macOS file-sharing behavior, actual frozen executables, container execution, or TLS/proxy disconnect handling. The implementer explicitly discloses these limits in `task-621-report.md`; the controller should retain them. Linux socket evidence is not evidence for those platforms.
- ⚠️ Broader upstream-default/privacy/release-preservation assertions span unchanged code and prior tasks. No conflicting change appears in this diff; this task-scoped review does not independently recertify the whole application. In-process scope and the deferred lost-update/replay/cancel-publication semantics are correctly disclosed in `task-621-report.md`.

### Strengths

- `openscrub_internal/lifetimes.py:35` and `openscrub_internal/lifetimes.py:64`: one lease abstraction makes release idempotent, includes secondary owners, and closes the underlying streaming iterator before releasing file ownership. The implementation remains compact and does not become a service framework.
- `openscrub_web.py:750`, `openscrub_web.py:804`, `openscrub_web.py:1315`: queue reservations, pickup and cancellation share the admission guard; stale ticket identity and idempotent release protect immediate retry. `tests/test_job_lifecycle.py:245` exercises the actual cancel-before-submission schedule, and `tests/test_job_lifecycle.py:405` covers worker-owned cleanup after cancellation.
- `openscrub_web.py:1045` and `tests/test_job_response_lifetime.py:17`: response ownership transfers into the iterable rather than ending at handler teardown. The new real configured Cheroot/socket schedules check Range headers and exact bytes, active delete/lock refusal, iterator failure, disconnect, and exactly-once release.
- `openscrub_web.py:3615`, `openscrub_web.py:3642`, `openscrub_web.py:3703`: the shared guarded busy decision and explicit closed/error state address partial transitions and signal-hook self-deadlock. `tests/test_job_lifecycle.py:196`, `tests/test_job_lifecycle.py:345`, and `tests/test_job_lifecycle.py:387` exercise held locks, delayed unlock/registration and failed recovery.
- `tests/test_job_lifecycle.py:90`: real report staging, atomic publication, encryption and exact-byte reopening are preserved in a bounded route schedule. `tests/test_job_lifecycle.py:519` exercises marker/retry and fresh rehydration instead of replacing deletion with a miniature model.

### Issues

#### Critical (Must Fix)

- None identified.

#### Important (Should Fix)

1. **Render does not reserve the original input that the engine actually reads.** `openscrub_web.py:357` derives a secondary lease only from `job["video"]`; `openscrub_web.py:935` passes that snapshot into the render engine. The unchanged engine then reads `provenance.original_input` and replaces `args.video` before normalization (`openscrub.py:8541`). In the ordinary cross-job normalization case, job B's video is now its own CFR/SDR copy while `original_input` remains job A's file. B therefore owns only B during render, and A can be deleted or retained while normalization/hash/decoding needs A. This directly misses the brief's requirement to protect the actual source chosen during normalization/source selection, including queued and worker work.

   Focused actual-route evidence: `/tmp/openscrub-task621-review/test_uncovered_owners.py:23` creates that synthetic report shape, POSTs B's real render route, runs the real queue worker and real `run_pipeline`, and pauses only at the normalization computational boundary. The engine-selected input is A's file, B is `rendering`, yet real DELETE A returns **200** and removes the source; expected **409** fails. Evidence: `/tmp/openscrub-task621-review/uncovered-owners.log:3`. Reserve the live containing job for the selected original source before its first stat/read and keep it through queue/worker cleanup, deduplicating aliases/self. Ensure the engine cannot switch to a subsequently unprotected source. Add the corresponding actual-route deletion/retention regression with normalized input and original provenance; a simple `job["video"]` dependency case is insufficient.

2. **The shared allowlist still bypasses admission and can create plaintext after a successful lock.** `openscrub_web.py:1026` admits only paths beginning `/api/jobs`; unchanged `/api/allowlist` uses `JOBS_DIR/allowlist.txt` (`openscrub_web.py:1914`) and writes it directly (`openscrub_web.py:1930`). The entire file is inside the encrypted tree: `openscrub_vault.py:164` encrypts every non-encrypted file under the root. The route has neither a store lease nor a closed-vault check, so it can race encryption or write plaintext after encryption finishes. This is the same missed tree-writer class that store-wide admission is intended to eliminate, and the shared file can contain user names.

   Focused actual-route evidence: `/tmp/openscrub-task621-review/test_uncovered_owners.py:10` enables and locks the real vault, then POSTs the real allowlist route. It returns **200**, `vault_locked()` remains true, and a plaintext `allowlist.txt` containing the synthetic name exists; expected **423** fails. Evidence: `/tmp/openscrub-task621-review/uncovered-owners.log:1`. Admit both allowlist reads and writes through store ownership before any existence check/open, preserving existing API behavior while ready and rejecting closed transitions. Add a bounded write-versus-lock schedule and locked-state regression.

#### Minor (Nice to Have)

- None identified beyond the blockers.

### Checks and Evidence Limits

- Read the supplied diff once in five bounded passes, plus the brief, report, task-reviewer template and the research's lifecycle/lock-order contract. No Git operations, product edits or subagents; only this requested review file and synthetic diagnostics under `/tmp/openscrub-task621-review` were written.
- Named outside-diff check — **lock inversion / worker ownership:** inspected the unchanged watchdog, update admission and startup call sites (`openscrub_web.py:967`, `openscrub_web.py:3517`, `openscrub_web.py:4328`). Their JOBS_LOCK regions do not call the new lifecycle gate while holding that mutex. Startup rehydration precedes worker/server startup. This check did not disclose another inversion.
- Named outside-diff check — **actual render source selection:** inspected unchanged `build_args`, `run_pipeline` and normalization entry (`openscrub_web.py:552`, `openscrub.py:8519`, `openscrub.py:6517`) because the new leases snapshot only the job's current video. This established Important issue 1; it was then confirmed by the focused schedule above.
- Named outside-diff check — **shared tree writer bypass:** the JOBS_DIR sink search identified unchanged `/api/allowlist`; inspected that one route and `encrypt_tree` (`openscrub_web.py:1913`, `openscrub_vault.py:164`) to establish that the unowned file is actually encrypted by vault transitions. This established Important issue 2.
- Named outside-diff check — **HEAD/304 response closure:** inspected the installed Werkzeug `Response.get_app_iter` and `Response.close` contract. Empty-body responses use a ClosingIterator calling response.close, which closes the wrapped OwnedIterable; the suspected lease leak is not present. No extra socket schedule was run.
- Read existing success artifacts, without rerunning successful validation: `/tmp/openscrub-task621/full-final3.log` (284 passed, clean output), `python39-focused.log` (54 passed, clean output), `build-final2.log` (sdist → wheel success), `packaging-final-head.log` (exact head/source bytes, static inclusion checks), and `installed-startup-final3.log` (installed CLI/web/vault/idle shutdown success). These artifacts support the reported checks, but do not cover the two additional schedules.
- Only new execution: two targeted synthetic actual-route diagnostics in the supplied compatible isolated environment. Pytest reported **2 failed in 0.41s**, each for the specific required status assertion above; both fixtures ended with zero ownership and the render worker was explicitly joined. Full output and reproducible diagnostic source are retained under `/tmp/openscrub-task621-review`. No broad suite/build/socket rerun was performed.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The lease, queue handoff and stream-close design is cohesive and substantially tested. Two real file owners remain outside the correct lifetime boundary, so the task's promised encryption/deletion safety cannot yet be trusted across its required scope.
