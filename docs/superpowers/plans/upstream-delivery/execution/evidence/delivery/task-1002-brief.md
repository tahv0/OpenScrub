# Strict tracker seeds implementation plan

> For agentic workers: use superpowers:subagent-driven-development. Execute the single coherent task below, then independent review. User already selected supervised GPT-6.1 Sol high execution; routine implementation choices do not require another user approval.

**Goal:** Let optional strict Track requests initialize every existing tracker from the inspected source sample, while preserving ordinary callers and tracking algorithms.

**Architecture:** Reuse Task1001's observed source owner and indexed reader. A short web verification capture closes before model work; a capture-free private seed carries pixels and validated timing metadata into the existing person/Vit/NCC branches. Their current capture owners remain responsible for cleanup and indexed priming.

**Tech stack:** Existing Python>=3.9, OpenCV/NumPy, Flask and existing inference/tracker integrations. No new dependency or model download.

**Spec:** [Exact-editor contract and adopted amendments](../research/exact-editor-contract-research.md), especially the final capture-free seed amendment; [readiness adoption](../research/exact-editor-readiness-adoption.md); [Task1001 supervisor decisions](task-1001-supervisor-rulings.md). Later adopted amendments supersede earlier live-capture-transfer examples.

## Global constraints

- Preserve Austin upstream defaults, all existing positional callers, P06 source/lifetime/report transactions, P07a draft ownership and P07b immutable manual replay.
- No custom training/workbench, new models/dependencies, frame digest, source registry, token history, whole-input scan/hash, alternate decoder or generic worker framework.
- Ordinary editor JS/CSS and legacy Track remain usable and unchanged. This task does not switch the editor, disable Track, change loss/search/smoothing thresholds or implement O02/P17.
- For strict requests, models initialize only after source/sample verification. A strict sample/prime failure cannot become tolerant nearby fallback. Ordinary model/detector failures may select another existing engine with the same supplied pixels; no-seed model ordering remains unchanged.
- Keep captures with existing owners; never transfer a live web capture to the engine. Source preparation/release and native/model work remain outside report_lock.
- Original checkout/user data and other branches remain untouched. No publication, nested agents, broad cleanup, new root production file or unrelated cancellation patch.

## Review focus

1. Fractional/last-frame selections: native24 requested0.2 resolves index4/canonical1/6; native5 requested1.9 resolves9/1.8; normalized duplicate pixels retain distinct indices. Initializers and strict prime use the retained integer, never rounded t_ref or a nearby frame.
2. Person miss/model failure: fallback may change engine, but supplied seed pixels remain identical. A failed strict prime propagates instead of entering tolerant fallback.
3. Cancellation/source/timeline change between admission, verification, model work and append: no stale rows publish, captures close before leases, and pre-model failures make zero model calls.
4. An unrelated choice/audio publication remains legal during tracking; changed coordinate timeline/source rejects conversion. Result append starts from latest raw JSON and preserves every unrelated/unknown field.
5. Legacy/no-seed calls retain nearby person/Vit selection, NCC reread/priming behavior and existing outputs/status protocol. Invalid explicit seed never silently takes that path.

## Task 1002: optional inspected-sample seeds through existing initializers

### What, why and delivery order

This is the second P10A backend contribution. Task1001 makes pixels/geometry coherent, but the tracker can still deliberately choose nearby initialization pixels. Fix that at each actual initializer before the ordinary editor submits strict seeds. Deliver this focused optional adapter after reviewed Task1001, then assemble only the necessary P16D/editor prerequisites and migrate the editor plus Track together. C01 composition remains a separate gate; do not use the entire combined branch as this focused PR's prerequisite.

Supervisor creates pr/exact-tracker-seeds from exact reviewed Task1001 head **335435e1e1120de9e6773656b7dfdfabf220e27b** in the existing managed source worktree. Preserve pr/exact-editor-samples, C01 b4fc209 and documentation refs. Read Task1001's final acceptance/fix review and its measured decoder/source limitations before implementation; do not repeat the28-capture feasibility study or earlier cost matrix.

### Files and responsibilities

