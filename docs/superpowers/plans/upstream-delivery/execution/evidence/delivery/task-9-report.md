# Task 9 / P09 — visible-first review cards and thumbnails

Implemented and locally committed for fresh supervisor review. No publication, adoption, other-candidate import, dependency change, model download, original product runtime/user-data change, or subagent work.

- Base: `2ae3257b9752e2d976ff7a0d39955a13c133273a` (reviewed P02/P07a).
- Head: `0c2b98e9e136abcd472bdda59cecaf546775ea4e`, `pr/visible-first-thumbnails`.
- Native worktree: `/home/tahv0/.codex/worktrees/c832/OpenScrub`; clean after commit.
- Product/test scope: `openscrub_web.py`, new `tests/test_thumbnail_scheduling.py`, and mounting-adapter changes in the two existing choice/save test files.
- Evidence: [task9-evidence/](task9-evidence/README.md). Source, PAGE and package hashes are in [identity.json](task9-evidence/results/identity.json) and [package-check.json](task9-evidence/results/package-check.json). Verified web SHA-256 is `7889b6f16e0989e95e263fa7bd5fd377a1056ebc818fe3c0c394d5df17fdd99b`; evaluated PAGE is `6c67cf985cfa946304b7a92a9ef98224f6c83dce8fedb028cbafb38510b64a76`.

## Behavior and ownership

`reviewDescriptors` (line 2795) derives the complete ordered category/group and independent outside-zone descriptors before HTML. Person-before-track grouping, chronological membership, confidence representative, category order, `TRKMEM`, and `ROWCARD` cover all rows. Representatives retain metadata summaries; descriptors contain no saved output values. `EN`, `EDITS.enabled`, existing `REVIEW_DRAFTS`, and the P07a equality acknowledgements remain authoritative.

The review/editor shell mounts once. The global normal window is at most 64 cards, rounded into complete native CSS grid rows; one actual focused card subtree can remain outside it, giving an explicit maximum of 65. Selection alone never pins a card. Section shells and two spacers per section remain; omitted rows are numeric heights/prefix offsets, not hidden cards, image nodes, retained HTML, or per-group row wrappers. Native `auto-fill` 175px minimum/9px gap is retained, including partial final rows. Computed grid tracks determine the real columns. The contained thumbnail well reserves 112 CSS px; text, scope, actions and enlarged originals remain available.

`ResizeObserver` measures mounted rows. Width changes invalidate width-dependent estimates and repartition the existing IDs. The last first-visible group/pixel anchor is retained through reflow. A real zoom regression went from group 866 at −54px being unmounted after zoom to the same group at −54.25px. Ordinary scroll never deliberately moves focus. Previous/next native controls plus range/total status traverse complete eligible order across categories and open zones; the supervisor accepted their sticky toolbar placement. These controls provide a deliberate path through omitted content, not a claim that unmounted subtrees are exposed to assistive technology.

`ReviewScheduler` (line 2883) owns only mounting, matching/layout eligibility, thumbnail bindings/queue/controllers/retry timers/URLs, its observer/listeners and bounded selection gesture work. Instance identity, captured job/view, current root, descriptor ID/current binding and target connectivity fence asynchronous work. A global `THUMB_FLIGHTS` set counts unsettled browser fetch **and full body consumption** across disposed/replacement schedulers. Exactly four slots are available. Abort marks obsolete work immediately; only settlement releases a slot. New metadata/cards can mount while old thumbnail work drains. This does not bound unrelated requests, server workers, native decoders, or browser caches.

Fresh visible work precedes visible retries, then nearby work. Total prefetch is at most one viewport and further limited by the card budget. Closed zones have zero mounted cards, image URLs and pending queue work. Initial plus three retries use 600/1200/1800ms; failure counts/deadlines survive ordinary unmount/remount within the view. Cancellation is not failure. Retry timers hold no slot and reenter the same queue. Exhaustion shows neutral unavailable text and keeps editing usable. Retry parameters use `URL.searchParams.set`.

