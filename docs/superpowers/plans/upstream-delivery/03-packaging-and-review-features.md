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

### P12A — persistent diagnostics, explicitly enabled

The [scope research](execution/evidence/research/diagnostics-scope-research.md) confirms the gap: actual worker failure details disappear after a fresh-process recovery, while capturing console output can retain an access token and arbitrary errors. Use the proposed private module and one default-off CLI flag; do not transplant the donor's always-on raw message/exception/root logger. Disabled operation creates no files, threads or hooks.

- [ ] **S/I:** Construct records from event-specific fixed enums and bounded finite counters only, with no arbitrary exception strings, paths, OCR/queries, crops, argv, headers or job dictionaries. Service/session-generated action references replace stable job IDs in persisted records. Keep existing UI error information unchanged.
- [ ] **I/V:** Store sanitized service records outside the job vault, with explicit documentation that they survive job deletion/lock until rotation/removal. Cap each event/marker at1KiB, files at5MiB with two backups, one exclusive writer and at most one heartbeat per minute per active job. Remove finished action state. Previous-run markers establish only an unobserved clean close, never an OOM diagnosis.
- [ ] **I/V:** Integrate only existing admission/operation/stage/finish/watchdog/shutdown owners, preserving lock order and vault refusal. Disable a failed sink without affecting jobs; no root/library/TLS/request or native fault capture. Test default-off, schema sentinels, rotation, second writer, failures, stale action, abrupt/clean exit and actual installed lifecycle. Research's inert-server startup/stop probes are not configured-server acceptance.
- [ ] **D/R/L:** State the concrete diagnostic gap, opt-in retention/ownership, error classification and platform limits. Follow the retained research contract for exact schema/hooks and packaging; native Windows/frozen checks remain outstanding until executed.

### P12B — bounded in-memory job logs and compatible cursors

**What / why / when:** Separate long-job memory candidate: the actual baseline retains1,208 lines although public metadata displays only30. A display tail is not storage retention. Establish representative count/byte growth and choose justified bounds before implementation; this is independent of persistent P12A and reuses P03's authoritative response handling.

- [ ] **E/S/I:** Bound producer storage with an explicit retained-base/next-sequence contract. Preserve absolute from/len semantics, clamp or reset obsolete cursors explicitly, and update ordinary job metadata/log routes coherently under concurrent append/retry/rehydration. Do not silently trim and renumber the list. Choose line/count/byte limits with recorded behaviour and truncation evidence, not arbitrary disappearance of diagnostics.
- [ ] **V/D:** Exercise actual producer/routes/client after overflow, clear/retry, stale/future cursors and concurrent polling. Preserve current last30 metadata/last400 initial UI conventions unless a separate justified change is declared. Show measured retained storage and remaining transient/allocator costs; no whole-process RSS ceiling from list bounds. Keep persistence/schema/logger hooks in P12A.

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

**Local validation readiness:** The [bounded platform check](execution/evidence/research/platform-readiness-research.md) reaches Docker29.7.2 on Linux/x86_64 and sees an RTX3080/driver621.01/10GiB through authorized read-only execution. Earlier ordinary socket/NVML failures were sandbox restrictions, not proof of absent host capability. Actual builds, cache timing, CUDA container handoff and model execution remain pending. No Intel GPU or usable native Windows toolchain is established; CPU/driver/provider listings do not substitute for those gates.

Preserve the pinned CUDA path: OpenCV and opencv_contrib4.10.0 built together under/opt/opencv, CUDA12.6/cuDNN and NumPy1.26.4, with pip OpenCV variants removed and compiled cv2 restored before no-dependency app installation. B02b's ordinary wheel bound must not replace this source build. Native Windows uses DirectML/PyInstaller/Inno separately. P13 may now proceed to scoped actual image builds when it owns the heavy workload; P14 first verifies device handoff and then actual registered-model execution. Keep scheduled SECURITY_REFRESH and existing registry layer caches intact.

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

**Refined filter contract:** [Source-only P15 research](execution/evidence/research/review-filter-scope-research.md) confirms the ordinary UI has category actions and a collapsed zone section, but no type/output view selectors. Implement after reviewed P02, reusing its grouping/effective choices and P07a draft owner. Both actual-category and output predicates apply to ordinary groups and independent zone cards, with Show all default/reset; no handled/training states or autosave are imported.

