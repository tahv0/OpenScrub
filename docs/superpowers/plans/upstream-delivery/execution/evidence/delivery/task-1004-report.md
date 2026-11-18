# Task1004 implementation report

Status: **DONE_WITH_CONCERNS** — implementation and required correctness/shipping gates pass; fresh independent review of the complete contribution is still required before adoption. No push, PR publication, merge, external deployment or working-version adoption occurred.

## Source and preserved boundaries

- Source: `/home/tahv0/.codex/worktrees/bde3/OpenScrub`, branch `pr/exact-editor-ui`.
- BASE: `07cfaa9539a2561c26b6f7280fae6702eb07137c`.
- HEAD: `dcaa0e5af6aedfca8685a3e64bea86ad0262f5c2` (one coherent editor-and-Track commit; clean).
- 136 tracked files; the ten existing runtime modules remain the runtime inventory. Seven changed paths: `openscrub_web.py`, `README.md`, the existing resize launcher/server/browser test, the shipped-JS owner test, and new `tests/exact_editor_browser.cjs`.
- Every Python AST node outside literal `APP_JS` is identical to BASE, including backend routes and `APP_CSS`. Engine, private helpers, dependencies, defaults, assets, report format, updater implementation and platform packaging sources are unchanged. The accepted exact/seed/backend proofs retain their original attribution.
- Web file SHA-256: `33cd9d19ff9ea9542d14408be7840929dafd2b9bc6c8ae240fc7aab410d8cc32`.
- Evaluated APP_JS SHA-256: `6eb555d4edf6500ca8f697b566f5b898e84925a8a246dd52b0c5e2233ff7ee57`; APP_CSS: `6c324da4b20e83eb740a31150ec8d166c326c49fd8914bec09e4abe2f79b3220`.

All 160 earlier refs remain present. Only this task branch and the explicitly authorized independent documentation ref changed. Documentation exception: `refs/heads/docs/upstream-delivery-plan`, `1e7c6e2c6ecc8384d5b3a2a6590c6d89f7bcd17d` → `cf044937e62fef0a08252fc863e82ce8173887c0`. Every other ref, including the independent matcher, is unchanged. See `task1004-evidence/refs-preserved.json`.

The original brief's policy literal was incorrect. The binding [protocol erratum](task-1004-protocol-erratum.md) requires the accepted backend's exact `opencv-ffmpeg-zero-cfr-v1`. Client validation, VM fixtures, geometry/manual evidence and Track use that value. A negative control rejects `cfr-index-v1`; the backend was not renamed or weakened. Original dispatch snapshots and failed wire diagnostics remain attributed.

## Delivered behavior

The bounded block beside BE_VIEW owns one unsettled exact-sample cycle through fetch, response body, detached decode, displayed-image decode, application and URL cleanup. One latest desired request survives across scrubs, mounts and jobs. Issued work is not aborted to release the slot. Readiness requires the current mount/serial, decoded current URL/dimensions, connected image/canvas and usable current transform. Geometry and Track refuse unavailable samples; audio, output choices and window controls remain independent.

Open intentions fence metadata/report continuations before awaits, including same-editor reopen. Playback has its own serial: tolerant responses, metadata, rAF and cleanup cannot overwrite paused exact geometry or a restarted session. Pointer continuations retain their pointer, selected raw row and mounted owner. Timeline continuations retain mount/editor/timeline/gesture ownership; old move/up events cannot edit or clear a replacement gesture. Recovery controls update after pointer completion to avoid moving the image during a drag.

The first deliberate geometry mutation captures complete strict evidence atomically. Scrub/reopen/report display does not rebase pending drafts. New Add/Track regions require finite nonempty in-frame bounds and a canonical reference inside the chosen window; rejection preserves the window. Add captures the eight-field sample precondition and canonical creation time after checking prompt continuations, with one stable manual ID. Genuine legacy drafts retain the optional legacy wire path.

