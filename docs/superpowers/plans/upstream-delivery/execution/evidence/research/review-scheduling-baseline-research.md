# S03 / P09 ordinary review scheduling baseline

Completed read-only research on 2026-11-17. Ordinary review mounts every group and creates an eager image request for every card. Chromium limits the observed held Flask requests to six, but this is not an application queue. A large jump can leave the current viewport behind offscreen work; switching jobs removes old cards without cancelling their pending image requests. P07a already supplies the pending-choice and view-generation ownership needed for a small scheduler. No product changes, installs, inference, full suite or build were performed.

## Pinned sources and method

Primary baseline: Austin plus the test-only prerequisite, `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. Only the small ownership case was repeated at reviewed P07a, `92124753736e287ac800af91f0ac96f3e96c01be`. Full exports live under `/tmp/openscrub-review-scheduling-20261117/{baseline,p07a}`; the active native implementation worktree was not used. The requested S03/P09/P15 sections were read as future contracts, not evidence of current defects.

| Source | `openscrub_web.py` SHA-256 | `APP_JS` SHA-256 |
| --- | --- | --- |
| Baseline | `9835e1137abee62c0a78e2669ed8bae7059e36bf4bed9f5c7a44f0eb8b40ed3a` | `9c20f2bcd754eac832cfbe6bab802f7b202d41fdf0608203ded89b8d74caf7ce` |
| P07a | `cb3b5fccffb2105982a914c2002d419519bceacf2c8bf3c2bb33ea13eb43b038` | `1430b0f69074524a2af5ba052b467746d17b79703870e67a5524078571c7ce33` |

Both exports have `openscrub.py` SHA-256 `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`. Production `/` responses contain the complete corresponding `APP_JS` byte string. Exact emitted HTML and metadata hashes are in [http-payloads.json](review-scheduling-baseline-evidence/http-payloads.json); source excerpts retain original line numbers in [source-excerpts.txt](review-scheduling-baseline-evidence/source-excerpts.txt).

The flow under test was: actual Flask `/` → `openJob` → ordinary review → first-card viewport → last-card scroll jump → ordinary mixed-group Keep → another job with thumbnail responses still pending. The small case also reopened the original job. Application JavaScript, grouping, controls, requests and callbacks remained intact. A wrapper calls the actual thumbnail view first, records completion of its production work, and then holds the response at the server boundary. An independent task-local control route releases selected responses. No application scheduler was replaced or simulated.

Browser plugin not available: the authorized regular Playwright fallback reused `/tmp/openscrub-save-as-20261116` read-only. Environment: Chromium `159.0.8154.6`, Playwright `1.65.1`, Node `v22.22.1`, Python `3.12.16`, OpenCV `4.14.0`, Flask `3.1.3`, WSL2 Linux, headless `1365×950`. Flask used Cheroot with 24 threads on loopback ports 18509/18519. Python reused the compatible `/tmp/openscrub-baseline-20261116/venv-opencv4` environment. Environment, probes and commands are retained in the evidence directory.

## Existing behavior and controls

Baseline `loadReview` at lines 2709–2800 fetches the entire detections response, fills `EN`, groups by category, then groups by person identity before track identity; independent sightings stand alone. It chooses the highest-confidence member as representative, retains every member index in `TRKMEM`, sorts person cards before other cards and inserts the complete card HTML. Thus 15,000 rows can already collapse to 10,000 groups. This existing collapse must be preserved.

Ordinary thumbnail elements at lines 2777–2779 have eager `src` URLs and no `loading="lazy"`. Zone-dropped thumbnails already have native `loading="lazy"` inside a collapsed details element at lines 2724–2745. They were source-inspected, not included in these ordinary-only browser fixtures. `thumbRetry` already permits three retries with 600/1200/1800 ms delays; no failure/retry behavior was exercised here.

The worker also already starts a separate background `_pregen` pass after scanning (lines 686–751): it sorts all uncached detection thumbnails by reference time and uses a single decoder with short forward reads. This is server-side pre-generation, not review-viewport scheduling, and was not started by the fixture. The on-demand production thumbnail route uses cached JPEGs when present and decodes media when absent. P09 alone cannot claim to cancel or reduce the worker's independent pre-generation work.

Ordinary review has category headers, group counts, category **all on / all off** output actions, per-card **Blur / Keep**, and marquee bulk actions. It has no ordinary detection-type/output-state view filter control in the inspected source or rendered control inventory. Category all-on/off calls `applyDet`; it changes output choices rather than hiding cards. The separate editor's `beFilter` selects enabled boxes for drawing, not review-card categories. Scan category checkboxes are not review view filters. No local view-filter interaction was available to exercise. P15 therefore remains separate.

## Fixtures and measured counts

[serve.py](review-scheduling-baseline-evidence/serve.py) generates a 10-frame, `320×180` synthetic MJPEG AVI and one tiny synthetic JPEG; cached thumbnails use hard links. It constructs real `openscrub.Detection` values and uses upstream `write_report`, then represents one ordinary previously saved mixed track by setting member 1 disabled and member 2 enabled. Even-numbered groups are independent `mrn` sightings; odd groups have two rows and alternate tracked faces and person groups. Names are plain synthetic text; there is no Findings, training, journal, sections or similarity data.

| Baseline fixture | Report bytes | Rows | Groups | Production detections JSON bytes | Mounted cards / image elements | Eager image requests / CDP outstanding initially | Flask views entered and production work completed while held |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 8,298 | 18 | 12 | 2,849 | 12 / 12 | 12 / 12 | 6 |
| oneK | 476,840 | 1,500 | 1,000 | 241,605 | 1,000 / 1,000 | 1,000 / 1,000 | 6 |
| tenK | 4,774,340 | 15,000 | 10,000 | 2,460,605 | 10,000 / 10,000 | 10,000 / 10,000 | 6 |

Beta has 4 rows / 3 groups and a 662-byte detections response. P07a's small response remains 2,849 bytes and its small case also mounts/requests 12 groups. Its report is 8,294 bytes because the provenance input path is four bytes shorter. [Fixture manifests](review-scheduling-baseline-evidence/fixtures-baseline.json) record exact generated report hashes; timestamps change on regeneration.

All initial ordinary images have `loading` other than `lazy`. The 1k/10k browser-request counts do **not** mean 1k/10k concurrent decodes or Flask requests. Only six thumbnail views had entered and completed their warm-cache production work; their outgoing responses were held. The remainder were browser-requested but not yet observed at Flask. The independent control route remained responsive, with 24 server threads available.

At default page scroll position zero, the review cards are below the viewport, yet all ordinary requests are already created. The probe explicitly scrolls the first card into view for the initial-review observation. There are 35 intersecting cards for each large pending-image fixture, then 40/36 intersecting cards at the 1k/10k bottom jump. Pending images have no intrinsic loaded dimensions; these visible counts describe this actual pending-response layout, not a stable prefetch target.

## Large jump and job switch

[browser-summary.json](review-scheduling-baseline-evidence/browser-summary.json) records visible card IDs/URLs, request counts, direct Chromium completions, source work timestamps and heap/task observations for every stage.

| Case | Scroll Y: initial → jump | Next six actual server thumbnail indices after first six responses released | Members of that flight visible at the jump |
| --- | ---: | --- | ---: |
| oneK | 861 → 18,073 | 24, 18, 21, 1463, 1277, 1391 | 3 / 6 |
| tenK | 861 → 175,416 | 18, 24, 21, 27, 30, 33 | 0 / 6 |

The visible 10k cards at that jump are representative indices 14789 through 14999, stepping by six. All next-flight 10k work is far outside that viewport. After the first flight completes, six images are loaded in the old top area, but no current visible image is complete in either large case because the next flight is deliberately held. Chromium itself sometimes promotes visible work: the 1k result contains three visible requests, and the exploratory pass contained two. The evidence does not establish strict FIFO browser ordering or a universal inability to prioritize.

After clicking **Keep** on the mixed track representative, `TRKMEM[2]` is `[1,2]`, both `EN` members become false and the actual button reads **Keep**. No save request is made. The probe switches to beta while the second flight remains held:

- Old cards disappear immediately; `CUR` is beta and there are zero mounted review cards during the 250 ms held observation.
- No old request cancellation is observed. CDP still reports 994 outstanding thumbnails for oneK and 9,994 for tenK. All six second-flight server views have completed their production work and are waiting only at the artificial response gate.
- Beta's metadata/card construction has not completed while those image connections remain held. Releasing them allows beta's three cards to mount. The old eager request backlog continues reaching the actual server: at the subsequent observation, oneK has 378 old-job thumbnail view entries and tenK has 303, compared with 12 immediately before release. Beta's image requests have been emitted but none have reached its thumbnail view in these two observation snapshots.
- No old thumbnail repopulates beta's DOM: beta remains the active job and its mounted image URLs are all beta URLs. This is already-satisfied behavior in the exercised path. It does not prove every asynchronous metadata race is safe on Austin.

These are non-atomic observations across DOM/CDP/server boundaries, so close completion counts can differ by a few requests. Direct CDP `Network.loadingFinished` is the authoritative browser completion counter here. At 10k, Playwright `requestfinished` notifications lagged even though CDP and image load events had recorded six completions. Both counter streams are retained; no conclusion treats the lagging Playwright count as actual server concurrency.

The warm held fixtures prove actual cached route work and request ordering. A separate first-pass cold 3-group fixture had three `cache_before=false` entries, production-decoded thumbnails, and three loaded images; those exact events are retained in [cold-and-exploratory-notes.json](review-scheduling-baseline-evidence/cold-and-exploratory-notes.json). The final repeated cold view is warm. There was no expensive cold 10k decode workload.

## Choice ownership and smallest justified P09 change

Austin's `EN` is page-global and reset by `openJob`; the small reopen restores the original mixed `[false,true]` report values. P07a's small case preserves `[false,false]` and the **Keep** button after switching away/back. Its `EDITS.enabled` stores both deliberate false choices. This is existing P07a protection, not a new P09 defect to repair again.

P07a owns pending drafts through `REVIEW_DRAFTS`, `EDITS`, and `VIEW_GEN`. `loadReview` captures `(id,gen)` and rejects obsolete metadata via `ownsView`; it overlays `EDITS.enabled` onto fetched report values. `applyDet` applies a group choice to every `TRKMEM` member and writes each member into `EDITS.enabled`. On leaving a job, `openJob` discards fetched display state while preserving pending edit bookkeeping. Source ownership and the small browser result agree.

The smallest justified change is a bounded ordinary-review mounting window and a visible-first thumbnail queue owned by the active P07a `(job, VIEW_GEN)` view. Build the complete grouped metadata/member mapping once; retain complete `EN` and `EDITS.enabled` choices independently of mounted cards. Mount only a bounded group window, enqueue the viewport and a limited nearby range, and abort/remove obsolete pending work on a jump or job switch. Generation-check result publication. Aborting a browser response after Flask has started work is not evidence that its decode stopped; server cancellation/pre-generation requires a separate contract.

Keep existing grouping, category counts, zone-dropped behavior, retry semantics and group-member actions. Category all-on/off currently iterates mounted DOM; virtualization must preserve its current whole-category output scope using complete metadata rather than silently affecting only mounted cards. A deliberate mixed-group choice must still set every member. Reuse P07a's draft store and generation guard, rather than creating another persistence layer or making filter/scroll actions save/refetch reports.

Provide one small queue-refresh input such as `(active owner, ordered visible group keys)` for view changes. P15 may compute category/output-state membership from complete local group metadata and call that hook later. Do not add P15 filters, training states or mixed-state filter policy inside this scheduler task. The proposed **64 mounted groups / four in-flight requests / one-viewport prefetch** remain design starting points, not values validated or tuned by these measurements. The complete 2,460,605-byte metadata response for tenK remains a separate cost; bounded cards are not server metadata pagination.

## Tasks, heap, timing limits and QA

`PerformanceObserver` page long-task entries before the initial review observation were none for small, 113/79 ms for oneK and 668/807 ms for tenK. CDP initial `Nodes` were 1,864 / 18,660 / 171,576 and `JSHeapUsedSize` was 2,818,092 / 4,645,040 / 8,655,120 bytes. These are single diagnostic page-level observations with network/DOM instrumentation, not isolated card-construction timings, retained-memory bounds or whole-browser RSS. No performance improvement has been implemented or claimed.

First-visible completion was observed through actual image load events plus viewport intersection: the small case records a visible load after the controlled first release; neither large jumped viewport records a visible completion before the next held response flight is released. No latency statistic is reported: deliberate response gates, pending-image geometry, page initialization and 10k-event instrumentation dominate the schedule, so three warmups/five timing samples would not produce a useful comparable latency signal. Browser-request timestamps retain observable pending age, but there is no application queue whose age could be measured separately.

| QA check | Result |
| --- | --- |
| Identity / meaningful page | Production `/`, title `OpenScrub`, populated ordinary controls/cards |
| Blank page / framework overlay | None observed in final screenshot/DOM checks |
| Console/page errors | Zero final page errors or console warnings/errors in all four final cases |
| Interaction | Real Keep button sets both mixed-track members; P07a restores pending Keep after reopen |
| Screenshot evidence | Actual initial cards, pending bottom jump and successfully decoded cold thumbnails retained |
| Isolation / cleanup | Pinned source hashes unchanged; all browser contexts closed, all entered thumbnail work returned, no held gates, both loopback listeners closed |

An exploratory large reopen recorded `Cannot read properties of null (reading 'style')` without a stack; it did not recur in the refined final flow and is not attributed as a scheduling defect. Early harness certificate-path errors and an observation that waited until a safety gate expired were corrected before the final captures; notes retain those limitations. Final ordering gates never timed out.

Not exercised: mobile/other browsers, empty or zone-dropped browser fixtures, real cold-cache large media, transient failures/retries, save/render, global bulk actions, or an implemented scheduler/filter. No global caches were dropped. A future P09 browser regression should assert bounded application requests separately from browser connection limits, scroll-jump priority, complete hidden-group decisions, whole-category action scope, and discarded old-view work, then measure real warm/cold visible latency without artificial ordering gates.

## Artifacts and reproduction

Compact evidence: [review-scheduling-baseline-evidence/](review-scheduling-baseline-evidence/), including exact hashes, fixture recipe, executable probes, structured observations, screenshots, environment, commands and cleanup records. Full transient exports, original emitted HTML, extracted JS and uncompressed browser observations remain in `/tmp/openscrub-review-scheduling-20261117`. [commands.sh](review-scheduling-baseline-evidence/commands.sh) records the actual export/start/browser pattern. All writes were confined to these task-specific temporary/evidence paths. Fixture reports contain timestamps, so hashes identify the captured run rather than promising byte-identical regeneration.