- [ ] **I/V:** Derive complete card metadata before filtering. Mixed groups appear in both Includes blurred appearances and Includes visible appearances, once per view. Counts represent ordinary group cards plus individual zone cards, including collapsed/unmounted matches; cross-filter option counts may overlap because of mixed groups. Keep zone real category separate from its action section, its collapsed default and current collapse choice.
- [ ] **I/V:** Category bulk still targets every ordinary group in that category; zone bulk still targets all independent zone rows. Card actions keep full original membership. Explicit filter/reset clears marquee selection; live output changes prune excluded IDs. Snapshot bulk targets before applying setters, then refresh aggregates/counts/view once, without quadratic per-member rescans.
- [ ] **I/V:** Re-evaluate membership locally after a choice. Preserve focus if its card remains; if the focused card is hidden, move focus to Output and announce counts. Leave the active editor/gesture/media/audio/manual/pending-save state intact even when its card is filtered out. No pinned-card system or editor remount. Empty and closed-zone-only matches have truthful text/reset controls.
- [ ] **I/V:** Filters never call save/render/full review reload or fetch metadata, and do not mutate EN/drafts. Keep a view-owned pair reset on new openJob; any future P09 hook receives complete matching IDs and owns subsequent mounting/requests. Without P09, local hiding does not claim request cancellation or metadata-memory savings. Verify actual keyboard/touch/editor/late-ACK/hidden-choice save-render paths, complete counts and390px layout.

## P16 — ordinary preview/render fidelity

**What:** Extract any remaining generic mismatch between review preview and rendered coverage/frame identity.

**Why:** The user should edit what the renderer will actually apply. The fork includes useful fixes mixed with compound masks and plate geometry, but those larger features are not required for ordinary boxes/faces.

**When:** W3, or earlier for a confirmed bug. Each independent reproduced mismatch can be its own PR. Donors: `539432c`, `a056dff`, `c79cb29`, `4a6675f`, `e15c5eb`, `98c3231`, `77755f0`.

**Files / contract:** Relevant rasterization/render-setting/frame-readiness functions in `openscrub.py` / `openscrub_web.py`; `tests/test_review_render_alignment.py`. Share a small existing-owner helper only where it removes divergent geometry; avoid a generic graphics abstraction.

