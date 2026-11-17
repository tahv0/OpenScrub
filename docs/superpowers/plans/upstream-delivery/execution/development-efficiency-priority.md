# D01 — development and verification efficiency

**Status:** Task901 tooling is independently reviewed at `081816d93d6aaa18944fc88f251040cf11d4135f` (initial `afbd207`, documentation base `0467743`). [Usage](tooling/README.md), [implementation report](evidence/delivery/task-901-report.md) and [fix review](evidence/delivery/task-901-fix1-review.md) are retained. Adoption on Task1631/P16C-G remains open; D01 is not yet complete.

**What:** Remove repeated environment setup and avoidable verification failures with a small amount of reusable local tooling and tighter task handoffs.

**Why:** The execution record contains checks importing the wrong checkout, an installed entry point using the wrong interpreter, concurrent pytest runs colliding in one temporary directory, and tests exhausting the small `/tmp` filesystem. Repeatedly copying environment hooks, package verification commands and broad source context also costs time. Existing guidance already addresses these problems; automate its repeatable parts instead of starting another framework.

**When:** Next priority after the current implementation and independent review finish, before another product feature starts. At scheduling time, use the actual recovery snapshot rather than interrupting its active owner. Keep this to one focused pass, then use it on the next real task and resume the contribution sequence.

**Source of truth:** The [delivery plan](../README.md), [execution record](status.md), and [preserved verification environment handoff](evidence/research/source-plans/verification-environment-handoff.md.txt). The live local handoff is `.superpowers/sdd/README/verification-environment-handoff.md`; reconcile it before implementation, since archived evidence is a snapshot.

## Work and delivery order

| Work | Why | When and concrete output |
| --- | --- | --- |
| Reuse the existing setup and identify its repeated manual steps. | Avoid spending the efficiency task rediscovering completed research or replacing working environments. | D01 establish: inspect the recent failures and current helpers; choose only repeated steps with a clear payoff. Record a short before-state from existing logs. |
| Add a small shared preflight and launcher where existing helpers are insufficient. Check the assigned checkout/base, actual interpreter and import locations, available cached prerequisites, scratch filesystem space and distinct test roots. | Fail immediately on setup mistakes instead of completing an invalid test or benchmark run. | D01 implementation: one documented entry point under existing local tooling. Accept explicit task/source/environment inputs; report identities and actionable failures. Do not switch branches or alter shared environments. |
| Consolidate repeated environment hooks and package checks. Reuse the prepared Python 3.12 and 3.9 environments, offline build tools, cached pretrained models and sdist-to-wheel-to-installed-smoke recipe. | Reduce copied shell commands and differences between otherwise equivalent verification runs. | Same D01 change: shared helpers plus small task-specific configuration, preserving source and installed-import checks. Resolve current paths from the live handoff; do not silently recreate or upgrade environments. |
| Make validation selection and evidence reuse explicit. | Avoid repeated full runs without weakening the evidence for each contribution. | D01 documentation, then every task: focused behavior checks, required stable full-suite/package/floor/browser/media gates as applicable, and scoped follow-up checks. Reuse prior results only when the relevant source, tests, fixtures, dependencies and environment still match; record their exact identities and limitations. A new failure or affected contract can require a broader rerun. |
| Give agents compact task briefs and bounded command output. Include exact base, owned paths/interfaces, relevant research links, working commands and acceptance checks. | Avoid repeated repository-wide discovery, large log dumps and re-reading unrelated history. | Next task handoff: extend the existing brief template. Link raw logs and return concise results/failures. Batch independent read-only checks where safe; preserve one product owner and fresh independent review. |
| Demonstrate that the helpers prevent the recorded mistakes and reduce manual work. | An efficiency change must pay for its own complexity. | D01 verification and next real task: check wrong-source/interpreter and unsafe scratch failures using isolated fixtures; exercise the normal setup/package path. Compare manual setup steps, invalid runs and available timings. Record what improved without promising an unsupported speedup. |

## Boundaries and completion

- [x] Reuse working helpers first. Keep any new scripts under existing local tooling, with scratch data on the designated workspace filesystem and a unique task/run directory. Do not add repository-root clutter, a general workflow framework or a new toolchain.
- [x] Preserve meaningful regression checks, compatibility checks and independent review. Label setup failures separately from product failures. Do not turn evidence reuse into a blind cache of passing results.
- [x] Preserve isolated settings, models, profiles, ports and temporary directories. Do not share mutable pytest roots or overlap benchmark timing with competing work. Do not prune other tasks' caches or data to make space.
- [x] Leave active implementation, branch ownership, shared environments and product behavior untouched. Do not restart completed work or reduce the user's requested implementation model quality.
- [ ] Retain a concise usage recipe, helper verification results and the before/after observations through the existing documentation/evidence process. Record the next real task's adoption result rather than starting a continuing optimization project.
- [x] Keep D01 outside unrelated feature PRs. Any generally useful developer tooling proposed to Austin later needs its own small, portable diff; local machine paths and execution archives are not upstream deliverables.

**Done means:** The next implementer can use the established environment and required verification path without rebuilding the setup instructions, common setup errors fail early, and the required product evidence remains intact. Close the task with measured benefits and any specific remaining limits, then return to the focused contribution queue.

## Reviewed tooling result and adoption gate

The helper consolidates twelve repeated setup responsibilities into four caller actions: freeze the selected source and gates, provide one explicit environment/configuration, invoke the required checks, and invoke/inspect the package path. This is a documented reduction in manual responsibilities, not a measured wall-clock saving. The original16 focused cases passed on each actual Python3.12/3.9. Independent review found direct-script import shadowing and prefixed-pytest ownership gaps; the fix's final25 cases pass on both, and the same final tests reproduce16 failing assertions against the old helper on each interpreter. Six affected source/default, installed CLI and listening-server checks also pass. The unchanged package artifacts were reused; no product-wide suite or timing was repeated for this tooling work.

Caller-selected module/file inventories remain explicit, including package parents. Python hooks do not provide OS/native containment; adapters still own ports and child cleanup. Minor M1 (an implicit tar-extraction filter warning in successful package output) is deferred for readiness. The next real task must record actual use, any setup failures, remaining task-specific adapters and the required product evidence before D01 closes.
