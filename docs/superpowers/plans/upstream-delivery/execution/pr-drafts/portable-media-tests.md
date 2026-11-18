# Let optional media tests write artifacts without local setup

The retained exact-media and strict-route tests can finish their product assertions and then fail with KeyError when VERIFY_RUN is unset. A small shared test helper now writes to pytest's temporary directory in that case. Explicit output roots retain their existing logs paths, filenames and JSON payloads.

The patch changes four files under tests and adds six real-filesystem cases for missing/empty configuration, explicit output, independent destinations, idempotent reuse and filesystem errors. Application code, defaults, assertions, dependencies and build settings remain unchanged. The helper uses the existing tests sdist include and stays out of the runtime wheel.

Validation at `d3d02770b8a42575236b11309b5a334170f7ec89`: frozen native full 566 passed; actual Python 3.9 affected fallback 48 and explicit 48 passed; offline native sdist→extracted-source wheel/install/defaults/both CLI checks passed. The original failure was reproduced in seven unchanged real-media owners, and all four owned sdist/extracted-source hashes were checked. Independent review approved with no findings.

Depends only on the owning exact/strict tests at BASE `6fde5ad60c6d78d69dbbd8e049a9196f15e4095f`. It can accompany that contribution if a separate tooling stack adds unnecessary work. Unrelated PRs need no dependency, rebase or repeated validation.

[Final acceptance](../evidence/delivery/task-10110-final-acceptance.md).

A [matched seven-case measurement](../measurements/portable-media-tests.md) ran three old/new pairs on the same Python3.9 inputs: every sample passed, with no retries, and all seven evidence files preserved their deterministic semantics. Pytest medians were1.46s old and1.45s new; this does not establish a repeatable speed gain. The explicit output recipe drops two setup commands (environment assignment and directory creation); this is an action count, not measured human-time savings.
