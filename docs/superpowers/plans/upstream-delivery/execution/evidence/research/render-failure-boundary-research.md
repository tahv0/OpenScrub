# P16C: invalid regions, owned render resources and output publication

Status: bounded correctness/source research complete; implementation remains open.
Research date: 2026-11-17. Source pin: `12919c96c6f7558136b50d7b4d85e5e6b62f1971`.

Task622 protects final report/status publication against an obsolete operation.
It does **not** preserve the prior video. Actual ordinary-worker execution here
retained the old JSON on report-replacement failure and on acknowledged
cancellation before report publication, while the final video had already
changed. A direct render cancellation also deleted a valid prior output.
Geometry errors need three distinct subcards; a geometry guard alone cannot
establish the full preservation contract currently written into P16C.

## Scope and reproducibility

All runtime imports and product-source reads came from the full, unmodified
`git archive` export at `/tmp/openscrub-render-failure-20261117/pinned`. No native
worktree was accessed. Only the explicitly authorized P16C plan and relevant
prior research sections were read from the supervisor workspace. There were no
product/Git edits, installs, models, user media, nested agents, suites,
benchmarks, external research or publication. The first seven-case probe was
followed by one bounded rerun adding post-cleanup file hashes and task-partial
removal; the retained JSON is the latter run. This is no timing or stress claim.

Environment: Linux WSL2 x86_64 CPU, Python 3.12.16, OpenCV 4.14.0, ffmpeg
8.0.1-3ubuntu2. The existing `env-opencv4.sh` was reused. Both synthetic input
and valid previous output are 64×64 MPEG-4, eight frames at 10 fps, no audio.
Actual worker outputs are eight-frame H.264. The HDR resource case invokes the
actual 10-bit YUV/HEVC branch with `libx265` on the tiny SDR source; it establishes
HDR-branch ownership/failure behavior, **not** HDR signal/fidelity correctness.

Pinned SHA-256 values:

| File | SHA-256 |
|---|---|
| `openscrub.py` | `275de34766d3d64592222be5633906a3dcd2557ce78e2dd7b7d6fb8075fd0355` |
| `openscrub_web.py` | `7762f0314df5e11e46a570af54cd20e928953e7bf92d55da7d648dad36e0fce2` |
| `openscrub_internal/reports.py` | `e8a7429c0b5430ee290f6635ca5d5a93445d3f0fe9bb0f58e57fec891ee01b7f` |

Additional source hashes, fixture validation and assertions are in
[summary.json](render-failure-boundary-evidence/summary.json). Exact prior/current
video **and report** hashes, process commands/states, lifetime snapshots and
exceptions are in [results.json](render-failure-boundary-evidence/results.json).

Recipe, from the supervisor repository (all render data stays in task `/tmp`):

```bash
mkdir -p /tmp/openscrub-render-failure-20261117/pinned
git archive 12919c96c6f7558136b50d7b4d85e5e6b62f1971 | tar -x -C /tmp/openscrub-render-failure-20261117/pinned
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/render-failure-boundary-evidence/probe.py > /tmp/openscrub-render-failure-20261117/results.json
cp /tmp/openscrub-render-failure-20261117/results.json .superpowers/sdd/README/render-failure-boundary-evidence/results.json
python .superpowers/sdd/README/render-failure-boundary-evidence/verify.py > .superpowers/sdd/README/render-failure-boundary-evidence/summary.json
```

The harness uses real module functions, encoders, `enqueue`, `worker`,
`run_pipeline(--from-report)`, Task622 callback and actual cancel route.
Observation retains actual child/capture/tempfile objects without changing
commands or render operations. Only the report-replacement OSError and the
post-hash synchronization gate are injected, scoped to exact task-owned paths.
Direct errors retain their actual traceback for resource inspection. There is
no miniature renderer/publisher or substituted render/report implementation.

## Actual lifetime and final-path inventory

Line references below are to the pin, not the moving checkout.

