# Task655 — reviewed renderer composition and final C01 verification

Implementation and the authorized verification sequence are complete on clean `integration/upstream-focused-renderer` at `c205ef5379778f63313b519411a2d5e37d07cba5`, based exactly on reviewed Task654 `00480c7e42ddb329f4dde9599c256555f2dabcf0`. Fresh independent root review remains required. The working `integration/upstream-focused` ref remains at the reviewed base; no publication, user-data adoption or next task occurred.

The sole whole discovered run at `6ef0b9d` produced **1,982 passes and 44 failures across 2,026 nodes**. Every failure was subsequently explained and its owning follow-up passed on unchanged production bytes. This is not a claim of one 2,026-pass invocation. Root explicitly ruled against repeating the full suite. The final actual Python3.9 affected selection passed **1,584 cases**; the final package and strict-installed listening gate passed.

## Provenance and adopted ownership

All eighteen exact original whole commits were applied with `git cherry-pick -x`, ordered R4 → approved P11 → G3. [Original/composed identities](task655-evidence/original-to-composed.json) retain full SHAs/messages, including all four integration-only fixture commits. [Provenance](task655-evidence/provenance.json) binds the unchanged standalone branches and existing N09/report prerequisite mappings. Neither prerequisite was replayed; Task16330 ancestry, already integrated browser/core originals and local tooling were excluded.

[Actual conflict and resolution patches](task655-evidence/assembly) retain the five encountered seams: P publication status and opened-descriptor downloads, G1 native-body/package ownership, G2 older body aliases, and G3 metadata helper cleanup. Resolutions preserve current owners:

- Public `render`/`render_hdr` validate enabled original geometry before constructing a delivery. `run_render` validates immediately after callback initialization, before logging, duration, coverage or staging. Validated `apply_coverage` precedes one outer video/report delivery; covered geometry calls `_render_into`/`_render_hdr_into` directly. There are no `_render`/`_render_hdr` aliases or nested stages.
- G metadata/ordinal/time/cum/box/band/leaf finite checks execute within R's resource boundary. `_geometry_metadata(cap, stage)` validates only; R owns release and retained-primary cleanup diagnostics. Healthy HDR metadata capture release and `meta=None` still precede decoder spawn. Finite negative counts, signed padding and legal rounded-empty coverage remain admitted.
- C01 touched-global-chroma-cell reduction, independent exact encoder-input oracles, full-known-box polygon fallback, clip behavior and Austin tight/archival defaults remain intact. [AST audit](task655-evidence/source-audit.json) proves C01 leaf bodies equal after removing only G entry guards, exact approved public/private signatures, unchanged R finalizers, unchanged PAGE/APP_JS, and identical runtime bytes after the first observer commit. Report construction and public `write_report` also match approved P exactly; named descriptor/frame/report publication functions match P ASTs.
- P preserves staged hash/final-name separation, full raw/unknown/disabled/audio reports, legacy callbacks, rollback of previous presence/absence, recovery descriptors/status, commit-before-success/cancel acknowledgement, per-attempt/rollback epochs, optimistic frame reads, and one-descriptor Range/HEAD/conditional closure. Existing long scan/edit/tracker transaction scopes remain owned as before.
- Web status retains JobLog atomic snapshots and export filenames beside recovery status. New recovery rehydration uses JobLog; other new/rehydrated constructors retain their current JobLog/FILES admission state. `_pregen(jb=job, video=thumbnail_owner.source)` remains unchanged. P03/P12 cursor/epoch/teardown, P07 drafts/audio, P09 membership/window scheduling, P16D editor ownership and source/operation/replay leases remain preserved.
- Actual recursive packaging and Docker/updater ownership remain unchanged; the added private leaf is included through the existing private directory recipe.

[Source/test/package hashes](task655-evidence/source-identities.json), [old/new changed identities](task655-evidence/old-new-identities.json), [fixture identities](task655-evidence/fixture-identities.json), immutable per-attempt preflight/runtime configs and [exact commands/results](task655-evidence/commands.md) bind the evidence. Current inventory comes from actual source and recursive pyproject includes, rather than an older standalone inventory.

## Observer and combined controls

`2944fef` adapts the adopted observer map without changing its behavioral oracles. C01 HDR/SDR write observers and the HDR `buf` selector target the actual private native bodies; public calls and exact whole-input comparisons remain. Polygon/default batch orchestration remains public. P's N09 traceback/write observers, R `into=True` fault selection and report-document/staged-hash/managed mutation fixtures remain intact.

