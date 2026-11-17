# Exact sample feasibility evidence

Research only, 2026-11-17. Inputs are the existing pinned export and three existing tiny synthetic clips. No product imports, native checkout access, media generation, models, browser, benchmark, build, suite, install, server or branch operation.

Run from `/home/tahv0/src/OpenScrub`:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/exact-sample-feasibility-evidence/probe.py > .superpowers/sdd/README/exact-sample-feasibility-evidence/probe.log
python .superpowers/sdd/README/exact-sample-feasibility-evidence/verify.py > .superpowers/sdd/README/exact-sample-feasibility-evidence/verification.log
```

`probe.py` verifies all 125 exported files against the earlier pinned Git blob/SHA-256 manifest before compiling just the AST node for the existing `_frame_at`. Its dependency wrapper delegates every seek/read to real OpenCV and records returned frame hashes, markers and post-read decoder timestamps. It does not synthesize successful frames. Sequential references start with a fresh capture and contain every actual decoded frame, without seeking. Independently run FFprobe frames supply integer PTS and stream time base. Setter returns/counters are diagnostic only. References are bounded to the existing 48/10/14-frame clips, never a proposed per-scrub production scan.

`results.json` records complete source/tool/media identities, commands and observations. `probe.log` is the compact human-readable result. `verify.py` checks matching pixels/PTS, natural EOF failures, duplicate ambiguity and release. The first run had 27 requests; adding the second duplicate index justified the final 28-request run. Only final results are retained. Every FFprobe call uses synchronous `check_output` with a 15s limit; all completed normally. There were no asynchronous children/ports to shut down; all 28 captures released. Existing inputs remain untouched for reproducibility; this probe creates no temporary media or running resources.

Public primary-source retrieval followed `githits-mcp` without `quick_start`. Retrieval: `read(target="github:opencv/opencv@4.14.0", path="modules/videoio/src/cap_ffmpeg_impl.hpp", selector="seek")` returned two overloads, then one bounded read at2290–2445; one exact-file grep for properties/PTS and bounded reads at1755–1832 and2190–2267. GitHits resolved the tag to **0654a42e19215ef25b1d367d822f3c630447e7c7**, committed2026-07-17. These upstream sources explain API behavior; the locally installed wheel is separately identified in `results.json` and was not rebuilt or proved byte-identical to that commit.

The following is the complete public-source-derived interpretation used by the report: [OpenCV FFmpeg backend](https://github.com/opencv/opencv/blob/0654a42e19215ef25b1d367d822f3c630447e7c7/modules/videoio/src/cap_ffmpeg_impl.hpp#L2302) rounds timestamp seeks to a frame number, while integer seeks use FPS-derived timestamps, backward seeking and forward decoding. The setter can return true without checking the resulting pixels. Frame count may be estimated from duration and FPS. Post-read `POS_MSEC` derives from decoded timestamps with backend timeline normalization; `CAP_PROP_PTS` is rescaled into frame-rate units, not the original stream time base. These mechanisms support a restricted tested CFR contract but do not establish exact ordinals for arbitrary VFR, missing timestamps, damaged media or misleading metadata. No FFmpeg alternative was run because the existing indexed path satisfied the bounded supported-source cases.
