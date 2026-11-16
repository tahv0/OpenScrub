# N01 / P11: late-window dense smoothing, real-video research

Research only, 2026-11-17 Europe/Helsinki (measurements 2026-11-16 UTC).
Pinned source: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, whose runtime is
Austin `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. No product source,
branch, Git metadata, model, user media or occupied P06A worktree was changed.
The harness reads the pinned Git blob and compiles five selected AST definitions;
candidate modifications exist only in that research namespace. No donor commit
was cherry-picked. The inspected `ccff62f` hunk contributes only the proposed
initial seek behavior, with its failure defect deliberately reproduced.

**Recommend the smaller sequential `grab()` alternative for a focused P11
proposal.** It reduced median time about 3–4× on these clips while preserving
actual cache-frame identities, all Detection fields and the existing
every-90-frame cancellation checkpoints. It still decodes the prefix; it
avoids retrieving/converting pixels that the smoother never uses. Add
deterministic `finally` cleanup as part of the decoder ownership.

The donor initial-seek hunk also has a real throughput benefit, including on
the one-keyframe clip, but remains **gated**: it regresses cancellation
responsiveness during native seeking. Failure also requires reopening and
clearing seek state. Pre/post cancellation checks cannot eliminate the native
delay. Do not ship that hunk unchanged or silently accept the hidden delay.
This research does not authorize a broad decoder subsystem.

The related contracts are N01 in [core-semantic-audit.md](core-semantic-audit.md),
the earlier [fake-decoder probe](probe_dense_smoothing_prefix.py) and its
[operation counts](dense-smoothing-prefix-results.json), and P11/S04/S06 in
[the large-video plan](../../../docs/superpowers/plans/upstream-delivery/02-large-video-performance.md).
The earlier 17,873-to-1 count stops at the first grayscale conversion. The real
function below runs to completion; its 18,001-to-130 read counts measure a
different, explicitly complete operation.

## Fixture and initial-seek measurements

Both deterministic clips have 18,300 frames, 610 seconds, 256×144 pixels, H.264
High / `yuv420p`, 30/1 nominal and average FPS, MP4 time base 1/15360, no audio,
no normalization and no model inference. ffprobe decoded every frame for the
keyframe census and confirmed PTS from 0 through 609.966667 seconds, spaced
0.033333–0.033334 seconds at its printed precision. GOP30 has keyframes every
30 frames (610 total), 18,134,863 bytes. The long-GOP clip has exactly one
keyframe at frame zero, 2,724,556 bytes. The lower long-GOP byte size follows
from the intentionally mostly static content; it is not an equivalent-bitrate
comparison between codecs.

A fixed NumPy seed `20261116` generates a textured background, a visible frame
number, and 16 high-contrast machine-readable frame-ID cells on **every** frame.
A different textured 64×48 target appears at 598 seconds, moves slowly, and is
sampled at 600.0, 600.2 and 600.3 seconds. This exercises real template matching,
backward onset walking, interpolation, grace padding and output detections.
The scan window starts at 590 seconds; the first needed cache frame is 17,872
(595.733333 seconds). The candidate calls the existing `_seek_cap` once at this
frame, sets `_seq['pos']` only on success, and preserves the sequential cache.
The timed `safe` variant additionally reopens on failed seeking; normal timing
does not include fault injection or the separate cleanup/cancellation variant.

The final timing pass was 22:03:01–22:05:08 UTC, with three paired warm-ups and
five measured pairs per clip. Measured order alternates. Every invocation has
a fresh capture, fresh function namespace, fresh detections and empty gray
cache. Filesystem cache is warm/uncontrolled; no global caches were dropped.
The separate FFmpeg diagnostics and lifecycle probes ran **after** this pass.
There was no overlapping media experiment from this harness. This is a shared
WSL machine, not an isolated CPU benchmark; ambient machine load was not pinned.

| Clip | Upstream wall seconds, five samples | Candidate wall seconds, five samples | Median before → after |
| --- | --- | --- | --- |
| GOP30 | 5.489894, 5.518836, 5.518025, 5.488143, 5.519689 | 0.066987, 0.067220, 0.068835, 0.070649, 0.067028 | 5.518025 → 0.067220 |
| One keyframe | 5.470593, 5.650854, 5.536006, 5.546259, 5.562241 | 1.404752, 1.418114, 1.403429, 1.404363, 1.423420 | 5.546259 → 1.404752 |

Every complete upstream run issues 18,001 Python `read()` calls. Every successful
candidate run issues 130: one consumed by `_seek_cap` positioning at frame
17,871, then 129 sequential cache reads for frames 17,872–18,000. Both cache
the **same actual pixel frame IDs in the same order**, with no missing or
duplicate cached frame. All warm-ups and measured runs produced exactly the
same 38 Detection records, including every geometry, timestamp, track, polygon
and other dataclass field. Return values were `(2, 30, 2.25)`: two bridged gaps,
30 onset samples, 2.25 lead seconds. Canonical output SHA256:
`0df780727712a9bce2d76498f31c29428798e1ca7f5e1b09ef7c17c05851bca0`.
The reference records and comparison booleans are retained in the raw results.
Direct helper probes also verified the **next read's marker**, not merely the
property value, at frames 30, 9,000 and 17,872 on both files.

The Python read reduction does **not** imply avoided codec prefix decoding.
On the one-keyframe clip, candidate native `cap.set` calls alone took
1.340260–1.360875 seconds; on GOP30 they took 0.006104–0.006463 seconds.
Independent FFmpeg CLI diagnostics requested 129 output frames after input
seeking to 595.733333 seconds:

| Clip | Demux packets read | Codec frames decoded | Diagnostic wall / CPU user / CPU system seconds |
| --- | --- | --- | --- |
| GOP30 | 164 | 153 | 0.032 / 0.028 / 0.021 |
| One keyframe | 18,014 | 18,003 | 1.723 / 1.107 / 1.081 |

Those are single diagnostic runs, not repeat latency benchmarks or exact
OpenCV decoder counts. CLI FFmpeg uses one decoder thread and a different
linked FFmpeg build; OpenCV uses 16 decoder threads here. Pipeline buffering
also explains a few extra decoded frames. They establish that an accurate
seek can hide essentially the full prefix decode inside native code. Avoided
Python/native round trips and avoided prefix BGR output are a plausible source
of the remaining speedup; this experiment does not attribute their individual
shares. It makes no 4K, high-bitrate, Windows, HDR or VFR latency guarantee.

## Failed seek, cancellation and lifetime

The failure injection uses a **real** VideoCapture: it seeks to frame 9,000,
reads one frame, leaves next-frame position 9,001 and a stale `_grab_state`
entry, then returns `False` from the helper contract. This is a controlled
fault, not a claim that these clean clips naturally fail seeking.

| Failed-seek behavior | Python reads | Captures released/opened | Remaining state | Result |
| --- | --- | --- | --- | --- |
| Unmodified upstream (no initial seek) | 18,001 | 1/1 | 0 | Reference 38 rows, 30 onset samples |
| Exact donor initial-seek behavior | 9,301 | 1/1 | 1 | Wrong: `(2, 0, 0.25)`; no onset walk |
| Reopen fallback | 18,002 | 2/2 | 0 | All reference rows and cache IDs restored |
| Reopen + `finally` | 18,002 | 2/2 | 0 | All reference rows and cache IDs restored |

The donor retains logical `_seq['pos']=0` after the failed helper has changed
the real capture position. It reaches EOF before any useful cache entry and
silently loses the onset coverage. Reopening restores the original sequential
origin; merely declining to update `_seq` is insufficient. A bare seek-to-zero
has the same trust problem if positioning is what failed, so reopen is the
minimal reliable fallback for this path.

Cancellation is checked at loop boundaries, not by the native codec. In the
separate lifecycle experiment, the callback becomes true when wall time passes
20 ms; this models a request arriving while native work runs, without claiming
that Python interrupted that work. Single observations on the one-keyframe clip:

| Scenario | Unmodified sequential | Seek/reopen candidate | Candidate with pre/post checks and `finally` |
| --- | --- | --- | --- |
| Already cancelled before call | 3.66 ms, zero reads | 1,361.31 ms, one helper read | 5.13 ms, zero reads/seeks |
| Callback true after 20 ms | 34.93 ms, 90 reads | 1,342.52 ms, one helper read | 1,357.39 ms, one helper read |

The upstream path checks every 90 raw reads. Initial native seek can decode the
large prefix with no callback opportunity, so pre/post checks only handle
cancellation before and after that blocking interval. They **do not preserve
the original response bound**. On higher-resolution/longer files this interval
could be far worse. The measured 1.36 seconds is not a proposed universal
timeout. A future integration must explicitly decide an acceptable seek policy
or use a separately justified interruptible path; a Python waiting-thread
timeout would not stop this native work.

Upstream cancellation raised before its normal-only `cap.release` call, so the
probe observed zero explicit releases. Calling the seeker additionally creates
per-capture `_grab_state` entries: successful simple candidate runs leave one
entry even after normal release, and cancelled runs leave both an unreleased
capture and one entry. The `safe-cleanup` AST experiment released every capture
and evicted all state on normal return, failed seek, already-cancelled and timed
cancellation paths. The harness records these facts **before** doing its own
cleanup, so it does not hide function-owned release failures. It does not
assert that Python destructors never release an otherwise unreachable handle;
the missing deterministic ownership is the issue.

## Recommended sequential alternative

After the cancellation finding, a separately authorized research variant kept
the original `_seq=0` forward decode and changed only the `_fill_to` operation:

```python
if _seq["pos"] in _span_lo:
    ok, fr = cap.read()