- [ ] **E:** Reproduce each candidate on current upstream: configured padding, clipped face ellipse, pending manual edit, dense-track frame, or asynchronous image/mask mismatch. Close already-fixed cases explicitly; preserve Austin's newer close-up face margins.
- [ ] **E:** Inspect the generic HDR silhouette and invalid-polygon hunks in compound-mask donor `8697c28` separately. Test sparse/edge masks at odd origins against every touched chroma cell, plus NaN/infinite/malformed geometry through actual render. The donor's all-filled-square fixture alone does not establish a regression. Exclude compound-hole schema/training dependencies; deliver independently proven fixes separately.
- [ ] **I:** Add a pixel/geometry regression per actual mismatch and a wrong-frame response case. The assertion compares the relevant mask/output pixels rather than mirroring the helper's implementation.
- [ ] **I:** Extract only the necessary coverage/settings/identity fix. A behavior-preserving helper extraction can be its own commit before the bugfix; no compound-hole, silhouette-training or plate-quad dependency.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_review_render_alignment.py -q`, build, affected browser checks and real synthetic SDR/HDR render where applicable.
- [ ] **D/R/L:** PR lead names the exact visible mismatch and affected setting/frame case. Include before/after synthetic evidence and preserve default output elsewhere. Declare any helper later used by P17 rather than bundling that feature now.

### P16A — cover every affected HDR chroma cell

**What / why:** Map the existing luma mask onto the global 4:2:0 grid by including every chroma cell touched by a covered luma pixel. Nearest-neighbor resizing misses cells at sparse/diagonal edges and odd origins. Research reproduced misses in 26 of 48 ordinary mask cases and in the exact bytes sent to an actual HDR encoder; luma coverage was unchanged.

**When:** Independent W3 bugfix, eligible earlier now that the actual render reproduction exists. It needs no compound-mask schema, plate-quad feature or custom model.

- [ ] **I:** Add an independent touched-cell oracle and sparse/edge regressions, including all origin parities, odd ROI sizes, clipping/frame edges and current padding. Retain the filled-square control, which alone also passes the old implementation.
- [ ] **I/V:** Change only chroma mapping in the existing owner; preserve luma, unrelated chroma cells, selected fill mode and current face/padding defaults. Check every supported mode and actual synthetic SDR/HDR paths, then run the suite/build.
- [ ] **D/R/L:** Explain the exact subsampling error and unchanged luma coverage. Use pre-encode planes for exact mask evidence and output probes for format/signalling; lossy decoded pixels do not prove exact coverage or a visible privacy leak. Keep geometry validation separate.

### P16B — retain the known-box fallback for invalid polygons

**What / why:** For a valid finite positive box, malformed/nonfinite or degenerate polygon data should use the existing full-box fallback. Current conversion errors stop rendering; collinear/repeated points can produce tiny nonempty masks that bypass fallback. Empty/two-point/empty-clipped masks already fall back and must keep working.

**When:** Separate W3 reliability PR after actual SDR/HDR regressions. Extract only this ordinary geometry behavior from mixed donor `8697c28`.

- [ ] **I:** Validate point shape, finite/int32-safe conversion and degenerate raster geometry, handling relevant conversion/OpenCV failures at the local boundary. Preserve the known valid padded/clipped region and selected mode. Do not import hole handling, arbitrary coordinate ceilings or changed dilation policy.
- [ ] **V:** Exercise real report-to-SDR/HDR rendering, malformed/nonfinite/collinear/repeated polygons, existing empty controls, valid clipped polygons, unchanged outside pixels, and failure cleanup. Run suite/build. A narrow shared raster helper is justified only if it removes actual SDR/HDR divergence.
- [ ] **D/R/L:** Lead with invalid polygon data inside a valid fallback box. State that an invalid box has no justified fallback; do not claim this patch resolves P16C or silently ignore invalid regions.

### P16C — invalid geometry, render cleanup and output publication

**What / why:** Establish separate contracts for invalid regions, owned render resources and preserving previous output. The [bounded actual-module research](execution/evidence/research/render-failure-boundary-research.md) on reviewed `12919c9` confirms that report/status transactions alone do not protect the previous video: failed report replacement or acknowledged cancellation can leave old JSON beside a newly encoded video. Direct cancellation deletes an existing final output, while geometry exceptions can bypass cleanup. These are separate failures and require separate reviewable changes.

**When:** P16C-G can be a small independent geometry PR; P16C-R follows the ownership inventory, with N09 kept independently reviewable. P16C-P depends on comprehensive resource cleanup and the reviewed P06 report/lifetime contracts. The parent card closes only after all three required contracts pass. None is a promise of crash-atomic video/report publication.

**Refined implementation handoff:** [Pinned source contracts](execution/evidence/research/render-delivery-contract-research.md) separate geometry preflight, complete resource ownership and staged publication without a broad renderer framework. The superseding amendment preserves ordinary Python/NumPy inputs and existing clip/control semantics, keeps legacy report publishers compatible, and distinguishes valid same-source/video fallback behavior from conflicting report/video destinations. For output-frame reads, capture an owning publication epoch, decode outside locks, then revalidate with one bounded retry/stale response; advance the epoch before final mutation and rollback attempts to prevent ABA. Streams still retain an opened descriptor and FILES ownership. Do not add long-reader admission gates or whole-media copies. A transient preprepared recovery descriptor keeps failed rollback artifacts identifiable through vault/restart, without promising crash-atomicity or automatic recovery. These are source-backed implementation directions, not passing runtime/platform evidence; exact reviewed prerequisites remain an implementation handoff gate.

#### P16C-G — validate source and derived regions

- [ ] **E/S/I:** Validate four finite numeric source coordinates with positive extents before coverage transforms and encoder acquisition, plus defensive checks at direct SDR/HDR painting boundaries. Validate relevant fps, offsets, translation/band arrays and margin inputs under an explicit compatibility policy; finite inputs can still overflow when combined. Preserve disabled/unknown report data. Give a useful detection/frame error rather than incidental conversion errors or a successful unredacted render.
- [ ] **I/V:** Keep valid offscreen boxes and ordinary empty intersections legal. Padding/clipping must not hide reversed or zero source extents. Invalid polygons inside a valid box remain P16B's fallback; an invalid box has no invented full-frame replacement. Check default/coverage modes, direct/worker SDR/HDR, per-frame overflow and valid clipping. Reuse existing geometry matrix evidence where applicable.
- [ ] **D/R/L:** Claim early malformed-input rejection and unchanged valid-input defaults. This card alone does not protect previous output from arbitrary later failures.

#### P16C-R — close all owned renderer resources

- [ ] **E/S/I:** Cover acquisition through final wait with explicit ownership and cleanup for captures/VideoWriter, both children, all pipe endpoints and temporary stderr. Include partial construction, geometry/callback exceptions, cancellation, write failure and nonzero encoder exit. Preserve primary exceptions and useful encoder diagnostics; bounded terminate/wait/kill fallback must act only on owned children.
- [ ] **V:** Keep exception tracebacks alive while asserting explicit closure and reaping, with tiny actual SDR/HDR/setup/mid-frame/final-wait cases and successful controls. Harness cleanup must be distinguished from production cleanup. N09's already-reaped-child/decoder-pipe case is a smaller prerequisite, not proof of this broader contract.
- [ ] **D/R/L:** State that cleanup alone cannot restore a final path already written by the encoder. P16C-P owns final-path preservation; this PR may land first with that limit explicit.

#### P16C-P — stage output before the final owned publication

- [ ] **E/S/I:** Encode SDR/HDR/OpenCV fallback into a private sibling stage, preserving container/extension/encoder defaults. Video-only calls replace the final path only after successful computation. For report-producing calls, finish report construction and hashes against staged bytes outside locks while provenance names the final path. Failed computation or cancellation removes owned stages, preserving previous final paths.
- [ ] **I:** Extend the caller's final publication hook to validate the exact operation and publish staged video/report plus success state under the stable report lock. Preserve P06B's admission lock order, selected-source pin, cancellation acknowledgement ordering and ownership through actual cleanup. No lease admission/release or large copy/hash work inside the report lock.
- [ ] **I/V:** Ordinary second-file replacement failure requires transient rollback references/copies and restoration, including absence of old finals. Test each step and failed rollback itself. If restoration I/O fails, expose an explicit failed/recovery state and retain necessary task recovery files; do not promise impossible restoration. No database or permanent generation archive. Staging names must fit vault cleanup and packaging conventions.
- [ ] **I/V:** Coordinate download stat/open with publication or derive metadata from one opened descriptor; retain that descriptor/lifetime through response close without holding the report lock for transfer. Pin output-frame decoder generations too. Test old streams/new commits, conditional/Range identity, cancel/retry and ordinary failures. Independent requests can straddle a commit; pair-level export snapshots need a separate explicit contract if required.
- [ ] **D/R/L:** Record the exact previous-video/report guarantee and tested failure boundaries. Two replacements are not a crash-atomic pair. Directory durability, crash recovery, filesystem refusal and native Windows open-file replacement remain explicit separate limits. Run relevant suite/build/Python-floor and real output checks, then C01 combined lifetime/publication validation.

### P16D — keep editor overlays and pointer coordinates aligned on resize

**What / why:** Recompute the ordinary editor's media-to-canvas transform when its displayed size changes. Paired full-browser probes of Austin's baseline and P07a show the same existing defect: the image shrinks from 640 to 326 CSS pixels while the canvas remains 640 pixels wide with scale 1. The painted edge is displaced by 158 pixels and clicking the visible target misses it. Scrubbing or reopening restores alignment. This is a display/edit-coordinate defect, not evidence of incorrect engine masks.

**When:** Separate small W1/W3 UX fix; baseline provenance is confirmed. It does not block or belong inside P07a. Reuse P07a mount/view guards only with an explicit dependency, or keep equivalent minimal ownership local when targeting Austin independently.

- [ ] **I:** Keep canvas CSS/backing size, drawing and inverse pointer mapping on one current transform derived from finite positive dimensions of the visible image/video. Observe the actual mounted media/container; viewport resizing must not require a frame reload, scrub or save. Do not merely CSS-scale an unchanged hit-test surface.
- [ ] **I:** Preserve source-space boxes/manual additions, content-space overrides and their `ox/oy` conversion, time bounds and pending drafts. Resize alone must not create/move a saved box. Handle an active gesture coherently when the transform changes, and release/invalidate observers/callbacks when the editor, job or media is replaced.
- [ ] **V/D:** Retain actual painted-pixel and target-hit regressions; test shrink/grow, pointer add/move/corners, nonzero offsets, unchanged save coordinates, playback/image switches, zero/hidden dimensions and close/job-switch cleanup. Run suite/build and browser checks. Record high-DPR/other-engine coverage honestly. Keep mask defaults, plate-quad features and broad responsive redesign out of this PR.

## N09 — close decoder stdout during ordinary HDR cleanup

**What:** Explicitly close the owned decoder stdout pipe in existing HDR cancellation/encoder-write cleanup, alongside the encoder stdin and child termination/wait steps.

**Why:** Actual `run_render` → `render_hdr` cancellation and injected real encoder-write failure leave decoder stdout open while a caller retains the exception traceback; both children are already reaped. Releasing the exception and collecting its frame cycle closes the pipe, so the evidence is missing deterministic cleanup, not an unconditional permanent leak. The complete pinned donor closes it immediately without section arguments.

**When:** A small separate W2/W3 reliability PR from the generic two-line part of `08f432b`, independent of section features, mask changes and P16C's broader output lifecycle. The [retained baseline](execution/evidence/research/hdr-decoder-cleanup-baseline-research.md) covers ten actual cases and terminal cleanup of all 40 children.

- [ ] **I/V:** Add actual HDR cancellation and encoder-write error regressions with retained traceback/handle references, asserting decoder stdout and encoder stdin are closed and both children reaped. Keep successful frame/tag and unchanged before/after output controls, using a tiny synthetic clip. Preserve raised cancellation/error semantics and the existing ordinary cleanup boundary.
- [ ] **V/D:** Run relevant render regressions, existing suite and build; record Python/platform/encoder coverage. Explicit close does not establish an interruptible native-call deadline or cancellation latency beyond existing checkpoints.
- [ ] **D/R/L:** Explain the concrete retained-exception case and small source provenance. Keep final encoder-wait failures, retained temporary stderr handles, arbitrary compute exceptions and prior-output publication/preservation under P16C; the baseline did not create a prior output to test its preservation.

## P17 — manual whole-plate four-corner masks

**What:** Let a user specify a plate quadrilateral and render it consistently in review/SDR/HDR.

**Why:** A rectangle can cover substantial surrounding image. A manual quad offers tighter whole-plate coverage using existing detection, with no custom segmentation model or new review database.

**When:** W3 after P10A exact editable samples and applicable P16D resize/P16A HDR coverage prerequisites; explicitly welcomed in #22. Use early `617c9ac7` / editor `5c0782f` and integrated equivalents. The source-frame lessons from unmerged PR #70 are evidence, not a pre-merged feature.

**Files / contract:** Existing editor/render/report code; `tests/test_plate_quad.py`, `tests/test_plate_quad_editor.py`, `tests/test_plate_quad_render.py`. Proposed additive geometry records four normalized points in the inspected source-frame coordinate system plus source/frame provenance; append optional dataclass fields to preserve positional callers. Keep the exact conversion contract in the PR so preview, persisted points and renderer agree.

**Source-backed refinement:** [P17 contract research](execution/evidence/research/plate-quad-contract-research.md) verifies the current report/replay/render interfaces at12919c9 and identifies incompatible donor assumptions. Prefer P17A source-bound record/transaction/render support, then P17B ordinary four-corner editing; combine only if the resulting diff remains small. The proposed field/token/PTS spelling remains provisional until P10A implements exact sample identity. This is source-only design, not passing frame/HDR capability evidence.

Preserve useful disclosure from mixed donor `eedef89`: a saved plate quad/group is not proof of perspective tracking through every frame. Retain plain detector/output wording where useful, excluding custom checker scores and learned-filter state. This belongs in P17's UI/docs review and O02's separately verified tracking contract.

- [ ] **E/S:** Use full-source-frame edge coordinates `(x/W,y/H)`, finite strictly convex ordered points and explicit source dimensions/frame identity; reject out-of-frame writes rather than silently clamping them. Derive the raster ROI from the quad, with existing configured padding/drift, rather than clipping to the detector box. Reuse existing scan-source digest work; no new whole-video hash per edit or fabricated PTS. Preserve all twelve positional Detection arguments by appending the optional field. Omit absent quad keys in fresh ordinary reports; preserve explicit raw stored data. Old upstream reports and experimental fork fields remain valid/opaque without silent migration.
- [ ] **I:** Add tests for ordered/convex finite points, degenerate/out-of-frame geometry, source/normalization transforms, report round-trip and positional constructor compatibility. Add a moving plate case proving the same relative quad is not blindly stretched across later boxes.
- [ ] **I:** Port the small editor/renderer behavior. Bind the manual quad to its actual source frame; preserve the detection's full interval rather than truncating it to that frame. In the upstream-default path use existing full-plate coverage on other/unsupported frames. Arbitrary shape tracking belongs to O02, not an implicit claim in this PR.
- [ ] **I:** Extend the existing latest-report transaction and per-job P07a deep snapshots/value-equality ACKs. Geometry deltas target the concrete inspected row, with a source/sample precondition; no group fan-out, new action version store or manual-creation schema change. Failed geometry saves retain independent Blur/Keep/audio and newer drafts; reapplying identical current geometry is idempotent. A saved quad never implies an output choice or training confirmation.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_plate_quad.py tests/test_plate_quad_editor.py tests/test_plate_quad_render.py -q`, build, browser editing and real SDR/HDR synthetic renders. Verify source-frame binding and unchanged default masks. Actual normalized/original HDR correspondence must be established by the owning source resolver, not injected metadata, equal dimensions or count tolerance. Unsupported correspondence keeps full-plate fallback and leaves P17 HDR capability open; a restricted SDR pass does not close the parent.
- [ ] **D/R/L:** Describe manual tighter whole-plate coverage, exact temporal limitations and fallback behavior. Do not advertise automatic plate boundaries or lettering-only anonymization. Submit the welcomed manual feature separately from downstream policy/research.

