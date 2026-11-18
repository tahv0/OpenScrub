# Task1001 — exact editor backend candidate

Implemented and committed the focused backend on `pr/exact-editor-samples`. Base: **12919c96c6f7558136b50d7b4d85e5e6b62f1971**. Head: **5acb655f98cc4699d4a05a5670e4e7ab33b477d6**. Commits: `631f517` adds the coherent sample/source owner and optional strict save; `5acb655` corrects explicit normalized-source recovery and retires completed/cancelled/replaced scan pairs. The engine, package configuration, report serializer and ordinary editor JS/CSS are byte-identical to the base. All prior recorded refs, including C01 `b4fc209` and documentation `54f1413`, remain preserved. Supervisor fresh review is pending; nothing was published.

The final clean head passed **471 discovered tests** on actual Python3.12.16. Actual Python3.9.25 passed **77 affected exact/source/save/adoption/media cases** after the recovery correction. The earlier clean `631f517` full/floor runs passed469/168 respectively and retain their original attribution. The final offline sdist→wheel→installed checks and native/installed real HTTP save→render→fresh-interpreter reopen both succeeded. Compact evidence is [task1001-evidence](task1001-evidence/README.md); complete commands, frozen source/tool/interpreter identities, logs and failure history are retained there.

## API and geometry representation

`GET /api/jobs/<jid>/edit_sample?t=0.2` requires a finite nonboolean numeric JSON spelling for `t`. It reads scan input only; `src` is rejected. It returns `Cache-Control: private, no-store` and:

```text
{version:1,
 sample:{source_ref,timeline_eq,policy,index,requested_s,canonical_s,
         observed_s,width,height,stream,origin:[0,0],offset:[ox,oy]},
 image:{mime:"image/jpeg",base64:"..."},
 boxes:[{i,category,text,enabled,t_start,t_end,box,
         row_context_eq,base:{cbox:[x1,y1,x2,y2],span:[start,end,effective_last_seen]}}]}
```

Resolve once: `i=min(floor(t*fps),N-1)` for `0<=t<=N/fps`. Canonical time is `i/fps`, offset is `cum[i]`; requested/observed/canonical times remain distinct. The whole last interval, including exact duration, selects the last sample. Visibility uses the existing renderer's ±.01s tolerance at canonical time. Disabled active raw rows remain present at their actual raw indices; this is a raw-row projection, not an effective grouped-mask preview.

Route-managed errors are JSON `{error,detail}`:400 `invalid_sample_request`;404 `missing_report`/`missing_source`;409 `source_report_pending`, `sample_conflict` or save `geometry_conflict`;422 `exact_sample_unavailable`;500 `sample_encode_failed`. Existing pre-route missing-job/authentication/vault/deletion refusals retain their current middleware body formats and statuses. This is an explicit supervisor wire clarification; such bodies need not be JSON. Every exact response remains no-store and a refusal carries no usable exact sample. [Actual admission response evidence](task1001-evidence/runs/admission-037/admission-results.json) confirms the missing-job404 HTML versus route-managed missing-report404 JSON boundary. A future UI must check HTTP failure before expecting JSON. The original interface proposal is preserved separately, including superseded candidate precision choices.

Existing `POST .../detections` accepts optional `geometry_preconditions[raw_index]` containing `version:1,source_ref,timeline_eq,policy,index,width,height,offset,row_context_eq,base`. Source refs are bounded to128 characters; digests are64 lowercase hex characters; consumed indices/dimensions/version are nonboolean integers; consumed vectors/times are finite and shape checked. The new optional contract does not reject opaque additive report values or impose a new legacy span/frame-bound policy.

Row context uses domain `openscrub-row-context-v1:` and incremental canonical JSON encoder chunks, sorted keys, ASCII escaping, compact separators and stable NaN/Infinity/-Infinity extension spellings. It excludes exactly `enabled,cbox,t_start,t_end,last_seen`; integer/float, signed zero and quoted versus extension spellings remain distinct. Every other current/unknown row field participates. Timeline equality uses `openscrub-timeline-v1:` over finite fps/N, every ordered cum pair and selected stream/dimensions/identity orientation/scan-source relation, while traversing the parsed list without another full-report read or whole-timeline copy. Report/output epochs, audio, enabled flags and unrelated rows do not bind geometry drafts.

All three adopted CAS rules are implemented. Box-only retains the baseline effective span; span-only retains the baseline box; combined edits accept only the complete baseline tuple or complete intended tuple. Intended last_seen is clamped from the immutable submitted baseline. Mixed tuples conflict. Already-equal replay still requires current source/timeline/context and leaves target fields alone. Missing last_seen uses its effective default and remains absent on a box-only save. Distinguishable reorder/replacement conflicts at the submitted index; identical duplicates remain semantically indistinguishable. Successful strict saves return `geometry_rows` only for submitted strict rows, with complete committed base/context. No persistent row identity or sample history is added.