A draft owns at most one unresolved save snapshot. Explicit Save confirms its identical payload before newer edits. All required strict ACK rows validate before any submitted state clears. Equal submitted kinds clear only in their owned family; newer/different kinds survive and advance only to the returned complete baseline, including returned last_seen. The current safe row is reconciled using its current offset and active-span rule; another mount/context instead loses readiness and obtains a fresh coalesced sample.

A first authoritative geometry_conflict releases only the rejected snapshot; uncertain attempts retain identical-retry ownership, including after a later conflict. The text-only save status has sibling bounded controls for abandoning an uncertain retry and discarding one selected pending row/addition followed by fresh inspection. They preserve other geometry, immutable additions/IDs, choices, audio and baselines; confirmation rechecks values and ownership. They do not undo saved data, rebase, remap, save or render automatically.

Track submits a synchronous copy of the inspected source box, canonical time, window and exactly eight seed fields. POST/poll URLs and results retain the initiating job/mount/launch. An owned result refreshes review and obtains a new exact sample while preserving pending drafts. The deterministic PAGE engine fake exercises the real strict route, decode, poll and append; it makes no tracking-quality claim.

## Verification and commands

Controller: `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py`, unchanged SHA-256 `354cf49b0c83d11f3945137fbdffc3ac6b2793f1217ac39a9b62270097940067`. Frozen configs prospectively pin all source/test files, ten imports, native extension/loader records, actual interpreter, cached media/model, adapters and browser prerequisites. Native and floor tooling remain separate.

The command prefixes below are exact canonical invocations; the controller records the actual child argv, run ownership and resulting logs. Paths abbreviate SOURCE=`/home/tahv0/.codex/worktrees/bde3/OpenScrub` and RUNTIME=`/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1004`.

| Gate | Actual result and source-bound run |
| --- | --- |
| Stable development owner, Python 3.12.16 | 141 passed, 17.98s; `task1004-cc5ee97f367e4f29aa7de89e2382562a` |
| Final native full suite + both PAGE cases, Python 3.12.16 | **620 passed**, no skips, 146.63s; `task1004-532cccd239cf421d9654b6493f3cb9d3`; command-log SHA `153c8ac420ef5d9a97e7a7f4aec560d17bd2e98539015af2205049517d44727b` |
| Changed JS owner, actual Python 3.9.25 | **141 passed**, 19.80s; `task1004-aebf628ae8394fc3b53ad8aff50a3d58`; log SHA `2c3bb569e01113feec36e9a605f3c5acddd9697c879a74691a7394b7dcb27cbc` |
| Actual 3.9 launcher/server compatibility | Adapter imports the changed launcher, starts the actual server with the same 3.9 executable, checks PAGE/mediainfo/exact sample, records child identity/origins and terminates/reaps; exit 0, `task1004-71c3d5513e184ffa8f5f50a02256c80b`; log SHA `72faeff1455df645eef76b5905192da8927866985e9bf159eb6dce06a39aa376` |
| Native offline package/installed gate | All actions exit 0; `task1004-79c561c306fd48dd8d2176788d0f4e3c`; installed-adapter log SHA `4dfb8330b6c6f37ff1ac38de6bb1531c414208e6637376c6071e29513e7b8da4` |

```text
/usr/bin/python3 VERIFY --config RUNTIME/final-full-page-312.json run -- -B -u -m pytest SOURCE/test_openscrub.py SOURCE/tests/ -q -o 'pythonpath=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task1631-evidence/adapters /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task654-evidence/adapters' -p task1631_fixture -p roundtrip_stdout_selected
/usr/bin/python3 VERIFY --config RUNTIME/final-owning-39.json run -- -B -u -m pytest SOURCE/tests/test_review_save_failures.py -q
/usr/bin/python3 VERIFY --config RUNTIME/final-owning-39.json run -- -B -u RUNTIME/floor_fixture_smoke.py
/usr/bin/python3 VERIFY --config RUNTIME/final-package-312.json package
```

Actual native interpreter: `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` 3.12.16. Actual floor interpreter: `/tmp/openscrub-python39-20261117/venv/bin/python` 3.9.25. The known cached YuNet and both existing fixture plugins were supplied, not just their JSON prerequisites. The stdout adapter remains restricted to `test_report_roundtrip.py::test_real_render_and_fresh_route_reopen_keep_all_ten_rows`. No downloads, environment installation, alternate decoder or shared-controller change occurred.

