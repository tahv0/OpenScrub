# Task 90 — B02a size-jump handoff regression reliability

Status: **DONE**. Local commit `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, branch `pr/tracker-handoff-regression`, native worktree `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Parent is the unchanged Austin baseline `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. The committed diff contains only `test_openscrub.py` (2 insertions, 2 deletions); the worktree is clean. P01/Save As is absent. No remote writes, user data access, new models or subagents.

## Change and rationale

At `test_openscrub.py:2335–2336`, replace the `size jump` diagnostic assertion with `any(q[0] >= 3.0 for q in s)` and the explanation `track must retain post-occlusion samples`. [Exact diff](task-90-artifacts/test-correction.diff).

The existing synthetic 150-frame video, detector stub, real tracker invocation, `step_frames=1`, docstring and area loop remain unchanged. Appearance rejection can put the tracker into held state before a suspicious size jump; production intentionally suppresses repeated diagnostics while held. Geometry is the observable safety contract. Requiring at least one sample at t≥3.0s prevents the existing area loop from passing vacuously. Subject/look-alike areas are 7,200/19,500px²; every post-occlusion sample must remain below their 13,350px² midpoint.

## Environment and isolation

Reused `/tmp/openscrub-baseline-20261116/env-opencv4.sh` and its interpreter read-only. Python 3.12.16; `opencv-python==4.14.0.94` (`cv2` 4.14.0), NumPy 2.5.5, pytest 9.2.0, build 1.6.1. Isolated builds resolved hatchling 1.33.0. [Complete package/import evidence](task-90-artifacts/environment.json).

Task-local root `/tmp/openscrub-task90-20261116` holds synthetic media, application data, model cache, pytest cache and artifacts. [Environment](task-90-artifacts/env.sh) overrides `PYTHONPATH` so imports resolve this native worktree rather than the environment's editable installation. [Isolation plugin](task-90-artifacts/baseline_isolation.py) relocates application data and blocks model network fetches. `PYTHONDONTWRITEBYTECODE=1` is inherited. The existing pinned YuNet cache was copied read-only from the baseline environment into the task cache, SHA256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`. No model was downloaded. VitTrack remains unavailable, using the real tracker fallback as in prior research.

## Commands and observed results

All active-tree commands ran from the native worktree after:

```bash
. /tmp/openscrub-task90-20261116/env.sh
```

That wrapper first sources the required OpenCV 4 environment, then overrides only task-local import/model paths. RED ran before editing the file:

```bash
python -m pytest test_openscrub.py::test_track_person_size_jump_handoff -q --basetemp=/tmp/openscrub-task90-20261116/pytest-red -o cache_dir=/tmp/openscrub-task90-20261116/cache-red
```

Exit 1: **1 failed in 0.61s**, specifically the absent `size jump` log. [RED log](task-90-artifacts/red.log). The original test SHA256 was `a3d7cba98e99ef2131608e5f0413a96cfc0945f8ce59e7de5ef78d0bac7e33a5`.

After the two-line edit:

```bash
python -m pytest test_openscrub.py::test_track_person_size_jump_handoff -q --basetemp=/tmp/openscrub-task90-20261116/pytest-green -o cache_dir=/tmp/openscrub-task90-20261116/cache-green
```

Exit 0: **1 passed in 0.47s**. [GREEN log](task-90-artifacts/green.log).

### Mutation sensitivity and restored source

The baseline was exported using `git archive HEAD | tar -x -C /tmp/openscrub-task90-20261116/mutation-snapshot`, and the corrected test was copied into it. An inline Python runner saved the original `openscrub.py` bytes, required exactly one match for `                    if par > 1.8:`, replaced it with `                    if False and par > 1.8:`, and executed the following command via `subprocess.run` with its working directory and `PYTHONPATH` pointing to that snapshot:

```bash
PYTHONPATH=/tmp/openscrub-task90-20261116/helpers:/tmp/openscrub-task90-20261116/mutation-snapshot python -m pytest test_openscrub.py::test_track_person_size_jump_handoff -q --basetemp=/tmp/openscrub-task90-20261116/pytest-mutant -o cache_dir=/tmp/openscrub-task90-20261116/cache-mutant
```

Exit 1: **1 failed in 0.62s**, at the retained geometry assertion: `track grew to the look-alike's box (area=19500) at t=3.03s`. This is actual larger-box adoption with the remaining appearance checks active, demonstrating that an unrelated appearance veto does not make the corrected test insensitive. [Mutation log](task-90-artifacts/mutant.log), [import provenance](task-90-artifacts/mutation-import.log).

The runner restored the original bytes in `finally` and verified equality. Original/restored snapshot and active tracker SHA256 are all `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`. [Restoration JSON](task-90-artifacts/mutation-results.json), [both source checksums](task-90-artifacts/restored-source.txt). The active tracker was never mutated.

### Final full suite and build

On final unmutated source:

```bash
python -m pytest -q -ra --basetemp=/tmp/openscrub-task90-20261116/pytest-full -o cache_dir=/tmp/openscrub-task90-20261116/cache-full
```

Exit 0: **134 passed in 55.86s**, no failures, skips or errors. [Full suite log](task-90-artifacts/full-suite.log).

```bash
PIP_CACHE_DIR=/tmp/openscrub-task90-20261116/pip-cache python -m build --outdir /tmp/openscrub-task90-20261116/dist
```

Exit 0: default **sdist then wheel from sdist**, both built successfully using isolated hatchling 1.33.0 environments. [Successful build log](task-90-artifacts/build-network.log). The first sandboxed build could not resolve PyPI to install hatchling and exited 1 before building; it was retried with approved network escalation and temporary pip cache, without changing dependencies or source. [Initial build failure](task-90-artifacts/build.log). An initial metadata probe also found hatchling absent from the application environment, as expected for an isolated build backend; that probe did not affect pytest execution.

Archive inspection verified the sdist contains the final test bytes and that the sdist/wheel runtime equals the untouched source. [Artifact verification and SHA256s](task-90-artifacts/artifact-verification.json). Build artifacts remain under `/tmp/openscrub-task90-20261116/dist`.

## Self-review and limits

`git diff --check` and final `git diff HEAD^ HEAD --check` pass. `git diff --exit-code HEAD -- openscrub.py` passed before committing. The [local commit](task-90-artifacts/commit.txt) changes only the intended two test assertion lines, and the native worktree is clean. Existing test text already describes the larger-box contract and required guard sensitivity; no prose edit was needed. There are no algorithm, threshold, logging, version, dependency, fixture or unrelated-test modifications.

The known unconstrained OpenCV 5.0.0 dependency compatibility issue remains separate: it lacks `cv2.CascadeClassifier`, which existing fallback paths use. That is documented in `task-1-report.md`; this task did not rerun or fix OpenCV 5, pin product dependencies, or claim that environment is green. The complete root suite is green only in the explicitly recorded OpenCV 4 environment. Validation is synthetic on Linux/Python 3.12, without new browser, platform-matrix or real-person-media claims. PR draft is local at `task-90-pr.md`; no upstream publication or integration was performed.