Strict manual entries add optional `sample_precondition`. Finite immutable creation is first computed from submitted offset/box/time; an identified matching `manual_creation` is replayed before current source/timeline freshness. Later mutable edits do not defeat a lost-ACK retry. Genuinely new strict work prepares source ownership outside report_lock, then reloads/reclassifies latest raw JSON and validates inside the existing transaction. Indexed/manual/choice/audio deltas publish once, or all fail. Legacy creation/replay/choice/audio behavior remains available without exact admission.

## Observed source, publication and lifetime owners

The existing `_JobFiles` owns current incarnation/source epoch/descriptor, a separate success-only `committed_report_epoch`, and one pending scan pair with operation/report epoch/report stamp/expected selected path. Coherent source selection is separate from exact timing eligibility. The descriptor records canonical scan path, device/inode/size/mtime_ns/ctime_ns and small stream facts or an explicit policy error. Repeated successful descriptor use makes no new probe; concurrent discovery converges on one descriptor/ref. There is no whole-input/report hash, registry, worker or token history.

Lifetime reservation and stream preparation happen outside report_lock. No VAULT admission or lease release happens under that lock. Opened/path stamps are checked around preparation/use; sample decode and JPEG encoding happen outside the lock, then current source, operation, report epoch and report stamp are checked before accepting detached bytes. An overlapping successful report publication produces409/retry even when it was only choices; that request fence is never a persistent geometry precondition. Captures/open handles/preparations/request leases release on successful, failed and retained-exception paths.

Successful atomic report replacement notifies the committed epoch at scan/render callback, save and tracker publication. Failed replacement does not. Every successful scan marks a pending pair and adopts its selected source before pre-generation, including unchanged native input. Preparation failure remains explicit unavailable and suppresses pre-generation. One later explicit exact request may recover only that still-current committed scan pair after operation/report epoch/stamp/path checks. Successful/cancelled/replaced pair evidence is retired. A known later observed source change retires the old reference and requires authoritative scan adoption; unchanged old reports cannot silently bless new pixels. Controlled holds cover publication/adoption/decode/encode/save preparation, cancellation/replacement and failed report publication.

Combined C01 output_epoch/render-delivery semantics are not imported into this standalone base. Later integration must keep attempted output mutations separate and notify committed report success only after authoritative render delivery returns successfully.

## Declared decoder policy and independent support evidence

Policy: **opencv-ffmpeg-zero-cfr-v1**, tested here with OpenCV4.14.0 FFMPEG (libavcodec62.28.102/libavformat62.12.102/libavutil60.26.102) and independent FFprobe8.0.1. A successful bounded metadata probe qualifies one unambiguous zero-origin video stream, compatible positive rates/dimensions/count/time base and no display transform. Each requested indexed read must return a nonempty correctly sized frame with matching post-read presentation time. Known raw timing bypass/VFR, ambiguous/nonzero-origin/rotation, missing/failed metadata, count/rate disagreement and EOF/adjacent/unusable-time evidence stay unavailable. Set-success and frame counters alone never establish success.

The explicit numerical bound is:

```text
q = 0 if (1/stream_rate)/stream_time_base is an exact integer, else one timestamp tick
bound = q + N*abs(1/report_fps - 1/stream_rate) + 16*ulp(max(1,N/report_fps))
require 0 < bound <= quarter frame
```

Exact rational arithmetic establishes grid integrality. The bound is passed explicitly into `read_indexed_capture`; that primitive returns raw pixels/index/canonical and observed time/dimensions and never transfers a live capture. A proposed fixed100µs cap was not adopted. The prior study's1µs display allowance is not production policy.

Production endpoint gates use retained synthetic H.264 native24/native5 and the actual retained normalized13 source, plus one tiny remuxed native24 Matroska with1ms ticks. Independent sequential arrays, burned markers and separately probed integer PTS/time_base verify pixels and presentation evidence. Four media cases issue eight endpoint samples per owning gate. Native24 `.2` returns index4/PTS1/6; native5 `1.9` and exactD return9/PTS9/5; normalized `.5` returns6/PTS6/13, and indices2/3 preserve duplicate marker2 at distinct PTS. Exact normalizedD returns13/PTS1. Native/normalized observed-versus-independent times agree at the recorded float precision; their grid bounds are7.1054e-15s and3.5527e-15s. Coarse Matroska index4 returns PTS167/1000:333.333µs from canonical1/6, within the measured metadata-derived1.000000000007ms bound. Adjacent-frame and zero-for-all evidence are rejected. The28-capture feasibility study was read and was not rerun as implementation evidence.

These are old dict reports using existing provenance/settings/render_state, with no new required report fields. Native and retained normalized compatibility passed through production selection. Metadata/rate agreement and flags define a declared, sample-verified subset assumption; they do not certify whole-file CFR or immutable source bytes. Initial legacy observation and external mutations preserving every observed attribute retain the documented limitation. Old list reports retain their legacy path and cannot acquire exact coordinates without a timeline.

## Verification and retained failures

