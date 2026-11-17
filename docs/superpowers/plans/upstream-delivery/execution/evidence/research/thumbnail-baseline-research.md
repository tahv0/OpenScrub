# P08 / S02 thumbnail and report baseline research

**Status: research complete; no product implementation or speedup claim.** Source is the full exported application at `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin baseline). The route probe imported `/tmp/openscrub-thumbnail-baseline-20261117/export/openscrub_web.py` and its sibling engine, never the moving worktree. Only this report, `thumbnail-baseline-evidence/`, and task-owned `/tmp/openscrub-thumbnail-baseline-20261117` artifacts were written.

The useful split is a thumbnail correctness fix followed by a separately measured, bounded read-only report snapshot cache. Three warm JPEG requests performed **zero report opens/parses**. Four parallel cold thumbnail requests performed **four report parses**, as did four parallel metadata consumers. Geometry, report replacement, and source changes all produced visibly stale warm JPEGs. Snapshot reuse alone cannot fix those JPEGs because the warm route does not read a report.

## Scope and provenance

Read P08 and S02/S06 in `docs/superpowers/plans/upstream-delivery/02-large-video-performance.md`, plus the relevant preview/cache/lifecycle rows in `.superpowers/sdd/README/core-semantic-audit.md` (N06/N07/N10, `_load_job_report`, preview identity, `job_thumb`, lifecycle) and `noncore-preservation-audit.md` (preview/index/journal helpers). The delivery plan exists in the original planning checkout, **not** on the active native product branch or in the pinned Git tree; it supplies requirements, not baseline implementation evidence. The existing wider audits are provenance, not repeated assignments.

Production source excerpts with pinned line numbers are in [pinned-source-excerpts.txt](thumbnail-baseline-evidence/pinned-source-excerpts.txt). No external research, user footage, model download, package installation, benchmark, or branch/worktree operation was needed. The supervisor authorized lightweight one-off fixtures while Task111 validation was in progress, before its timed comparisons; the route probe completed in approximately 0.55 seconds of shell wall time. This is an execution observation, **not a latency benchmark**. No repeated timed workload was run.

## Actual pinned read paths

| Caller | Pinned lines in `openscrub_web.py` | Behavior / ownership |
|---|---:|---|
| `_load_job_report` | 1103–1105 | Opens `job['dir']/report.json`, calls `json.load`, returns a fresh mutable tree on every call. No cache, lock, revision, or source check. |
| Scan `_pregen` | 686–750 | Loads one report, enumerates rows, skips every existing `thumb2_<index>.jpg`, sorts reference times, opens one decoder on `jb['video']`, crops with report geometry/offsets, writes JPEGs directly. A daemon thread; no lifecycle or publication generation check. |
| Scan normalized-source selection | 752–760 | Separately reads report provenance and changes `job['video']` after starting `_pregen`. The source-selection race identified by N07 remains a source-backed possibility; this probe did not schedule/reproduce that worker race. |
| `job_detections` GET | 1132–1148 | Read-only report projection: numeric row indices, category/text, timing, decisions, grouping/confidence, fps/duration. No report/source revision returned. |
| `job_detframe` | 1152–1170 | Parses report, chooses `last_seen` clamped to the span, applies `cum` offset, uses actual `_frame_at`, draws box on the full source frame, encodes JPEG. |
| `job_boxes_at` | 1174–1197 | Parses report; projects active boxes plus offset at requested time. Read-only. |
| `job_thumb` | 1201–1248 | **Checks JPEG existence before reading report**. Cold path parses report, tries sighting/midpoint/start+0.2 reference times until sufficiently nonblank, uses `cbox`, fps/cum and source frames, draws red outline, writes JPEG. Warm path goes straight to `send_file`. |
| `_frame_at` | 1108–1115 | Actual `cv2.VideoCapture(job['video'])`, frame-index seek using report fps, read, release. No report parsing itself. |
| `job_frame_at` | 1252–1274 | No report read. Timestamp seeks/fallbacks on `job['video']` or selected `job['output']`; returns encoded JPEG. Different tolerant preview contract from report-indexed `_frame_at`. |
| `job_video_stream` / mediainfo / preview | 1278–1287 / 1119–1129 / 1075–1082 | Source stream, file properties, or saved callback preview; they are not report snapshot consumers. |
| Saved report download | 1717–1721 | `send_file(report.json)`; no parsed-tree reuse. |

The two read-only consumers inside `_run_job(scan)` can share valid snapshots only after lifecycle/source integration is sound. The mutating callers of `_load_job_report` are `job_save_edits` (1295) and tracked-row publication (1394). They must retain fresh transaction documents; replacing `_load_job_report` globally with a shared mutable cache would silently change their ownership contract. Engine render loading also belongs to writer/transaction design, not automatic read-cache conversion.

## Mutation and derived identity inventory

The thumbnail depends on row identity/order, `cbox`, `t_start`, `t_end`, `last_seen`, report fps/cum, and the actual decoded source including normalization/tone mapping. The JPEG also depends on crop padding/outline/encoding rules; a future format version should change its derived identity. `aoff` and `poly` are not used by this pinned crop path. Text, confidence, grouping, enabled state and audio do not change its pixels by themselves, although broad report-revision invalidation may deliberately invalidate them too.

| Mutation | Actual pinned path | Required cache consideration |
|---|---|---|
| Initial scan / rescan | `_run_job` calls `openscrub.write_report` (683); retry (1028–1057) retains source/options and enqueues another scan | Replaced geometry, timing, render state, row count/order and source can all change at reused indices. Existing thumbnails are not purged. |
| Geometry/time/manual/decision/audio edit | POST detections (1290–1334 and following): fresh load, in-place changes to its private document, `json.dump` to the same report path | Box overrides move the crop. Time overrides alter span and clamp `last_seen`. Manual boxes append content-coordinate rows using report offsets. Decision/audio-only changes need snapshot invalidation, even when JPEG pixels are unchanged. No JPEG invalidation exists. |
| Tracked rows | Background tracker (1387–1427): samples source, later loads report, appends new rows, direct `json.dump` | A pending tracker can outlive source/report changes. Appends require new listing/snapshot revision; no shared cached mutable document. P06B must coordinate latest-state publication and source/lifecycle validation. |
| Render | `run_pipeline` → `run_render` → engine `write_report` (8499); web loads report after pipeline (775) | Baseline `load_report` drops disabled rows before render; rewrite can change indices (N06). Even absent geometric changes, same row number can name a different detection. P06D changes this behavior later; do not assume it here. |
| Engine source normalization | `normalize_vfr` assigns `args.original_video` / `args.video` (6581–6583); HDR tonemapping similarly (6666–6668); report provenance records normalized input | Scan options can affect normalized source/timeline/geometry. Source identity is actual `job['video']` plus file identity, not only provenance pathname or original upload hash. |
| Job registration/source selection | Create job server/upload path (918 etc.); post-scan normalized switch (756); restart recovery selects provenance input (3788 etc.) | A source switch may leave report bytes unchanged. Job incarnation/lifecycle generation must prevent cached state from a former job or session attaching to a new one. |
| Job options | Creation persists options; `build_args` (430 onward) consumes source, scan/detection options, windows/zones/model selection and render settings; retry reuses options | No ordinary existing-job options update endpoint was found in this baseline. Rescan is the publication boundary for new scan geometry. Invalidation must follow actual report/source changes, not merely a POST-options assumption. |
| External/same-path replacement | Ordinary filesystem/CLI publication can replace a report or source | A writer-notification-only solution misses these unless explicitly unsupported. Stat/file identity must include device/inode, size and high-resolution times, checked around reads/fills. Size alone and size+mtime alone failed the constructed report case. |
| Delete/retention/cancel/restart/vault | `job_delete` removes tree then registry entry or marks pending deletion; retention/startup reap trees; cancel changes event/generation/phase; vault encrypts files, unlock decrypts/rehydrates | Evict retained report data and invalidate pending/derived publications on lifecycle transition. Merely deleting dictionary entries after encryption is insufficient: existing readers/builders can still hold plaintext or recreate it. |

Current `_vault_lock_now` (3240) encrypts under `VAULT_LOCK` then forgets the key. The request guard checks locked state only at request entry. Neither snapshots nor thumbnail fills have a read lifetime coordinated with that lock. The scan daemon has no later check that `JOBS[jid]` is still the same live job. These are integration requirements, not newly reproduced lifecycle failures or a new broad security audit.

## Browser and HTTP identity

Review HTML uses `api/jobs/${CUR}/thumb/${x.i}` for ordinary and zone-dropped cards (2737/2777). Lightbox uses `/detframe/${i}` (2649). Editor and compare use `/frame_at?t=...` with optional `&src=output` (2492/2705–2706). None carries a report/source revision. `thumbRetry` (2808–2814) adds a timestamp `?r=` only after load errors, up to three retries; it does not refresh a successful stale image.

Pinned thumbnail responses are `image/jpeg`, **`Cache-Control: public, max-age=3600`**, with Expires, Last-Modified and a Werkzeug file ETag. A conditional request using the old JPEG ETag returns **304**, without parsing the report. After the geometry POST the same URL, bytes and JPEG ETag remained valid to HTTP caches, although `/boxes_at` returned the new geometry. JSON responses use `no-store`; dynamically encoded detframe/frame_at JPEGs in this probe had no explicit Cache-Control, ETag, or Last-Modified. HTML alone gets the stronger no-store/no-cache policy. Deleting/rebuilding a server JPEG by itself does not force a browser to ask for that URL again during its one-hour freshness window.

## Actual-production-route observations

[probe.py](thumbnail-baseline-evidence/probe.py) imports the **complete exported Flask application**, configures a fresh synthetic `JOBS_DIR` using the existing `baseline_isolation` harness (its ROOT is redirected to this task's `/tmp` root), and preserves its model-fetch blocking behavior. The fixture is four 320×144 MJPEG frames at 4 fps, with visibly different colored thirds and four real `Detection` rows. Initial publication uses actual pinned `openscrub.write_report`; geometry modification uses actual POST detections; all crop/frame reads and HTTP responses use production routes. Only counters wrap `builtins.open`, `json.load`, and the real `_frame_at`. No miniature route, AST-extracted application, substituted parser, fake frame reader, or proposed cache was used.

The later source-switch case directly changes the synthetic job's `video` field, exactly the field consumed by production routes and assigned by the normalized-source branch. It does not run normalization or claim to reproduce `_pregen` scheduling. The atomic replacement case uses task-local `os.replace`, deliberately exercising a future publisher/external-replacement boundary absent from baseline `write_report`.

| Case | HTTP results | Report parses / frame-helper calls | Observable output |
|---|---|---:|---|
| One cold thumbnail | 200 | 1 / 1 | 80×80 blue crop; center BGR `[240.2,29.8,30.2]`. |
| Three warm requests | 200 each | **0 / 0** total | Three JPEG opens; identical bytes. |
| Warm conditional GET | **304** | 0 / 0 | Existing file ETag accepted; body absent. |
| Four simultaneous cold indices | 200 each | **4 / 4** total | Four independent fresh report trees. Barrier synchronized request starts; separate indices avoid testing concurrent JPEG overwrites. |
| Four simultaneous metadata requests | 200 each | **4 / 0** total | Two detections and two boxes consumers each parse. |
| POST row-0 box from left to right; GET boxes, thumbnail and detframe | 200 all | 3 / 1 for combined case | Boxes correctly `[208,48,240,80]`, full frame has new outline; warm thumbnail remains old blue. After explicit fixture JPEG removal, actual route returns yellow `[37.7,241.7,242.6]`. |
| Same-size atomic report replacement, restored mtime | 200 boxes + thumbnail | 1 / 0 | Boxes become `[108,48,140,80]`; JPEG remains yellow. After fixture JPEG removal the route returns green `[31.9,240.7,32.3]`. |
| Normalized-source field switch | 200 frame + thumbnail | 0 / 0 | Full frame changes to alternate palette; thumbnail remains green. Forced-cold route returns magenta `[239.85,32.15,239.0]`. |
| Atomic source replacement at same path | 200 frame + thumbnail | 0 / 0 | Current full frame returns original palette; JPEG remains magenta. Forced-cold returns original green. |
| Corrupt report with existing JPEG | 200 thumbnail | 0 / 0 | Warm JPEG still served. This illustrates the bypass; no claim about an untested cold corrupt-report response. |

Combined geometry counts include POST, boxes and detframe; the thumbnail itself parses zero reports. `frame_at` opens/decodes directly and is not counted as `_frame_at`; zero helper calls in source-switch cases does **not** mean zero decoding.

The atomic report case held size **1878 bytes** and mtime **1794870108900491485 ns** constant while inode changed **95690 → 95702** and content SHA-256 changed `2d15bc6d…` → `08a7cd5a…`. Full identities (path, dev/inode, size, mtime/ctime, SHA-256), exact request/status/headers/bodies, counters, output SHA-256 and center pixels are retained per case in [results.json](thumbnail-baseline-evidence/results.json). A compact JPEG table is [thumbnail-observations.csv](thumbnail-baseline-evidence/thumbnail-observations.csv). Synthetic output images remain under `/tmp/openscrub-thumbnail-baseline-20261117/images/`; paths are recorded in JSON. SHA values prove equality/difference, while the visibly blue/yellow/green/magenta pixels establish that these are meaningful stale crops rather than renamed files.

## Smallest reviewable split

**P08A: demonstrated thumbnail invalidation correctness, without report snapshot retention.** Give disk thumbnails a report/source/job-generation identity and make clients request the corresponding revision. A coarse report revision that invalidates decision/audio-only changes is an acceptable first correctness tradeoff; per-row geometry signatures are a later optimization. Keep warm hits free of JSON parsing, using small current identity checks or a publication generation plus verified filesystem identity. Include report/source file replacement and source-path switches. Honor/reject an obsolete requested revision instead of serving new pixels under an old immutable identity. Choose a compatible policy for unversioned URLs (revalidation/no-store) so a successful old URL does not remain fresh for an hour. Old thumbnail files must not accumulate plaintext history.

Select normalized source **before** starting pre-generation, and share the same source/geometry identity with demand generation. Build into a task-owned staging file, then under the lifecycle/publication coordination validate report+source+job generation again before replacing the current derived artifact. Discard obsolete work; no post-delete/post-lock publication. A generation mismatch needs bounded failure/retry and a client metadata refresh, not endless decoding. Merely unlinking a JPEG on POST is insufficient: it misses browsers, source changes, external atomic replacements and already-running fills.

P08A can target baseline independently only if it supplies and tests the necessary publication/lifecycle boundary itself. The smaller implementation route is likely an explicit dependency on the adopted P06A publisher and P06B read/write lifecycle interface. Do not quietly depend on the entire integration branch. Disk identity and lifecycle checks still matter when using publisher notifications.

**P08B: bounded read-only snapshot reuse.** Limit initial users to measured cold thumbnail, detections and boxes consumers; consider detframe/pregen only after the same contract is established. Define `get_snapshot(job_id, report_path, source_identity)` with report revision and in-process single-flight parsing per identity. Check actual opened report identity and source/job generation before/after parsing/admission; reject stale in-flight fills. Mutable edit/tracking/render transactions obtain a fresh document through the transaction owner and never mutate/share the retained read tree. Explicit immutable nested containers are stronger than a caller convention; if immutability changes route assumptions, test those projections. A parse failure must surface correctly; do not silently return an older revision or replace a last valid entry with a poisoned one. Oversized documents remain correct without retention; coalescing them transiently still requires bounded in-flight memory/lifetime.

Cold parse counts demonstrate repeated work, **not sufficient performance benefit** for a cache on large videos. Before implementation/merging, measure representative synthetic report sizes and cold concurrent consumers; compare CPU/latency and total RSS in a separate coordinated run. P08A correctness is independently justified by the pixels. P08B remains conditional on a meaningful measured benefit.

## What a 128 MiB budget can honestly mean

Raw JSON length is not retained Python memory: dict/list tables, numbers, strings, duplicate/shared keys, immutable wrappers and cache metadata matter. A one-time identity-deduplicated `sys.getsizeof` traversal of the final retained graph at admission can account for ordinary JSON builtins and owned wrappers in this CPython environment. Cache the resulting charge; eviction updates totals in constant time. There is no need to deep-walk on each hit. If size is known only after an O(n) admission walk, that admission cost belongs in cold-path measurements. Accurate exact size cannot be inferred universally from encoded byte length with a fixed multiplier.

Per-entry traversal with a visited-object set avoids double-counting repeated references within one document. Shared objects across entries make the sum conservative, not an exact globally unique total; exact incremental cross-entry accounting needs reference bookkeeping and more complexity. State whether 128 MiB is a conservative owned-object admission budget and include keys/revisions/entry/container overhead. Freeze/copy first and count the actually retained representation, not its discarded mutable predecessor. Reject/stop counting oversized entries early if safe, but do not disguise an estimate as exact accounting.

The limit is **not a 128 MiB process-RSS ceiling**. Parsing buffers, transient mutable/frozen copies, concurrent parses, response projections, active reader references, decoder buffers, allocator arenas and other application state are outside an idle retained-entry budget. An evicted entry can remain alive in an active request. Separately bound concurrent fills and drain/cancel readers at lifecycle boundaries; track admission/eviction accounting independently from process RSS. Removing Python references does not prove secure heap erasure or immediate RSS shrinkage. No memory measurement was performed here.

## P06 integration and tests still required

P06A's existing chain tip **`66787aa`** includes atomic report publication from its parent **`c7cf1f0`** (`openscrub_internal.reports.atomic_report`); `66787aa` itself fixes vanished report-stage handling during vault cleanup. Neither exists on this pinned baseline. Its atomic replacement makes inode/publication changes a real cache integration point; staged files must be excluded/cleaned consistently during encryption and deletion. Do not hook only engine publication while web writers still bypass the transaction boundary.

P06D **`7063082`** preserves complete review rows/metadata through rendering and decodes the enabled render subset separately. It also is absent from baseline. It reduces the baseline index-projection problem but does not justify treating a row number as a permanent source/geometry identity.

Forthcoming **P06B** lifecycle/transactions must establish coherent read lifetimes, publication notification/generation order, fresh mutable transaction documents, latest-state tracked append, lock/delete/source invalidation and pending-fill cancellation. Notifications must occur in coordination with publication, and a failed publication must not advertise a new committed revision. Invalidation must prevent a fill admitted before eviction from repopulating after it. Scope is **in-process only**; multiple workers or external writers need verified file identity or a separately specified cross-process protocol. No training state, Findings cache/workbench, SQLite crop index, persistent row index, journal, or diagnostics database is required.

Future tests must retain the plan's named warm-no-parse, parallel-single-flight, same-size-replace, writer-cannot-mutate and vault-lock-evicts cases. Add actual-route pixel assertions for box/time/cum/fps and source changes, row reordering/render round trips, both demand/pregen paths, JSON failure/recovery, over-budget bypass/eviction, and entry-size accounting. Test HTTP cache behavior and client revision refresh, not just server filenames. S06 should interleave active reads/fills with successful/failed publication, lock/unlock/autolock, delete/pending deletion/retention, source switch, cancel/rescan and restart; assert no stale publication, bounded retries, preservation of legitimate decisions, and draining of plaintext readers. Pending builder ownership checks must include job incarnation and actual source/report revision. Windows file-handle behavior and network-filesystem identity limits need separate verification; this baseline used the local Linux environment only.

S06 was inventoried here, **not executed as a full lifecycle race suite**. No cache was introduced, and no new lifetime was claimed safe. Large-video latency/RSS, actual browser cache execution, same-index simultaneous JPEG writes, decoder accuracy across VFR/HDR, multi-process behavior and a deterministic `_pregen` normalization race remain outside this small baseline.

## Reproduction and verification

Use only task-owned temporary artifacts; the export command is read-only against Git objects:

```bash
mkdir -p /tmp/openscrub-thumbnail-baseline-20261117/export
git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 | tar -x -C /tmp/openscrub-thumbnail-baseline-20261117/export
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/thumbnail-baseline-evidence/probe.py > .superpowers/sdd/README/thumbnail-baseline-evidence/results.json
/usr/bin/python3 .superpowers/sdd/README/thumbnail-baseline-evidence/verify_results.py
```

The probe removes only its own prior `synthetic-data/route-probe` directory before constructing a fresh fixture. The supplied environment uses existing OpenCV **4.14.0** and disables model autofetch. `verify_results.py` checks counts, response codes, same-size/same-mtime replacement identity and stale/current JPEG hash relationships without codec work. [verification.json](thumbnail-baseline-evidence/verification.json) reports **PASS, 14 recorded cases**, with recorded-results SHA-256 `b004cd653940fb6a828738baaa07c384cb5cafd4ff666f05aa329a6e1edf4f4b`. All broader product checks remain requirements for a future implementation.
