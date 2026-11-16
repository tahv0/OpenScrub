# Packaging and Review Features Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` when implementation is requested. Keep P12–P18 independently reviewable and use the delivery cycle; checkboxes are future work.

**Goal:** Preserve useful diagnostics, build/inference improvements and ordinary review features without restoring the experimental workbench.

**Architecture:** Extend existing owners and extract coherent leaf modules only when useful. Keep view filtering separate from decisions, generic rendering fixes separate from plate quads, and checkpoints separate from learning/rescanning systems.

**Tech stack:** Current Python >=3.9, Flask/embedded JavaScript, OpenCV/FFmpeg, Hatch, Docker and existing Windows packaging.

**Spec:** [Decisions and research](decisions-and-research.md), [delivery cycle](README.md), [PR ledger](../2026-11-16-upstream-pr-map.md).

## Global constraints

Preserve upstream defaults, entry points, security refreshes, declared Python floor, report compatibility and current face coverage. New tests live under `tests/`. Any runtime extraction includes its wheel/sdist/container and applicable updater/Windows checks in the same delivery unit. No extra training image, generated inference-image architecture, SQLite review journal or persistent unredacted examples.

## P12 — bounded diagnostics for long jobs

**What:** Extract useful structured error/stage/heartbeat diagnostics with bounded retention and graceful logging failure.

**Why:** A long scan failure is difficult to investigate after the process exits, but raw callback/OCR logging would create new personal-data retention.

**When:** W3, or earlier once independently ready; not a dependency of ETA, polling or save fixes. This is a proposal for upstream, not one of the four explicitly welcomed features. Donors: `b7bc4172`, `50e3816`.

**Files / contract:** If justified, `openscrub_internal/diagnostics.py`, narrow existing lifecycle hooks, `tests/test_runtime_logging.py`, concise `docs/LOGGING.md`. Proposed `event(kind, job_id=None, stage=None, **allowed_fields)` accepts an explicit allowlist of counters/status fields; it must not import the web app. Keep current behavior when persistent diagnostics is not enabled. Initial proposed file rotation: 5 MiB per file, two backups; heartbeat no more often than once per minute per active job.

