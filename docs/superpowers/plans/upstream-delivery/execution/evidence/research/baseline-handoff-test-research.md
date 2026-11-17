# Baseline person-handoff test correctness research

The minimal correction is to replace the brittle `size jump` log assertion with
an explicit post-occlusion-sample assertion. Keep the existing geometric rejection
assertions, synthetic fixture, and `step_frames=1` unchanged. The corrected actual
test passes the unchanged production tracker and fails when only the size-jump
guard is disabled, observing adoption of the larger lookalike at 3.03s.

This is research for a **separate test-only upstream candidate after P01**. No
active worktree, product branch, shared dependency environment, or remote was
modified. No new dependencies/models were installed/downloaded. No permanent
production change is proposed or retained.

## Source and isolated execution

- Exported baseline: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
- Export: `/tmp/openscrub-handoff-research-20261116/snapshot`, from `git archive`;
  it has no Git checkout/branch relationship to the active P01 worktree.
- Interpreter, reused read-only:
  `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python`, Python 3.12.16;
  `opencv-python==4.14.0.94` (`cv2` 4.14.0), NumPy 2.5.5.
- Verified `openscrub.__file__` points to the exported snapshot, not the editable
  installation's active product checkout.
- Original/restored `openscrub.py` SHA256:
  `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`.
- Original `test_openscrub.py` SHA256:
  `a3d7cba98e99ef2131608e5f0413a96cfc0945f8ce59e7de5ef78d0bac7e33a5`.
- The baseline isolation helper was copied into this research directory, with its
  `ROOT` changed to the research root. Process-local environment overrides point
  imports, model cache, web data, pytest cache and fixtures exclusively there.
  `PYTHONDONTWRITEBYTECODE=1` remains enabled. App model downloads are blocked;
  the real tracker uses its existing fallback when VitTrack is unavailable.
- The existing test's stub detector is unchanged. Histogram comparison, tracking,
  decoding and geometric assertions use the real production implementations.

## Exact proposed test diff

[Preserved diff](baseline-handoff-test-research-artifacts/test-correction.diff):

```diff
--- a/test_openscrub.py
+++ b/test_openscrub.py
@@ -2332,8 +2332,8 @@
                                       StubDet(), logs.append,
                                       step_frames=1)
     assert s, "track must produce samples"
-    assert any("size jump" in m for m in logs), \
-        "the size-jump guard should refuse the engulfing look-alike"
+    assert any(q[0] >= 3.0 for q in s), \
+        "track must retain post-occlusion samples"
     a_area = (A[2] - A[0]) * (A[3] - A[1])
     b_area = (B[2] - B[0]) * (B[3] - B[1])
     # once the subject is hidden the track must FREEZE near the subject's
```

The following existing loop remains byte-for-byte unchanged: for every returned
sample at t>=3s, its box area must remain below half the sum of subject and
lookalike areas. Those fixture areas are 7,200px² and 19,500px², giving a 13,350px²
upper bound. The new assertion ensures this loop checks at least one sample,
preventing a vacuous pass if coverage ends early.

The original logging assertion is brittle because the ordinary appearance veto
already enters the held state near 2.9s. Subsequent size-jump rejection executes
while held; production intentionally suppresses the extra log with `if not held`.
That logging policy is not the geometric privacy behavior this test should pin.
Earlier observation evidence is in the [baseline report](../delivery/task-1-report.md).

## Mutation and results

Only this line was temporarily changed in the exported production file:

```diff
-                    if par > 1.8:
+                    if False and par > 1.8:
```

This bypasses only the suspicious-size guard; ordinary appearance checks and the
rest of the tracker remain active. Full contextual
[mutation diff](baseline-handoff-test-research-artifacts/guard-disabled.diff).

| Exported state | Result | Evidence |
|---|---|---|
| Original test, unchanged tracker | Exit 1; 1 failed in 0.54s; missing `size jump` log | [original.log](baseline-handoff-test-research-artifacts/original.log) |
| Corrected test, unchanged tracker | Exit 0; 1 passed in 0.48s | [revised.log](baseline-handoff-test-research-artifacts/revised.log) |
| Corrected test, size guard disabled | Exit 1; 1 failed in 0.53s; larger target adopted | [mutant.log](baseline-handoff-test-research-artifacts/mutant.log) |

