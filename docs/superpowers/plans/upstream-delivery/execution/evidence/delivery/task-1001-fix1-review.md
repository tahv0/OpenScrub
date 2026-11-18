# Task1001 fix round1 scoped re-review — 335435e

**Verdict: APPROVED within the requested repair scope. I1 and I2 are ADDRESSED.** No new Critical, Important or Minor breakage was found in the fix diff.

Reviewed FIX_BASE `5acb655f98cc4699d4a05a5670e4e7ab33b477d6` → `335435e1e1120de9e6773656b7dfdfabf220e27b`. I read the complete16,534-byte packet once, the fix brief, original findings, complete fix report, appended implementation report/rulings, current PR draft and fix evidence. Packet SHA-256 is `727667a1fa3c31d9a33c97d0e7ce1991711582b7e8419eee4704c185b3e44064`, matching the supervisor proof. Only the14-line web repair and new264-line regression module were reviewed for implementation changes; the unchanged backend was not reviewed again.

## I1 — Revalidate explicit recovery authority at its commit boundary: ADDRESSED

At `openscrub_web.py:1692–1697`, the final report-lock section now checks that the captured recovery pair remains current, its operation is still selected and unset, its committed epoch/report stamp match, and its expected path equals the prepared canonical path. These checks accompany the existing current-job, active-work and actual report-stamp fences. Authority consumed by another request produces JSON409 before authoritative selection, source-epoch allocation or `job.video` assignment. The conservative conflict after concurrent identical recovery is explicitly permitted by the brief.

At `openscrub_web.py:1740`, final detached-sample acceptance also checks the captured Event. A cancellation signalled before its lock-mediated state update can no longer pass merely because Event identity remains unchanged. The new conditions add no lifetime acquisition or release inside `report_lock`; refusal still unwinds through the existing outside-lock lease cleanup.

The new production-route regressions cover the actual gaps:

- `tests/test_exact_recovery_races.py:100`: holds after real source preparation, signals the real cancel request before its delayed lock entry, and checks refusal with unchanged descriptor/source epoch/job.video/report and released prepared leases.
- `tests/test_exact_recovery_races.py:143`: two requests capture one pair; A consumes it, then the path is observably replaced before B prepares. B cannot acquire new authority/ref/epoch or decode. The unchanged-descriptor parameter is the allowed convergence/conflict control. Later ordinary observation still retires the replaced source.
- `tests/test_exact_recovery_races.py:191`: holds after actual indexed decode/recovery commit and signals cancellation before final acceptance. The response conflicts and the capture releases.

The tests retain failures/prepared leases, compare report bytes/stamps/committed epochs, assert owner counts and join controlled threads through cleanup paths. Recorded RED results show the three authority/acceptance cases returning200 on5acb655; the repaired tests pass on the final frozen head.

## I2 — Map disappearance after selection to JSON409: ADDRESSED

At `openscrub_web.py:1768–1773`, only the selected source's next open catches `FileNotFoundError` and raises JSON409 `sample_conflict`. The handle immediately enters its existing context-manager owner on success. Unrelated exceptions are not hidden by a broad catch, and initial source discovery retains its separate missing-source404 path.

`tests/test_exact_recovery_races.py:225` holds after the actual snapshot returns, unlinks the source and checks JSON409/private-no-store, no image/sample, no decoder creation, unchanged report and released snapshot lease. The original RED records HTML500 at that boundary. The control at `tests/test_exact_recovery_races.py:253` confirms a never-selected absent source remains JSON404/no-store without a descriptor/decoder or owner leak. Existing admission-body compatibility is unaffected by this localized repair.

## New breakage and quality assessment

Critical: none. Important: none. Minor: none.

The repair is appropriately narrow: final authority/cancellation checks and one selected-open adapter. The new tests distinguish authority retirement from source-stamp limitations and distinguish initial absence from disappearance after observation. No helper, engine, serializer, dependency, UI, lifetime-owner or package-declaration change was introduced.

## Evidence verification

The stdlib-only audit in `task-1001-fix1-review-audit.json` confirms:

- All53 fix payload hashes and all132 original payload hashes match. All three original index hashes remain unchanged. Raw report/PR snapshots match their original hashes; the live report's first15,593 bytes match the original report exactly.
- Original RED test bytes and the final new test reconstructed from the diff have identical ASTs after stripping assertion messages. Its reconstructed SHA-256 matches the frozen runtime and package record. The transformed RED diagnostic is exactly reproducible from the unchanged original runtime log: precisely three JPEG base64 values become size/hash markers. It is correctly labelled transformed/non-lossless.
- Original logs/configs retain4 genuine REDs/2 controls at5acb655, then6 GREEN cases after the repair. Frozen335435e native3.12.16 and actual3.9.25 logs each record157 passes/6 deselections. The approved selection retains all three real source-video stream endings; six unchanged report/download cases retain their earlier attribution.
- Both157-ID collector lists are preserved:155 IDs match verbatim and exactly the two declared long-parameter display aliases account for the rest. The retained first-finalizer failure is explicitly metadata-only. No test-selection change or workload replay is concealed by that correction.
- Runtime configurations and original logs identify the repaired web bytes for native/floor/package runs. The final offline sdist/wheel hashes match. Read-only archive inspection independently checks33/13 selected file bytes against the frozen manifest, including the new race test, and counts42/21 regular files. No extraction occurred.
- Installed defaults/origins and CLI/web evidence, real listening sample/strict-save/manual-retry/10-frame render, and fresh-interpreter listening reopen retain3 raw rows at335435e. Earlier471/77/full/package/cost claims remain attributed to5acb655; no broad or cost replay is represented as fix-head validation.

## Out-of-scope observations and remaining operational checks

No additional execution or product change is required to close I1/I2 on the supplied evidence. I did not execute the recorded tests/build/media/HTTP workloads; this review verifies their supplied code, identities and outputs. Root retains responsibility for final integration/bookkeeping and preserving this exact reviewed head/evidence attribution.

The original report's separate C01 authoritative render-delivery boundary, strict seeds/UI/P16D, P08 coordination, native interruption, P17/HDR mapping and platform/latency limits remain nonblocking future gates for this scoped repair. This review does not certify them or expand the original declared decoder/source guarantees.

No product source outside the supplied fix packet was read during this round. Outside-packet reads were limited to the requested documents, original/fix evidence, the named immutable original RED runtime log, and recorded sdist/wheel archives for the stdlib audits. No Git command, product import, test/workload replay, decoder, server, source mutation or nested agent was used. Only this report and its small audit file were written.