Category and zone bulk actions snapshot complete metadata targets, including unmounted/collapsed members. `applyDetBatch` (line 3173) refreshes affected cards/editor once per transaction. Representative actions still cover the full group; nonrepresentative editor Remove remains row-local and refreshes its containing group. Selection IDs survive ordinary unmount and regain highlight. Marquee freezes a bounded set of actual intersecting cards, excludes pins/spacers/closed zones, retains touch scrolling/button exclusion/Escape/menu behavior, and reconciles after release. Explicit zone closure prunes selected zone IDs.

Disposal removes scheduler/selection UI work and URLs; it does not clear legitimate choices, geometry/time/manual/audio/editor/playback drafts. In-review editor opening keeps the scheduler. New job, exact review replacement, panel removal, successful render teardown and actual synthetic-job deletion dispose the correct owner. A save captures its review scheduler so an old same-job result cannot tear down a replacement root. Page-hide cleanup/restoration reuses complete metadata and drafts. Local scroll/resize/details/queue operations perform no save, metadata refetch, editor reload or editor remount.

### Derived structures and P15 seam

| Structure | Purpose and lifetime |
| --- | --- |
| `REVIEW_META.sections`, descriptors and `byId` | Complete immutable grouping/order/category/zone targets for this metadata incarnation, independent of mounting. |
| `TRKMEM` / `ROWCARD` | Existing group action scope and reverse member-to-card refresh identity, complete for all rows. |
| `matching`, section IDs | Complete matching set intersected with open-section eligibility; initially every descriptor matches. |
| Numeric `heights` / `prefix`, widths and columns | Full scrollbar extent, direct jump lookup, measured variable-row correction and width invalidation. |
| Bounded row/binding maps, normal IDs, optional focus pin | Actual mounted DOM and stable target identity; no offscreen blob/HTML cache. |
| Eligible priorities / queue | Small current visible/nearby admission set, rebuilt and deduplicated on reconciliation. |
| Per-view retry map | Failure budget/deadline continuity across ordinary remounts; no output decisions. |
| `THUMB_FLIGHTS` | Cross-view unsettled thumbnail fetch/body drain; unrelated requests have separate owners. |
| `selSet`, frozen gesture targets, last anchor | Explicit selection independent of mounting; bounded hit testing and visual position preservation. |

The exact future seam is `refreshReviewVisibleSet({jobId,viewGen,matchingCardIds})` at line 2876. It accepts the **complete matching descriptor-ID array**, validates current job/view/instance/root, and schedules local reconciliation. Omitting the IDs refreshes the current complete set. Future P15 owns predicates/counts/filter-selection/focus behavior. No predicate or filter UI is introduced here. Bulk actions retain full category/zone scope regardless of this mounting seam.

## Verification results

| Gate | Actual result |
| --- | --- |
| Meaningful descriptor/admission RED → GREEN | Missing descriptor extraction failed first; three missing scheduler body/admission/retry cases failed next. Four initial owning scenarios then passed. |
| Final owning/P02/P07a focus | 78 passed; eight new scheduling cases evaluate shipped `APP_JS`, not reimplemented grouping/admission logic. |
| Required `test_openscrub.py` + scheduling + choice/save controls | 212 passed, 84.84s. |
| One normal full discovered suite | 212 passed, 81.27s, serial distinct basetemp. |
| Actual Python 3.9 owning/P02/P07a | 78 passed, 10.02s, Python 3.9.25/OpenCV 4.14.0; active-source compile/AST floor also passed. |
| Evaluated shipped JS | `node --check` passed, Node v22.22.1. |
| Offline package | sdist built, extracted, wheel built **from that extracted sdist**, installed without dependencies/network. Runtime bytes, sdist test bytes, registries, entry points and Python >=3.9 checked exactly. |
| Installed boundary | CLI/web help and actual listening HTTP `/` and `/api/jobs` passed. Installed imports/PAGE hash asserted, editable checkout paths excluded; 71 native/installed parser defaults match as JSON. |
| Final source binding | All verified source/package hashes matched immediately before commit; clean native worktree afterward. |