- [ ] **E/S:** Identify the exact failures Austin needs to diagnose and inspect donor call sites for OCR text, plate queries, paths, crop metadata and learning hooks. Remove those from the persistent record; do not rely on a promise that arbitrary exception text is safe.
- [ ] **I:** Add tests for bounded rotation/heartbeats, unwritable storage, absence of synthetic sensitive sentinels and graceful shutdown. An unclean-exit marker records an unclean exit, not a fabricated OOM diagnosis.
- [ ] **I:** Add the minimal opt-in logger and lifecycle integration. Logging errors must not stop scanning or saving. Document where logs live and how they are removed; keep job-owned caches under the existing lifecycle.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_runtime_logging.py -q`, full build and an installed startup/stop/error exercise. Inspect output and package contents; validate Windows behavior before claiming it.
- [ ] **D/R/L:** PR material includes a concrete diagnostic gap, sample synthetic structured events, retention bounds and failure behavior. Keep training-subprocess telemetry and model-library events out.

## P13 — Docker cache and refresh improvements

**What:** Reuse package downloads and avoid invalidating security-refresh work unnecessarily during local source-only rebuilds, preserving upstream's release/security workflow.

**Why:** Upstream already caches heavy dependency/model layers. The remaining donor benefits must be measured as deltas, not sold as a new cache architecture.

**When:** W3 or earlier independently; no dependency on product features. Donors: `36636c4`, CPU `8fb396a`, CUDA `7063167`, Intel `bcda47f`.

**Files / contract:** `.dockerignore`, affected Dockerfiles, minimal workflow/comment adjustments, `tests/test_docker_build_cache.py`, concise build documentation. Preserve current image names, architecture/provider choices and `SECURITY_REFRESH` behavior. Cache IDs separate incompatible CPU/Intel/CUDA package contexts. Do not copy training overlays or artifact/media directories into build contexts.

- [ ] **E:** Record current cold build, local source-only rebuild with the same refresh argument, dependency change and forced refresh. Separately record CI's existing registry layer cache and per-run refresh argument; local mount reuse and cross-run CI persistence are different claims.
- [ ] **S/I:** Port pip cache mounts and refresh-layer positioning only where they reduce work. Preserve dependency/model layers and explicit scheduled/release refreshes. Keep container caches out of final image contents.
- [ ] **V:** Run `python -m pytest tests/test_docker_build_cache.py -q`, normal suite/build, and actual affected image builds with stage timings/layer evidence. Test source-only change and changed `SECURITY_REFRESH` separately; verify startup and model-provider registration.
- [ ] **D:** Document builder/cache lifetime and which layers were reused. Docker documents that cache mounts live with the builder and are not automatically persisted in GitHub Actions cache; do not assume a mount survives fresh CI runners or add a new cache-workaround action without a demonstrated need. [Cache mounts](https://docs.docker.com/reference/dockerfile/#run---mounttypecache), [CI cache behavior](https://docs.docker.com/build/ci/github-actions/cache/).
- [ ] **R/L:** Submit a focused build PR, splitting CPU/Intel/CUDA only if they differ materially. Describe security refresh preservation and untested hardware explicitly; no release/version ownership changes.

## P14 — Windows/NVIDIA inference setup

**What:** Preserve a small, working inference-only Compose/helper path and necessary GPU compatibility fixes.

**Why:** A registered provider is not proof that the chosen plate model executes on the GPU; Windows path/context/build handoff can also fail independently of inference code.

**When:** W3 once reproducible setup/hardware evidence exists; separate from P13 cache tuning. Donors: `9f63f6e`, narrowly selected `7c47815` changes.

**Files / contract:** Appropriate existing Compose/deploy documentation, a small helper under `tools/` or the relevant platform directory only if needed, `tools/check_cuda.py`, focused tests under `tests/`. No training image or generated parallel inference Dockerfile.

- [ ] **E:** Reproduce the actual daemon/context/path or provider issue on the target setup. Compare current upstream image requirements; do not restore an old ONNX Runtime pin just because the fork used it.
- [ ] **I:** Keep the minimal inference configuration and explicit fallback/error behavior. Mock command construction/path handling in tests; never treat those mocks as GPU verification.
- [ ] **V:** Build/run the supported image and execute an existing registered plate model on representative synthetic input with provider evidence. Check CPU behavior remains available and the chosen model/output agrees within justified tolerance.
- [ ] **D/R/L:** PR material names OS, Docker/driver/provider/model versions, the original trigger and actual hardware exercised. If no suitable GPU/Windows environment is available, keep hardware verification outstanding rather than marking the task complete.

## P15 — useful view-only filters

**What:** Add useful detection-type/output view filters and preserve drafts/lazy loading while changing the view.

**Why:** Large reviews should be navigable without triggering a timed save/refetch or losing hidden choices. This is a modest improvement to upstream review, not a return to the workbench.

**When:** W3 after assessing existing controls; can follow P02 and coordinate with P09, but neither O01 nor training labels are prerequisites. Donors: `64afc3cc`, `c3a8c7a5`, `8209a82`, `a80a85d`.

**Files / contract:** Existing review functions, category/group metadata and `enabled` values in `openscrub_web.py`; `tests/test_review_view_filters.py`. Filter state is view-local. Show all stays default. A group containing both output states must have documented membership behavior in each filter; counts represent groups consistently.

- [ ] **E/S:** Identify genuinely missing filters and the clean application's available states. Do not create handled/training/confirmation states merely to retain the donor's dropdowns.
- [ ] **I:** Add tests for mixed groups, empty results, hidden/pending edits, bulk-action scope and job switching. Assert filtering causes no save request and does not mutate output choices.
- [ ] **I:** Apply filters from local metadata, updating only view/card scheduling. With P09, notify its queue of the changed visible set; without it, keep a small standalone implementation. Avoid copying the learning sample selection or similarity system.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_review_view_filters.py -q`, build and S03 browser cases with many groups. Reopen/save/render to verify hidden decisions survived.
- [ ] **D/R/L:** Describe a concrete navigation problem and view-only behavior, not a new review methodology. Keep this separate from P02's output actions and O01's uncertainty policy.

## P16 — ordinary preview/render fidelity

**What:** Extract any remaining generic mismatch between review preview and rendered coverage/frame identity.

**Why:** The user should edit what the renderer will actually apply. The fork includes useful fixes mixed with compound masks and plate geometry, but those larger features are not required for ordinary boxes/faces.

**When:** W3, or earlier for a confirmed bug. Each independent reproduced mismatch can be its own PR. Donors: `539432c`, `a056dff`, `c79cb29`, `4a6675f`, `e15c5eb`, `98c3231`, `77755f0`.

**Files / contract:** Relevant rasterization/render-setting/frame-readiness functions in `openscrub.py` / `openscrub_web.py`; `tests/test_review_render_alignment.py`. Share a small existing-owner helper only where it removes divergent geometry; avoid a generic graphics abstraction.

