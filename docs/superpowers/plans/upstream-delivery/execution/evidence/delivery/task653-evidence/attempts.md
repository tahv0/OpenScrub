# Task653 attempt record

No runtime acceptance failure or discarded test run.

1. `git cherry-pick -x e96deb59e1b3c36585672be4c74d90eb6d0a49b5` returned1: benchmark/README.md and pyproject.toml content conflicts. Exact conflict state: p11b-conflicts.diff. Retained both guidance owners and recursive C01 metadata; continued9999f25.
2. `git cherry-pick -x 952af20da205133886ba69799e134b86d1654137` returned0, composed77e5130.
3. `git cherry-pick -x 9d888708d08cccf6e5f0ec8c9cf81740d3868fa1` returned1: same two metadata/guidance conflicts. Exact state: p11c-conflicts.diff. Retained both owners; continuedafe0fd4.
4. `git cherry-pick -x 17dfe5d575306dea395b680205038e606ad598a2` returned1: pyproject.toml content conflict. Exact state: n12-conflicts.diff. Retained C01 metadata; continued3a1dc0b.
5. Read-only native bundle `git diff --cc; cat tests/test_tail_history_index.py; cat tests/test_reverse_recall_index.py; cat tests/test_first_scan_sanity.py` returned1 because N12 had not yet been picked: `cat: tests/test_first_scan_sanity.py: No such file or directory`. No product execution occurred.
6. Read-only original-checkout bundle reading helper/rg followed by `cat tests/test_dense_smoothing_io.py`, `sed -n '85,125p' tests/test_report_roundtrip.py`, and root/private import grep returned2. The native-only test/private paths do not exist in the planning checkout (`No such file or directory`); corrected the cwd for subsequent reads. No product execution occurred.
7. New test initially committed07b344b with accidental space in one synthetic near-miss, then amended to117e41a before any config freeze, product import or test execution. The amendment changed only that fixture spelling to `zzzpqr#sample.invalid`. No failed/invalidated acceptance evidence exists for either earlier spelling.
8. Prepared actual-interpreter version identification, config freeze, helper preflight, discovery, acceptance3.12, acceptance3.9, static review and evidence harvest all returned0. Every run's complete output remains in this directory and the assigned runtime tree.

All shell calls used login:false. Original socket-capable invocations used the already authorized escalation. No escalation was rejected.

9. Initial final evidence status one-off script returned1 at line6 (`AssertionError`) because it compared `Path.iterdir()` run names in unsorted filesystem order to creation order. The directory list contains exactly the four expected completed runs; the helper lock was absent. This is evidence bookkeeping only. `finalize_evidence.py` now compares sorted names and records the idle process/lock state. Product source/configs and acceptance results were untouched; no acceptance rerun was warranted.