- Modify openscrub_internal/exact_samples.py: one small frozen StrictSeed value; existing finite/indexed policy remains the source of timing validation.
- Modify openscrub_web.py: optional seed parsing/admission, one shared raw-source decoder adapter for sample/strict worker, and launch/pre-model/pre-append fences. Keep existing operation/status/publication owners.
- Modify openscrub.py: optional strict_seed keyword branches in track_manual_region and _track_person_dense; existing initializer/capture owners otherwise remain intact.
- Add tests/test_strict_tracker_seed.py for actual person/Vit/NCC initializer/prime contracts and no-seed controls; tests/test_strict_tracking_routes.py for production route/operation/publication boundaries. Reuse owned exact media/store fixtures rather than duplicate fixture systems.
- Existing package declarations already include the private package/tests; verify actual source→sdist→wheel bytes instead of adding speculative packaging changes.

### Adopted interfaces

Consume the existing exact.read_indexed_capture(cap,index,*,fps,count,width,height,tolerance_s), DecodedFrame, POLICY, _exact_snapshot(job), _exact_policy(doc,selected), _parse_sample_precondition(value,row=False), _check_sample_precondition and _exact_current_locked owners.

Add a private frozen StrictSeed in exact_samples.py with fields:

    pixels, source_selection, index, canonical_s, observed_s,
    fps, count, width, height, policy, tolerance_s

count and tolerance_s are the minimal additional validated facts required by the now-concrete indexed reader when priming existing engine captures. Carry no timeline copy/live capture/HTTP image bytes or mutable browser authority. source_selection is the small in-process observed selection; source lifetime remains the web worker lease's responsibility.

Append keyword-only arguments without changing current positional signatures:

    track_manual_region(video,box,t_ref,t0,t1,cb=None,step_frames=2,
                        thr=0.55,scale=0.5,person_det=None,*,strict_seed=None)
    _track_person_dense(video,box,t_ref,t0,t1,det,log,step_frames=2,
                        cancelled=None,*,strict_seed=None)

Factor only the shared raw-source open/stamp/read/close boundary in web:

    _read_exact_source(selected,index,*,fps,count,tolerance_s) -> exact.DecodedFrame

The caller already owns admitted source lifetime. The adapter owns/releases its short file handle/capture and preserves Task1001's selected-source409 handling and observed checks. It returns raw pixels, never a live capture. The sample route encodes afterward and keeps its final source/report/cancellation fence; strict workers close verification before models and keep their own operation/source/timeline fences.

POST /api/jobs/<jid>/track_object adds optional seed with exactly the sample-precondition fields: version:1, source_ref, timeline_eq, policy, index, width, height, offset. It is not the whole sample-response object and contains no browser pixels/row context/baseline. Explicit malformed/null seed is an error, not legacy fallback. Existing accepted response/status polling structure remains compatible.

### Steps and checks