Legacy choice tests now mount emitted cards through a documented mounting adapter; they continue to exercise the real choice/grouping/setter logic. The save-only adapter suppresses layout setup. An initial 73-pass/one-failure run exposed its missing `ResizeObserver` primitive, not a product regression; that failure is retained. Real browser validation supplies geometry/interaction evidence. Deterministic adapters cover delayed headers/body, abort settlement, same-job root/A→B→A, stale blobs/load/error/timer, retry continuity/exhaustion, priority, HTTP error bodies and exact URL/listener/observer cleanup.

### Browser, counts and actual routes

Browser plugin/skill was absent. Prepared Playwright/Chromium 159.0.8154.6 was reused without installation; Node `TMPDIR` was set before Playwright import. The flow was actual `/` → review metadata/cards → scroll/jump/choice/editor/save → current ownership and rendered output. Exact viewport coverage: desktop 1365×950; resize 1100×850; narrow 390×844, including a mobile/touch context and actual touch events. Native CSS layout zoom at 125% and 200% was exercised; browser toolbar zoom/other engines were not tested.

Actual layout covered variable long text, images with no intrinsic HTML dimensions, loaded/failed previews, multiple categories, open/closed zones, empty lists, first/final reachability, jumps both directions, one retained focused subtree, native Enter/Space/Tab, selected-ID remount, a frozen marquee during scrolling, Escape, active editor identity/drafts, and resize. Real narrow touch scrolled 615px with zero marquee, a narrow range-control activation moved focus, and a thumbnail opened the actual 640×360 original via `detframe`; Escape closed it. Actual synthetic-beta deletion left disposed=true, zero bindings/listeners, removed only its draft, and cleared current job.

Held real save acknowledgements preserved a newer opposite choice through a window move. A controlled HTTP 423 retained the draft. Local movement retained the editor/canvas/draft object and unfinished gesture with zero metadata/save/editor reload I/O. Playback retained its video node and continued through a window move after an explicitly controlled native `video.load()` startup; see the P16D limitation below. Final main page JS errors were zero; the single console error was the intentionally injected 423. Deliberate failed-thumbnail probes generated expected network failures separately. Page identity, meaningful content, no error overlay, screenshots and interaction checks passed; screenshots were visually inspected.

| Observation | Retained original / exact-base control | Candidate |
| --- | --- | --- |
| Small 12 ordinary groups + 2 zones / 20 rows | Exact-base 14 cards and 14 images, including 2 collapsed-zone card subtrees. | Initial actual small viewport 5 cards/images; collapsed zones 0 cards/images/queue. Complete metadata remains authoritative. |
| Historical S03, not repeated | 10k groups/15k rows, 2,460,605 metadata bytes, 10k cards/images and 9,994 old outstanding requests at the controlled switch. | No same-workload latency or memory comparison claimed. |
| Final bounded large fixture | No new old 1k/10k baseline. | 1,200 ordinary + 2 zone descriptors, 1,802 rows, 304,628 metadata-response bytes; report 598,398 bytes. First settled normal window 42 cards/images, 6 rows and 12 spacers across 6 section shells. Observed matrix maximum 56 normal + 1 focused exception. Contract remains 64 normal + at most 1 pin. |
| Unsettled browser thumbnail fetch/body | Old eager design has no application four-slot owner. | Main browser maximum 4, including controlled old-view switching; deterministic body/abort gates prove drain semantics. |
| Tiny actual warm/cold route observer | Separate bounded evidence, no latency workload. | 6 browser operations settled and 6 image loads; 6 server route entries, 6 WSGI body iterator exhaustions/closes, 3 cached JPEG hits, 3 verified cold misses, 3 thumbnail-route decoder opens. Closed zones 0. |