| Path | Lifetime and final publication |
|---|---|
| `run_render`, 8451–8520 | Coverage transforms precede encoder creation. Calls SDR/HDR renderer with final `dst`; afterward constructs/hashes report via `write_report`, then returns summary. No enclosing resource/output transaction. |
| SDR `render`, 4060–4297 | Owns OpenCV input capture, ffmpeg stdin/child and temporary stderr. ffmpeg `-y ... dst` writes directly to final path. Existing cleanup runs only at cancellation checkpoint or encoder-write error. Arbitrary frame/geometry/callback errors, setup failures and final nonzero encoder wait lack comprehensive cleanup. |
| SDR OpenCV fallback, 4154–4163, 4295–4297 | Owns capture/VideoWriter; writes `dst + '.noaudio.mp4'`, then `os.replace(tmp_video, dst)`. This is one video replacement, still before report publication; cancellation/error cleanup currently removes `dst` as well as the partial. Source-only here. |
| HDR `render_hdr`, 3885–4057 | Metadata capture released before child creation; then decoder stdout/child, encoder stdin/child and stderr file. ffmpeg `-y ... dst` writes final path. Narrow cleanup handles checkpoint cancellation/write failure; ordinary completion closes decoder stdout and waits both children. Generic exceptions can bypass it, including errors after one child starts but before cleanup helper exists. |
| `write_report`, 6286–6346 | Constructs provenance and hashes final video before invoking optional publisher. CLI/GUI/default uses `atomic_report`; web installs Task622 publisher. From-report preserves full raw document/unknown fields and disabled rows while rendering enabled objects. |
| `atomic_report`, reports.py 7–40 | Exclusive sibling `.report-*.tmp`, JSON dump/flush/fsync/close, then `os.replace`. Pre-replacement failure preserves old JSON, cleans stage. No video rollback; no directory fsync/crash-pair guarantee. |
| Web `_run_job`, 946–1130; `worker`, 897–943 | Queue/worker owns job and selected source lifetime. Task622 callback acquires report lock, checks operation identity and event, publishes JSON. Success later assigns `job.output`/`done` under same lock with another identity check. Error/cancel status also guarded. Worker finally releases lifetime outside report lock, then clears `active` under report lock. No owned encoder tracking or video rollback is added by the lifetime token. |
| CLI/batch/GUI | `run_pipeline` delegates to same `run_render`; batch 8582–8620 and GUI 460–475 have no later video move or pair commit. Source-only caller inventory. |

Other render-report publication entry points are scan's `write_report` through
the same Task622 hook, review saves (`atomic_report`, web 1802) and tracker
append (`atomic_report`, web 1918). They publish JSON, not final video. Source
normalization writes CFR/HDR/tonemap intermediates; model-download replacements
are not final render-video paths. Startup rehydration (web 4515–4525) exposes an
existing `output.mp4` by existence; it does not make a new video or validate
report/video generation agreement. No crash recovery guarantee is inferred.

Downloads use `send_file(job.output)` without the report lock (web 2229–2238).
`frame_at?src=output` opens the output decoder without that lock (1660–1689).
Report `send_file` stat/open is inside report lock (2242–2247). Request admission
and `OwnedIterable` retain FILES ownership through response close, protecting
deletion/vault transitions; that lifetime is not a video-generation snapshot.

## Representative observed cases

`P` is the valid prior video, 1150 bytes, SHA-256
`0f9aa6ec687d422526c67976a472eaa8971626d63fbc7f097c8f50cc521c02f2`.
`V` is the completed worker encode, 1800 bytes, SHA-256
`4e76a9aeeed4f748ca6e7f9f7c7ab5b3b62d46dd7acb4d1d6902c594ca9f3e6f`.
All seven cases preserved their exact prior report bytes/hash. Direct calls
have no web job, active operation or FILES lease; those fields are recorded as
null, rather than inventing a job terminal state.