G public invalid-input sentinels cover delivery construction as well as capture/coverage. Clip and rounded-empty spies require actual private symbols, use tmp destinations, write bounded real stage bytes and exercise publication. Metadata controls count one production release before harness cleanup and retain geometry exceptions plus release diagnostics. Eight tiny actual per-frame-overflow cases cover SDR/fallback/HDR, preview and prior-pair/absence; retained tracebacks prove R closes/reaps resources before P delivery cleanup and leaves finals unchanged.

The initial focused run found two additional C01 managed report seed calls to the removed `web.atomic_report`. `6ef0b9d` adapts exactly those calls under the existing FILES report lock to `_publish_job_report_locked`; raw/audio/HTTP/reopen assertions are unchanged. The two failed nodes then passed. These were fixture API mappings, not product RED.

## Whole-suite failures and bounded follow-ups

The one discovered run is retained in full, including all forty-four failures and its actual node inventory. No production failure was hidden or relabeled as passing.

**Forty-two cascading ownership failures.** Forty-one large-report cases reached only their ending `FILES.count == 0` assertion with count2; a later vault case raised FilesBusy from the same outstanding owners. The actual retry→replace→retry diagnostic established `0→1→1→2`: `polling_http` replaced `enqueue` with a no-op, discarded two accepted queue tickets (one on an obsolete replaced job), and its teardown left both owned. Explicit removal/release of exactly those harness-owned tickets restored0. `ea57a98` captures substituted enqueue tickets, preserves live ticket assertions, shuts down its owned server, removes only those queued tickets under their existing locks, calls `_finish_operation` outside locks and asserts release/restored initial count. It does not reset FILES. The same actual browser retry producer followed by all41 failed report consumers, the vault consumer and exact probe case passed44 cases together, proving the cascade is removed in sequence.

**One JSON-only probe harness failure.** The unchanged real OpenCV capability probe parses pure JSON child stdout. Verification startup records made it appear malformed. Root approved a new separate task-only `opencv_stdout_selected.py` scoped to exactly `test_real_compatible_runtime_has_required_fallback` and its exact argv/`_PROBE` bytes. It validates source/profile records and payload schema, retains complete stdout/stderr/real exit and exposes only that validated payload. Every other child remains untouched; the existing reviewed roundtrip stdout adapter is byte-identical. Both actual3.12 and3.9 exact probe cases pass. Product and shared helper code are unchanged.

**One unsettled reflow fixture.** The original failure read offset−154.953125 instead of29.8125. A first diagnostic omitted console forwarding and retained the same failure; corrected per-event forwarding passed but affected scheduling, so it was not acceptance proof. The root-approved in-memory trace reproduced failure without per-event console I/O: the programmatic scroll's first event arrived after width changed to326, remembered seq0/offset97 on current A/gen1, and its owned ResizeObserver/RAF completed before the fixture read. The intended pre-resize seq1 anchor was never established. `c205ef5` awaits that actual scroll event before changing viewport, using the existing bottom-case pattern. The original plain case then passed, retaining every original offset/clamp/bottom tolerance and production byte. No arbitrary sleep, retry-until-pass, alternative browser or native-visibility substitution was used.

All diagnostic variants, raw failures, exact old/new fixture bytes/hashes and scope limits are retained. No new product runtime fix was necessary, so there is no invented runtime RED. These fixture corrections belong with their corresponding future focused Austin delivery tests; Task654's generic editor lifetime runtime fixes `61dbb31`/`a4649a2` remain visible for P09/P16D delivery, not erased as integration bookkeeping.

## Verification and exact revision limits

| Gate | Frozen revision/result |
| --- | --- |
| Focused geometry/resource/publication/HTTP/report/observer owners | `2944fef`:1,207 passed /2 fixture failures |
| Two failed managed seed nodes only | `6ef0b9d`:2 passed |
| **Only whole discovered C01 suite**, actual3.12.16 | `6ef0b9d`:1,982 passed /44 failed;2,026 nodes;218.19s |
| Actual retry/replacement diagnostic | `6ef0b9d`:confirmed two discarded harness tickets; exact harness release restored0 |
| Original reflow diagnostics | Original assertion fails; forwarding diagnostic passes; minimal in-memory trace reproduces failure with missing settled precondition |
| Retry producer→all41 failed report consumers→vault→exact probe | `ea57a98`:44 passed |
| Original plain reflow case after real-event precondition | `c205ef5`:1 passed |
| Actual3.9.25 affected owning/combined selection | `c205ef5`:1,584 passed;83.65s;no skips/failures |
| Actual3.12/3.9 source/default/evaluated Node/grammar audits | `c205ef5`:both passed;71 defaults;68 Python files parsed under3.9 grammar |
| One offline package / strict installed gate | `c205ef5`:passed;79 exact sdist assets /15 wheel runtime+registry files |

