# N09 ordinary HDR decoder stdout cleanup baseline

Date: 2026-11-17. **Confirmed, narrowly scoped; research only, no product fix.**
Actual ordinary `run_render` → `render_hdr` cancellation and encoder-write error
leave the decoder stdout pipe open when the caller retains the raised exception
and its traceback. Both children are already waited/reaped. Unmodified donor
`08f432b` explicitly closes the decoder pipe in those same ordinary paths.

This establishes missing deterministic descriptor cleanup, **not** an unreaped
child or an unconditional permanent application leak. With weak-only observers,
discarding the exception and collecting its traceback/frame cycle releases the
remaining handle. A separate explicitly strong diagnostic Popen reference keeps
the pipe alive after that release; its lifetime is an observer effect and is
not evidence that ordinary callers always retain it.

## Source and environment

| Owner | Pinned source | Actual module/import scope |
| --- | --- | --- |
| Baseline | `e21ebdf6e3ee46e6c65050dc956a9a3459152269` | Full `git archive` export at `/tmp/openscrub-hdr-cleanup-20261117/baseline`; complete `openscrub.py` imported as `hdr_cleanup_baseline`. `render_hdr` lines 3887–4059; `run_render` 8435–8502. |
| Donor | `08f432b6160d2fc22e51456020df929de6717e16` | Full `git archive` export at `/tmp/openscrub-hdr-cleanup-20261117/donor`; complete, unmodified `openscrub.py` imported as `hdr_cleanup_donor`. `render_hdr` 3827–4035; `run_render` 8664–8755. |

Both complete production functions run in their original module namespaces;
no extracted cleanup, substituted leaf, modified renderer, or mini-renderer is
used. Baseline engine SHA256 is
`0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`;
donor is `0dcf1686c4696fc2e8bc78b2853b2b145556ef81cad78c3a6ed34ff3f2d18f14`.
The donor's older engine and other features are not proposed for wholesale import.
All donor runs omit section parameters and exercise ordinary full rendering.

Baseline `cleanup_partial` lines 3970–3983 closes only `enc.stdin`, then
terminates/waits for each child. Donor lines 3923–3938 adds the independent
`else: pr.stdout.close()` before the same terminate/wait sequence. The baseline
normal-success path already closes decoder stdout at line 4047. Exact source
identity, imported `__file__`/code filenames and executed commands are in
[results.json](hdr-decoder-cleanup-baseline-evidence/results.json).

The reused read-only setup is
`/tmp/openscrub-baseline-20261116/env-opencv4.sh`: Python 3.12.16, OpenCV 4.14.0,
installed NumPy, FFmpeg/ffprobe `8.0.1-3ubuntu2` from the isolated tools directory.
Recorded imports resolve to that environment's OpenCV/NumPy and Python stdlib;
there is no OCR, inference, training, optional model import/download or install.
One CPU affinity limits interference. No speed/timing measurement is claimed.

## Actual fixture and observation method

The task-owned fixture is just 64×64, 3 fps, three frames. Its raw native 10-bit
Y/U/V planes are constant 900/800/300, encoded with lossless libx265 and explicit
PQ (`smpte2084`), BT.2020 primaries and `bt2020nc` matrix flags. Decoding all
three source frames reproduces every source byte. No user media are involved.

Each case calls the actual `run_render` with an ordinary synthetic state:
three zero-motion/band entries, no detections, `box`, pad 0, `libx265`, no report
write or audio. That function calls its actual module's `render_hdr`.
`Callbacks.cancelled()` returns true at the existing initial frame-0 checkpoint
for cancellation. This bounds the trigger; it does not test cancellation after
30 frames or promise interruption of an arbitrary native decode call.

The representative encoder failure uses the same callback checkpoint, returning
false after sending SIGKILL to the **actual encoder child**. A harness-only
`waitid(WNOWAIT|WNOHANG)` observation confirms it has exited without reaping it;
the real first `enc.stdin.write` then raises `BrokenPipeError`, and production
error handling waits/reaps the encoder, calls `cleanup_partial`, and raises its
normal `RuntimeError`. This is deliberate child-failure injection, not a claim
that normal valid libx265 encoding fails spontaneously.

A Popen subclass records real `wait` return values and weak references to each
process/pipe, without changing commands, reads, writes, return values or cleanup.
`/proc/self/fd` records the actual open descriptor and its pipe identity; a reused
FD number pointing to a temporary file is not counted as the earlier pipe.
`/proc/<pid>` state, wait results, all subprocess commands and temporary encoder
stderr files are recorded at return/retained exception, after exception release
plus GC, and after harness `finally`. The tracker also covers fixture/output
FFmpeg/ffprobe children and the renderer's real audio ffprobe. A read-only Python
trace observes the actual `buf` immediately before production writes; it does
not replace a stream or alter data. Strong Popen retention is enabled only in
two separately labelled diagnostic controls.

## Observed results

| Actual ordinary boundary | Baseline at return/retained traceback | Unmodified donor at same boundary |
| --- | --- | --- |
| Successful control | Decoder/encoder waited with rc 0; both pipes closed. Weak observer owners gone. | Same. |
| Frame-0 callback cancellation | `PipelineCancelled`; decoder stdout **open**, encoder stdin closed; both children waited/reaped. | Same cancellation, both pipes **closed**, both children waited/reaped. |
| Real first encoder-write broken pipe | `RuntimeError`, underlying real `BrokenPipeError`; decoder stdout **open**, encoder stdin closed; decoder rc 0, encoder rc −9, both reaped. | Same error and child outcomes, decoder stdout **closed**. |
| Missing output parent / final encoder wait | Explicit ffmpeg error rc 254; decoder already closed; both reaped. | Same ordinary-path result. Adjacent P16C observation, below. |

