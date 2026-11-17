# Task 1: B01/B02 isolated baseline and test environment

## Global constraints

- Upstream means `austinmabry/OpenScrub`; remote means the user's `tahv0/OpenScrub`, currently `origin`.
- Preserve upstream's current defaults. Assistance and uncertainty policies require explicit selection.
- Remove custom training, saved learned models, training data collection and the expanded review workbench from the cleaned application; preserve upstream's ordinary review and pretrained inference.
- Preserve every applicable generic fix through an explicit disposition. Long/large-video performance is a primary deliverable.
- Keep existing runtime data and the integration snapshot. Planning/extraction does not authorize deletion, force-push or remote publication.
- Preserve Python >=3.9 for the core, report compatibility, source-frame accuracy, current privacy fixes, vault/retention behavior and release ownership.
- Use synthetic fixtures. Add new tests under `tests/`, measurements under `benchmark/`, and justified runtime extractions under a single proposed private namespace `openscrub_internal/`.
- No helper package, frontend toolchain, database or broad reorganization merely to make the repository look cleaner.


## B01 — preserve references and create the clean baseline

**What:** Preserve the donor snapshot and use a separate worktree/branch based on Austin's verified current main.

**Why:** The fork has 500 integration-only commits by ancestry and mixed changes. Extracting into upstream avoids carrying training/workbench dependencies and losing Austin's newer fixes.

**When:** W0, before product edits. Local preparation; not an upstream PR.

- [ ] **E:** Refresh Austin's `main` SHA using the connected GitHub API, compare it with local `main`, and record both it and donor `b4d0c75f25d91510fe1692f901d11853dc7db005`. The research baseline is `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
- [ ] **S:** Preserve an archive reference and create an isolated checkout using the worktree workflow. Keep the original branch and uncommitted planning files. Use a separate synthetic job directory so old learned decisions cannot affect baseline behavior.
- [ ] **V:** Confirm branch/base, clean product diff and absence of removed-module imports on the baseline. Record existing failures before attribution to a port.
- [ ] **D:** Record baseline/environment in the evidence template and mark B01 complete. Do not rename configured remotes merely to match conversational terminology.


## B02 — establish test discovery and a reproducible environment

**What:** Prepare an isolated Python environment, upstream checks and the first `tests/` additions when a selected PR needs them.

**Why:** This workspace's default Python currently lacks pytest, Flask, OpenCV, NumPy and build. Research probes cannot substitute for application tests. Upstream's documented single-file pytest command will not collect new tests automatically.

**When:** W0 before application verification; minimal test-discovery changes travel with the first owning PR, not as a broad infrastructure prerequisite.

- [ ] **E:** Read the then-current contribution guide and dependency files. Record Python, FFmpeg, Node/browser availability and inference providers. Install the existing declared development/runtime requirements into an isolated environment at implementation time; do not add training dependencies.
- [ ] **I:** Keep `test_openscrub.py` in place. For a new test file use `python -m pytest test_openscrub.py tests/test_<topic>.py -q`; add the same collection to the relevant contribution instructions/CI rather than relying on an unexecuted folder.
- [ ] **V:** Run baseline `python -m pytest test_openscrub.py -q` and `python -m build` (sdist then wheel). For each UI change parse the evaluated embedded scripts with Node and exercise the affected browser interaction. For engine changes render a synthetic clip.
- [ ] **D:** Record skips, missing hardware/models and existing failures separately. Keep actual output/counts with the tested SHA; never replace them with the fork's historical test counts.


## Supervisor scope and rulings

The native managed worktree exists at `/home/tahv0/.codex/worktrees/c832/OpenScrub`; use that path explicitly. It is based on verified upstream `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f` and is now on `pr/save-as-progress`. The original checkout is untouched. Planning is committed separately on `docs/upstream-delivery-plan`; archive ref preserves `b4d0c75`. Do not duplicate those preparations.

This task prepares a test environment and captures baseline evidence only. Do not implement P01 or change product files. Core dependencies come from pyproject, not requirements.txt's optional spaCy addition. Default Python is 3.14.4; use an isolated available supported interpreter or establish a compatible isolated environment. Do not modify system packages. Install declared core/development dependencies as necessary. No training, model downloads or user job access. Use a separate synthetic data root. Read CONTRIBUTING.md and relevant CLAUDE.md verification/architecture instructions. Keep release/version ownership upstream.

Run the existing test suite, full sdist→wheel build, evaluated embedded-JavaScript syntax checks, and basic synthetic HTTP/startup checks if available. Record unavailable ffmpeg/tesseract/browser/hardware separately. Tests must exercise the real app where applicable; report genuine baseline failures and their cause rather than silently fixing unrelated code. Record the exact interpreter/environment path, test commands/counts and build results.

The worktree is outside the initial writable roots. Use tool escalation for necessary writes if blocked; automatic review already approved local branch preparation there. Do not silently relocate implementation or make remote writes. Reports live in the original repo's writable SDD workspace.
