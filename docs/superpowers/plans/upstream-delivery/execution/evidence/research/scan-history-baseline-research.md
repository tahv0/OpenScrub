# S05 / P11 residual scan-history baseline — 2026-11-17

The `a11a3926` preview-cache optimization remains **removed-system-only**. Actual Austin callbacks did not show growing-history work in this bounded probe. Three separate history-dependent operations were demonstrated in **post-scan final aggregation**, so the broader P11 investigation should remain open with a narrower scope. These are work-count findings, with no throughput or speedup claim and no product changes.

## Source and boundaries

All executed application code came from a full export of `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin plus the reviewed test-only prerequisite), tree `795af785b672d397d2e287b5b963c10dcc4dbdf8`. Archive SHA-256: `c44d383d99f4c3f9857331dfd8dda23ee5080abb6a57b5809dba9a586b2de17f`. All 113 exported files were checked against their Git blob identities after the experiment. Nothing was executed from or changed in an active native implementation worktree. The source export and synthetic work were under `/tmp/openscrub-scan-history-20261117`.

Read S05 and P11 in `docs/superpowers/plans/upstream-delivery/02-large-video-performance.md` as requirements, not evidence of a defect. P11A at `f19be5fe3b9176e568ea7bf761493bd267fee95e` was excluded: no dense-smoothing tests, timings, or implementation were repeated.

The exact donor `a11a39263130741bd9ec6e18b1de17afa3a2019b` changes only `finding_previews.py`: SQLite preview totals/schema preparation, seen-group suppression and capture bookkeeping. The pinned export has neither that file nor a Python reference to it. Austin's live preview is the current annotated frame, not a persistent Findings crop database. Preserve this historical optimization as accounted for; importing its cache would add a removed subsystem.

## Owners actually checked

- **Inference and current scan work:** `openscrub.py:7860–7908`, `8015–8071`. OCR results pass through actual normalization, `group_lines`, `detect_phi`, forward memory recall/add, raw-history append and current-frame drawing. Raw detections, OCR scans and motion history are appended during scanning; their growing storage does not itself imply repeated traversal.
- **Forward PhiMemory:** `openscrub.py:754–862` already uses exact lookup and length-indexed/batched fuzzy lookup. Constant call counts here are not a claim that arbitrarily large eligible fuzzy buckets are constant cost.
- **Callbacks/publication:** `WebCallbacks` at `openscrub_web.py:364–427` appends one log message, updates scalar ETA/progress, and throttles resize/JPEG publication to the current `preview.jpg`. It does not walk accumulated detections or log history. `run_scan` draws the current `found` and current dense boxes, not all `raw` entries.
- **Final aggregation:** `run_scan` calls `reverse_pass` after decoder release (`openscrub.py:8122`), then `merge_detections` (`8280`); the inspected functions are at `7096–7134` and `2915–3062`.
- **Report and thumbnail publication:** `write_report` (`6287–6334`) serializes motion arrays and detections once per invocation. The web scan owner calls it once after `run_scan` returns (`openscrub_web.py:682–685`). Its subsequent thumbnail pre-generation reads the final report, sorts outstanding thumbnails and traverses them once (`687–749`); that is post-scan work, not per-frame preview caching. This worker/pre-generation path was source-inspected, not executed by the probe.

## Bounded actual-module probe

[Evidence and executable recipe](scan-history-baseline-evidence/) include `probe.py`, `commands.sh`, raw `results.json`, `run.log`, source identity/excerpts, donor patch and cleanup record. The harness imports the complete unmodified pinned `openscrub` and `openscrub_web` modules. It executes actual `run_scan`, actual `WebCallbacks`, actual reverse/merge algorithms and actual `write_report`. A trace counts specified source-line executions and function calls; no target algorithm or callback is replaced with a miniature implementation.

Six cases use 10/50/100 OCR scans (20/100/200 decoded frames), 160×96 at 6 fps, lossless FFV1 in AVI. Each frame is the same seeded (`1411`) uint8 image. Only computational OCR inference is stubbed: one deterministic synthetic email plus `pending` and `ready`, fixed boxes/confidence `.99`. The repeated scenario returns the same email; the unique scenario uses seed `83011 + scan_index` to produce a different 24-letter email local part each scan. Thus the unique scenario deliberately controls growing **record history**, not realistic OCR of the fixed pixels. Every case has nonzero primary detections.

Categories are `email`; sample interval `1/3` second; adaptive cadence, scroll tracking, OCR upscaling, VFR normalization and backtracking are disabled to isolate the stated boundaries. Face/plate/person/audio models are not loaded. A controlled clock advances `.5s` per preview publication so writes are counted deterministically. No timing samples were taken. This is controlled pipeline-overhead evidence, not real model/OCR inference throughput or a default-settings performance assessment.

At scans 1/50/100 in the unique 100-scan case, accumulated raw/history/memory sizes are 1/50/100, while **each current scan** calls OCR once, `detect_phi` once, forward recall twice, memory add once and actual preview publication once. Neither reverse pass nor merge/report is called in those scan intervals. `cum` sizes at the callback are 1/99/199 because scans occur every two frames. All JPEGs published within each case are byte-identical.

Direct actual `WebCallbacks` calls with 0/1,000/10,000 pre-existing log rows append one message, call progress twice and publish one frame each; they produce the same JPEG, progress `.09` and ETA `32`. This is source-backed absence of a history walk for the tested callback inputs, not a universal latency measurement.

| Scenario | Scans / remembered | Reverse memory-key visits | Merge prior-candidate visits | Tail OCR-history timestamp visits |
|---|---:|---:|---:|---:|
| repeated | 10 / 1 | 20 | 19 | 10 |
| repeated | 50 / 1 | 100 | 99 | 50 |
| repeated | 100 / 1 | 200 | 199 | 100 |
| unique | 10 / 10 | 155 | 55 | 64 |
| unique | 50 / 50 | 3,775 | 1,275 | 1,324 |
| unique | 100 / 100 | 15,050 | 5,050 | 5,149 |

The markers are respectively `openscrub.py:7111`, `2978`, `3033`; contradiction-history visits (`2941`) were zero in these fixtures. Each run calls reverse and merge once. Reverse recall adds duplicate ordinary email records, giving `2N` final raw hits; unique email cases still produce exactly `N` merged regions, repeated cases one region. `ready` is filtered by the existing stop-word rules; the remaining no-match benign token contributes `N²` reverse candidate visits, while email matches contribute `N(N+1)/2`. Merge checks contribute `N(N+1)/2` including duplicate records. Tail walks contribute `N(N+1)/2 + N − 1` in the unique scenario.

The actual report uses one `json.dump` in every case, with 1/1/1 `asdict` calls for repeated cases and 10/50/100 for unique cases. At 100 unique scans it is 50,361 bytes. Every serialized detection field matches the returned state after JSON tuple/list normalization; rounded `cum` and `bands` match too. This verifies the exercised serialization boundary, not equivalence of a proposed optimization: no alternate implementation was written or compared.

## Disposition and smallest independent fix contract

1. **Close the donor cache portion as removed-system-only.** Keep the donor/source proof in the preservation ledger. Do not add SQLite, a Findings library, a preview cache or an ETA-based speedup claim.
2. **Retain a focused final tail-history candidate first.** `merge_detections` restarts at scan zero for every merged text region even though early timestamps cannot support its tail. The smallest independent contract is to construct a timestamp index once for chronological scan input, begin each tail iteration strictly after the existing `last_seen + .01` boundary, and retain the existing ordered support walk and stopping rules. Avoid a full-history slice per region. Preserve duplicate-timestamp handling, confidence/box/fuzzy thresholds, `bridge_gap`, `last_seen`, all Detection fields and input-order semantics; unordered caller inputs need a semantics-preserving fallback. Contradiction-window indexing is a separate extension, unexercised here, rather than a required bundle. Add a deterministic operation-count regression and complete before/after record equality at this real boundary before claiming a fix.
3. **Record reverse-pass indexing separately.** Indexed forward recall does not fix `reverse_pass`'s all-memory loop. A future small reverse-only change must preserve lower lenient thresholds, numeric same-length/two-digit tolerance, name sighting gates, category/allowlist filtering and the first eligible insertion-order match. Reusing forward recall unchanged would alter behavior. These counts justify investigation, not a measured wall-time win.
4. **Record merge candidate selection separately.** Distinct text regions leave a growing `mergeable` list. Any future index must preserve reverse candidate order, overlapping-box/union behavior and visual long-gap verification. No arbitrary age cutoff is justified because long verified gaps intentionally remain mergeable. This is a larger semantics risk than skipping irrelevant tail timestamps.

## Environment, cleanup and limits

Reused read-only `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python`: Python 3.12.16, OpenCV 4.14.0, NumPy 2.5.5, RapidFuzz 3.14.6, Linux x86_64 WSL2; OpenCV threads fixed to one. No dependency/model/network downloads, full suite, build, user media or heavy/long/4K benchmark. The largest synthetic clip has 200 small frames and is 10,248,324 bytes. Runtime fixtures were removed after compact evidence was preserved; the full pinned source export and reproducer remain task-local. A preliminary lossy-MJPEG fixture failed identical-preview validation, so the final recipe uses lossless FFV1; a preliminary ambiguous source-line marker was narrowed to its actual owner before the successful results. Neither issue required application changes.

Not verified: real pretrained inference, same-length worst-case forward fuzzy buckets, large motion histories, dense modes/P11A, actual HTTP polling/browser rendering, thumbnail pre-generation lifecycle, cancellation behavior, default backtracking/tracking, audio, memory ceilings, multi-platform performance, or time saved by any candidate. The final source-owned post-processing loops above do not establish progressive per-frame slowdown. Privacy decisions, cancellation and upstream defaults remain unchanged because this task made no product changes.