## P18 — Stop & Review and resume

**What / why:** Commit a consistent partial scan, inspect/edit it in ordinary review, and resume the suffix without replacing reviewed prefix choices. Long jobs should retain useful progress without custom learning, sections, a journal or a full-prefix rescan.

**When:** Three reviewable parts after the relevant P06/P07 contracts. The welcomed donor interfaces are retained, but [source research](execution/evidence/research/checkpoint-scope-research.md) shows the early bodies lose raw fields, assume reset scroll coordinates are compatible and conflate EOF/fast-stop/completion. Its partial-render amendment supersedes the initial blanket export-gate proposal. Research is source-only; implementation/runtime acceptance remains open.

### P18A — portable checkpoint and raw-document merge

- [ ] **S/I:** Add `openscrub_internal/checkpoints.py` with `with_checkpoint(doc, frame, total, options)`, `validate_resume(doc, source_sha256=None)` and `join_reports(previous, continuation, next_frame, total_frames, completed=False)`. Use strict schema/type/identity validation and useful errors; reuse atomic reports. Unsupported incomplete donor schema requires an explicit fresh-scan/migration disposition, not guessed compatibility.
- [ ] **I:** The first unprocessed frame b defines committed `[0,b)`. Partial cum/bands arrays have exactly b finite entries; full arrays have N. Capture exact scanned/original/render source participants and normalization identity, FPS/dimensions/count provenance, plus immutable effective scan settings and file-backed/model content identities. Paths/mtime/default config strings alone do not establish resume compatibility.
- [ ] **I:** Begin merge from a deep copy of the full previous raw document. Preserve all old row dictionaries/order, disabled/zone/manual/geometry/time/grouping fields, immutable replay data, audio redactions and unknown row/top/provenance fields. Append only authorized suffix output with fresh track/person IDs; change only declared scan-owned fields and invalidate stale output identity. No cross-boundary remerge or inferred inheritance of Keep.
- [ ] **I/V:** Require forward progress and exact completion proof; no-progress stop keeps prior bytes/file identity. New automatic checkpoint rows carry paired strict integer `scan_frame_start` / exclusive `scan_frame_end`, intersected with existing time activity. First prefix gets `[0,b)`; appended suffix `[b,e)`. Preserve original timestamps and keep bounds after completed resume/render. This is the selected contract; timestamp bias is excluded. Legacy ordinary rows omit the pair and keep their behavior. Older renderers ignoring bounds are not compatible checkpoint renderers.
- [ ] **V/D/R:** Pure validation/merge/repeat tests establish strict source/settings/schema/timeline/progress and full raw preservation before engine/UI use. Verify helper packaging/Python floor. Describe a portable contract; this PR alone does not ship Stop & Review.