| Actual entry/scenario | Exception/status and observed video boundary | Production resources before harness cleanup |
|---|---|---|
| `run_render`, NaN source cbox, dense manual track, `coverage=concealed` | `OverflowError: cannot convert float infinity to integer` in coverage union conversion; P unchanged; no encoder opened. This is incidental early failure, **not** a general preflight validator. | No children/capture/temp created. |
| `run_render`, same NaN source, default tight coverage | `ValueError: cannot convert float NaN to integer` at actual box painting. P unchanged in this bounded observation. | Encoder still running, stdin open; capture open; stderr retained with traceback. Encoder had already been created. |
| `run_render`, SDR, finite source box; `cum[6]=(inf,0)` after six writes | `OverflowError: cannot convert float infinity to integer`. P at exception snapshot; changed to 1769 bytes/SHA `08afdf097ad1fc2d7cda835b8a42a4dade09ff7f6e54ab5caee2570aefb0fdf9` while the real child unwound under harness cleanup. | Encoder running, stdin/capture/stderr open. |
| `run_render`, HDR branch, same translation | Same overflow. P at exception snapshot; 3478 bytes/SHA `aa2efcfb68e434ebd2420df09f4b1d0fc59ce84f432cbce2618f2ea3f76cbdf6` after child cleanup. | Decoder exited but was unwaited (`returncode=None`, `/proc` zombie), stdout open; encoder running, stdin/stderr open; metadata capture already released. |
| `run_render`, cancellation true at initial checkpoint | `PipelineCancelled`; P removed by production `cleanup_partial`, even though no frame needed painting. | Encoder terminated/waited, stdin/capture closed; stderr still open while traceback/observer retains it. |
| Ordinary from-report worker, real encode completes, injected final report `os.replace` error | Job `error`, exact injected message; video P→V before attempted report replacement, prior JSON retained and staged JSON removed. Existing `job.output` still points at changed path. | Encoder and probe children waited; capture released, no live child/pipe. Observer retains stderr handle. FILES/work counts 0, active cleared. |
| Ordinary worker paused after real video SHA, cancel route acknowledges HTTP 200, then gate released | At gate video already V and JSON old. Acknowledgement invalidates operation; Task622 rejects final report; terminal `cancelled`, video V and JSON old. | At gate active owner/source pinned, count/work=1. After cancel ack still owned/active with operation invalidated. Worker cleanup then count/work=0, active cleared, no live children/pipes. |

The last case proves the boundary **before** final report publication, not a
claim that every cancellation preceding a network acknowledgement undoes a
commit already holding the report lock. Task622 permits a valid publication
that wins that lock before cancellation's acknowledgement boundary.

The mid-render snapshots demonstrate why checking output bytes immediately at
exception time is insufficient: the live child still owns final-path writes.
The exact change is bounded between the exception snapshot and completed
harness resource cleanup; no finer syscall/timing claim was measured.

Harness `finally` closes/releases captures, terminates/waits task children,
closes tracked streams and stderr files, uses bounded wait/kill fallback, then
records changed failure-output hashes and removes those task partials. All 17
observed children (including ffprobe helpers) were reaped, every tracked pipe,
capture and stderr handle closed, and both changed direct-failure partials
removed. Failed worker publication left a **complete** new final video, not a
stage; it is retained as synthetic evidence. Production does not acquire these
guarantees from the harness. Observer-held stderr references also extend handle
lifetime on successful worker encoding: an open observer handle is not proof
of an unconditional permanent production leak.

N09 stays separate: its handled HDR cancellation/write-error paths already
terminate/wait both children and miss an explicit decoder-stdout close when a
traceback retains it. This geometry-exception path **bypasses** that cleanup;
the unwaited child here does not contradict or enlarge N09's narrow evidence.

## Small reviewable split

### P16C-G: finite, positive geometry validation

Validate exactly four finite numeric source coordinates with `x2>x1` and
`y2>y1`, before coverage transforms can hide malformed extents and before
encoder creation; validate transformed coverage boxes afterward. Apply this
to the enabled render subset, preserving disabled/legacy/additive report data.
Do not depend solely on report loading: direct `render`/`render_hdr` entry
points also need preflight, and painting boundaries need a defensive check.
Give the caller a useful geometry error identifying the detection/frame.

Known report state permits preflight of finite `aoff`, `cum`/`bands`, positive
finite fps, and relevant pad/margin values before encoder creation. Extending
this to malformed structure/time fields should be an explicit contract,
not accidental `int(NaN)` behavior. Retain a per-frame check of the derived
unpadded and padded region: finite inputs can overflow on translation/padding,
and direct callers can mutate/provide state outside report loading. Do not
check only clipped or padded extents: padding can hide a reversed/zero source
box and clipping can erase the distinction between invalid and offscreen.

Finite positive boxes may extend outside a frame; positive boxes with no
intersection remain legal no-ops after ordinary clipping. No arbitrary
coordinate ceiling or invented full-frame fallback. Invalid polygons inside a
valid known box remain P16B's separate known-box fallback, not permission to
repair an invalid cbox. Existing prior geometry matrices need not be repeated.

Small verification: default tight and coverage-transformed preflight failures
open no encoder; direct/worker SDR/HDR and per-frame overflow fail clearly;
valid clipping/no-intersection controls retain defaults. This card can claim
early invalid-input preservation, not arbitrary mid-render failure preservation.

### P16C-R: comprehensive owned render-resource cleanup