### PAGE, pixels, persistence and console

Browser plugin absent; the prepared regular Playwright 1.65.1, Node 22 and Chromium headless-shell 1255 were used on Linux, DPR 1 and 2. Each scenario and its fresh-process check has its own artifact directory. Both PAGE cases ran as part of the final native full suite; no second final PAGE replay was performed.

Retained media hashes match the existing task1001 manifest. Sequential native decode, independent FFprobe integer PTS and source marker pixels establish the expected frames; `cum[i]=[2*i,-i]` supplies the independent offsets:

| Input/request | Inspected ordinal/canonical | Independent marker | Offset/source row box |
| --- | --- | --- | --- |
| CFR24, .2s | 4, 4/24 | 4 | [8,-4], [28,26,88,66] |
| CFR5, 1.9s | 9, 1.8 | 9 | [18,-9], [38,21,98,61] |
| Normalized, .5s | 6, 6/13 | 5 | [12,-6], [32,24,92,64] |

The normalized source marker is 5 at ordinal 6; the expectation comes from the independent sequential source, not from editor response fields. Both disabled raw rows and concrete indices remain available.

The actual PAGE checks hold response bodies and detached image decode separately, exercise rapid scrub/same-editor reopen/A→B→A, ensure only the latest wanted request survives, and reject geometry until ready. Candidate URLs remain bounded to one active candidate in addition to the displayed URL. Resize checks independently measure painted edges and inverse pointers through DPR/shrink/grow/fractional/mid-gesture/hidden/zero/containment changes without a sample request or pending-value rebase. Readback copies the production canvas into a test-only `willReadFrequently` surface; production painting is unchanged.

DPR2 uses the real detections route, retains exact row/manual preconditions and immutable IDs with nonzero offset, commits a real save while losing its ACK, adds opposite-kind geometry, verifies the identical retry and returned complete-baseline advancement, then saves the newer edit. Disabled/opaque rows, audio and deliberate enabled choices survive. A controlled HTTP409 render refusal follows a successful save and preserves the saved report with one manual ID. The other PAGE case performs a real SDR render and independent dark-core/outside-edge validation. Fresh pages and separate actual server processes reopen the UI-written reports, recovering geometry/manual/audio/choices without a save or render.

Final SDR evidence: source box approximately `[186.258,123.442,401.508,275.942]`; independently decoded dark edges `[184,402]`, within the declared 3-source-pixel tolerance; dark-core fraction **1.0**, outside samples remain bright. Output decoded shape is 360×640×3. This is coordinate/persistence evidence, not redaction-quality research.

Final resize DPR1/2 console errors/warnings are empty. Final exact DPR1/2 page errors and unexpected warnings are empty. One expected console diagnostic identifies the deliberately controlled `/api/jobs/cfr24/render` HTTP409; it is retained separately with its URL. Screenshots and raw console/results were inspected.

### Packaging and installed boundaries

Using the prepared native 3.12 build tools, the gate built the wheel from the extracted sdist, installed offline/no-deps/no-compile into an owned site-packages directory and excluded checkout imports. The sdist includes README and all changed/new tests; wheel and installed web bytes match the frozen source. Exact metadata remains Python `>=3.9`.

- Sdist: 626,029 bytes, SHA `fed59651d64059089e53cd63247835e63ff518c027a3b925255788f94fea6273`.
- Wheel: 464,218 bytes, SHA `b24cd5ff40abe34cbbfe02540d4bd6f83372437bd34df5f898e11d8f18e45fc9`.
- All ten installed import origins, defaults and CLI entry points pass.
- Actual installed listening HTTP exercises strict and no-seed Track, verifies native initializer input against sequential decode/PTS, and rejects malformed/stale seeds without publication.
- Evaluated installed APP_JS/CSS/PAGE match exact MAXUP/VERSION/observed guest FREEDISK substitution and nonempty runtime custom-category substitution. Installed PAGE hash for the recorded empty-custom response is `7ffc26d04ffc6f3e65d39ce7df4d92c25c18971a5b77e6861f22069721b556e2` (dynamic disk field included).
- Updater fixtures retain the exact new/changed test bytes, including the new exact browser script; the adapter restores the scoped updater opener before its own HTTP check.