### P18B — whole-frame engine boundary and suffix coordinates

- [ ] **I:** Add a distinct operation-owned graceful stop callback/Event. Finish the current frame and ordinary postprocessing before committing a candidate boundary; Cancel still aborts. Record explicit loop exit reason, complete selected scope accounting and consistent arrays. A false OpenCV read or missing end_frame is not proof of completion; verify canonical count/termination provenance and fail without replacing a checkpoint when that cannot be established. Do not add an unbounded second full-video pass to manufacture confidence.
- [ ] **I/V:** Use a declared bounded context overlap (initial donor-derived proposal one second in frames), with verified start and no semantic analysis before it. Reconcile new scroll origin using a common observed frame: shift new cum and aoff by delta, cbox by minus delta; preserve old arrays/rows and splice bands as deltas. Prove screen-position/drift equivalence with nonzero scroll and an old user-extended row. Exact uninterrupted detector equivalence is not promised.
- [ ] **I/V:** Clamp new automatic authority to suffix frames, including120fps where existing±0.01time slack crosses a raw cutoff. Preserve geometry/authority through coverage projection, SDR/HDR, boxes/thumbnail reference frames and render/reopen. Explicit accepted time edits can relinquish only that row's bounds; enabled/box changes or replay cannot. Such an edit must still have supported coordinates.
- [ ] **I/V:** Preserve manual annotations and raw audio choices. Unsupported setup-track continuation must refuse explicitly, not discard an earlier seed's remaining interval. Partial audio analysis may be deferred and labelled; final full-file transcription is a declared exception to suffix-only visual scanning, and must not overwrite saved redactions or reapply automatic choices.
- [ ] **V/D/R:** Actual tiny scan/postprocessing/stop/resume tests with controlled detector input, source-frame/scroll/high-fps/output assertions, cancellation/failure and packaging checks. Keep P11A decoder optimization separate and reuse its evidence. No UI/diagnostics/training dependency.