The mutation fails at the retained area assertion, not the new existence check:

```text
AssertionError: track grew to the look-alike's box (area=19500) at t=3.03s — the larger person was grabbed
assert 19500.0 < (0.5 * (7200 + 19500))
```

After the mutation run, the temporary production file was restored byte-for-byte
to the exported baseline and its SHA256 rechecked. The corrected test/diffs/logs
remain only as research artifacts. No full-suite rerun was performed for this
bounded experiment; the three results above are focused runs of the actual test.
The previous full baseline run remains documented separately (133 passed, one
pre-existing failure in this environment).

## Exact setup and run commands

Initial export, from the original repository (read-only Git operation):

```bash
mkdir -p /tmp/openscrub-handoff-research-20261116/snapshot /tmp/openscrub-handoff-research-20261116/helpers
git archive 5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f | tar -x -C /tmp/openscrub-handoff-research-20261116/snapshot
```

The preserved helper and process-local setup can be staged without altering the
shared environment:

```bash
cp /home/tahv0/src/OpenScrub/.superpowers/sdd/README/baseline-handoff-test-research-artifacts/baseline_isolation.py /tmp/openscrub-handoff-research-20261116/helpers/
cp /home/tahv0/src/OpenScrub/.superpowers/sdd/README/baseline-handoff-test-research-artifacts/env.sh /tmp/openscrub-handoff-research-20261116/
cd /tmp/openscrub-handoff-research-20261116/snapshot
. /tmp/openscrub-handoff-research-20261116/env.sh
```

That `env.sh` sources the existing OpenCV 4 environment and then overrides
`PYTHONPATH` with research helpers/snapshot and `OPENSCRUB_BASELINE_MODEL_DIR` with
the separate research cache. For all stages, the selector remains identical:

```bash
# Original exported files:
python -m pytest test_openscrub.py::test_track_person_size_jump_handoff -q --basetemp=/tmp/openscrub-handoff-research-20261116/pytest-original -o cache_dir=/tmp/openscrub-handoff-research-20261116/cache-original > /tmp/openscrub-handoff-research-20261116/original.log 2>&1

# Apply only the proposed test diff, keeping production unchanged:
patch -p1 < /home/tahv0/src/OpenScrub/.superpowers/sdd/README/baseline-handoff-test-research-artifacts/test-correction.diff
python -m pytest test_openscrub.py::test_track_person_size_jump_handoff -q --basetemp=/tmp/openscrub-handoff-research-20261116/pytest-revised -o cache_dir=/tmp/openscrub-handoff-research-20261116/cache-revised > /tmp/openscrub-handoff-research-20261116/revised.log 2>&1

# Temporary production mutation, strictly within this exported snapshot:
patch -p1 < /home/tahv0/src/OpenScrub/.superpowers/sdd/README/baseline-handoff-test-research-artifacts/guard-disabled.diff
python -m pytest test_openscrub.py::test_track_person_size_jump_handoff -q --basetemp=/tmp/openscrub-handoff-research-20261116/pytest-mutant -o cache_dir=/tmp/openscrub-handoff-research-20261116/cache-mutant > /tmp/openscrub-handoff-research-20261116/mutant.log 2>&1
patch -R -p1 < /home/tahv0/src/OpenScrub/.superpowers/sdd/README/baseline-handoff-test-research-artifacts/guard-disabled.diff
```

In the executed experiment, exact guarded Python string replacement generated the
two diffs and the mutation was restored from the saved original bytes; `patch`
commands above are equivalent reproduction commands for the retained exact diffs.
[Environment/import provenance](baseline-handoff-test-research-artifacts/environment.json)
and [result summary](baseline-handoff-test-research-artifacts/results.json) are
preserved alongside the logs.

## Recommendation

Make a separate tiny test-only branch after P01, replacing the two-line logging
assertion exactly as above. Retain the fixture, stepping contract and area checks;
include this mutation evidence in that candidate's review notes. Run the normal
full suite on that eventual branch before claiming it green. Do not include the
temporary production mutation, dependency constraints, research helpers or Save As
changes in that test-correctness candidate.