The prior D01 archive-warning item and shared controller remain unchanged. No archive warnings were emitted in this package run; this is not a resolution of the inherited controller item. Docker and Windows direct-import/package paths are unchanged source analysis only. Installed Python 3.9 packaging/build was not claimed or replayed; actual 3.9 owners and fixture-server compatibility were executed separately.

## RED/GREEN attribution and retained failures

Development invocations are explicitly marked `development`, based on 07cf with prospective per-file hashes; they are not invented intermediate commits or frozen acceptance. `task1004-evidence/commands-results.json`, configs and raw product logs bind their exact source/test fingerprints. Final acceptance is frozen dcaa.

- Initial BASE run: 29 selected failures. The overlapping fetch/body and same-editor metadata-intention assertions reproduced actual old behavior. Other cases stopped at the missing coherent-sample/decode prerequisite; these are not falsely counted as independent save/Track-owner REDs.
- Once sample input worked, the accepted 07cf save function was temporarily transplanted onto that prerequisite, run and restored byte-for-byte: **14 failures / 1 pass** across paired ACK, identical retry, malformed ACK and confirmed display-baseline controls. The exact composition recipe and hashes are retained; no partial Track-disabled contribution was delivered.
- First owner attempts: 97 pass/23 fail (DOM fixture gaps, new ownership failures and Python string escape warnings), then 118 pass/2 fixture failures. Missing appendChild/timer/ancestor behavior and cross-realm assertion comparison were repaired at the DOM/I/O boundary. Legacy audio toggle-back coverage was updated to confirm identical unresolved payload first, then send the retained newer toggle-back on the next explicit Save.
- Further genuine REDs exposed hidden-canvas readiness, finite existing-row overvalidation, stale same-editor review retirement, authoritative rejection changing the audio baseline, changed-family discard, hidden-canvas gesture cancellation, stale successful-Track status, detached timeline move/up and wrong-pointer geometry continuation. These progress through 130, 135 and final **141 passing** owner cases. The finite out-of-frame row control prevents rejecting or clamping existing source geometry.
- PAGE02–04 preserve HTTP200 sample wire plus pre-decode refusal: the wrong plan/fixture policy caused those failures; the binding erratum corrected the client/fixture, not the backend.
- PAGE05 exposed a genuine drag jump when inserting recovery controls during movement; updates were deferred to pointer completion. Its second-DPR fixture also incorrectly expected only two raw rows after the first DPR had appended actual tracked rows; the expectation now preserves initial indices while allowing those real additions.
- PAGE06 passed the entire resize/render/process case. Exact DPR2 had already passed lost-ACK/owned-baseline checks, then its fresh-page fixture tried to access a row deliberately inactive at initial time zero after saving span [.1,1]. PAGE07 explicitly inspected .2 before that assertion and passed. The backend's inactive-row behavior was correct; no ACK or source equality was relaxed.

The final 620-test run and package gate have no unresolved failures. All earlier product failures remain retained with their original inputs and attribution. Environment/permission/accounting diagnostics are excluded from the product archive.

## Evidence and remaining limits

Compact evidence: `task1004-evidence/manifest.json` records selected raw inputs/logs/configs/adapters/test sources/screenshots and hashes. `PAGE/resize`, `PAGE/exact` and both fresh-process subdirectories retain owning results, pixels and identity records. Complete original runtime artifacts remain under `runtime/task1004/runs`; media, environments, source exports, installation trees and local execution-control contents are not copied into the compact archive.

Fresh independent review must inspect **07cf..dcaa**, including ordinary editor, save/recovery, playback, timeline and Track together. Browser claims cover prepared Linux headless Chromium at DPR1/2, including narrow viewports; no touch, Windows execution, HDR output, interruption, generic cancellation latency, cross-client Track attribution or real tracking-quality claim is made. Native strict initializer evidence remains separately attributed. The independent matcher and upstream/user working versions remain unadopted.

