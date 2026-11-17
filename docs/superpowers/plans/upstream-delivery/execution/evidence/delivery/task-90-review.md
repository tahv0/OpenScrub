# Task 90 review — B02a handoff regression

Spec-compliance verdict: **PASS**.

Code-quality verdict: **PASS**. No severity/file-line findings; no revisions required.

Reviewed Austin base `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f` to head `e21ebdf6e3ee46e6c65050dc956a9a3459152269` on `pr/tracker-handoff-regression`, against `task-90-brief.md`, `baseline-handoff-test-research.md`, `task-90-report.md`, and the retained artifacts. Read-only Git inspection independently confirms the head, direct parent, clean worktree, and one-file diff containing exactly two insertions and two deletions. `git diff --check` passes.

At `test_openscrub.py:2335–2336`, the correction replaces the diagnostic expectation with an explicit requirement for at least one sample at t≥3.0s. The existing area loop uses the same time predicate, so it cannot pass with zero post-occlusion samples. The subject is hidden from 2.9s; the look-alike is present through 4.0s. The unchanged loop at `test_openscrub.py:2341–2347` rejects every sampled post-occlusion box whose area reaches the midpoint of the subject/look-alike areas: (7,200 + 19,500)/2 = 13,350px². The fixture, real tracker call, `step_frames=1`, and explanatory contract remain unchanged.

The production guard at `openscrub.py:2236–2260` suppresses its diagnostic when already held, confirming that a required log was brittle. Retained `red.log` records the original failure at the removed assertion; `green.log` records the revised focused test passing. `mutant.log` records the corrected test passing the existence assertion and failing the retained geometry assertion at `test_openscrub.py:2344`: actual larger-box adoption, area 19,500px² at 3.03s. Together with the documented one-line guard bypass and snapshot import provenance, this supports sensitivity to removal of the size guard while the ordinary appearance checks remain enabled. An unrelated appearance veto therefore did not conceal that mutation in the recorded environment.

Restoration evidence records byte-identical snapshot restoration in `mutation-results.json`. Independently hashing the active checkout's `openscrub.py` yields `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`, matching the original/restored hashes and artifact verification. No production source, threshold, logging policy, dependency, version, model, Save As feature, skip, or xfail change travels in this patch.

Retained `full-suite.log` supports **134 passed**, without skips or xfails; `build-network.log` supports successful default sdist then wheel-from-sdist builds. `artifact-verification.json` records final test bytes in the sdist and unchanged runtime bytes in both artifacts. These are reviewed execution records, not reviewer reruns. No focused, full-suite, or build execution was necessary to resolve an unanswered doubt, and none was performed during review. The recorded validation remains limited to synthetic media in the stated Linux/Python 3.12/OpenCV 4 environment; the separately documented OpenCV 5 compatibility problem is outside this correction.

Review operations were read-only against the product checkout. Only this SDD review document was written; no product/Git mutation, remote operation, real user data access, or subagent delegation occurred.