Wrap acquisition through final wait in an ownership scope/`try/finally`, covering
capture/VideoWriter, decoder/encoder children, all owned pipe endpoints and
stderr file, including partial construction, geometry/callback errors and final
encoder failure. Preserve the original error/cancel meaning; harvest useful
encoder diagnostics before closing stderr. Ensure child shutdown/wait and
stream close have a defined order, bounded fallback and no masked primary
exception. Never close unrelated descriptors or kill unrelated processes.

Do not promise prior-output preservation merely by adding cleanup: current
cleanup explicitly deletes `dst`, and a live child may already have overwritten
it. Delete only an owned partial/stage once P16C-P exists. P16C-R can land
separately with an explicit output-preservation limitation; N09 can land first
independently. Keep tiny retained-traceback/setup/mid-frame/final-wait tests
focused on ownership, not another mask matrix or broad renderer rewrite.

### P16C-P: staged video and report publication under operation ownership

Encode to a private sibling stage with the selected muxer/extension semantics;
use the same mechanism for SDR, HDR and OpenCV fallback. On failure/cancel,
clean only task stages and preserve prior final paths. For video-only direct
calls, successful computation followed by one final replacement supplies the
ordinary-failure boundary. For report-producing calls, report construction,
input/output hashing and encoding must all complete against staged bytes
outside report/lifecycle locks; report provenance still names the **final**
video path and hashes the staged video. Keep complete source-report/additive
preservation and Python 3.9-compatible APIs.

Extend the caller-owned final hook to encompass the staged video, staged report
and success state, rather than publishing a video before `publish_report` can
validate its owner. For web: reserve/pin source and job lifetime through
`VAULT_LOCK -> JOBS_LOCK` admission, release admission locks, compute/stage,
then acquire the stable per-job report lock and validate the exact operation
identity/event. Never reacquire vault admission or release a lease inside
report lock. Keep active mutation gates until actual cleanup/lifetime release;
`Event.clear()` must not revive an invalidated attempt.

Inside the final transaction, replace video and report and acknowledge success
state under the same publication boundary. A video-first replacement followed
by report replacement can still fail on the second operation. Preserving
**both prior files on normal publication failures** therefore requires transient
rollback copies/references plus restoration (including removal of a new final
when no prior existed), or a narrower declared guarantee. Staging alone protects
computation failures, not that second-replacement failure. Large backup/copy
work must also stay outside the locks, under the active operation/lifetime.
Serialize cooperating readers until commit or successful rollback completes.
If rollback I/O itself fails, report an explicit failed/recovery state and retain
the required task recovery files; universal restoration cannot be promised when
the filesystem rejects restoration too.

Two ordinary replacements are **not a crash-atomic pair**. A process/machine
crash between them can leave different generations. Directory fsync and crash
recovery are separate claims; no database, generic storage framework or permanent
generation archive is needed or proposed. Preserve Task622's cancellation order:
the event reaches compute before the canceller waits for report lock; a commit
that already passed the valid-owner boundary may finish before cancellation
acknowledgement, and an invalidated old owner must publish nothing afterward.

For coherent video headers/body after replacement, the download path must
coordinate `send_file` stat/open with this publication lock, as the report path
already does, or open once and derive headers/ranges/ETag from that same open
file's `fstat`. Keep its descriptor plus FILES lease until response close; do
not hold report lock for the stream duration. Output-frame decoders should pin
the chosen file similarly. POSIX open streams can finish on the old inode;
Windows replacement of an open destination may fail and must follow the normal
publication error contract. Independent video/report requests can straddle a
completed commit even if each response is coherent; paired-generation export
would need an explicit shared snapshot contract, not an inferred guarantee.

## Dependencies and open choices

P16C-G and N09 can be small independent cards. P16C-R owns broader resource
failure handling; P16C-P depends on that ownership to discard stages safely and
must preserve Task622's existing lock/source/operation contracts. Full P16C's
current “preserve prior reports/output and clean resources” acceptance requires
G+R+P; do not close it with only early validation or decoder-stdout cleanup.

Resolve the numeric coercion policy, validation location/error type, transient
rollback mechanics/failure reporting, and whether independent downloads need
pair-level generation consistency during implementation review. Ensure staged
names work with existing vault crash-cleanup conventions and selected container
without changing encoder/default quality behavior. Available evidence is Linux
CPU correctness only: Python 3.9 runtime, true HDR fidelity, GPU, native Windows,
container/storage variants and crash durability remain unverified. Harness
Python 3.9 grammar acceptance is recorded, not a Python 3.9 product test pass.