Server completion here means **body iterator exhaustion and close**, not client receipt. Original `send_file.call_on_close` instrumentation reported zero completions and was ineffective for this boundary; those raw observations remain. The separate tiny WSGI observer resolves the measurement gap without modifying server product code. Headers-only real response gates and ungated visible image completion complement deterministic controlled body/image/timer continuations. Browser abort is not native decode termination.

A single final page observation under normal GC recorded JS used heap 5,776,760 bytes, 5,182 CDP DOM nodes, 6 documents, 423 listeners and no captured long tasks. The context included navigation history; no forced GC or retained-memory ceiling is claimed. Separate owned-process RSS observations are retained: base 111,272 KiB, candidate 250,000 KiB, installed 83,204 KiB, count fixture 167,576 KiB. Different process states/workloads make these noncomparative diagnostics. Full metadata/indexes, explicit selection, category shells, browser caches and native resources remain proportional or separately owned. No total-DOM/heap/RSS bound, latency improvement, benchmark, p95 or throughput claim is made; no timing slot was requested.

### Actual persistence and render

Actual UI chose ordinary Keep, a grouped mixed choice using representative Blur followed by row-local editor Remove, independent zone Blur/Keep, moved a box, applied times, completed an additive manual region after scrolling its unfinished gesture out of view, and added an audio span. Choices were scrolled out of the narrow window before saving through real HTTP. Every original raw row/index and unaffected metadata field was checked; the edited row's `last_seen` correctly clamped to its new 0.2s start. A fresh page reopened 21 rows (20 originals + 1 manual), zero pending choices and the intended flags before allowing actual render.

The real CPU libx264 render produced 201,688 bytes. Decoded selected/moved, zone and additive regions were black (means 0–0.084); kept ordinary/member/zone and unrelated regions retained content (mean absolute errors 3.208–3.256). Complete raw pre-render geometry/times/category/person/track/zone/text/flags and two audio spans were retained in evidence. This synthetic clip has no audible track; it proves audio draft/report ownership, not audible codec correctness.

The UI script's final page-poll/next-sample assumption observed transient `rendering` and failed its immediate terminal assertion. All pre-render/fresh-page assertions had already passed. Independent authoritative HTTP polling subsequently observed `done` and actual decoded output passed. The failure is retained; the reproduction script now uses authoritative HTTP polling, without repeating the completed edit matrix. These distinct results are not relabeled as one uninterrupted passing browser script.

As expected on this standalone base, render rewrote the report from 21 to 18 rows by dropping disabled rows. **Full after-render row/group preservation is not passed here**; it remains P06D/C01. No report changes were copied.

## Failed attempts and limits

All material failures and corrections are listed in the evidence README/logs. They include the initial loopback sandbox bind denial (transcribed note; its initial raw log was overwritten), missing scheduler features in RED, the legacy Node layout adapter, real implicit columns at 125% zoom, the reproduced anchor loss, an offscreen-pin/sticky-toolbar marquee probe target, editor probing before the fixture's first detection time, unscoped `details` locators, a raw `last_seen` expectation, transient render polling, missing cached build `tomlkit`, and an installed-path filter that initially excluded the authorized scratch nested beneath the original checkout. The initial defaults byte comparison differed only by a final newline; parsed equality passed. No failed run is counted as a pass.

The earlier mp4v decoding diagnosis was **unconfirmed**. H264 fixture replacement did not fix the playback wait. Actual media diagnostics showed preload=none, readyState=0, networkState=1, paused=true and no media error: the reviewed P02 base waits for metadata before invoking play/load. The supervisor identified the already reviewed P16D fix at `47e9f6d5614365e00d899c87df6c209cd7aaabf6`, intentionally absent here. The final playback ownership probe explicitly invoked native `load()`; ordinary Play startup remains a P16D/C01 prerequisite. No playback fix was imported.