The weak-only baseline cancellation and write-error cases retain the **exception
itself**, not just a formatted traceback string, for the first snapshot. Its
traceback retains `render_hdr` locals, including `dec`/`enc` and `ff_err`.
Clearing that exception and collecting the cycle releases the pipe without a
harness close. Thus caller error retention, not an observer's strong Popen list,
is sufficient for the reproduced open descriptor. This is a supported embedding
boundary (`run_render` raises to its caller); no claim is made that every GUI or
worker actually retains exceptions for a particular duration.

The strong diagnostic success control has both pipe objects still present and
explicitly closed, demonstrating that the normal path closes them independently
of garbage collection. The strong diagnostic cancellation control keeps baseline
decoder stdout open even after exception release; harness `finally` closes it.
That extra lifetime comes from the diagnostic reference and is labelled as such.

Three successful controls (baseline weak, donor weak, baseline strong) each pass
all three exact raw source frames unchanged to the real encoder, produce three
decodable HEVC/yuv420p10le frames at 64×64, and retain PQ/BT.2020 tags. Decoded
output planes are constant 856/560/341 in this lossy production encode, rather
than the exact source values; this report does not claim bit-exact output or
attribute those encode/color effects to cleanup. Source decode and pre-encode
bytes are the exact fixture/control checks.

All 40 tracked children have recorded `wait` returns and are absent at
terminal snapshot; every tracked pipe/tempfile is closed or its weakly observed
owner is gone with its original FD target absent. The harness has unconditional
cleanup for live children/descriptors and a containment fallback; this is not
product cleanup. Only the deliberately strong cancellation diagnostic required
a harness close. Detailed identities, return codes and per-pipe states remain
in JSON rather than being inferred from an exit-only assertion.

## Smallest generic cleanup contract

On existing ordinary HDR paths that already call `cleanup_partial` (cancellation
and encoder-write `BrokenPipeError`/`OSError`), explicitly close the owned decoder
stdout pipe as well as encoder stdin before completing the existing child
termination/wait cleanup. Preserve the current raised cancellation/error and
successful output behavior. Closure must hold even while a caller retains the
exception traceback or a diagnostic retains the Popen object; it must not rely
on CPython destruction/GC. A regression gate should execute the real render
boundary, assert that closed-pipe state with retained owners, verify both
children are reaped, and retain a successful HDR frame/tag control.

This is the two-line generic close from the section-titled donor, independently
extractable from sections. It does not add a deadline, guarantee interruption of
blocked native decode, change decode short-read semantics, geometry, algorithms,
output overwrite/publication behavior or broad exception handling. Platform and
encoder variants remain delivery validation, not established by this Linux CPU
fixture. No product patch or app-suite/build pass is claimed.

## Separate adjacent observations / P16C

The actual missing-output-parent probe failed at the **final** encoder wait,
after three successful parent writes and normal decoder close, rather than in
the write-error cleanup. It proves useful error propagation (ffmpeg rc 254),
not N09. The donor's additional final-encoder failure cleanup is section-gated;
these ordinary runs intentionally omit sections.

Both versions also retain the encoder's temporary stderr file with an exception
traceback; it disappears after exception release/GC. That descriptor is distinct
from decoder stdout and the candidate close does not fix it. Generic arbitrary
compute exceptions that bypass the existing cleanup calls, comprehensive encoder
failure handling, existing-output preservation and safe output publication belong
to broader P16C lifecycle work. No prior-output file was created or overwritten
for this investigation, and no preservation assertion is inferred.

## Reproduction and retained evidence

Full export preparation (no checkout/index mutation):

```sh
mkdir -p /tmp/openscrub-hdr-cleanup-20261117/baseline /tmp/openscrub-hdr-cleanup-20261117/donor
git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 --output=/tmp/openscrub-hdr-cleanup-20261117/baseline.tar
tar -xf /tmp/openscrub-hdr-cleanup-20261117/baseline.tar -C /tmp/openscrub-hdr-cleanup-20261117/baseline
git archive 08f432b6160d2fc22e51456020df929de6717e16 --output=/tmp/openscrub-hdr-cleanup-20261117/donor.tar
tar -xf /tmp/openscrub-hdr-cleanup-20261117/donor.tar -C /tmp/openscrub-hdr-cleanup-20261117/donor
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/hdr-decoder-cleanup-baseline-evidence/probe_cleanup.py > /tmp/openscrub-hdr-cleanup-20261117/run.log 2>&1
python .superpowers/sdd/README/hdr-decoder-cleanup-baseline-evidence/verify_results.py > .superpowers/sdd/README/hdr-decoder-cleanup-baseline-evidence/summary.json
```

- [probe_cleanup.py](hdr-decoder-cleanup-baseline-evidence/probe_cleanup.py): full-source imports, real subprocess observation, contained failure injection and unconditional harness cleanup.
- [results.json](hdr-decoder-cleanup-baseline-evidence/results.json): ten actual boundary cases, executed commands, identities, fixture/control checks and every child/pipe/tempfile snapshot.
- [verify_results.py](hdr-decoder-cleanup-baseline-evidence/verify_results.py) and [summary.json](hdr-decoder-cleanup-baseline-evidence/summary.json): assertions over the retained research evidence, including terminal resource state.
- Task-owned full exports, tiny raw/media fixtures and run log remain under `/tmp/openscrub-hdr-cleanup-20261117`.

No active native-worktree changes, Git mutations, installs, downloads, models,
subagents, expensive workloads or full suite/build were used for this task.
