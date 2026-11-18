# OpenScrub Upstream Delivery Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` when implementation is requested. Use delegated execution only if that approach is selected. Checkboxes are future work unless explicitly marked complete. This documentation does not authorize publishing PRs or replacing branches.

**Goal:** Deliver the useful fixes from the user's remote as small, defensible PRs to Austin's upstream, then assemble a clean application with separate optional assistance features and no custom training/workbench.

**Architecture:** Base each contribution on Austin's current `main`, extracting behavior rather than merging the experimental branch. Keep downstream options independent. Improve module structure only where a task justifies it, preserving existing entry points and distribution paths.

**Tech stack:** Current upstream Python >=3.9, Flask/embedded JavaScript, OpenCV, FFmpeg, ONNX and Hatch packaging. Additional pretrained inference is optional; no custom training.

**Spec:** [Decisions and research](decisions-and-research.md), incorporating this conversation. [Original extraction outline](../2026-11-16-upstream-extraction.md) and [preservation/PR ledger](../2026-11-16-upstream-pr-map.md) retain donor history. This directory supplies the detailed delivery sequence and task contracts; where the older outline is less specific, use these researched details.

## Development efficiency — completed

The user-prioritized [D01 development and verification efficiency](execution/development-efficiency-priority.md) is complete after independent tooling review and real adoption on Task1631/P16C-G. New tasks use the reviewed local verification helper and the current environment handoff, with explicit source identities and required checks. P16C-G geometry, P16C-R resource cleanup and P16C-P output preservation are independently approved on their declared bases. The reviewed core/browser/renderer assembly and small readiness follow-ups are integrated locally with P15 view filters at `b4fc209`. The selected cycle is complete; the remaining generic/optional roadmap and adoption remain open. Separate PR boundaries and upstream defaults remain in force.

The [ordinary exact editor and Track](execution/evidence/delivery/task-1004-final-acceptance.md) are accepted locally at d1f056e on the accepted backend 335435e, strict seeds 6fde5ad and mounted prerequisite 07cf lineage. The review-found error-body slot issue is repaired and independently approved. [Portable media-test artifact output](execution/evidence/delivery/task-10110-final-acceptance.md) is separately accepted at d3d0277 on 6fde5ad, with no runtime changes or blanket dependency. The dormant matcher 3547f82 and P08A source preparation remain independent. The reviewed application stays b4fc209; C01 composition, upstream publication and working-version adoption remain open.

The [portable test-output measurement](execution/measurements/portable-media-tests.md) records six matched seven-case runs and a reproducible recipe. It establishes fewer output setup commands and preserved evidence, with no repeatable speed gain; failed missing-environment runs are reliability evidence only.

## Global constraints

- Upstream means `austinmabry/OpenScrub`; remote means the user's `tahv0/OpenScrub`, currently `origin`.
- Preserve upstream's current defaults. Assistance and uncertainty policies require explicit selection.
- Remove custom training, saved learned models, training data collection and the expanded review workbench from the cleaned application; preserve upstream's ordinary review and pretrained inference.
- Preserve every applicable generic fix through an explicit disposition. Long/large-video performance is a primary deliverable.
- Keep existing runtime data and the integration snapshot. Planning/extraction does not authorize deletion, force-push or remote publication.
- Preserve Python >=3.9 for the core, report compatibility, source-frame accuracy, current privacy fixes, vault/retention behavior and release ownership.
- Use synthetic fixtures. Add new tests under `tests/`, measurements under `benchmark/`, and justified runtime extractions under a single proposed private namespace `openscrub_internal/`.
- No helper package, frontend toolchain, database or broad reorganization merely to make the repository look cleaner.

Current implementation progress and local PR drafts are recorded in the [execution record](execution/status.md). Future task checkboxes below remain open until their actual checks and review are complete.

## Read these documents together

| Document | What it supplies |
| --- | --- |
| [Decisions and research](decisions-and-research.md) | What the user chose, what Austin requested, verified source findings, probe results and remaining uncertainty. |
| [Core UX and reliability](01-core-ux-and-reliability.md) | P01–P07: downloads, choices, polling, ETA, preview publication and report/save correctness; separate N08 input, N11 filename-display and N12 first-scan sanity candidates. |
| [Large-video performance](02-large-video-performance.md) | P08–P11, shared scale fixtures and measurement contracts. |
| [Packaging and review features](03-packaging-and-review-features.md) | P12–P18: diagnostics, builds, inference setup, view filters, preview fidelity, manual quads and checkpoints; separate N09 HDR pipe cleanup. |
| [Optional assistance](04-optional-assistance.md) | O01–O05: confidence/continuity policy, seeded tracking, OCR search, boundary evaluation and lettering-only mode. |
| [PR evidence and description template](pr-evidence-template.md) | Information to collect during implementation and a reviewer-facing description structure. |
| [Preservation ledger](../2026-11-16-upstream-pr-map.md) | All 28 issue #22 donor references, extra candidates, exclusions and named P01–P18 boundaries. |

