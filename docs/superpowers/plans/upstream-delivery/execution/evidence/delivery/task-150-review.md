# Task150 independent review

**Spec verdict: Approved within the brief's explicit standalone boundaries.** Reviewed exact supplied base `2ae3257b9752e2d976ff7a0d39955a13c133273a` → head `c0ebcc7a8c3121330730bea3619bbfea8add7992`, including the fixture-only follow-up after implementation `ac28a2ac981f2612cbaeadedddbfac8db1efeefb`. No blocking requirement deviation found. Show all remains the default, and the change preserves Austin defaults, Python >=3.9, P02 grouping/action semantics and P07a draft/acknowledgement ownership.

**⚠ Cannot verify beyond these limits:** this was an independent static review of code and retained acceptance evidence, with no replay of product tests, browser, media, packaging or benchmarks. Ordinary Play startup remains excluded by the disclosed native `video.load()` fixture prerequisite; the evidence establishes retention of already-started playback. The real save/reopen preserves 11 raw rows before rendering, while standalone rendering retains 5; combined post-render full-row preservation remains P06D/C01 acceptance. Linux/headless Chromium evidence does not certify physical touch devices, other browser engines, desktop platforms or GPU/production media. Tool binary hashes were audited after execution, not enforced by Task150 preflight. Current matching bytes and retained prior pins support the bounded evidence; they cannot establish retroactive preflight enforcement.

## Concrete strengths

- `openscrub_web.py:2875` derives complete category-local groups before filtering, preserves person-before-track identity, representative selection, full members and ordering, and keeps dropped rows independent singletons with their real category. `TRKMEM`/`ROWCARD` remain the output-action lookup rather than a second decision store.
- `openscrub_web.py:2910` and `:2936` use live effective `EN` values and full metadata. Mixed groups contribute once to each applicable output view; option counts apply only the other selector, category badges count ordinary groups, and the zone subtotal includes collapsed matching rows. The exact seven-card oracle, false representative, opposite pending overlay, unknown/zone-only categories and distinct empty states have relevant retained checks.
- `openscrub_web.py:3001` batches setters and refreshes affected aggregates/editor locally followed by one count/view refresh. Ordinary-category, zone and selected bulk targets are snapshotted from complete metadata, including hidden ordinary groups and all independent zone rows, with visible scope explanations. The bounded 600-row/200-group test checks one transaction refresh and a finite EN-read bound without making a latency claim.
- `openscrub_web.py:2913`, `:2921` and `:3031` keep explicit filter/reset selection clearing separate from live pruning. Zone close removes unavailable selected rows, and reopen does not restore them. Marquee excludes hidden/closed/zero-layout cards and touch/button interactions, cancels on Escape and view changes, and rejects stale ownership.
- `openscrub_web.py:2960` hides existing nodes in place, retains matching-card focus, and moves focus to Output when a focused card/section disappears. Filter/reset do not call output setters, fetches, review/editor loading, save or render, and leave the editor outside the card predicate. Existing save ACK reconciliation remains value-based and view-guarded.
- The delivery explicitly retains failed harness runs and describes browser acceptance accurately as core scenarios plus a targeted native-touch/help follow-up on identical product bytes. It does not disguise the timed-out synthetic-scroll invocation as green or claim image request cancellation/performance scheduling.

## Findings

**Critical:** None.

**Important:** None.

**Minor:** None requiring a product or fixture change.

## Task quality

**Approved.** The implementation is localized to review JS/CSS, uses existing choice/save/editor owners, and adds meaningful emitted-JS and full-PAGE fixtures under `tests/`. No new dependencies, report fields, decision state, training/confirmation states, autosave, expanded workbench or frontend reorganization appear in the supplied change. The complete diff and retained evidence support the requested behavior; no heavyweight replay is necessary for this review.

Keep the explicitly deferred C01 post-render row-preservation acceptance and P16D ordinary playback-startup acceptance in their owning work. Those are the narrowly relevant outstanding validations, not reasons to expand this PR.

## Checked evidence and review limits

Read the full Task150 brief, implementation report, PR draft and complete scope research. Reviewed all supplied changes in the review package, including implementation and fixture-only follow-up. Large embedded unchanged image-data context caused tool-output truncation during the initial diff read; unread review ranges were recovered in bounded chunks. No second full-diff pass, Git command, branch/index/ref operation or product mutation was performed.

The single named outside-diff product-source check addressed a concrete integration risk: an existing non-representative editor Remove blur or late save ACK might bypass the new refresh or update another view. The focused `EN`/setter/refresh call-site inspection and existing editor/save owners in the pinned native `openscrub_web.py` show that Remove blur calls `applyDet`, which resolves complete card refresh through `ROWCARD`; ACKs reconcile submitted owner maps without changing current filter membership/focus/selection and retain `ownsView` guards. This was a source check, not a new runtime race test, and was not broadened into other product files.

Static integrity checks passed for all **71** retained manifest entries and all **25** current native source/test/config/asset identities. Product `openscrub_web.py` is SHA256 `0f94a94edd2e08e739cdf756b4bf1383b029a54f1e4cd147a0a9d56843015f06`. Full/floor preflight records bind the implementation commit, and final fixture-only source identities retain identical product and owning Python-test bytes.

Inspected retained commands, per-run configs, preflights, complete relevant logs and result records: genuine missing-selector JS/browser RED; **78 passed** focused owners; **212 passed** full discovered suite on actual Python 3.12.16; **88 passed** selected active-source cases on actual Python 3.9.25; eight completed core browser scenario groups before the retained scroll timeout; native-touch follow-up with real window scroll **1673 → 2082**, pending overlay/no-detections/closed-zone/help checks; actual listening HTTP save, raw reopen, terminal render `done` and nine selected/kept/unrelated output-pixel regions. Independently inspected the retained 390px controls and help screenshots.

Checked package build/install/default/CLI/web/listening-HTTP records and independently read the retained archives without extraction or execution: sdist and wheel sizes/hashes match, all **25** required sdist files and **9** wheel files match source identities, and installed module bytes also match. The wheel derives from the extracted sdist; Python metadata remains >=3.9. The existing extraction-tool warning remains disclosed.

Read the execution handoff and task launcher/fixture/config evidence. The retained recipes use the supervisor-owned workspace runtime root and reviewed guarded launcher for native, floor, direct browser/server and installed checks. No prepared environment, original checkout/user data or model was changed during this review.

Independently rehashed the **11** audit-listed tool/backend/browser/package entries and both resolved interpreter binaries against the disclosed expected pins; all match. The retained configs still omit those binary-hash preconditions, as reported. I accept the transparent matching post-run audit as bounded supporting evidence and do not characterize it as a pre-execution guarantee or request broad workload replay.

Only this review report was written. No runtime workload, publication, controller action or subagent was launched.