## Fix round 1 — T1004-R1 error-body settlement

Latest status: **DONE_WITH_CONCERNS** — T1004-R1 is implemented and its assigned owner/shipping gates pass; the same reviewer's scoped `dcaa..d1f056e` closure remains pending. This section supplements the immutable original 17,313-byte report above. The earlier 620-test/PAGE/server-compatibility results remain attributed to dcaa; they were not rerun or relabeled as results at the fix head.

Original task BASE remains `07cfaa9539a2561c26b6f7280fae6702eb07137c`. Fix BASE is `dcaa0e5af6aedfca8685a3e64bea86ad0262f5c2`; final clean fix HEAD is **`d1f056e86fcae2dcfaa01bbc7f97e79ca662faaa`**, on `pr/exact-editor-ui`.

The full review (`task-1004-review.md`, SHA `24ca193c29f0d731cf7b0a9a73901c7fb95b6a3f1c3416329d73cdf510fad3cb`) found one Important item: non-success response headers caused `bePumpSamples` to throw before consuming the response body. Its finally block could start the latest wanted sample while the older error body remained unsettled. The original body-coalescing controls covered successful JSON bodies only.

The repair changes only the non-OK branch inside literal APP_JS: await `response.text()` through exhaustion or body-read failure, then throw the existing useful HTTP-status error. HTTP is checked before body interpretation; a non-JSON refusal is never parsed as JSON. The active slot remains owned across retired mounts until this await settles. There is no abort, decode, image URL allocation or change to the success/decode/playback/backend paths. Catching body-read failure preserves the original HTTP status while allowing normal settled cleanup and latest-wanted pumping.

Only `openscrub_web.py` and `tests/test_review_save_failures.py` change in this fix (57 insertions, 2 deletions total). All Python AST nodes outside APP_JS remain identical to dcaa; CSS, the ten runtime origins, defaults, engine/helpers, report/API formats and platform sources remain unchanged.

### Covering controls and exact source attribution

Two new test functions contribute 12 cases: HTTP409/423/500 × body exhaustion/body-read failure.

- `test_exact_error_body_retains_slot_across_mounts`: deferred non-JSON refusal; A1 has queued A2, then desired requests change through B and a new A mount. Error headers alone cannot start another fetch. No decode or URL is allocated. Only the latest A/.8 request starts after the old body resolves or rejects; the stale error cannot overwrite the new mount's status, and its subsequent exact sample becomes ready.
- `test_exact_current_error_body_settlement_keeps_http_status`: an active current failure retains the slot until its deferred body settles; no decode/URL occurs, readiness stays blocked, and the resulting status retains its HTTP code and explicit retry guidance even when body reading fails.

The existing HTTP response fixture now models `.text()` alongside `.json()`; production functions are not substituted. The complete prior 141 owner controls remain and pass.

| Stage | Product/test fingerprint and actual output |
| --- | --- |
| Genuine RED at exact dcaa product bytes | web SHA `33cd9d19ff9ea9542d14408be7840929dafd2b9bc6c8ae240fc7aab410d8cc32`; new test SHA `3ee8f7ab7a41639f85d6ad568aa4e5b01916a54424b4bbe7594ba908f506ecfb`; **12 failed, 141 deselected**, exit 1, 1.70s. Six failures assert premature second fetch; six assert premature active-slot clearing. No parser or harness error was counted as the behavior RED. Run `task1004-fix1-84b494de56c24532929be706ceca4ae0`, log SHA `bbbe563e0ca5fee63ba12870acf490622acd56bd93a1cfdc13c83a94895deea3`. |
| Actual Python 3.12.16 full changed JS owner | **153 passed**, exit 0, 19.55s. Run `task1004-fix1-0d22e7ca429b4f6996c49bbcd0824545`; log SHA `f822b59137ef1e62937f708fe4b3a46f8e19394986d39d4f3f3309a0f2cc458b`. |
| Actual Python 3.9.25 full changed JS owner | **153 passed**, exit 0, 21.57s. Run `task1004-fix1-e5af3ff6b0d6489390b45072682b025d`; log SHA `1a192eb2a27e0613ba7105c6b4a0fa599094bacc988201c9e481c2bb70e9de60`. |

