# Task 20 / P02 — explicit review output choices

Repeated **Blur** or **Keep visible** actions now retain the requested output. Every ordinary and outside-zone card exposes both native actions, a truthful state derived from all its existing members, and contextual accessible grouping. Mixed groups show exact blurred/visible counts with neither action pressed and no whole-card dimming.

The candidate is committed on `pr/explicit-review-choices` in `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Base: `92124753736e287ac800af91f0ac96f3e96c01be` (reviewed P07a). Head: `2ae3257b9752e2d976ff7a0d39955a13c133273a`. Worktree clean after commit. No publication, subagents, new framework, global installation, inference, model downloads or original-checkout product changes.

## Before and after

- Previously, a mixed person group `[0,1,11]` with `[true,false,true]` displayed the representative's `Keep` and dimmed the card. Its button reversed the representative on each click. It now displays **Mixed — 2 will be blurred; 1 will stay visible**. Blur twice leaves all three true; Keep visible twice leaves all three false.
- Uniform groups display **Will be blurred** or **Will stay visible**, with the corresponding action's boolean `aria-pressed=true`. Both actions remain enabled/reachable. In-place state/attribute updates preserve focus.
- A three-member face group says **Applies to all 3 appearances in this face group**, replacing a promise about all a person's appearances. Category actions say **Blur all / Keep all visible**; marquee uses **Blur / Keep visible**. The zone summary neutrally says to choose output below.
- Removing a nonrepresentative blur in the actual editor still changes only that row. Its containing card immediately becomes mixed. Removing the representative still applies its existing group and clears the selection/editor controls.

## Scope and ownership

Existing category-local grouping, person-before-track precedence, confidence-based representative, time-sorted membership/order, zone-row independence and category/marquee mutation scopes are unchanged. `ROWCARD` is a derived view-local row-to-representative lookup, rebuilt with review mounting; it contains no decisions. One group action refreshes affected cards without scanning unrelated groups. The bounded regression uses 600 rows in 200 groups and asserts no more than 2,400 enabled-value reads during category setting; this is operation-count evidence, not a large-list latency claim.

Every action enters P07a's existing `applyDet` enabled-draft write path, including deliberate choices equal to loaded values. The supervisor clarified the authoritative P07a contract: successful acknowledgement clears submitted entries whose current values still equal the submitted values. An in-flight repeat of that same submitted value is satisfied by that ACK; a newer opposite value remains pending and withholds render. P02 introduces no version/baseline/second dirty store and changes no acknowledgement code. Failed saves and job A→B→A ownership continue through existing entrypoints.

All engine code, zones code and server functions are byte/AST unchanged. Installed CLI/web defaults remain `auto` engine/device/encoder, `blur`, pad 8, tight coverage and archival quality. Audio/geometry/timing, thumbnails/retries, enlarged original preview, marquee/Escape, mobile scrolling and Austin's existing help placement/tap guard remain in their owning paths.

## Verification

Artifacts, executable harnesses, commands, logs, reports, decoded frames and screenshots are under `/tmp/openscrub-task20`; see `commands.txt` for exact invocations.

| Check | Result and boundary |
| --- | --- |
| Initial emitted-JS RED | `red.log`: 5 failures / 1 pass. Genuine product failures included missing mixed/scope feedback, missing Keep action and Blur submitting false on an already-true row. The editor case also exposed an incomplete test DOM fixture, subsequently corrected. |
| Focused final GREEN | `green.log`: 70 passed (8 new output-choice tests + 62 existing P07a cases). Actual emitted onclick handlers, full member state, repeated singleton/person/track/zone actions, category/selection isolation, editor scope, bounded refresh, same-value ACK, opposite edits, failed save and job switching. |
| Stabilized full discovery | `full.log`: **204 passed in 67.86s**. Run once after source stabilization; no repeated passing broad suite. |
| Evaluated JS parsing | Actual PAGE composition from literal assignments, both script blocks joined; `node --check evaluated.js` passed. The harness preserves the full emitted application rather than replacing its review logic. |
| Browser QA | Browser plugin **not available**. Prepared Playwright 1.65.1 / Chromium headless shell 1255 used with required native-runtime escalation. `browser-results.json`: **8 scenarios**, zero page errors and zero console warnings/errors. |
| Python 3.9 | `python39.log`: 71 passed / 1 audit-blocked test / 132 deselected. All 70 web tests passed; `test_report_roundtrip_preserves_tracks` was blocked because its temporary directory was outside that environment's allowed root. Only that test retried using the allowed temp root: `python39-report-retry.log`, **1 passed**. No product changes required. Packaged Python 3.9 grammar checks also passed. |
| Build / package | Full sdist→wheel build passed (`build.log`), using existing hatchling from the prepared environment with `--no-isolation`. `packaging.json`: exact packaged source/test bytes, both standalone test files in sdist, packaged Python 3.9 grammar and unchanged server/engine/zones boundary checks passed. |
| Installed smoke | Offline, dependency-free wheel installation into task-local `installed/site-packages`; exact installed sources verified. Actual installed `openscrub --help`, actual `openscrub-web --http` startup, homepage/jobs API, unchanged defaults and idle SIGTERM exit 0 passed (`installed-startup.json`). |
| Self-review | Focused diff inspected against all brief contracts; `git diff --check` passed; all four changed files committed. Independent review belongs to supervisor. |

Initial environment-only issues were corrected without product workarounds: missing browser shared-library path; localhost sockets requiring the already-authorized native runtime; missing hatchling in the default 3.12 build environment; unavailable pip there (prepared uv used offline). Temporary browser locator/coordinate/hidden-details checks were corrected, and asynchronous native touch input was driven through Chromium's touch events. Logs/report results distinguish these from product failures. One early draft-ownership regression overrequired version semantics; it was corrected to the supervisor-confirmed value-equality contract above.

## Browser evidence

The flow was full emitted page → actual job link → mounted review → actual pointer/Tab/Enter/Space/category/marquee/editor/touch actions → rendered state. All HTTP in this UI matrix was controlled synthetic HTTP, not evidence of backend persistence/render.

| Required browser check | Result |
| --- | --- |
| Page identity / meaningful content | Title `OpenScrub`, intended synthetic origin `http://127.0.0.1:18507/current.html`, actual review/job content. |
| Blank/overlay | Meaningful full page and review rendered; plain application, no framework error overlay. |
| Console health | Zero page errors and warning/error console messages in final controlled matrix. |
| Interaction | Repeated pointer setters; category→Blur→Keep Tab order; repeated Enter/Space; focus retained; visible keyboard outline; accessible group name/pressed attributes and mixed counts. |
| Existing flows | Actual pointer marquee selects only card 4; Keep visible changes only its group; Escape clears selection. Independent zone actions and truthful summary; enlarged original image opens and Escape closes. Actual editor row 0 removal refreshes mixed card 1; row 1 removal retains group fan-out. |
| Responsive/touch/help | 1365×1000 and 390×844; controls fit viewport and document has no horizontal overflow. Actual touch tap works; Chromium native touch moves scroll from 1405 to 1810 without marquee. Existing mobile help opens, positions itself and leaves checkbox unchanged. |