## What “when” means

Use delivery waves and readiness gates rather than guessed calendar dates. Small PRs may finish while another candidate is still being reproduced. A later wave is not permission to combine its tasks into one PR.

| Wave | Work | Entry condition | Deliverable / exit condition |
| --- | --- | --- | --- |
| W0 — establish evidence | B01–B03 below; synthetic scale baseline starts here | Planning complete enough to begin a selected task | Pinned upstream checkout, preserved donor snapshot, test environment, candidate ledger and reproducible baseline. |
| W1 — first contributions | P01–P05; P06/P07 correctness regressions start immediately | B01/B02; each relevant baseline reproduced | Independent branches with tests and reviewable descriptions. No dependency on optional modes. |
| W2 — scale and persistence | P06–P11, with P07 as its own follow-up if a shared contract is needed | Baseline measurement and source identities established | Proven large-report, queue or decoding improvements with measured costs and failure tests. Close inapplicable candidates explicitly. |
| W3 — supporting improvements | P12–P18 | Each task's evidence/dependencies; P13/P14 can proceed earlier when ready | Independent diagnostics/build/UX/geometry/checkpoint PRs. No requirement that all preceding PRs be merged. |
| W4 — optional application behavior | O01–O05 | Clean base plus selected necessary generic fixes | Downstream branches first; separately discuss upstream suitability where unresolved. |
| W5 — assemble and adopt | C01/C02 below | Chosen fixes independently validated | Tested clean application, preserved old environment, accurate outstanding-work list. |

Within **every** P/O task use the same PR cycle:

1. **E — establish:** pin the base, reproduce the trigger or define the new-feature scenario, and capture baseline evidence. This prevents fixes aimed only at a removed subsystem.
2. **S — scope/structure:** identify touched functions, API/report compatibility and any small extraction. Record why each new file exists. This keeps the diff understandable.
3. **I — implement:** add the behavior regression, make it fail for the intended reason, then implement the smallest coherent change. Separate a meaningful behavior-preserving extraction from the behavior commit.
4. **V — verify:** run the task-specific checks and upstream contribution checks; exercise real browser/HTTP/render paths where the task requires them. Record limits rather than declaring untested platforms supported.
5. **D — document:** write the PR body from the recorded trigger, change and results. Rewrite it around the final diff if scope changed. Do not copy conversation history or experimental notes wholesale.
6. **R — review/submission:** inspect the diff against its declared base, prepare a local PR draft, and publish only when requested. Address Austin's feedback in that focused branch and rerun affected checks.
7. **L — land/integrate:** after upstream accepts/merges, update the ledger with the actual commit, rebase dependent branches, remove duplicate patches from the assembled branch and rerun affected integration checks. A rejected/deferred proposal can remain downstream or close with a reason.

The task cards below specify their own **what**, **why**, **when**, implementation steps, validation and PR evidence. The same E–L cycle applies to each card; it is not a separate boilerplate PR.

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
- [ ] **I:** Keep `test_openscrub.py` in place. For a new test file use `python -m pytest test_openscrub.py tests/test_<topic>.py -q`; add the same collection to contribution instructions and an existing test CI job if present. The researched upstream has no test CI job, so P01 updates documented discovery and sdist inclusion without adding an unrelated CI pipeline.
- [ ] **V:** Run baseline `python -m pytest test_openscrub.py -q` and `python -m build` (sdist then wheel). For each UI change parse the evaluated embedded scripts with Node and exercise the affected browser interaction. For engine changes render a synthetic clip.
- [ ] **D:** Record skips, missing hardware/models and existing failures separately. Keep actual output/counts with the tested SHA; never replace them with the fork's historical test counts.

### B02b — preserve the model-unavailable face fallback

**What:** Prepare a separate compatibility PR that keeps the existing OpenCV wheel flavor and YuNet → Haar fallback usable. Bound the currently unbounded normal OpenCV dependency to a verified compatible major version, and ensure an already importable unsupported runtime is not reported as healthy by installation checks.