else:
    ok, fr = cap.grab(), None
```

Both branches retain the original EOF handling, advance `_seq` once after
success, and cache only needed frames. The variant also wraps capture ownership
in `try/finally`. There is no bulk native seek: the original callback check
still occurs every 90 sequential frame advances. No helper seek state is
created. Codec prefix decoding remains, while OpenCV retrieval/BGR output and
array allocation for unused frames are avoided. The timing experiment does not
separately attribute the costs of conversion, retrieval and allocation.

This comparison ran 22:09:02–22:10:59 UTC with three paired warm-ups and five
alternating measured pairs for each clip, on the same files/settings as above.
The report implementer's last three-second render-test batch ended at
22:09:10.142 UTC, within the first warm-up phase (the three GOP30 warm-up pairs
alone consumed 22.028 seconds plus source setup). It deferred all subsequent
heavy tests/renders until measurement completion. Thus the retained measured
pairs have no overlap with that controlled workload; the shared-machine
ambient-load limitation still applies.

| Clip | Upstream wall seconds, five samples | Sequential `grab()` wall seconds, five samples | Median before → after |
| --- | --- | --- | --- |
| GOP30 | 5.665950, 5.564965, 5.572661, 5.548964, 5.566963 | 1.834963, 1.867508, 1.815983, 1.833344, 1.812924 | 5.566963 → 1.833344 |
| One keyframe | 5.516288, 5.534414, 5.521539, 5.485725, 5.454764 | 1.381043, 1.411619, 1.400082, 1.409957, 1.379583 | 5.516288 → 1.400082 |

Every complete variant run made 17,872 `grab()` calls and 129 `read()` calls,
versus 18,001 `read()` calls upstream. Total sequential frame advances remain
18,001. All warm-ups and measured runs had the same frame markers
17,872–18,000, the same 38 Detection records and the same output hash reported
above. Every variant capture was explicitly released; no `_grab_state` entry
remained. Neither helper seek nor native positioning was called.

For the callback that becomes true after 20 ms, single observations were
34.67 ms upstream versus 25.80 ms / 180 grabs for GOP30, and 34.68 ms upstream
versus 27.68 ms / 270 grabs for the one-keyframe clip. Already-cancelled variant
calls returned in about 5 ms with zero frame advances and proper release.
These observations support the source-level preservation of the same
every-90-frame checkpoints; they are not universal millisecond deadlines.
A single codec frame decode can still block, as it can in upstream's `read()`.

The minimal recommended implementation contract is to use `read()` only for
`_span_lo` indices, `grab()` otherwise; preserve the success/EOF/position/cache
logic and all matching/Detection semantics; retain the current cancellation
checks; and put capture release under `finally`. The function has no reason
to create `_grab_state` for this path. Keep the helper-failure evidence below
for any later seek proposal, rather than making reopen machinery a dependency
of this smaller alternative. A focused regression should check frame advances,
cache identities/output equality, EOF and cancellation/release. No product
implementation or product tests were added by this research.

## Gated initial-seek contract

The direct seek remains measured but should stay deferred until its
cancellation gate is resolved. If revisited, preserve all interpolation, span,
matching and Detection semantics; do not copy the mixed donor's other changes.

1. Initialize callbacks before positioning. Check cancellation before starting
   the initial seek and immediately after native seeking returns. Keep the
   existing sequential-loop checks.
2. Seek only when there is an actual needed span and its first frame exceeds
   the existing proposed two-second threshold. Reuse `_seek_cap`; never treat
   `cap.set` alone as exact proof. The helper itself tolerates ±1 PTS and can
   trust arithmetic when PTS is unavailable; this research verifies actual
   frames on this backend, not every supported source/backend.
3. Set `_seq['pos']=first_needed` only on successful positioning. Clear that
   capture's `_grab_state` as soon as direct sequential ownership resumes;
   direct reads do not maintain the seek helper's position state.
4. On helper failure, remove old state, release the old capture, reopen the
   same pinned source, remove any stale entry for the new/recycled capture ID,
   and retain `_seq['pos']=0`. If reopening fails, raise before altering the
   detection list; silently treating the replacement as absent would weaken
   onset coverage. Do not retry seeking repeatedly.
5. Own the capture under `try/finally`: clear state and release on success,
   cancellation, positioning error, matching error and reopen failure. Preserve
   all previously computed detections; do not publish a partial successful
   smoothing result after cancellation.
6. Resolve the native seek cancellation delay before calling the integration
   ready under a no-regression requirement. Pre/post checks and `finally` are
   necessary but insufficient for that requirement. No product fix was made
   here to conceal this unresolved tradeoff.

Implementation verification should keep a small frame-marked real-media test
for exact outputs and a deterministic helper-failure test that **moves** the
capture, plus state/release checks on every exit. The expensive 610-second media
belongs in opt-in measurements, not Git. The existing fake count probe remains
useful for deterministic work bounds but cannot replace these real-video and
failure-position checks. P11's separate OCR/history profiling and P10's full
VFR/4K/concurrency/source-replacement coverage remain outside this experiment.

## Reproduction and retained evidence

Run from the original repository. The source environment was supplied by the
parent task; no dependencies or models were downloaded. Generated media and
full FFmpeg debug logs stay under the uniquely named `/tmp` directory.

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/late-window-research-evidence/probe.py \
  --work /tmp/openscrub-late-window-20261116 \
  --output /tmp/openscrub-late-window-20261116/results.json --generate
python .superpowers/sdd/README/late-window-research-evidence/codec_work.py \
  --work /tmp/openscrub-late-window-20261116 \
  --output /tmp/openscrub-late-window-20261116/codec-work-results.json
python .superpowers/sdd/README/late-window-research-evidence/lifecycle.py \
  --work /tmp/openscrub-late-window-20261116 \
  --output /tmp/openscrub-late-window-20261116/lifecycle-results.json
python .superpowers/sdd/README/late-window-research-evidence/grab_compare.py \
  --work /tmp/openscrub-late-window-20261116 \
  --output /tmp/openscrub-late-window-20261116/grab-results.json
```

