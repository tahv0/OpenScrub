## Task 108: reject malformed and non-object scan options before job creation

### Global constraints

Preserve Austin upstream defaults, Python>=3.9, ordinary upload/server-path input behavior, current privacy fixes and accepted option-object semantics. No training, learned models, expanded review workbench, dependency/version changes or runtime helper package for this small guard. New tests belong in `tests/`. No original-checkout or user-data changes, remote publication or subagents.

### What, why and when

The actual shared multipart `options` boundary returns HTML500 for malformed JSON and queues valid JSON scalars/arrays/null that cannot be consumed by `build_args`. Give these invalid inputs a clear JSON400 before any durable job side effect. This is a small independent W1 reliability PR, using only the generic guard separated from donor `cd1786880f602e479d5666bef0ba90c8b03697de`. No learned/narrow-specific validation is included.

The supervisor will create `pr/scan-options-validation` in `/home/tahv0/.codex/worktrees/c832/OpenScrub` from exact Austin-plus-test-only base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` before dispatch. Read only `options-input-baseline-research.md` and its compact evidence as needed. The completed36-case baseline already establishes the issue; do not repeat its whole research pass. This task must integrate with P06 lifecycle changes later, but does not copy their implementation into this independent branch.

### Implementation contract

1. In the shared actual `create_job` route, decode `request.form.get("options", "{}")` once, catching the malformed JSON boundary, and require a `dict`. Return HTTP400 JSON `{"error":"Scan options must be a JSON object."}` for malformed/empty/whitespace JSON and every non-object, including falsey arrays/null/strings/zero/false. Do not use `json.loads(...) or {}`. Do not catch unrelated job creation or file errors under this validation response.
2. Validate before `new_job`, input copying, writing `options.json`, JOBS registration or enqueue. Normal framework multipart form parsing/spooling remains outside that durable-job guarantee. Keep current file-presence/path/type/auth/vault/disk-room checks and their ordering except for this existing shared options boundary.
3. Omitted options still means `{}`. Explicit `{}`, ordinary supported settings, nested unknown keys and the existing unknown-key policy remain accepted/persisted exactly. Do not introduce semantic per-key validation, new scan defaults, model selection or a settings framework.
4. Keep the product change local to `openscrub_web.py`. Add meaningful actual registered-route regressions to `tests/test_scan_options.py`, with task-local synthetic jobs and input. Do not test a miniature parser/route or add tests that merely assert source strings. Update the existing test discovery/contributor commands and sdist inclusion only as needed to include this first branch-local tests directory, using the established pattern from reviewed P06A/P07a branches. Do not add CI infrastructure.

### Evidence and delivery

- Observe owning RED cases on the original branch: malformed JSON gets500; falsey/nonfalsey non-object gets200 with a queued unusable value. Cover both multipart upload and server-path forms in the final regression. Use actual application parsing and route admission, with worker/inference execution prevented; no model downloads.
- Assert HTTP400 JSON and no durable files/job registration/queue work for invalid payloads. Valid controls must verify exact stored options/input hashes, relevant unchanged `build_args` defaults/settings and existing cancel/delete cleanup. Do not claim a worker execution or permanent leak was reproduced.
- After focused RED→GREEN, run the full discovered suite once at stabilized source, sdist→wheel and packaged source/tests inclusion. Use `/tmp/openscrub-baseline-20261116/env-opencv4.sh`. Run focused new cases against active source on Python3.9 using `/tmp/openscrub-python39-20261117/env.sh` with explicit import-path assertions. Reuse already installed tools; no environment/model/dependency changes.
- Run a bounded real loopback HTTP multipart invalid/valid pair through the configured server and clean installed CLI/web startup, retaining exact requests/statuses and cleanup. No browser work is needed for this server input guard. Generated artifacts live under `/tmp/openscrub-task108`, not the repository.
- Self-review and commit the coherent change. Write `task-108-report.md` and `task-108-pr.md` in `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/` with exact base/head, RED/GREEN/full/build/floor/HTTP evidence, changed files and practical limits. Lead the PR with invalid scan options receiving a clear400 before a job is queued. No push or publication.

Native worktree/Git writes may require `require_escalated`; local edits/commits are authorized. Keep root-workspace planning documents untouched except your designated report/draft. Ask the supervisor about concrete unresolved scope rather than dispatching helpers or changing other branches.
