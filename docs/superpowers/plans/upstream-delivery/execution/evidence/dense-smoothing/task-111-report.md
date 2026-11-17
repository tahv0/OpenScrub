# Task111 / P11A: retrieve only needed dense-smoothing frames

Completed locally on `pr/dense-smoothing-prefix`, worktree
`/home/tahv0/.codex/worktrees/c832/OpenScrub`.

- Before: `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin `5d3a15a` runtime plus the reviewed test-only prerequisite).
- After: `f19be5fe3b9176e568ea7bf761493bd267fee95e` (`Retrieve only needed dense smoothing frames`).
- Independent base; no P06, Save As, optional-mode or other feature-branch dependency. No remote publication, inference/model download, new dependency, version bump, source-media or user-data changes. No subagents.

## Change and compatibility

The existing sequential `_fill_to` now calls `read()` for indices in `_span_lo`
and `grab()` otherwise. Both follow the same failure sentinel, logical index
advance, cache fill and matching path. Codec prefix decoding still happens.
Cancellation retains the original loop-boundary check every 90 sequential
advances and the per-track checks. There is no initial seek, positioning state,
worker process/thread, decoder framework, or policy option.

One `try/finally` owns the original capture, including a failed-open capture
that the matching path treats as unavailable. Success, EOF, cancellation,
opening/property/callback/retrieval/conversion/matching errors explicitly
release it. No-video/no-track behavior and default masks remain compatible.
Cache spans, the +2 PTS tolerance, eviction, matching threshold, interpolation,
grace padding, all Detection fields and report/default policies are unchanged.

README and CONTRIBUTING consistently use `python -m pytest -q` to collect root
and `tests/` regressions. The sdist includes `tests/`; no CI or runtime package
layout changes were needed. The opt-in `benchmark/dense_smoothing.py` imports
complete source modules, unlike the earlier AST-isolated research.

## Regression and actual runtime evidence

20 cases in `tests/test_dense_smoothing_io.py` cover unused prefix/gap
retrieval counts and exact frame identities/output, overlapping/all-needed
cache reuse, natural EOF during grab/read, failed grab/read, pre-cancellation
and operation-timed cancellation at 0/90/180 advances, deterministic cleanup
on success/error/cancel and failed opening, legacy unavailable/no-video
behavior, and no decoder for no tracks. Decoder doubles isolate actual I/O
cost and failures; image conversion and matching stay real except at their
explicit injected-error boundaries.

RED against the complete imported baseline module: **17 failed / 3 passed**
([raw log](task111-evidence/red-final.log)); GREEN: **20 passed in 0.10 s**
([raw log](task111-evidence/owning-final.log)). The first draft mistakenly
excluded the first span's two trailing PTS-tolerance frames from a later gap;
that fixture expectation was corrected, then the corrected full tests were
rerun against baseline for RED. These frames remain needed. An early shell
attempt invoked `python` before sourcing the supplied environment; it changed
no product files and was corrected before the implementation run.

A committed lossless FFV1 test marks all 130 128×96 frames at 10 FPS; the target
appears late and moves. All 45 needed frame IDs 16–60 match, with 16 prefix
grabs and no seek. Matching/interpolation yield `(1, 5, 1.25)` and 10 complete
Detection records with baseline SHA256
`2c61c2352afd72a6f69ea46398b3947eaf00b80e82609d9148c3368b805ba050`.
The golden came from the full baseline module before the optimization.

The standalone [runtime check](task111-evidence/verify_runtime.py) additionally
renders those detections through both complete modules using actual default
blur, pad=8 and ellipse face shape, x264 encoding. **All 130 decoded BGR frames
are equal**, aggregate decoded-frame hash
`99047cfa56bb1b128e3477a60d00003ee48b9377dea2c644a6140351e699c1d2`.
A separate real Tesseract `run_pipeline` scan/report/default render on a
synthetic SSN video produced one report row; output capture metadata reports 20 frames.
This checks engine integration without representing the OCR scan as a dense
face-detector benchmark. [Runtime results](task111-evidence/runtime-results.json).

Final complete suite: **154 passed in 68.82 s** (134 existing + 20 new),
with task-owned runtime data, copied existing local YuNet model, pytest temp
and cache paths. An earlier 151-test run before adding three extra failure/EOF
cases also passed. [Final log](task111-evidence/suite-final.log).

Full `python -m build` passed, building the sdist and then the wheel from that
sdist with isolated Hatchling 1.33.0. Extracted sdist source/tests/config/README
and wheel runtime match the committed files. Initial sandboxed build DNS
failed; `--no-isolation` exposed absent Hatchling in the supplied venv; the
normal full build then succeeded with approved escalation for the existing
build dependency. [Build log](task111-evidence/build-final.log).
Three edited Python files parse; `git diff --check` passes. Self-review reversed
only the ownership wrap and read/grab branch and recovered the baseline
smoother AST exactly; no matching/Detection/default behavior changed. The
self-review found no remaining required fixes or deferred minor findings.
Author self-review is weaker than independent review; supervisor review remains.

## Actual complete-module measurements

Reused synthetic files under `/tmp/openscrub-late-window-20261116`: 610 seconds,
18,300 CFR 30 FPS H.264 frames, 256×144, yuv420p, no audio. GOP30 has 610
keyframes; the other clip has one at frame zero, per the retained research
census. Window start=590 s; detections at 600.0/600.2/600.3 s; first needed
cache frame=17,872. Files and source modules are SHA256-pinned in
[raw results](task111-evidence/timing-results.json) and source bytes independently
compare equal to the exact Git blobs in
[source identity](task111-evidence/source-identity.json).

The benchmark uses full imported before/after modules without AST extraction
or alteration, fresh detections/capture/gray cache per call, FFmpeg-backed
OpenCV, three paired warm-ups and five alternating measured pairs per clip.
Only actual `smooth_dense_tracks` calls are timed; imports are outside timing.
Frame-marker and decoder-operation instrumentation is included, equally for
both variants. No controlled heavy workload ran during this timing pass; the
supervisor was notified before/after. Filesystem caches are warm/uncontrolled;
this is a shared WSL machine, not pinned or isolated CPU testing.

| Clip | Before samples (s) | After samples (s) | Median and observed ratio |
| --- | --- | --- | --- |
| gop30 | 5.529398, 5.529710, 5.535447, 5.544441, 5.530690 | 1.797305, 1.811116, 1.792094, 1.797271, 1.814185 | 5.530690 → 1.797305 (3.08×) |
| single-keyframe | 5.524841, 5.460098, 5.453764, 5.491272, 5.479827 | 1.386866, 1.392670, 1.368725, 1.403149, 1.373607 | 5.479827 → 1.386866 (3.95×) |

Every warm-up and sample has **18,001 reads → 17,872 grabs + 129 reads**,
zero positioning/seek calls, actual converted markers **17,872–18,000** in
exact order, **38 entirely equal Detection records**, return `(2, 30, 2.25)`
and reference row hash
`0df780727712a9bce2d76498f31c29428798e1ca7f5e1b09ef7c17c05851bca0`.
All normal captures explicitly release; no `_grab_state` entries are created.
Raw results include reference markers/records, every sample, counts and checks.

Separate cancellation probes become true before the call or after 20 ms wall
time; these are single observations, not latency deadlines:

| Clip | Source / request | Observed ms | reads / grabs | releases / captures |
| --- | --- | --- | --- | --- |
| gop30 | before/before | 3.842 | 0 / 0 | 0 / 1 |
| gop30 | before/timed | 34.742 | 90 / 0 | 0 / 1 |
| gop30 | after/before | 4.957 | 0 / 0 | 1 / 1 |
| gop30 | after/timed | 25.523 | 0 / 180 | 1 / 1 |
| single-keyframe | before/before | 3.780 | 0 / 0 | 0 / 1 |
| single-keyframe | before/timed | 34.608 | 90 / 0 | 0 / 1 |
| single-keyframe | after/before | 5.023 | 0 / 0 | 1 / 1 |
| single-keyframe | after/timed | 27.172 | 0 / 270 | 1 / 1 |

Timed pass UTC: `2026-11-16T23:04:42.117192+00:00` through `2026-11-16T23:06:36.042438+00:00`.
Process peak RSS: 131364 KiB. This is whole-process high-water
memory including both imported modules, Python, allocator and instrumentation;
it is **not** an isolated smoothing-memory delta or a native-memory leak proof.
Gray-cache span/eviction logic is unchanged. Generated media, output renders,
pytest artifacts, copied local model and build artifacts remain task-owned under
`/tmp/openscrub-task111` for review and can be removed by their owner afterward.
The reused research inputs belong to the research task and were not removed.

## Commands and limits

From the isolated worktree:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
# Task-owned overrides: task111_isolation is a copy of supplied isolation;
# it uses /tmp/openscrub-task111 data and a copy of the existing local model.
. /tmp/openscrub-task111/env.sh
python /tmp/openscrub-task111/red.py  # full baseline module; expected RED
python -m pytest tests/test_dense_smoothing_io.py -q \
  --basetemp=/tmp/openscrub-task111/owning -o cache_dir=/tmp/openscrub-task111/pytest-cache
python /tmp/openscrub-task111/marked_probe.py  # baseline golden, generated media outside Git
python /tmp/openscrub-task111/verify_runtime.py
python -m pytest -q --basetemp=/tmp/openscrub-task111/full \
  -o cache_dir=/tmp/openscrub-task111/pytest-cache
PIP_CACHE_DIR=/tmp/openscrub-task111/pip-cache python -m build \
  --outdir /tmp/openscrub-task111/dist
# Full baseline source; no cherry-pick or AST alteration:
git show e21ebdf6e3ee46e6c65050dc956a9a3459152269:openscrub.py > /tmp/openscrub-task111/before/openscrub.py
python benchmark/dense_smoothing.py \
  --before /tmp/openscrub-task111/before/openscrub.py \
  --before-revision e21ebdf6e3ee46e6c65050dc956a9a3459152269 \
  --after openscrub.py --after-revision f19be5fe3b9176e568ea7bf761493bd267fee95e \
  --media-dir /tmp/openscrub-late-window-20261116 \
  --output /tmp/openscrub-task111/evidence/timing-results.json
```

Retained [runtime log](task111-evidence/runtime.log),
[timing log](task111-evidence/timing.log), fixture/isolator scripts and the
[research report](late-window-research.md) make the measurement repeatable in
the supplied environment. Fixture generation, complete keyframe/PTS census,
FFmpeg CLI codec diagnostics and the rejected initial seek's ~1.36 s versus
~35 ms cancellation observation remain in that research evidence; they were
not rerun or copied as product implementation. Native prefix decode is still
required, and avoided retrieval/BGR conversion/allocation costs were not
separately attributed. This result makes no 4K, high-bitrate, VFR, GPU,
Windows/frozen-app or universal wall-time/cancellation bound claim. Native
single-frame decode can still block. Broader P11 scan-history profiling and
S04 platform/media coverage remain separate.