The generator pipes identical BGR24 frames to two FFmpeg encoders with
`libx264 -preset fast -crf 18 -threads 1 -pix_fmt yuv420p`,
`keyint=min-keyint=30` or `18301`, `scenecut=0:open-gop=0:bframes=2`.
Exact complete encoder commands are retained in
[generation-commands.json](late-window-research-evidence/generation-commands.json).
The final reported timing pass reran `probe.py` without `--generate` and with
output `final-results.json`; the harness was extended afterward for the
separate before/timed cancellation diagnostics and the `grab` variant. Those
extensions do not alter the timed normal `base`/`safe` algorithm paths.
Evidence:

- [Real function samples, metadata, reference detections and failed-seek results](late-window-research-evidence/results.json)
- [Codec work and beginning/middle/end marker checks](late-window-research-evidence/codec-work-results.json)
- [Cancellation timing and cleanup results](late-window-research-evidence/lifecycle-results.json)
- [Sequential grab samples and cancellation/release results](late-window-research-evidence/grab-results.json)
- [Pinned-source AST harness and generator](late-window-research-evidence/probe.py)
- [FFmpeg/internal-work harness](late-window-research-evidence/codec_work.py)
- [Cancellation harness](late-window-research-evidence/lifecycle.py)
- [Sequential grab comparison harness](late-window-research-evidence/grab_compare.py)
- [OpenCV build details](late-window-research-evidence/opencv-build.txt)

Environment: AMD Ryzen 7 5800X3D, 16 logical CPUs, WSL2 Linux
6.18.58.1-microsoft-standard, glibc 2.43, Python 3.12.16, NumPy 2.5.5,
OpenCV 4.14.0 / FFmpeg backend with 16 decoder threads; OpenCV compute threads
set to one. Bundled FFmpeg avcodec 62.28.102, avformat 62.12.102, avutil
60.26.102; system FFmpeg CLI 8.0.1-3ubuntu2. The low-resolution, mostly static
synthetic fixtures isolate this function's prefix cost. No inference, full
application scan/render, HTTP, browser, general 4K benchmark or native seek
interruptibility was tested or claimed.
