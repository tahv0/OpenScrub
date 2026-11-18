# Task1001 fix round 1 — recovery authority and selected-source disappearance

The focused repair is committed on `pr/exact-editor-samples` at **335435e1e1120de9e6773656b7dfdfabf220e27b**, directly after FIX_BASE **5acb655f98cc4699d4a05a5670e4e7ab33b477d6**. It addresses I1 and I2 from the [independent review](task-1001-review.md). Fresh scoped re-review remains pending. Only the named web ownership/IO paths and the new race regression module `tests/test_exact_recovery_races.py` changed; there is no schema, engine, private-helper, lifetime-owner, serializer, package-declaration or UI change.

## Repair

I1: the final report-lock selection now requires the captured recovery pair to remain current, its operation identity to match, its cancellation Event to be unset, and its epoch/report stamp/expected prepared path to match. A request carrying authority already consumed by another recovery returns JSON409 `sample_conflict`; it cannot mint a replacement descriptor or update `job.video`. This deliberately uses the allowed conservative409 policy rather than rebinding a completed pair. The final sample acceptance fence also checks the captured Event, closing cancellation after valid recovery/actual decode but before detached acceptance. These are request fences, not new persistent geometry-draft conditions.

I2: only the selected source's next `open(...,'rb')` has a localized FileNotFoundError adapter to JSON409 `sample_conflict`. A never-selected missing source keeps JSON404 `missing_source`. Existing middleware body formats/statuses and unrelated internal failures are unchanged. All refusals remain private/no-store with no image/sample. Existing capture/handle/lease cleanup stays with its owner and outside report_lock where required.

## Genuine RED and controlled holds

`tests/test_exact_recovery_races.py` reuses the existing synthetic exact/scan/store fixtures and actual scan publication/adoption. Its six cases cover:

- Cancellation after the early recovery check and actual preparation, with the real `/cancel` Event signalled while that request's report-lock entry is held. Recovery must refuse before adoption; the old descriptor/source epoch/job.video/report remain unchanged.
- Two requests capturing one unavailable pair. A completes recovery, then the source path is observably replaced before B prepares it. B must refuse without a new ref/epoch or decoder. The unchanged-descriptor case is a separate convergence/conflict control. A later ordinary read still detects/retires the replacement stamp.
- Cancellation after actual indexed decode and recovery commit, with cancel's lock update delayed. Final detached acceptance must refuse and release the verified capture.
- Unlinking the selected source after the actual `_exact_snapshot` returns but before the route opens it. The result must be JSON409/no-store with no decoder, image/sample or report mutation. A never-selected missing404 is a separate control.

The tests retain ExactError objects/tracebacks and prepared leases through cleanup assertions. They compare report bytes/stamps/committed epochs, descriptor/ref epochs, capture releases and global owner count; all controlled threads are joined in finally paths.

Before product edits, **fix1-red-002 failed four genuine cases and passed two controls** on5acb655: cancellation-before-commit, completed-pair+replacement and final-accept cancellation returned200/images; post-snapshot disappearance returned HTML500. After the narrow repair, **fix1-green-004 passed all6**. A subsequent diagnostic-only edit stopped assertion messages from printing image bytes; AST equivalence with all assertion messages removed proves assertions/controls were unchanged. Original RED test bytes and immutable runtime inputs/logs remain retained.

The compact RED log is explicitly **transformed, not lossless**: only three synthetic JPEG base64 values are replaced with decoded-byte size/hash. [Transformation records](task1001-fix1-evidence/red-diagnostic-transformation.json) retain complete original log size/SHA, exact replaced field/encoded/decoded sizes and hashes, and the original runtime path. All source/sample/error fields, status assertions and terminal summaries remain present. No completed original log was edited.

## Covering gates on clean335435e

| Run | Interpreter / scope | Actual result |
|---|---|---|
| fix1-native-006 | Python3.12.16; all exact/adoption/media/race, transaction/manual owners and three real source-video streaming endings | **157 passed,6 deselected**,11.46s |
| fix1-floor-007 | actual Python3.9.25; identical approved selection | **157 passed,6 deselected**,12.03s |
| fix1-package-008 | one offline sdist→wheel-from-sdist, strict installed defaults/origins/CLI/web and real listening HTTP roundtrip | **exit0** |

The complete public helper/workload argv, prospective byte configurations, terminal outputs and actual selected test IDs are in [commands-results.json](task1001-fix1-evidence/commands-results.json) and [selection.json](task1001-fix1-evidence/selection.json). The pytest workload is:

```text
-m pytest tests/test_exact_recovery_races.py tests/test_exact_samples.py
 tests/test_exact_adoption.py tests/test_exact_media.py
 tests/test_report_transactions.py tests/test_manual_addition_replay.py
 tests/test_job_response_lifetime.py -q
 -k 'not test_configured_wsgi_closes_stream_owner_exactly_once or video'
```

The recorded argv uses absolute selected-source paths; the unchanged helper adds unique run-local basetemp/cache. Selected real stream IDs are `[complete-video]`, `[disconnect-video]`, `[iterator_error-video]`. The six report/download permutations retain explicit5acb655 full-suite attribution; their owner/test bytes are unchanged. No fixtures were shrunk and no prior run was deleted.

One artifact finalizer assertion initially compared literal collector IDs across prepared pytest9.2.0 and8.4.2. Two long-string manual-ID cases have different display IDs (`identity7`/`identity1` versus their full129/128-character values). The finalizer attempt retains actual exit1; the correction aliases exactly those two display strings using the identical pinned test function/parameter/source evidence. All other155 IDs match verbatim; both original157-ID lists remain preserved. This was metadata handling, not a product/test failure or changed selection; no test was replayed. [Alias/version proof](task1001-fix1-evidence/collector-id-aliases.json).

The final sdist explicitly includes and byte-checks `tests/test_exact_recovery_races.py`. Assertions cover **33 sdist /13 wheel files**, against **42/21 total regular archive files**. Sdist586434B; wheel455308B; Python>=3.9 remains unchanged. Installed startup/defaults and ten product imports resolve from the new wheel. CLI/web help pass; the unchanged pinned listening HTTP adapter exercises exact samples, strict combined save/manual replay, an actual10-frame render, and fresh-interpreter listening reopen retaining3 raw rows, disabled/unknown metadata, audio and manual identity.

No whole-project suite, old cost matrix or28-capture feasibility study was replayed in this repair round. The original471 full/77 affected-floor/package/cost results remain attributed to5acb655, and469/168 remain at631f517. The original132 evidence payloads and all three index files remain untouched; raw-byte original report/PR snapshots are plain-text `.md.txt` files in the fix evidence. The live implementation report is appended, and the current PR draft is revised for the repaired candidate. Other refs, ordinary UI/defaults, engine, existing lifetime owner and private exact helper are unchanged.

The existing declared decoder subset, observed-stamp limits, O(N) timeline work, later strict-seed/UI/P16D and P17/HDR integration gates remain as recorded in the [original implementation report](task-1001-report.md). This focused repair makes no new media/platform/latency claim. Product/runtime ownership will be released after compact evidence integrity closure for root's scoped re-review.
