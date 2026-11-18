## Task 16331: clarify recovery-stage cleanup wording

### Global constraints, what, why and when

Comment-only follow-up for inherited P M1 after approved P publication. Preserve all executable ASTs, signatures/defaults/runtime behavior and Python>=3.9. No tests to mirror a comment, dependency, data, environment, publication or nested-agent work. The current comment says the report context is not exited while _stack.close() immediately follows; this wording misstates correct cleanup ownership and should be corrected before focused P submission.

Root will create pr/render-recovery-comment from exact a132081f1e609ed19deb4477044ee1c9b77871cc only after Task51's review, using the same isolated worktree sequentially. Do not change pr/render-output-publication or the reviewed combined ref.

Assigned managed source worktree: /home/tahv0/.codex/worktrees/bde3/OpenScrub. Root-created proof/evidence paths: runtime/task16331 and task16331-evidence in the SDD workspace; no product workload is needed.

### Scope and verification

Modify only the misleading comment at openscrub_internal/render_delivery.py:188. Explain accurately that closing the ExitStack discards expendable report staging while recovery retains the required backup/final paths and recovery descriptor. Inspect the actual nearby implementation before choosing wording; do not claim that needed recovery material is removed or that the context stays open.

- [ ] Change only comment text.
- [ ] Programmatically compare complete parsed AST against exact base; all executable code and docstrings remain identical. Verify one-file/comment-only diff, unchanged public signatures/metadata and git diff --check.
- [ ] Do not replay functional suites, media, browser or package builds for this non-executable change.
- [ ] Commit/self-review and write task-16331-report.md/task-16331-pr.md plus a tiny source/diff/AST proof. Fresh root-assigned review checks wording and ownership before any integration cherry-pick/publication.

Task16331 is prepared only until root fills its branch/runtime/brief; Task51 runs first. All branches and user runtime data remain preserved.