Both GREEN invocations were prospectively bound development states before the clean fix commit; their web and test bytes exactly match d1f056e. Final web SHA is `422ed86c602be624f17ac6f2ef7e607121552afcaff0801ce23ffc467dc02a09`; evaluated APP_JS SHA is `f841e636aead565afcd716c1ec8694eb44e389a73c0ca67d2cd0b1e75d28e322`. Test SHA is unchanged between RED, GREEN and final package. APP_CSS remains `6c324da4b20e83eb740a31150ec8d166c326c49fd8914bec09e4abe2f79b3220`.

Canonical commands, with SOURCE/RUNTIME/VERIFY abbreviations defined above:

```text
/usr/bin/python3 VERIFY --config RUNTIME/fix1-red-312.json run -- -B -u -m pytest SOURCE/tests/test_review_save_failures.py -q --tb=short -k error_body
/usr/bin/python3 VERIFY --config RUNTIME/fix1-green-312.json run -- -B -u -m pytest SOURCE/tests/test_review_save_failures.py -q --tb=short
/usr/bin/python3 VERIFY --config RUNTIME/fix1-green-39.json run -- -B -u -m pytest SOURCE/tests/test_review_save_failures.py -q --tb=short
/usr/bin/python3 VERIFY --config RUNTIME/fix1-package-312.json package
```

### Final shipping gate and retained attribution

The frozen native Python 3.12 offline package gate passes at d1f056e: run `task1004-fix1-1cd1061244c54db38fb45c31b67aefde`, every build/install/default/CLI/installed adapter action exit 0. Installed-adapter log SHA is `7fa688633136acb2efd13c7aff2bbf6fdac4b5a299968346fde13dd8f6198a88`.

- Sdist: **626,648 bytes**, SHA `770c2af3575d7e0ad05bc038ae0e6eeb1bf0de9803d9a00b524725493f723d74`.
- Wheel built from that extracted sdist: **464,269 bytes**, SHA `f23859d612b82c1036c05ddb837dccaccf70f77d863e65fc1b41ad8e93dedc7f`.
- Offline/no-deps/no-compile installation, ten installed origins/defaults/CLI, strict and legacy listening HTTP, malformed/stale seed refusal without publication, exact APP_JS/CSS/PAGE and runtime custom-category substitutions, and updater test bytes all pass. The changed owner-test SHA is present in the sdist/updater proof. Metadata remains Python `>=3.9`.
- Recorded installed empty-custom PAGE SHA is `96f4c48f3cf1a229115f4ae17dd1d48b12c97d158d3be49ae04ee1394e786870` including the observed dynamic guest-disk field. The original corrected adapter is preserved; a separately pinned fix adapter selects the new APP_JS identity file.

As assigned by `task-1004-fix1-brief.md`, this isolated failure-branch closure uses the full affected JS owner on both actual interpreters plus the frozen package gate. No normal 620-test/PAGE successful-body run, heavy DPR replay, floor-server replay, new browser/platform claim, dependency/environment/model download or shared controller change was introduced. Earlier successful-sample/pixel/render/Track results and their limitations retain their dcaa attribution.

All original **182 compact-evidence files remain byte-for-byte unchanged**. The original report prefix SHA remains `8d91b56bf30631a33943f92e9cf973de64b8ccb5b3b2ac1e449d41601e276989`; the original PR is retained as `task-1004-pr-before-fix1.md`. New compact evidence lives only in `task1004-fix1-evidence` with its own manifest, archive hashes, exact diff, prospective configs, raw RED/GREEN/package logs and adapter/test inputs. All earlier refs remain; during this fix only the task branch advances from dcaa to d1f056e, and the docs ref stays cf044937.

The same reviewer must inspect the scoped fix range before adoption. No source composition, publication, push, merge or user-version adoption occurred. Source/runtime are released after the final report phase completes.