| Run | Source attribution | Actual result |
|---|---|---|
| red-003 | development at base |22fail: missing endpoint/helper, before product implementation |
| green-005 | development |81pass/12fail: initial one-tick bound rejected grid-aligned AVI |
| focused-007 | development |102pass/10fail: test-only `.2` query spelling violated adopted JSON numeric syntax; corrected to `0.2` |
| media-009 | development |51pass |
| holds-011 | development |147pass including legacy transactions/lifetimes |
| adoption-red-013 → adoption-green-015 | development |1 genuine report-stamp race RED →72pass |
| strict-source-red-017 → strict-source-green-019 | development |2 genuine missing/replaced-source status RED →100pass |
| freeze-check-021 | final first-commit bytes |75pass |
| full-023 / floor-024 | clean631f517 |469pass119.81s /168pass actual3.9 |
| recovery-red-026 → recovery-green-028 | development after631f517 |2 genuine old-source recovery RED →111pass |
| final-full-030 | clean5acb655 |471pass116.09s |
| final-floor-031 | clean5acb655, actual3.9.25 |77 affected pass4.42s |
| native-http-032 | clean5acb655 |real listening sample/save/manual replay/real10-frame render/fresh-interpreter listening reopen pass |
| package-034 | clean5acb655 |one offline sdist→wheel-from-sdist; installed origins/defaults/CLI/web/listening HTTP roundtrip pass |
| costs-035 | clean5acb655 |one approved bounded cost run,19 route requests, all observations retained |
| admission-037 | clean5acb655 | missing-job404 HTML/no-store and missing-report404 JSON/no-store confirmed |

The final full invocation is normal discovered pytest against the assigned source, using the exact reviewed cached YuNet fixture and scoped fresh-route stdout adapter. Relevant floor/source suites use actual prepared interpreters with explicit task-local paths and source-byte checks. Full/floor/HTTP/package commands and copied immutable runtime configurations are indexed by [commands-results.json](task1001-evidence/commands-results.json). A second full run was justified solely by the newly reproduced recovery state-transition bug; original results were not relabeled.

Offline package assertions compare32 selected runtime/test/data files in the sdist and13 runtime/data files in the wheel; the archives contain41/21 regular files overall. Exact private helper and all shipped test bytes are checked; Python metadata remains>=3.9. Artifact sizes: sdist584151B, wheel455162B. Both native and installed HTTP scenarios preserve3 raw rows, disabled/unknown fields, strict manual identity and audio, then decode10 rendered frames and reopen through a fresh interpreter/server. Installed default profiles and all ten runtime imports resolve from the task-installed wheel. Docker/updater/frozen inclusion is source-inspected; no Docker/Windows runtime acceptance is claimed. The reviewed shared helper remains unchanged, including its existing tar extraction behavior.

## Introduced cost and integration limits

Uninstrumented medians of five, normal GC, fixtures outside timing:300 parsed pairs1.376ms;120000 parsed pairs596.891ms. Separate later tracemalloc peaks are65638B/1056462B, excluding parsed input allocation and RSS. The hash is visibly O(N); no constant-cost claim is made.

Tiny real native5-source Flask route medians: descriptor-cold48.845ms; reused9.163ms; legacy choice-only8.388ms. These include production request/parse/decode/encode work and exclude network/socket/OS-cold-cache claims. They are not long-report request measurements.19 total requests comprise5cold,1warmup,5reused,5legacy choice and3separate instrumented controls. Post-timing cold/reused/choice counts: probe1/0/0; descriptor commit1/0/0; report read1/1/1; source opens2/2/0; decoder read/release1/1/0; timeline projection1/1/0. All elapsed samples, complete non-image response fields and image sizes/hashes are retained; raw media is excluded.

Before ordinary UI migration, account for this O(N) work with request coalescing and bounded dispatch under the later UI contract. This backend does not claim universal latency, a long-video decode bound, native interruption, HDR/original frame mapping, strict tracker initialization, resized editor correctness, tracking quality or P17 geometry support. Strict seeds are the next slice; ordinary editor+Track migration follows them and P16D. Existing defaults and ordinary UI/legacy callers remain usable meanwhile.

## Fix round 1 — current candidate335435e

The preceding body is preserved as the original5acb655 implementation/evidence record. Independent review required I1 recovery-authority retirement and I2 selected-source disappearance repairs. The current clean candidate is335435e1e1120de9e6773656b7dfdfabf220e27b; final pair authority/Event fences and a localized selected-open409 adapter address both findings. Four genuine REDs became six passing race/control cases. Frozen covering checks pass157 cases on each of actual3.12/3.9 (six unchanged report/download stream permutations deselected), and a new offline package/strict installed listening HTTP roundtrip passes with the new race test byte-checked in the sdist. No full-suite or cost results were relabeled or replayed. Original132 evidence payloads/indexes remain untouched, and original report/PR bytes are preserved as plain-text snapshots. [Fix report](task-1001-fix1-report.md) and [fix evidence](task1001-fix1-evidence/README.md) contain exact commands, outputs, provenance and limits. Fresh scoped re-review remains pending.