All twelve selected runtime parent/leaf bytes remain identical from `2944fef` through final `c205ef5`. Later changes are precisely the two seed mappings, queued-fixture cleanup and settled-scroll fixture. No later result is relabeled as an earlier single green full run. Root explicitly adopted these bounded failed-owner follow-ups and no broad full repeat.

Every workload used the unchanged approved verification helper, actual pinned interpreter, clean controller environment, `login:false`, unique serial task-owned settings/models/cache/jobs/temp and original-call socket/browser/listening escalation. Only the pinned YuNet model was seeded where needed; no dependency/model downloads or shared environment changes occurred. Allocations used bounded external development admission; private guard code/configuration/policy/receipts remain outside product evidence. Existing protections and locks remain retained for root review.

## Browser and installed proof

Browser plugin unavailable; the explicitly approved fallback used the existing prepared Playwright/Chromium159.0.8154.6 headless library/output-dir setup. The discovered suite exercised actual PAGE/core/browser/server interactions, controlled P03 clocks/deadlines, P09 virtual scrolling, literal filenames, retained drafts/audio, ordinary Play/editor resize, review/save/render/reopen and default SDR. Its combined browser cases and ordinary default SDR control passed. Expected injected503/423/409 diagnostics remain classified; zero unexplained combined page errors were recorded. Three representative desktop/narrow/log screenshots were visually inspected and retained. Settled reflow subsequently passed separately with no tracing. These are controlled lifecycle results, not native BFCache/suspension/visibility proof.

One final package pipeline built sdist, safely extracted it, built the wheel **from extracted sdist**, installed without dependencies and verified strict installed origins/bytes/defaults and actual CLI/web entry points. The recursive inventory retains tests and benchmark assets plus private parent, JobLog, render_delivery, reports and lifetimes. Python metadata remains `>=3.9`.

- Sdist SHA256:`ce088c7d45e1afee3088ff568b20988f6080ddab8854003f42c700f0ac51d78e` (753,126bytes).
- Wheel SHA256:`cfad6540e69a7d926c76d980d8e9083c8559e9f22616958e9b131f6361426c77` (478,963bytes).

Strict-installed actual configured Cheroot verifies complete/partial/suffix/unsatisfiable Range, ETag/date304, If-Range, HEAD, early close followed by successful delete, and child reap. Actual old-stream/new-publication/rollback and FILES cleanup remain covered by final combined source owner tests on the same approved descriptor/publication ASTs; installed Range/close verifies their packaged origins. Tiny ordinary review-save-reopen/default SDR is covered by final combined browser/source cases. This does not claim a second installed media/browser matrix. No successful package or adapter was rebuilt/repeated.

## Self-review, rulings and retained limits

Complete base/head diff, exact18-pick map, signatures, native-finally/paint ownership, report/frame/descriptor ASTs, every modified constructor, selected source lease, recipes and clean head were reviewed. No further Critical/Important issue was identified by the implementer; fresh independent review is still required.

Nonblocking inherited minors remain explicit: P recovery M1's comment contradicts the immediately following ExitStack close while code correctly discards the expendable report stage; defer wording to focused P delivery to keep reviewed helper bytes. Task901's extraction warning remains separate local-tooling readiness work. Task119 viewport wording, Task115 key-order comment, Task164 classified canvas warning and Task652 optional ffprobe/encoder prerequisites remain accepted minors by reference to their reviewed reports. P12C dense-budget/initial-cost tradeoffs and P backup-copy disk/I/O costs remain unchanged.

Setup history also retains an initial nonexistent evidence-target admission denial resolved by root before source writes, and a source-only AST audit that incorrectly assumed PAGE was a literal. The audit failed; an initial shell continuation recorded the wrong terminal status, which root corrected while preserving both records and accounting. Corrected audit compares actual PAGE/APP_JS construction ASTs. These are setup/bookkeeping failures, not product RED or acceptance passes.

No speed, RSS, accuracy, crash durability, permanent long-source generation, Windows/GPU/container/network-filesystem or universal HDR claim is made. Native operations remain cooperative and small synthetic media limits apply. Evidence excludes media/environment/export/install trees and all private guard material. Root owns the independent review, joint documentation checkpoint and any later integration-ref advancement. No external publication or working-version adoption is authorized here.