**Why:** Matched probes of the actual pinned `FaceDetector`, with the same empty cache and blocked downloads, execute Haar on `opencv-python 4.14.0.94` but raise on `5.0.0.93`: the core OpenCV5 wheel has neither `CascadeClassifier` nor the required XML. The same cached YuNet runs on both. The earlier full-suite comparison changed model availability too, so it cannot attribute every failure to OpenCV. Official [migration guidance](https://github.com/opencv/opencv/wiki/OpenCV-4-to-5-migration#objdetect-haar-and-hog-moved-to-contrib) confirms the moved Haar implementation; switching to an untested contrib5 wheel is a larger alternative, not the selected minimal fix.

**When:** Independent W1/W3 compatibility candidate after B02's matched diagnosis. It can target Austin plus the test-only B02a prerequisite. It does not belong in every unrelated feature PR or require the Docker cache work. Local execution remains authorized; publication is separate.

- [ ] **E/S:** Recheck the exact dependency/installer inventory from local `opencv-compat-research.md`. Define one compatibility policy across package metadata, source requirements and `install.py`; `<5` is the evidence-backed proposed bound, without an arbitrary new lower bound or Python-floor increase. Distinguish fresh installs from existing source updates, which do not reconcile dependencies.
- [ ] **I:** Synchronize the selected bound and make the existing runtime/installer health check detect the demonstrated incompatible configuration, with an actionable bounded repair path. Preserve cached YuNet and the offline fallback. Do not silently report no faces, require a download, remove Haar, change wheel flavor or co-install conflicting `cv2` distributions as a repair.
- [ ] **S/I:** Account explicitly for optional CPU/GPU Paddle installers in the desktop/web/standalone paths: a bound on `opencv-python` does not constrain `opencv-contrib-python` or headless distributions sharing `cv2`. Verify the actual resolver behavior before selecting common constraints/checks; preserve existing inference/provider choices. If this needs a separate follow-up, name the unprotected flow in the first PR rather than claiming global compatibility. CUDA's default source build is a separate path; do not change its version or security-refresh policy incidentally.
- [ ] **S/I:** Current primary metadata narrows that follow-up: PaddleOCR 3.7.0 selects PaddleX 3.7.x OCR-core, whose declared contrib dependency is 4.10.0.84. This already excludes OpenCV 5 for those releases but can coexist with core's normal wheel; metadata alone is not a resolved/platform-tested environment. Keep flavor reconciliation separate from B02b. The core fix should share a small read-only installer/setup diagnosis, give deliberate repair instructions for a sole incompatible/broken normal wheel only when known runtime and metadata release versions agree, avoid automatically modifying mixed/alternate/source-built installations, and recheck standalone OpenCV status after optional Paddle so an earlier healthy result is not reused.
- [ ] **V:** Verify wheel/sdist metadata, fresh resolution, an already importable unsupported runtime, the real supported Haar API/XML with model fetching blocked, and the existing cached-YuNet path. Run the current suite/build in the compatible environment. Establish Python3.9/platform resolution and focused runtime evidence before making those support claims; Linux3.12 evidence alone is not a Windows/macOS/GPU/frozen-build test.
- [ ] **D/R/L:** Lead the PR with the concrete missing-model fallback crash, exact package versions and small remedy. Include resolver/install limits, current-source update instructions and which optional/platform paths were exercised. Keep new compatibility tests under `tests/` and any truly shared helper under the existing private namespace.

**Completed resolver evidence:** The [bounded core resolution](execution/evidence/research/opencv-resolution-research.md) changes only the normal OpenCV requirement and resolves from fresh official PyPI metadata on the existing Linux CPython 3.12.16 and 3.9.25 targets. Both select `opencv-python==4.14.0.94`, with no other cv2 distribution; all selected Python markers/dependency edges/wheel tags were checked. No wheel archives were downloaded or packages installed. This covers the ten package-core declarations, not the extra spaCy requirement, optional Paddle/GPU commands or another platform. The implementation should compare its built metadata to that exact candidate input and reuse this evidence unless the declarations or a concrete concern change; health checks and installed runtime remain separate gates.

B02b platform context: the current CUDA image deliberately bypasses ordinary wheel installation and restores a compiled OpenCV/contrib4.10.0. A healthy importable source-built4.x runtime without wheel metadata is not a missing install; diagnose its actual Haar constructor/XML capabilities and preserve that provider path. Missing required capabilities need explicit source-build guidance, not automatic replacement with pip wheels. [Readiness evidence](execution/evidence/research/platform-readiness-research.md) establishes available Docker/host GPU metadata only, with builds/inference still open.

## B03 — complete the preservation audit and scale baselines

**What:** Reconcile integration changes and older/open donor references with the ledger, and start the scale evidence described in the performance plan.

**Why:** Every relevant improvement needs a destination, including useful hunks in commits dominated by training. Equally, already-upstream fixes and improvements to deleted systems should not become duplicate PRs.

**When:** Start W0, update during E/D/L of every task, finish before W5 cutover. This is local planning/evidence, not a monolithic upstream issue or PR.

- [ ] **E:** Inventory `main...integration/all-prs`, production file changes and non-merge feature/fix families; inspect merge first-parent deltas where the named donor is a merge. Use ancestry only as provenance, not proof that behavior is absent/present.
- [ ] **E:** Add every candidate to the ledger with donor/follow-ups, affected upstream path and one disposition: PR, already upstream, downstream, removed-system-only or investigate. Mark source inspection, isolated probe and full integration reproduction separately.
- [ ] **V:** Complete the S01–S06 scale scenarios in the performance plan. Preserve raw measurements and fixture-generation parameters; compare identical settings at a pinned base.
- [ ] **D:** Prepare a small reproducible issue draft only for a confirmed upstream problem needing discussion, linking issue #22. Do not post it without a request to publish.

## Dependencies that actually matter

- P01/P04/P05 use Austin plus the test-only B02a prerequisite. P02/P03 use the reviewed P07a browser ownership contract as an explicit dependency; neither copies server report features or adds optional state. Their standalone server limitation and complete roundtrip checks remain declared for C01.
- P06 owns report transaction/publication correctness. P07 may use its contract for request replay; P08 consumes publication invalidation if that is the chosen cache design. Declare those dependencies explicitly rather than copying conflicting helpers.
- P09's browser scheduling can be independent of P08's server cache. P10's decoding contract can be independent of either; share only if measured work justifies it.
- P15 can build on P02's explicit actions, but view filters must not depend on O01 or a training label.
- P16 generic preview/render bugs must be extractable without P17 plate quads. P17 may use a necessary P16 helper, with its dependency declared.
- P18 reuses P06's atomic helper if shipped; it does not require P12 diagnostics or any custom journal.
- O01 and O02 must integrate before claiming the complete select-once-and-follow workflow. O03 search can produce candidates before O04 boundary evaluation passes. O05 lettering-only stays usable with its declared limitations; it does not require custom models.

## C01 — assemble and validate the cleaned application

**What:** Assemble accepted/selected focused fixes on `integration/upstream-focused`, with downstream options layered separately.

**Why:** Independent PR correctness does not prove combined behavior, packaging or runtime-data lifecycle. This is also where removal of custom training/workbench dependencies is verified.

**When:** Smoke-test after meaningful compatible batches; full check in W5. The assembled branch is not an upstream PR base.

- [ ] **I:** Apply selected, individually reviewed patches; retain upstream implementations of already-landed fixes. Include no training/Findings/journal/section-only modules, routes, dependencies or CI.
- [ ] **V:** Run the combined suite/build and clean installed CLI/web startup. Exercise scan → review → render → export, large-report saves, cancellation/restart, deletion/retention/vault and default-policy equivalence. Run hardware checks only on platforms actually available.
- [ ] **V:** Repeat the relevant scale benchmarks on the assembled version to detect interactions, and check that optional modes do not change default output. Keep optional OCR queries/crops job-scoped.
- [ ] **D:** Write a local acceptance record listing included PR/commit IDs, measured outcomes, downstream-only features, known limits and outstanding candidates. No claim that all upstream proposals are accepted.

## C02 — choose the working version without discarding the old one

**What:** Adopt the validated clean application and record how existing work/data is retained.

**Why:** Experimental report fields and saved learned suppressions cannot be silently interpreted as trusted clean-app decisions.

**When:** After C01 passes and the user chooses the clean version as their working environment; no automatic force-push or data deletion.

- [ ] **E:** Inventory old jobs/models/datasets as retained runtime data, separate from code removal. Use copies/rescans for any migration evaluation.
- [ ] **V:** Verify the selected launch path uses the clean build/data root and can be rolled back to the preserved environment.
- [ ] **D:** Update the ledger with landed, downstream, excluded and unresolved work. Any later branch replacement or publication is a separate concrete operation, not implied by this document.

## Review focus

- Cross-job responses and in-flight edits: P03/P07/P09 must fence publication to the initiating job/view.
- Correct bytes attached to the wrong frame/report: P08/P10/P16/P17 must validate identity, not only speed.
- Lost edits despite a successful response: P06/P07/P18 need failure, overlap, replay and restart tests.
- A helper present in source but absent from a release: the owning PR must verify sdist, wheel, container and applicable Windows/updater paths.
- A convenient optional mode changing upstream defaults or being presented as maintainer-approved: O01–O05 and C01 must preserve opt-in and scope labels.