Not covered: other browser engines/platforms, browser-toolbar zoom, all possible viewport heights/category cardinalities, screen-reader access to omitted subtrees, native decoder termination, audible audio rendering, or combined-candidate races. No supported measured viewport exceeded the card budget. No new timeout/HTTP taxonomy, metadata recovery, filter, server cache/decoder rewrite, transaction stack or report schema was added. Benign synthetic names were used; the platform-blocked filename probe was not retried.

C01 must combine P03 automatic-review ownership; P08 source/version/recovery bindings; P15 complete descriptor/filter/focus/selection semantics; P01 original-job streaming progress; P06 publication/leases/report/lifetime gates; and P16D Play startup. In particular, scrolling/disposal during original-job exports must cancel only P09 controllers, and complete after-render rows must be checked on the accepted P06D combination.

## Isolation and cleanup

All mutable hooks/profile/model/cache/temp/job/export/build/install/browser/server paths were under the expressly assigned ignored scratch `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9`, on the workspace filesystem (804,611,313,664 bytes initially free). Shared prepared environments/tools were read-only. Actual task-local `sitecustomize` guards protected standalone Python as well as pytest, blocked outward connections/writes outside that exact root, and retargeted expanduser. No storage guard was stubbed. The cached 232,589-byte YuNet model SHA-256 matched `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`.

Pytest invocations were serial with distinct basetemps. Native/base/floor/installed imports were asserted; installed checks filtered editable paths while permitting only the assigned nested scratch. Browser contexts closed; main lifecycle cleanup recorded zero live object URLs, zero duplicate revocations and zero active browser operations. Gates were released with no pending/held work; only the four verified owned server PIDs were terminated and ports 18509/18510/18511/18512 closed. Runtime/media/environment/source-export/install trees are excluded from compact evidence. The product branch is ready for the supervisor's fresh review, not adoption.

## Fix1 after fresh review — current head fe20dff

The initial sections above are the **original `0c2b98e` implementation/evidence record**. Fresh review identified DOM/Tab insertion order, abandoned restoration structure and restored retry-budget reset. All three are addressed in `fe20dff7b73efb5afdbf3130e75a19c8b35ecba3`, from fix base `0c2b98e9e136abcd472bdda59cecaf546775ea4e`, with only `openscrub_web.py` and `tests/test_thumbnail_scheduling.py` changed.

See [task-9-fix1-report.md](task-9-fix1-report.md) for exact covering test names, commands, outputs, source/package identities and boundaries; [task9-fix1-evidence](task9-fix1-evidence/README.md) retains fix1 artifacts separately. Four amended emitted-JS tests reproduced all findings (8 old pass/4 new fail), then the scoped native and actual-3.9 runs each passed **82**. Actual Chromium verified upward overlapping-window DOM/native Tab order, width repartition with the same focused control, three controlled transition cycles with stable 6 rows/4 spacers/42 cards, exhausted retries remaining at four attempts, fresh-metadata reset and zero abandoned work. The additional controlled mid-window restore retained group77 at−199px, scrollY4445 and height8478 throughout. Actual BFCache navigation remains unobserved.

Final evaluated JS parsing, offline extracted-sdist→wheel exact source/test binding and installed actual HTTP containing exact APP_JS passed. Web SHA is `435ee74b112635a9694333fafc9460b3f454d371760f3aba1c4d4fa4875e4563`; PAGE SHA is `8dc91cdf482ba9117777aa3723695477d54925223099bac11d2c610c91aa1483`. The first focused browser cleanup counter's null-global harness failure is retained; its corrected invocation passed. All fix1-owned servers/ports closed and the native worktree is clean.

The original full/required212 and save/render results were **not rerun or relabeled** for the fix head. P06D/P16D and combined C01 limitations remain as above. The candidate is ready for scoped re-review, not adoption/publication.
