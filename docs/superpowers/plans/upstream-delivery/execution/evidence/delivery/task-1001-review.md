# Task1001 independent review — 5acb655

## Spec Compliance verdict

**Changes required.** The frozen backend substantially implements the adopted contract, but two Important issues remain: explicit recovery can reuse retired authority, and a selected-source disappearance can escape the documented JSON conflict response. Neither is covered by the recorded passing tests. No Critical finding was identified.

Reviewed base `12919c96c6f7558136b50d7b4d85e5e6b62f1971` through head `5acb655f98cc4699d4a05a5670e4e7ab33b477d6`. I read the complete 93,000-byte review packet in bounded chunks, all required contract/amendment/ruling documents, and the full implementation report/PR draft. The packet SHA-256 matches the supervisor's proof. Product and Git state were not modified; no product import, test, decoder, server, package build or benchmark was run during this review.

## Strengths

- The indexed helper owns no live capture, resolves the requested integer once, checks observed presentation time and dimensions, and cannot silently walk to an adjacent frame. Final interval/D, canonical visibility, nonzero offsets, disabled rows and concrete raw indices are implemented directly.
- Timing admission is a declared metadata-qualified/sample-verified subset. Rational grid qualification, report-rate drift, timestamp quantization and a quarter-frame ceiling are explicit. The independent native24/native5/normalized13/coarse1ms pixel/PTS evidence supports the stated subset; the report correctly avoids whole-file CFR or immutable-byte certification.
- Current source metadata remains in `_JobFiles`; success-only report publication has a distinct epoch. Ordinary choices/audio do not require exact source admission. Preparation and lease release occur outside `report_lock`; samples parse one private raw document and hash the timeline incrementally.
- Strict save validation precedes mutation and one atomic publication. All three baseline/intended tuple rules retain their non-target fields; row context covers opaque additive fields with the adopted canonical JSON recipe. Manual immutable replay is classified before current source/timeline freshness. Unknown metadata and legacy callers remain supported.
- Scope is controlled: exactly six intended files changed, no engine/package/serializer/UI changes, no extra dependencies/models/workers/identity ledger. Ordinary APP_JS/APP_CSS preservation is independently recorded in the supervisor pre-review proof.

## Critical findings

None.

## Important findings

### I1 — Revalidate explicit recovery authority at its commit boundary

**Location:** `openscrub_web.py:1685–1694`, especially the authoritative `_select_observed_locked` call at line1692; authority is captured at1652 and checked only before preparation at1678–1682. `_select_observed_locked` clears the completed pair at1605. Cancellation signals the captured Event at1488 before waiting for `report_lock`.

The final recovery lock checks report epoch/Event identity, active work, report stamp and pending status, but does not require that `files.source_pair` still equals the captured recovery pair or that its Event remains unset. Two concrete interleavings violate the binding supervisor rulings:

1. An explicit recovery passes the early cancellation check and prepares outside the lock. Cancel then signals the same Event while waiting for the lock. Recovery can acquire the lock first: Event identity and report fence still match, so it adopts the source and clears the pair despite the signalled cancellation. Cancel subsequently sees no pair to retire. A coherent descriptor can survive that cancellation; depending on final-request scheduling, detached sample success is also possible before cancellation updates `files.operation`.
2. Two requests capture the same unavailable scan pair. Request A recovers successfully and clears it. Before request B opens/prepares the source, the same path is observably replaced. B prepares the replacement and reaches the final lock with unchanged report/operation fences and coherent status. Its stale local `recovery` still supplies `authoritative=True`, allowing replacement pixels to acquire a fresh source reference against unchanged old geometry. The completed scan pair has granted authority twice. This is an observable-stamp replacement, not the documented equal-attribute external-mutation limitation.

**Fix:** Under the final report lock, require the still-current recovery pair, its operation/epoch/report stamp/expected path, and an unset cancellation Event before authoritative selection. A completed/replaced/cancelled pair must refuse atomically; a concurrent completed recovery may only converge through ordinary non-authoritative same-descriptor selection, or return409. Preserve the already-prepared lease through validation and release it outside the lock on every refusal. Ensure final acceptance cannot revive the cancelled operation.

**Required regression evidence:** controlled holds after the initial recovery check and before source preparation/commit for both interleavings, including a changed source stamp after A completes. Assert no stale `job.video`/descriptor adoption, no usable image on refusal, no report mutation, and zero leaked owners/captures with retained failures. Existing adoption cancellation tests exercise `_adopt_scan_source`, whose final check is stronger; existing recovery tests are sequential and do not cover this gap.

### I2 — Map disappearance after selection to JSON409

**Location:** `openscrub_web.py:1761`; exception handlers at1797–1800.

Once `_exact_snapshot` returns an observed selected source, removing that path before the route's next `open(..., 'rb')` raises `FileNotFoundError`. The route catches `ExactError` and consumed-value errors, but not that filesystem race. There is no general JSON500 adapter elsewhere in the app. Flask therefore returns an HTML500 instead of the adopted JSON409 `sample_conflict`. No-store still applies and leases close, but the explicit error contract and retry classification are broken.