- [ ] **1. Establish meaningful initializer REDs.** Add production-engine spies for person detection/histogram/both anchors, both Vit initializers and NCC template. Supply a marker-distinct verified frame and compare actual initializer arrays against that independent frame through the existing resize/gray operations. Retain missing-API RED, then actual branch-oracle REDs before their fixes; a missing keyword alone is not all behavioral evidence. Add tests named test_strict_person_uses_supplied_pixels, test_strict_vit_uses_supplied_pixels_in_both_directions, test_strict_ncc_template_uses_supplied_pixels, and test_strict_prime_failure_never_enters_nearby_fallback. Their assertions include exact arrays, selected index4/canonical1/6 and exactly-once capture releases.
- [ ] **2. Implement the capture-free seed and strict engine branches.** Person examines the supplied frame once, with no nearby dt loop; its histogram and both propagation anchors use it. Vit skips nearby selection and uses the supplied frame for both initializers. NCC derives g0 from it rather than _gray(t_ref). Validate strict input/policy/window/box, propagate ExactError before tolerant fallback, and preserve ordinary detector/model error fallback with the same seed. Direct no-seed calls keep existing behavior.
- [ ] **3. Prime existing captures through the indexed reader.** Each needed person/generic capture establishes its after-seed position using the shared reader and validated count/tolerance; priming pixels cannot replace supplied initializer pixels. No rounded _grab_frame(t_ref), unchecked index+1 seek or nearby priming. Keep current try/finally ownership even if prime/model/helper fails. Tests inspect actual primer indices, initialization arrays and release ordering; no new tracker algorithm or subsequent exact-propagation claim.
- [ ] **4. Add the optional web launch path.** Strict box/time values are finite/nonboolean; require 0<=x1<x2<=width and 0<=y1<y2<=height, with canonical t_ref=index/fps inside the chosen t0..t1 window. A narrow incompatible window fails clearly without moving the seed/widening it. Validate source/timeline/policy/index/dimensions/offset before model work. Prepare snapshot/source/work ownership outside report_lock and revalidate before installing the operation. A recovered normalized selection must be the source actually owned by the work lease. Release extra preparations outside the lock.
- [ ] **5. Verify/release before models and revalidate before append.** The strict worker decodes the retained integer through _read_exact_source, releases that capture, rechecks current operation/source/timeline, then resolves existing models. After tracking, reload latest raw JSON under the existing transaction, revalidate coordinate equality/source/operation before conversion, allocate latest track ID and publish once through the existing success notifier. Do not bind geometry to whole-report publication epochs; an independent choice/audio update remains legal. Explicit strict failures use existing done/added0/error status and zero publication.
- [ ] **6. Exercise real route races and legacy compatibility.** Tests named test_strict_launch_verifies_before_models, test_strict_capture_closed_before_model_resolution, test_strict_source_or_timeline_change_rejects_append, test_strict_unrelated_choice_audio_merge, test_strict_window_rejects_uncanonical_reference, and test_legacy_tracking_keeps_nearby_behavior cover Review Focus1–5. Use actual production routes and bounded Events/joins with unconditional cleanup, including decode/prime/model/thread-start/commit errors and retained exceptions. Preserve raw rows/disabled/manual/audio/unknown fields. Before any body change, retain the relevant genuine RED. No model download is needed for deterministic branch spies.
- [ ] **7. Check real tiny-source pixels and ordinary UI compatibility.** Reuse the retained native/normalized sources and independent sequential/PTS oracles at the known wrong-sample times, including distinct normalized duplicate indices. Actual web verification and engine priming must agree under the existing policy; supplied initializer pixels remain the inspected ones. Run one bounded full-PAGE ordinary legacy Track smoke: unchanged button/payload without seed, real route/worker/status polling, deterministic no-model tracker control, failure disclosure/cleanup and retained drafts. This is legacy protocol compatibility, not exact editor migration, resize or tracking-quality acceptance. Use prepared browser tooling only; record Browser-plugin availability/fallback and all test doubles.
- [ ] **8. Freeze and verify the coherent slice.** Run focused owners, ONE stabilized discovered full suite, actual Python3.9 owning cases, and one offline sdist→wheel-from-sdist/installed origins/defaults/CLI/web/HTTP gate. Check exact engine/web/private-seed/new-test bytes and actual shipped inclusion; preserve Python>=3.9 and unchanged JS/CSS/default profiles. Installed no-model strict/legacy HTTP checks retain source/cleanup/publication behavior. Record seed/prime work counts and their scope; no old cost/scale/feasibility or universal latency benchmark. Any timed comparison requires root coordination.
- [ ] **9. Commit, self-review and document.** Commit assigned branch only; write task-1002-report.md and task-1002-pr.md with base/head, optional schema/private interfaces, initializer/prime evidence, resource/operation boundaries, actual commands/REDs/results/package/browser limits and what remains for UI/P16D/C01. Compact evidence goes under task1002-evidence; runtime under runtime/task1002. Root dispatches independent task review before source adoption or the next dependent slice.

Verification commands name the actual source files, for example python -m pytest tests/test_strict_tracker_seed.py tests/test_strict_tracking_routes.py plus existing exact/manual/lifetime/transaction/tracker owners; full discovery remains python -m pytest. Execute through the existing reviewed launcher and task-local configuration, not an unisolated environment. The supervisor's local execution notes supply finite pools/tool pins; they are deliberately outside this public source handoff.

## Self-review and remaining delivery gates

The five review-focus classes map to steps1–7. Interfaces retain all old positional parameters and reuse the reviewed integer/policy/source owners; count/tolerance resolve the concrete priming requirements without a new service. No user-facing switch occurs here. The next editor/Track migration must consume reviewed P16D, preserve current draft/ACK/mount ownership, handle non-JSON admission failures and account for measured O(N) sample work with coalescing/bounded dispatch. Prefer a focused prerequisite assembly and focused UI PR, then separately validate C01's current scheduler/source/output/cancellation owners. P10B native interruption, O02 correction/loss policy and P17 source/HDR mapping remain separate.
