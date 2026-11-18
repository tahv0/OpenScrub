# Task1001 fix round1 — recovery authority and selected-source race

FIX_BASE:5acb655f98cc4699d4a05a5670e4e7ab33b477d6 on pr/exact-editor-samples. Original implementer owns the repair after root releases the next allocation. Read original task/contract/supervisor rulings and the complete independent review. Product source is frozen until that dispatch. Both Important findings below are reproduced code-supported gaps, not waived limits. Preserve the original report/evidence/commands and append a clearly attributed fix section; do not relabel471full/77floor/package/cost at5ac.

Fix only the named authority/IO paths and meaningful tests. Require the still-current committed recovery pair at final selection, including operation/epoch/report stamp/path/unset cancellation, and preserve ordinary same-descriptor convergence or explicit409 after another recovery completes. Retired authority never bypasses source replacement refusal. Adapt only the selected-source open/stamp disappearance race to JSON409sample_conflict; never-selected missing-source404 and existing admission body formats remain unchanged.

Retain genuine REDs for cancellation after the initial recovery check, concurrent completed recovery followed by an observed replacement, and disappearance after actual snapshot before route open. Controlled Events/joins/retained failures; no stale descriptor/job.video/report publication, no image on conflict, no decoder created at pre-open failure, zero leaked owners/captures. Source lifetime release stays outside report_lock. No new registry/history/retry framework/helper edits/model/dependency/UI work.

After fix: affected production source/adoption/sample/media plus transaction/lifetime/manual owners on native; actual3.9 affected owners; final offline package/strict installed origins/defaults/CLI/web/real HTTP roundtrip. Freeze clean source before acceptance. No whole-project/old cost/28capture replay: existing full471 stays correctly attributed and focused checks cover amended functions. If code scope expands beyond these boundaries, report the concrete new cause to root. Preserve all other refs and the current clean C01/docs. Commit assigned branch only and return covering test file/command/output evidence, final head and fix report. Root then generates a5ac→fixHEAD packet for scoped independent re-review.

## Open findings, verbatim


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