- [ ] **E:** Reproduce each candidate on current upstream: configured padding, clipped face ellipse, pending manual edit, dense-track frame, or asynchronous image/mask mismatch. Close already-fixed cases explicitly; preserve Austin's newer close-up face margins.
- [ ] **I:** Add a pixel/geometry regression per actual mismatch and a wrong-frame response case. The assertion compares the relevant mask/output pixels rather than mirroring the helper's implementation.
- [ ] **I:** Extract only the necessary coverage/settings/identity fix. A behavior-preserving helper extraction can be its own commit before the bugfix; no compound-hole, silhouette-training or plate-quad dependency.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_review_render_alignment.py -q`, build, affected browser checks and real synthetic SDR/HDR render where applicable.
- [ ] **D/R/L:** PR lead names the exact visible mismatch and affected setting/frame case. Include before/after synthetic evidence and preserve default output elsewhere. Declare any helper later used by P17 rather than bundling that feature now.

## P17 — manual whole-plate four-corner masks

**What:** Let a user specify a plate quadrilateral and render it consistently in review/SDR/HDR.

**Why:** A rectangle can cover substantial surrounding image. A manual quad offers tighter whole-plate coverage using existing detection, with no custom segmentation model or new review database.

**When:** W3 after essential P16 frame/geometry prerequisites; explicitly welcomed in #22. Use early `617c9ac7` / editor `5c0782f` and integrated equivalents. The source-frame lessons from unmerged PR #70 are evidence, not a pre-merged feature.

**Files / contract:** Existing editor/render/report code; `tests/test_plate_quad.py`, `tests/test_plate_quad_editor.py`, `tests/test_plate_quad_render.py`. Proposed additive geometry records four normalized points in the inspected source-frame coordinate system plus source/frame provenance; append optional dataclass fields to preserve positional callers. Keep the exact conversion contract in the PR so preview, persisted points and renderer agree.

- [ ] **E/S:** Specify the stored quad coordinate convention, source dimensions/frame/time and migration behavior before editing code. Current upstream reports without quad fields remain valid. Experimental fork jobs are not silently migrated.
- [ ] **I:** Add tests for ordered/convex finite points, degenerate/out-of-frame geometry, source/normalization transforms, report round-trip and positional constructor compatibility. Add a moving plate case proving the same relative quad is not blindly stretched across later boxes.
- [ ] **I:** Port the small editor/renderer behavior. Bind the manual quad to its actual source frame; preserve the detection's full interval rather than truncating it to that frame. In the upstream-default path use existing full-plate coverage on other/unsupported frames. Arbitrary shape tracking belongs to O02, not an implicit claim in this PR.
- [ ] **I:** Keep editor gestures, pending drafts and ordinary Blur/Keep choices coherent. A failed geometry save does not silently discard independent output choices; reuse P07 only if its contract is needed.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_plate_quad.py tests/test_plate_quad_editor.py tests/test_plate_quad_render.py -q`, build, browser editing and real SDR/HDR synthetic renders. Verify source-frame binding and unchanged default masks.
- [ ] **D/R/L:** Describe manual tighter whole-plate coverage, exact temporal limitations and fallback behavior. Do not advertise automatic plate boundaries or lettering-only anonymization. Submit the welcomed manual feature separately from downstream policy/research.

## P18 — Stop & Review and resume

**What:** Save a consistent partial scan checkpoint, review it using upstream's ordinary UI, and resume the unprocessed suffix while preserving the reviewed prefix.

**Why:** Long scans should not have to restart solely because the user wants to inspect progress. The useful feature does not require learned rescans, sections or a SQLite journal.

**When:** W3 after a stable atomic-report contract if reused; independent of diagnostics and optional inference. Explicitly welcomed. Donors: early `72efeb02`, `ffb4ed9e` and integrated equivalents.

**Files / contract:** `openscrub_internal/checkpoints.py`, shared `reports.py` only if needed, narrow scan/worker/review hooks, `tests/test_stop_review.py`, concise `docs/STOP_REVIEW.md`, packaging. Preserve the donor interfaces `with_checkpoint(doc, frame, total, options)`, `validate_resume(doc, source_sha256=None)` and `join_reports(previous, continuation, next_frame, total_frames, completed=False)`. Keep only clean-upstream fields: checkpoint schema/state, first unprocessed `next_frame`, total frames, FPS, input hash and relevant options. The committed prefix is `[0, next_frame)`; continuation timestamps/frame indices and `cum`/`bands` use the original video's coordinates, not an unexplained suffix-relative offset.

- [ ] **E/S:** Identify where scan postprocessing produces a consistent report and how cancellation differs from a requested checkpoint. Persist source/normalization identity, committed next frame, total frames and settings needed to validate continuation.
- [ ] **I:** Add tests for checkpoint after postprocessing, process restart, changed source/FPS/options, no forward progress, overlap boundaries and preserved audio/manual/geometry choices. Assert no full-prefix rescan or replacement of reviewed prefix decisions. A small declared boundary overlap for detector continuity may be read/scanned, but its output cannot overwrite prior human choices.
- [ ] **I:** Implement distinct Stop & Review / Resume actions and atomic checkpoint publication. Resume commits new work from the recorded boundary; if a bounded context overlap is needed, keep its purpose and merge rules explicit. Remap suffix track IDs without merging unrelated objects. Preserve current queue generation/cancellation/retry behavior.
- [ ] **I:** Distinguish partial scan status from a complete redaction. Ordinary checkpoint inspection does not imply every later frame was scanned. Do not add training/model/section dependencies to offer resume.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_stop_review.py -q`, build and a synthetic scan → stop → review → process restart → resume → render browser/CLI exercise. Validate packaged imports in CPU/Intel/CUDA and applicable Windows distribution.
- [ ] **D/R/L:** PR description states the exact interruption/resume scenario, what checkpoint identity protects, what edits survive and any unsupported changes that require a fresh scan. Keep it a standalone feature with its small shared-helper dependency declared.

## Review focus

Do not claim hardware support from mocks, cross-run cache persistence from a local builder, exact temporal geometry from box tracking, or full scan completion from a checkpoint. Keep default review/redaction semantics intact and test every new module in the distributions that ship it.
