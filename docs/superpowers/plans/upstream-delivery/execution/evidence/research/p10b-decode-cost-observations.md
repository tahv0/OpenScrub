# Qualified observations of cold frame-decoder costs

**Stage:** P10B E1, observed on 2026-11-19 at `194864493962d9951cab482bde507d489f07c998`. Independent review and two scoped corrections approved the historical record with explicit limits. Source was unchanged. The original strict recovery, pre-timing native-identity, whole-tree memory and overhead-free timing controls remain unmet; this is not acceptance of the full decoder implementation gate.

## What, why and when

Measure actual frame reads and resource ownership before selecting a mechanism for long-video work. Use the accepted exact-source helper and ordinary cold-thumbnail paths, preserving upstream defaults and source/report publication fences. The independent editor UI and application assembly were not composed or tested here.

The useful observations are the size of per-capture memory, time spent in the native seek path, correct frame/crop results, and saves and invalidation during decoding. They support a further controlled comparison; they do not select a worker count, deadline or application cancellation design.

## Inputs and method

Five low-complexity H.264 fixtures were generated with visible frame ordinals: CFR 24 fps, two B frames, scene cuts disabled, yuv420p, time base 1/12288, zero origin, one video stream and no audio.

| Case | Dimensions | Frames / GOP | Encoded bytes |
| --- | ---: | ---: | ---: |
| Short GOP | 1280×720 | 480 / 12 | 460,350 |
| Long GOP | 1280×720 | 480 / 240 | 213,444 |
| 4K | 3840×2160 | 480 / 240 | 576,140 |
| Longer duration | 1280×720 | 1,440 / 240 | 639,470 |
| Bounded 2 Mbit/s CBR | 1280×720 | 480 / 240 | 4,957,125 |

These are 20-second and 60-second synthetic clips, not large production footage. All 6,846,529 fixture bytes, complete frame counts, keyframe spacing, ordinal PTS and full decodes were checked. Independent sequential OpenCV references used no seek; all 35 retained number crops were independently read in order. Production full-frame and odd-coordinate crop hashes matched those references.

The host was Linux/WSL2 on a Ryzen 7 5800X3D with 16 logical CPUs, Python 3.12.16, OpenCV 4.14.0, NumPy 2.5.5, FFmpeg/FFprobe 8.0.1 and production Cheroot 11.1.2 with 64 workers. New captures and derived entries were cold; OS caches were not dropped. Each fixture/position cell used one warmup and five measured samples at the first, middle and final frame.

## Helper and HTTP observations

The production helper series times only the source-owned read, excluding snapshot preparation, JPEG encoding and reference validation. It ran later, with a scoped harness watchdog and a pre-helper native-identity comparison.

| Helper median, milliseconds | First frame | Middle frame | Final frame |
| --- | ---: | ---: | ---: |
| 720p short GOP | 13.45 | 17.73 | 15.94 |
| 720p long GOP | 14.81 | 50.34 | 49.74 |
| 4K long GOP | 101.04 | 438.15 | 409.86 |
| 720p longer duration | 13.88 | 49.72 | 48.61 |
| 720p CBR | 15.11 | 61.15 | 66.35 |

All four scalar series have 90 observations: direct capture, production helper, exact HTTP and cold-crop HTTP. All 90 exact images and 90 cold crops matched their references; every sampled crop succeeded on its first candidate. Direct native spans were timed separately and are not added across different observations to predict HTTP latency.

Save-free four-client 4K batch medians were 1.8697 seconds for exact images and 1.9656 for crops, from one warmup and three measured batches per shape. These include barrier entry, collection and client validation. Scalar crops had in-memory counters; parallel crops also performed synchronous stage-log I/O. Individual HTTP durations ended at complete body read. The exact-client collection tail was 1.21–2.30 ms after the latest recorded client completion, following connection close. Overhead-free request latency and pure last-body makespan were not separately measured. All numerical values and ranges remain retained with these method labels.

## Memory, saves and lifecycle

Fresh-process observations measured process-wide server RSS. The collector followed only the process leader's child list, so request-thread descendants and whole-tree peaks are not established. Sampling requested 100 ms and could miss short peaks.

| Shape | Ready RSS MiB | Sampled request RSS peak MiB | Request / all snapshots |
| --- | ---: | ---: | ---: |
| One 4K exact read | 104.1 | 553.1 | 7 / 13 |
| Two exact requests | 104.1 | 1,046.2 | 11 / 17 |
| Four exact requests | 103.0 | 1,882.8 | 20 / 26 |
| Two crop requests | 102.9 | 1,010.0 | 10 / 16 |
| Four crop requests | 103.1 | 1,910.2 | 19 / 25 |

Lifetime high-water values were recorded separately. Available memory exceeded the declared pre-workload thresholds; the two discovered cgroup ancestors reported no finite limit. No peaks from different times or processes were added.

All nine complete saved reports were independently reconstructed and their byte hashes matched, including untouched source/geometry fields and the intended enabled/audio changes. Same-job publication caused pending responses to return 409; other-job saves also persisted. Separate instrumentation observed native-call overlap, reaching two exact and three crop captures before invalidation in the four-client controls. Four scheduled HTTP requests alone do not prove four simultaneous native decodes.

A real client closed during native open; work continued and the first observed owner drain was about 602 ms later. DELETE during decoding returned 409 and succeeded after drain. Source replacement during native open caused a 409 and drained ownership. The later short synthetic watchdog test reaped its child and grandchild; it proves harness recovery, not application-level native cancellation.

## Provenance, recovery and remaining gates

Original direct reads had no external deadline. Coordinated HTTP runs had 60-second client/collection timeouts but a 1,200-second outer wait; a blocked native call was not protected by a strict 60-second process-tree deadline. The later helper/watchdog has separate attribution. No real decoder hang occurred.

Original OpenCV/NumPy binaries were not freshly hashed before the initial timing series. Later hashes matched the previously protected environment and were checked before and after the helper run, which corroborates continuity without proving the earlier in-run bytes. Command and digest observations were later transcribed from the session; they are not original persisted pre-run receipts. Historical script names are mapped to retained snapshots.

An extra exact-float assertion stopped the scalar controller after 54 valid pairs. Those samples were kept; only the remaining 36 pairs ran after using production's precision bound. The stopped worker's five job trees were inventoried and removed after process absence was established, with master hashes checked. That was filesystem recovery, not graceful DELETE. Other successful workers drained, deleted and joined. Fixture and 125 JPEG-stage totals are recorded; cumulative non-media write accounting remains incomplete. Thumbnail-version query values were not retained for the crop parallel, memory and save observations.

The corrected record preserves all numerical tables. Its manifest-driven checkpoint validator passed after later audit files were added. Source, refs, stash, immutable fixtures and identified process cleanup were checked at that checkpoint; later authorized documentation ref advances are separate.

## Next delivery

E2 will compare the original per-capture constructor with requested FFmpeg thread counts 1, 2 and 4, using fresh pre-run receipts, tested deadline supervision, no timed log I/O and an all-thread child sampler. OpenCV exposes an open-time thread limit, which makes this a testable hypothesis about the RAM cost; causation and benefit have not been established. [OpenCV capture properties](https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html), [constructor parameters](https://docs.opencv.org/4.13.0/d8/dfe/classcv_1_1VideoCapture.html).

A useful result needs preserved pixels, source ownership and a documented latency/memory tradeoff across the controlled cases. Any resulting code change needs its own narrow PR, supported-runtime checks and compatible fallback. Windows, GPU/inference, HDR, other codecs, raw VFR and hour-long production 4K remain separate validation.