Screenshots: `mixed-desktop.png` shows two distinct mixed groups and exact counts; `mobile.png` shows paired controls/scope at 390px; `mobile-help.png` captures the existing tap-guard flow. `mixed-accessibility.txt` is the native accessibility snapshot, with the contextual group and both action names. `desktop.png` shows the existing editor and independent zone controls.

## Actual backend and decoded output evidence

The separate real flow used the actual application server at `http://127.0.0.1:18520`, real detections GET/POST, filesystem report writes, worker and report-based pipeline. It used a four-second 320×180 checkerboard clip with thirteen ordinary synthetic rows, mixed person/track groups and two dropped rows. No scan/inference was run.

1. Actual UI Keep visible twice on person card 1 set rows `[0,1,11]` false. Actual Blur twice on track card 4 set `[4,5]` true. Actual zone-row Blur enabled row 8 only. Other rows retained their initial values.
2. Actual Save edits & render POST persisted those flags. Only its subsequent render request was deliberately answered with an explicit 409 QA gate, allowing inspection before render. `saved-before-render.json` retained all thirteen rows. A deep equality comparison excluding only `enabled` confirmed every other field, including audio, boxes, timing, person/track/category, zone and provenance data, unchanged.
3. The first page was closed; a fresh browser page entered the actual job anew. Real GET showed all thirteen correct flags and truthful card states before any render. `real-reopened.png` and `real-result.json` record this fresh-view boundary.
4. The fresh page's actual Save edits & render was then allowed through entirely. The real worker completed using CPU libx264. Existing box redaction mode was selected solely for precise pixel evidence; defaults were not changed.
5. At decoded 1.5s, all eight enabled regions were black (mean intensity 0.015–0.185), all five kept regions retained their texture (mean absolute error 3.07–3.36/255 against decoded original), and an unrelated region remained unchanged within the same codec tolerance. `output-check.json`, `decoded-original.png` and `decoded-output.png` record the measurements. No HTTP callback substituted rendered output.

**Known prerequisite:** the base intentionally predates P06D. Actual rendering rewrote its report from enabled detections and reduced thirteen rows to eight (`post-render-report.json`). This is the existing disabled-row/lifecycle limitation, not fixed or hidden by P02. There is no claim of complete disabled-row/zone preservation on an after-render fresh review. P06D plus the C01 combined after-render gate remain required; do not transplant that server/lifecycle code into this standalone diff.

## Changed files and remaining limits

- `openscrub_web.py`: local pair/status/scope CSS and emitted review controls; derived membership lookup; in-place state refresh; consistent bulk labels/neutral zone summary. Server functions unchanged.
- `tests/test_review_choices.py`: eight evaluated-JS behavioral regressions reusing the existing P07a harness with a minimal mount/attribute DOM adapter.
- `CONTRIBUTING.md` and `CLAUDE.md`: corrected the owning test command from engine-only invocation to `python -m pytest -q`, including standalone web tests.

No new persisted state, learning/handled label, report migration, dependency or model. Chromium is the tested browser; no claim of Safari/Firefox, screen-reader user testing or large-list responsiveness. The supervisor performs the fresh independent review. Browser plugin installation may improve future in-app browser inspection, but it was unavailable and unnecessary for this authorized fallback.
