# Qualified decoder-thread comparison

**Stage:** P10B E2, observed on 2026-11-19 at source `194864493962d9951cab482bde507d489f07c998`. Independent review accepted the corrected comparison for this host and fixture set. No production source or default changed. Historical cumulative per-pool write accounting and a pre-workload control of the actual memory sampler remain unmet; later checks do not repair their chronology.

## What, why and when

Compare the original `cv2.VideoCapture(path)` constructor with explicit per-capture FFmpeg thread requests of 1, 2 and 4 before choosing a larger decoder mechanism. The [earlier E1 observations](p10b-decode-cost-observations.md) suggested investigating per-capture resource costs. This experiment measures a source-owned helper, not application-wide responsiveness or inference.

OpenCV documents the thread property as an FFmpeg open-time setting and exposes constructor parameter pairs. Existing project dependencies do not require a version with that capability; any product option needs a compatible fallback. [Capture properties](https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html), [constructor parameters](https://docs.opencv.org/4.13.0/d8/dfe/classcv_1_1VideoCapture.html).

## Method and correctness

The host was WSL2 Linux, Ryzen 7 5800X3D, 16 logical CPUs, Python 3.12.16, OpenCV 4.14.0 and NumPy 2.5.5. The original constructor read back 16 FFmpeg threads; explicit requests read back 1/2/4. Untimed OS task counts corroborated that difference. No global OpenCV thread or FFmpeg environment setting changed.

Use the same five synthetic CFR 24 fps H.264 fixtures as E1: 720p short/long GOP, 4K long GOP, 60-second 720p, and bounded 2 Mbit/s CBR. They total 6,846,529 encoded bytes. These small, low-complexity 20/60-second clips are not production large files.

Each of 15 fixture/position cells used one warmup and five measured observations for each of four modes: 360 helper calls, balanced rotating mode order. The timed span includes helper source open/stat and native open/seek/read/release; snapshot preparation, currentness checks, reference hashes, watchdog signalling and harness log I/O are outside it. OS caches were uncleared. Five samples support medians/ranges, not tail percentiles.

All 360 full BGR and odd-coordinate crop hashes matched independent sequential references. Index, dimensions and the production time precision bound passed. The independent frame-marker/PTS facts and normal snapshot/source-lease currentness checks were retained.

## Latency and memory tradeoff

Selected helper medians in milliseconds; the complete retained record includes all cells, samples, ranges and regressions.

| Fixture / frame | Original auto | 1 thread | 2 threads | 4 threads |
| --- | ---: | ---: | ---: | ---: |
| 720p short GOP / middle | 18.6 | 22.9 | 19.1 | 14.0 |
| 720p long GOP / middle | 53.1 | 160.9 | 103.8 | 66.6 |
| 4K long GOP / first | 104.8 | 67.3 | 52.3 | 54.8 |
| 4K long GOP / middle | 473.2 | 1,548.0 | 938.3 | 591.1 |
| 4K long GOP / final | 448.6 | 1,484.2 | 920.2 | 579.1 |

Explicit 1/2/4 had slower medians in 10/9/8 of 15 cells. Four threads slowed 4K middle/final reads by about 25/29%; one thread slowed them by about 227/231%. Frame-zero reads often improved. There is no universal faster setting.

Separate fresh processes measured a 4K middle-frame read with one or four scheduled helpers. Returned arrays remained held during request and post-drain samples; completed futures retained them through route DELETE until worker exit. Each row is one observation, not a distribution.

| Requested threads | One helper sampled request RSS peak MiB | Four scheduled helpers sampled request RSS peak MiB |
| --- | ---: | ---: |
| Original auto | 601.5 | 1,937.5 |
| 1 | 234.0 | 562.6 |
| 2 | 280.1 | 745.3 |
| 4 | 287.5 | 935.6 |

Ready worker RSS was about 102 MiB. Kernel lifetime HWM and post-drain values are separate from sampled request peaks. Sampling requested 10 ms and recorded actual timestamps; every TID's descendants were traversed with PID/start identities. Short-lived processes or peaks can still be missed. Child observations are not added to worker peaks. Four scheduled helpers do not prove four simultaneous native decodes. No listening server ran in these memory observations.

All four parallel gates had sufficient MemAvailable against the recorded 5,264,539,648-byte threshold; both discovered cgroup ancestors reported no finite limit. These are pre-run gates, not a resource guarantee.

## Controls and limits

Durable per-launch command/controller/native/source/media identities preceded nine successful launches. Tested 60-second harness scopes covered bootstrap, requests and ownership cleanup. Synthetic timeout escalation/reaping proves harness recovery, not native application cancellation. All 45 route DELETE calls succeeded after owner drain.

The original nonleader-child control tested a separate traversal implementation, not the sampler used in the eight observations. A later standard-library control invoked the exact retained sampler, saw the child and matching start identity while leader-only traversal missed it, and reaped it. This corroborates later behaviour only.

The original final checker covered 27 named processes and omitted sampled descendants. Later reconciliation found those 27, 20 sampled descendant identities and seven known control identities absent. Source pins, refs/stash and fixture bytes/stamps matched at that checkpoint; later authorized branch/documentation advances are separate. Original report-path audit failure and its corrected archived-report mapping were preserved.

The outer system verifier omitted its prescribed bytecode flag while selected workloads had it; no attributable write size or measurement effect was established. Retained sizes, deleted-report bounds and a successful allocation finish do not prove cumulative per-pool use or physical host headroom. Those accounting limits remain explicit.

A declared-manifest validator passed the 204 original and 18 correction artifacts after actual later audit metadata was added. All 27 original table lines were unchanged. The corrected record passed independent re-review; it is acceptance of qualified observations, not the full decoder implementation gate.

## Next delivery

Prepare one optional preview-thread setting directly on Austin's pinned baseline, with default 0 retaining the original constructor. Explicit 1/2/4 may expose the measured tradeoff; unsupported or rejected capabilities must fall back compatibly. Keep this small constructor policy separate from scan/render/tracking and from a native-worker/cancellation design. Real legacy-route pixels, floor-runtime, installed CLI/service and package checks belong to that PR.

These Linux synthetic H.264 observations do not validate Windows, GPU/inference, other codecs, raw VFR/HDR, hour-long/high-bitrate footage, application memory bounds or end-to-end speed. Upstream defaults, separate PR boundaries and the existing delivery order remain in force.