### P18C — controls, restart and owned publication

- [ ] **I/V:** Distinct Stop & Review/Resume actions use current admission, stable report lock, qgen and operation Events. Signal captured attempts, reject stale/double admission, compute/hash outside locks and publish latest raw document plus matching partial state under the existing transaction. Retain ownership through actual cleanup, preserve queued Cancel/Retry, and never publish an old operation after cancellation acknowledgement.
- [ ] **I/V:** Restart recognizes a valid partial marker even beside an old/new output file. Resume validates source/settings, saves the captured current drafts first and does not start on failed acknowledgement. Newer/pending/manual/audio choices survive. CLI uses explicit checkpoint/resume controls; ordinary Ctrl-C keeps cancellation semantics. Use full canonical duration plus a separate processed boundary so partial arrays cannot reinterpret fractional UI times.
- [ ] **I/V:** Permit an explicit render/export of current valid choices while keeping scan paused, boundary/audio-incomplete labels and Resume available. Stop never automatically queues skip-review rendering. Generated rows honor their frame bounds; automatic bands end at b, and unprocessed regions without an explicit choice pass through. No frozen detector box, repeated final band, inferred future scroll or mandatory completion gate.
- [ ] **S/I/V:** Preserve explicit manual/audio choices. Geometry depending on unavailable future cum must produce a targeted row/span error, not be silently reinterpreted or dropped. A separate explicit screen-coordinate path may be justified, but its proposed geometry_space/manual-replay representation is not adopted by this initial contract. First delivery must state any unsupported manual-after-boundary coordinate case precisely; malformed/incompatible source/geometry errors remain valid correctness checks.
- [ ] **V/D/R:** Real web/CLI scan→stop→edit→restart→resume→render plus explicit partial render, current-operation races, failed publication, no-progress cycles and full row/audio/output preservation. Include strict120fps activation boundaries and nonzero terminal bands. Document feature-version compatibility, source/count limits, supported manual geometry and actual package/platform validation in `docs/STOP_REVIEW.md`. No claim that partial inspection/export means all frames were scanned.

## Review focus

Do not claim hardware support from mocks, cross-run cache persistence from a local builder, exact temporal geometry from box tracking, or full scan completion from a checkpoint. Keep default review/redaction semantics intact and test every new module in the distributions that ship it.
