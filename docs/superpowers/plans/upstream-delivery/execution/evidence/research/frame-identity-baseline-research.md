# P10 / S04 source-frame baseline research

Research date: 2026-11-17. **A correctness prerequisite is demonstrated; an expensive-decode performance prerequisite is not measured.** Ordinary box-editor scrubbing can display pixels from a different source frame than the geometry calculation. A valid low-FPS slider endpoint also receives an unlabelled earlier fallback frame. The editor remains editable in both cases. No product, Git, dependency, user-data or environment configuration was changed; only requested SDD evidence and task-local `/tmp` artifacts were written.

## Provenance and scope

Requirements: [frame-identity-baseline-brief.md](frame-identity-baseline-brief.md), P10/S04 of `docs/superpowers/plans/upstream-delivery/02-large-video-performance.md`, and exact-source paragraphs of [core-history-audit.md](../../preservation/core-history-audit.md). All executed production imports came from the **complete** `git archive` export of `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, tree `795af785b672d397d2e287b5b963c10dcc4dbdf8`, at `/tmp/openscrub-frame-identity-baseline-20261117`. The active native source tree was not imported. Archive/source SHA-256 and import paths are in [source-provenance.json](frame-identity-baseline-evidence/source-provenance.json) and [results.json](frame-identity-baseline-evidence/results.json).

Existing isolated `env-opencv4.sh`: Python 3.12, OpenCV 4.14.0; extracted FFmpeg 8.0.1. Full `openscrub`/`openscrub_web` imports; task-local model/data directories; `OPENSCRUB_NO_AUTOFETCH=1` and `_fetch_model` replaced by a rejection function. Synthetic jobs and JSON reports only. No scan, render, model download, full suite/build, stress run or long/4K media. Production route functions were exercised through Flask's actual test client and Cheroot loopback HTTP, without extracting route bodies.

## Actual callers and policies

Locations below refer to the pinned export's `openscrub_web.py`.

| Producer/caller | Actual behavior | Baseline contract assessment |
|---|---|---|
| `_frame_at`, 1108 | New OpenCV capture of `job.video`; `POS_FRAMES=int(t*report_fps)`; one read; release; `None` on false read | Frame-index selection, no fallback or proof metadata. Tested short CFR reads match markers; do not generalize to every decoder/media. |
| `job_detframe`, 1152; browser `zoomDet`, 2640 | Clamp sighting time inside detection span; offset from `cum[min(int(t*fps),n-1)]`; decode with `_frame_at`; outline; JPEG quality 84. Review card click opens lightbox. | A sighting preview, not the ordinary editor's image loader; 404 on failed read. Upper offset clamp alone does not clamp the decoder request. |
| `job_thumb`, 1201; review card images, 2737/2777 | Existing `thumb2_i.jpg` fast path; otherwise try last-seen, midpoint, start+0.2 using `_frame_at`, with per-attempt offsets and content check; 24px padded crop; red outline; JPEG quality 80 | Intentionally tolerant representative preview. Different successful sighting is legitimate; it is not an exact editor sample. |
| `_run_job._pregen`, 692–752 | Independent capture, sorted references; short forward reads or indexed seek to clamped frame index, crop/content test, cached thumbnail | Does not call `_frame_at`. Source code inventory only; worker/pregeneration schedule not executed. |
| `job_frame_at`, 1252 | Input or optional output capture; timestamp seeks at `t`, `max(0,t-.34)`, `max(0,t-1)`, 0; stop at first successful read, or after attempted zero; release; JPEG quality 82 | Explicit tolerant walk-back, documented for end-of-file/compare recovery. No actual source/frame/time/fallback information in response. |
| `loadBoxEdit`, 2222; `beScrub`, 2481 | `mediainfo` supplies duration; slider max `max(.2,duration-.1).toFixed(1)`, step .1. Requests `frame_at?t=BE.t` and independently `boxes_at?t=BE.t&all=1`; boxes use floor-based report frame. Image load updates scale and paints. | Same tolerant endpoint is used for geometry editing. Neither UI nor response distinguishes fallback or rounded frame identity. |
| `bePlayStop`, 2329; `beHook`, 2561 | Pause/end re-enables pointers and calls `beScrub`; pointers during paused scrubbing can select/drag/add/track. Draft coordinates subtract `BE.ox/oy`; add records `tref=BE.t`. | Exact image/geometry/source binding is needed before editing. No load identity or fallback gate exists. Playback scheduling races were not injected here. |
| `loadCompare`/`cmpShow`, 2690–2706 | Slider max is report duration, step .2; original and redacted requests share time, redacted adds `src=output` | Tolerant fallback is intentional and should survive a P10 split, with actual-time/fallback labelling. Browser done/render entry was not exercised. |

`job_video_stream`, 1278, serves `job.video`, the same input path as `frame_at`. Normalization in `openscrub.normalize_vfr`, 6494, changes `args.video` to the CFR scan copy; `write_report`, 6287, stores it as provenance `input` and keeps `original_input`. `_run_job`, 753–760, adopts the normalized provenance path for `job.video` after scan. The synthetic normalized job was installed with precisely that path/provenance relationship. The normalizer itself ran; an end-to-end detector scan and the pregen/adoption race were not run or claimed correct.

## Media and independent frame evidence

All clips are H.264, 320×180, yuv420p, no audio. Diagonal target texture supports crop verification. Frame `i` has visible `FRAME ii`, a six-bit grayscale marker in six 12px blocks, and target `[50+2*i,70,90+2*i,110]`. Synthetic report content box is `[50,70,90,110]`; offsets follow actual target pixels. After VFR normalization, offsets follow original marker motion, not an invented constant displacement per normalized index.

| Fixture | FPS / time base | Frames / duration / bytes | GOP evidence |
|---|---|---|---|
| CFR24 | 24 / 1⁄12288 | 48 / 2s / 11,454 | Requested `-g 24`; I frames at indices 0,24 |
| CFR5 | 5 / 1⁄10240 | 10 / 2s / 6,349 | Requested `-g 5`; I frames at 0,5 |
| VFR input | nominal 25, average 13 / 1⁄12800 | 13 / 1s | PNG concat with durations .04,.12,.08,.04,.16,.04,.08,.12,.04,.08,.04,.12 plus terminal duplicate |
| Actual normalized copy | 13 / 1⁄13312 | 14 / 1.076923s / 5,577 | Production normalizer, explicit `encoder=x264`; one I frame at index 0 |

Independent reference evidence sequentially decodes every frame and records decoded pixel hashes plus FFprobe frame PTS. Full-frame route JPEG bytes are compared against independently encoded sequential references at the production quality. Matching bytes and machine markers establish returned pixels; capture seek setter success and position metadata are **not** identity evidence. Exact duplicate normalized frames can match multiple indices; recorded duplicate matches remain ambiguous. Thumbnails are checked against independently reconstructed source-coordinate crops, including production outline/JPEG encoding.

## Demonstrated natural correctness defects

Browser flow: loopback app → synthetic job link → visible **Preview video & edit boxes** button → fill/dispatch the ordinary range slider → inspect the image's real pixels → pointer-select and drag the existing box. No altered slider bounds, arbitrary out-of-range value, decoder injection, HTTP mutation or Save/render action was used. Local drag moved the content box by 5 source pixels to `[55,70,95,110]` in all three cases, confirming that editing remains enabled.

| Ordinary editor selection | Returned source pixels / PTS | Geometry assumption / source target | Observed consequence |
|---|---|---|---|
| CFR24, **0.2s** | Sequential frame **5**, marker 5, PTS **.208333** | `int(.2*24)=4`, PTS **.166667**; box `[58,70,98,110]` | Timestamp decoder rounding and report floor select different frames. Visible target is `[60,70,100,110]`. No fallback needed. |
| CFR5, **1.9s**, slider's valid maximum | First timestamp read at 1900ms naturally fails. Retry at 1560ms returns frame **8**, marker 8, PTS **1.6** | Frame **9**, PTS **1.8**; box `[68,70,108,110]` | **Unlabelled earlier fallback in a naturally reachable editing request**. Visible target is `[66,70,106,110]`; time label remains **1.9s**. |
| Normalized VFR, **0.5s** | Normalized frame **7**, original marker **6**, PTS **.538462** | Normalized frame **6**, marker **5**, PTS **.461538**; box `[60,70,100,110]` | The actual normalization path does not resolve timestamp-versus-index selection disagreement. Visible target is `[62,70,102,110]`. |

For 5fps, `duration-.1=1.9` lies beyond the last frame's start time 1.8 and the timestamp backend rounds toward unavailable frame 10. The fallback implementation then walks back by .34s. This is not evidence that every ordinary 10/24/30fps endpoint fails: CFR24 max 1.9 succeeds on frame 46, and CFR5 1.8 succeeds on frame 9.

Responses contain JPEG bytes with no source-frame/actual-time/fallback headers. The UI uses the requested time label and `boxes_at` offsets without checking which sample arrived. Screenshots and browser state are in [browser-results.json](frame-identity-baseline-evidence/browser-results.json), [CFR24](frame-identity-baseline-evidence/cfr24-editor.png), [CFR5](frame-identity-baseline-evidence/cfr5-editor.png), and [normalized](frame-identity-baseline-evidence/normalized-editor.png).

## Boundaries, intentional fallback and injected schedules

Direct duration requests were tested separately: CFR24 `t=2` returns frame40/PTS1.666667; CFR5 `t=2` returns frame8; normalized `t=14/13` returns normalized index10/marker9. These deliberately terminal API requests are **not by themselves evidence of a reachable editor defect**: the editor slider caps earlier. Compare's actual source caller permits report duration, so tolerant recovery is useful there. Its original/output source branches were both exercised by actual routes, using a separate synthetic output-path copy; no real rendered output or done-panel browser navigation is claimed.

Controlled `TraceCapture` delegates to the real OpenCV capture boundary and records requested setter/read outcomes. It never creates fake successful frames. At CFR24 `.9s`, injected first-read failure then real success yields frame13/PTS.541667 from retry `.56s`; this is fallback semantics, not natural corrupt-media evidence. Injecting every read failure returns 404. At `.9s`, the loop attempts .9,.56,0 then stops, so a fourth supplied failure flag is intentionally unused. All attempted captures release normally.

For detection0 at `.2s`, natural `detframe` returns marker4, and natural thumbnail bytes match the source-frame4 crop. Inject first false read: `detframe` returns404; thumbnail tries midpoint1s and bytes match source-frame24 crop with that frame's correct offset. This is intentional thumbnail representative fallback, distinct from the editor's unlabelled time mismatch. Natural mid-file failed reads, native exceptions, corrupt/truncated media, native hangs and source replacement were not induced.

## Smallest P10 implementation split recommended

1. **Correctness prerequisite:** use one shared source/timeline resolver for image selection and `boxes_at`. Separate exact geometry requests from tolerant compare/sighting previews. Exact samples need verified source identity, requested time, actual source frame/PTS, dimensions and an exactness result. Reject unverified success; define a consistent boundary policy and have the UI resolve the final valid editable sample explicitly. A successful `cap.set` or frame-position reading is insufficient. The ordinary editor must bind image and geometry to that same sample before enabling pointer edits; requested-time labels alone are insufficient.
2. **Preserve preview tolerance:** keep compare's intentional walk-back and thumbnails' representative search; return actual sample/fallback information and label it where the UI displays a time. Do not convert representative cache keys into source-frame identities. Make source/output choice explicit.
3. **Resource work remains separately justified:** measure the smallest relevant actual cold-seek workload before choosing a new worker. Reuse interruptible existing subprocess/FFmpeg helpers if appropriate. A 10s normal budget, explicit ≤60s retry and two shared workers remain **planned parameters**, not measured or installed settings. No evidence here establishes an expensive-seek bottleneck, memory/concurrency bound or an optimal worker count. Do not copy donor Findings/confirmation-repair protocols.

Tests for the prerequisite should include the three ordinary UI cases above, exact source-byte/frame marker matching near start/middle/end, normalized resampling/duplicate frames, consistent final-frame range resolution, finite/nonnegative times, missing/changed source identity and out-of-order image/box completion with pointer edits blocked. Crop tests should compare an odd-coordinate source crop against the same verified full-frame sample, preserve source dimensions/offset round trips and distinguish crop-local from source coordinates. Keep P16 masks, chroma coverage and responsive resize work separate.

Resource tests should cover a real blocked decoder boundary, deadline/cancel → terminate/kill → wait/reap, slot release and no late publication; a stopped HTTP waiter with a live native decoding thread does not pass. Add source replacement during decode (discard pending result), obsolete queue requests, concurrent save responsiveness, error/exception cleanup and Windows/Linux lifecycle checks. Successful/false-read release in this baseline is useful evidence but does not prove those timeout guarantees.

## Commands, verification and limitations

Runnable scripts and compact results live in [frame-identity-baseline-evidence](frame-identity-baseline-evidence/). Primary commands:

```sh
git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 --output=/tmp/openscrub-frame-identity-baseline-20261117.tar
mkdir -p /tmp/openscrub-frame-identity-baseline-20261117
tar -xf /tmp/openscrub-frame-identity-baseline-20261117.tar -C /tmp/openscrub-frame-identity-baseline-20261117
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/frame-identity-baseline-evidence/probe.py
python .superpowers/sdd/README/frame-identity-baseline-evidence/probe.py serve
# In another task-local process, with the existing extracted browser libraries:
export LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu
node .superpowers/sdd/README/frame-identity-baseline-evidence/browser.cjs
python3 .superpowers/sdd/README/frame-identity-baseline-evidence/verify.py
```

All generation commands are serialized in `results.json`. Final verifier: **24 route observations, 25 released captures, three ordinary browser states; source/media hashes match**. Playwright1.65.1 / Chromium159.0.8154.6, desktop1100×900. Browser plugin not available; existing isolated fallback explicitly permitted by the brief. Page identity/nonblank/overlay/interaction checks passed; no page errors or HTTP mutations. Three canvas-readback advisory warnings came from the inspection canvas, not app failures. No mobile or playback/async-delay schedule is claimed. Initial harness attempts required the existing browser library path and removal of compare navigation from a review-only synthetic job; neither was classified as a product defect.

Server PID485764 was stopped; session exited143; independent cleanup check confirms PID absent and port18571 refused connection. Chromium closes in `finally`. [cleanup.json](frame-identity-baseline-evidence/cleanup.json) records this. Synthetic files remain only for reproducibility.

Remaining S04/P10 gates: long-GOP/4K/high-bitrate opt-in measurements, source FPS/time-base variants and codec backends, genuine mid-file decoder failures, HDR/source-coordinate transforms, native hang/exception cleanup, source changes, overlapping saves and queue pressure, Windows/Linux supported lifecycle paths. The short software-H.264/Linux evidence establishes the concrete identity defects above and makes no universal latency or decoder-exactness claim.
