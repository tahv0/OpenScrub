## Task 116: make scan-report test coverage wording precise

### What, why, when and constraints

Comment-only follow-up to the accepted N12 minor before focused upstream submission. Base17dfe5d575306dea395b680205038e606ad598a2; root creates pr/scan-sanity-test-comment in the managed bde3 source worktree after Task16331 review. Preserve original pr/no-backtrack-scan-sanity, C01 and all previous refs. No production behavior/default, test assertions, dependencies, data or publication changes.

Assigned source /home/tahv0/.codex/worktrees/bde3/OpenScrub; root proof/evidence paths runtime/task116 and task116-evidence. Preserve Python>=3.9.

Modify only the comment near tests/test_first_scan_sanity.py:105. Current wording says Detection fields/report choices are pinned including order; dict equality verifies fields/values and list order but not each row's key order. Narrow that claim accurately; do not add key-order assertions or change serialization.

- [ ] Read exact surrounding assertions; change only the comment wording.
- [ ] Prove complete parsed AST including docstrings and non-comment tokens equals exactbase; retain both source hashes, one-file/comment-only diff, Python3.9 grammar and git diff --check.
- [ ] No runtime/pytest/media/browser/package replay or new tests for this non-executable change.
- [ ] Commit/self-review; write task-116-report.md/task-116-pr.md and tiny task116-evidence. Root assigns fresh independent review. No integration-ref advancement/publication.

Use separately supplied local execution notes; source/runtime/evidence paths are root-assigned before dispatch and private execution-control material stays outside product evidence.