**Fix:** Adapt the focused selected-source open/stamp race to `ExactError(...,409,'sample_conflict')`. Keep the initial never-selected missing-source404 distinct, and avoid a blanket catch that masks unrelated internal failures.

**Required regression evidence:** hold after the actual snapshot has returned, unlink the selected source, then resume the route. Assert JSON409/code, private/no-store, no image/sample payload, no report change and zero owners. At this boundary no decoder should be created; retain existing capture-release assertions for later decode/encode failure cases.

## Minor findings

None in this product diff. The inherited verification helper's tar extraction warning is outside this diff and is not authorization to change that tooling.

## Evidence assessment and limits

The stdlib-only audit in `task-1001-review-audit.json` verified **all132 indexed payload hashes**, the packet identity, and copied final runtime configurations. `final-integrity.json`, `commands-results.json`, supervisor pre-review metadata, original final logs/configs, media records, HTTP smoke recipe/outputs, package identities and cost recipe/outputs are mutually consistent:

- `final-full-030`: **471 passes**, actual3.12.16, frozen5acb655. `final-floor-031`: **77 affected passes**, actual3.9.25, frozen5acb655. Earlier469/168 results remain attributed to631f517. Genuine missing-implementation/adoption/source/recovery RED summaries retain their original failures; the reports distinguish provisional precision/query-spelling failures.
- Native and installed real listening HTTP evidence covers exact samples, strict combined save, manual retry, a real10-frame render and fresh-interpreter listening reopen retaining3 raw rows, disabled/unknown fields, audio and manual identity. The installed origins/defaults/CLI/web logs resolve the ten modules from the installed wheel.
- The offline package records distinguish32/13 asserted selected byte identities from41/21 total regular sdist/wheel files and retain Python>=3.9. Private helper and shipped test inclusion are explicit.
- Independent media outputs match the stated indices/PTS, including normalized duplicate markers at distinct PTS and coarse1ms Matroska's333.333us deviation within its1ms-derived bound. This supports the named environment/fixtures, not arbitrary media/backends.
- Cost accounting is accurate:300/120000 already-parsed pairs have1.376/596.891ms medians; separately traced peaks65638/1056462B exclude parsed input and RSS. Tiny-source cold/reused/legacy-choice Flask medians48.845/9.163/8.388ms are not network, OS-cold-cache, real-long-report or long-video measurements. All19 route requests are accounted for; instrumented probe counts1/0/0 and decode counts1/1/0 confirm the legacy-choice control does no introduced source/decode work.

**Cannot verify / root follow-through:** I1 and I2 need original-owner RED/fix/focused evidence on a new frozen head and renewed review; this review did not execute them. The existing full/floor/package/HTTP evidence establishes5acb655 only and must not be relabelled as validation of later fixes. No Windows/Docker runtime execution is claimed; inclusion is source-inspected. No new real-browser ordinary Add/Track exercise was supplied; unchanged UI bytes plus legacy backend regressions support compatibility, while the owning browser gates remain necessary when strict seeds/UI/P16D are integrated. C01's authoritative render-delivery success boundary, P08 coordination, native interruption, P17/HDR/original mapping, tracking quality and general long-video latency remain separate integration/acceptance work. The O(N) projection cost is an accepted measured limit, not missing backend acceptance; later UI coalescing/bounded dispatch still needs its owning gate.

## Focused outside-diff inspection

Only the frozen native `openscrub_web.py` was inspected beyond the packet, for named ownership/fence risks:

1. Lines300–475: existing admission, containing-source reservation, `_job_video`, `_update_job_source` and lease preparation/release order, to judge whether the new source adapter introduces report→VAULT inversion or loses existing containing-job ownership.
2. Lines790–870 and a focused `rg` of operation/cancellation/publication call sites: `_report_current`, `_edit_gate`, operation begin/finish and queue transfer, to confirm the final recovery fence's meaning and inventory managed report notifications.
3. Lines1478–1492: the earlier part of `job_cancel`, absent from the changed hunk, to establish that Event signalling precedes report-lock acquisition (I1).
4. A focused `rg` for `errorhandler`, `HTTPException` and `teardown_request`: to check whether a pre-existing adapter rescues the selected-source filesystem exception (I2). Only a413 handler was found.

No broader source crawl or changed-function reread was needed. Required documents/evidence and the exempting subagent bootstrap skill were also read; audit output and this report are the only review writes.

## Assessment / quality verdict

The implementation has a coherent small helper, good raw-report preservation, meaningful production-route/media evidence, careful ownership cleanup and candid cost/support limits. Its remaining recovery authority gap can bind new pixels to old geometry, so **do not accept5acb655 until I1 and I2 are corrected and reviewed**. Address both in one scoped repair round; no redesign, broader replay or unrelated tooling change is warranted by this review.
