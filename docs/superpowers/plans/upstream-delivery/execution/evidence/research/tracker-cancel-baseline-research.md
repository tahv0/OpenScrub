# P10C ordinary manual-tracker cancellation baseline

Disposition: **reproduced, small cooperative-polling follow-up justified**. The real ordinary NCC tracker ignores the existing cancellation callback during repeated matching and during fail-closed held coverage. The existing web route already suppresses cancelled publication and releases ownership correctly when computation eventually exits. P10C should shorten this remaining computation, without replacing the tracker or changing matching parameters.

## Scope and provenance

Research date: 2026-11-17. Product source pin: `12919c96c6f7558136b50d7b4d85e5e6b62f1971`. A **full** `git archive` export of all 125 tracked files was made at `/tmp/openscrub-tracker-cancel-20261117/pinned`. All product source reads and imports used that export. The only additional supervisor product-document reads were P10C in `docs/superpowers/plans/upstream-delivery/02-large-video-performance.md` and the manual-tracker cancellation/release limitations in the Task621 report. The brief was read from this SDD workspace. There were no product/Git/shared-environment/user-data changes, subagents, installation, model downloads, suites, builds, stress runs, long-media work, or timing benchmarks. SDD evidence files are the only workspace writes.

The Task621 limitation is confirmed rather than duplicated: its existing outer `finally` releases the manual capture on every exit; NCC and `_hold_rest` polling remain absent. This pin also includes operation identity/publication guards in the web route; those already protect the report.

| Evidence item | SHA-256 |
| --- | --- |
| `git archive` stream for the full pin | `0db174c7af4548fda4a28048b48d546056b88f5328300fa7601dd1501753ca52` |
| exported `openscrub.py` | `275de34766d3d64592222be5633906a3dcd2557ce78e2dd7b7d6fb8075fd0355` |
| exported `openscrub_web.py` | `7762f0314df5e11e46a570af54cd20e928953e7bf92d55da7d648dad36e0fce2` |
| exported `openscrub_internal/lifetimes.py` | `dbfc317c1c878b8e8a599391578504c44a8964199f2cdae6e2ed60a6336d6743` |
| `tracker-cancel-baseline-evidence/reproduce.py` | `a4f22a6c6957410a1e8c57ff251874cb09c811a0caacfbbbb6873ee637d94c9c` |
| `tracker-cancel-baseline-evidence/results.json` | `07b94fd525581145781879fe8e017e38c47222e0db3cc1a0d3548a7b74cc5c8b` |

Runtime: Python 3.12.16; OpenCV 4.14.0; existing `/tmp/openscrub-baseline-20261116/env-opencv4.sh`. The script asserts that engine, web, lifetimes, and reports imports are from the export. It sets `OPENSCRUB_NO_AUTOFETCH=1`, routes model lookup to an empty task-local directory, and rejects `_fetch_model` before any network access. It sets OpenCV's thread count to one in its own process to keep this tiny experiment bounded.

## Reproduction and evidence

The compact script and full output are in `tracker-cancel-baseline-evidence/`:

- `reproduce.py`: actual full-module tracker and Flask/job calls; bounded synthetic-media generation, instrumentation, Event control and cleanup.
- `results.json`: full uncancelled and cancelled sample arrays, callback/work counts, actual seek target times, capture release counts, import paths, versions, source/media hashes, web outcomes and cleanup results.
- `run.log`: concise counts and actual web-route results from the successful final run.
- `verification.json`: all 125 exported files byte-compared to a fresh pinned archive; saved evidence hashes/counts and resource assertions verified without rerunning tracking.

Export once from the supervisor checkout, then run only the evidence script from the export:

```bash
mkdir -p /tmp/openscrub-tracker-cancel-20261117/pinned
git archive 12919c96c6f7558136b50d7b4d85e5e6b62f1971 | tar -x -C /tmp/openscrub-tracker-cancel-20261117/pinned
cd /tmp/openscrub-tracker-cancel-20261117/pinned
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python /home/tahv0/src/OpenScrub/.superpowers/sdd/README/tracker-cancel-baseline-evidence/reproduce.py > /home/tahv0/src/OpenScrub/.superpowers/sdd/README/tracker-cancel-baseline-evidence/run.log 2>&1
```

The final invocation exited 0. This is a bounded evidence run, not a product test suite. A prior successful invocation was repeated only after adding native-read counts, the cancellation-inside-hold case, and the explicit pre-cleanup capture assertion. No timing results are collected or claimed.

Both generated AVI clips have 31 marked 96×96 MJPEG frames at 10 fps. The window is `[0, 2.8]`, reference time 1.4, box `(32,32,64,64)`; all tracker arguments retain defaults (`step_frames=2`, `thr=.55`, `scale=.5`). Thus there are seven forward and seven backward sample steps plus the reference. The steady clip retains a textured target; the loss clip shows it only at the reference. Frame numbers are drawn outside the target template. Full generated media hashes and byte sizes are stored in the JSON; temporary media are removed.

### Real branch selection and controlled schedules

NCC selection uses the **real** `_vittrack_factory`, which returns `None` through its existing offline/missing-model error path when the explicit download blocker rejects the missing model fetch. The factory and NCC algorithm are not replaced. The loss clip **naturally** falls below the unchanged threshold and enters `_hold_rest` in both directions; no scores, margins, thresholds, geometry, native match results or native decoder outputs are injected.

The following schedules deliberately control when the Event is set while preserving the real compute:

1. A wrapper first executes the real `cv2.matchTemplate`, then sets cancellation after match #1 returns. Counts after cancellation exclude that already completed match and include subsequent calls.
2. The real `LOST the object` log callback sets cancellation before the first held append.
3. A Python line trace at the actual unchanged held-append statement sets cancellation after one held append, immediately before the second. It also counts actual append-statement visits. This trace does not replace the loop or its output.
4. The actual web case pauses after real match #1, calls actual `/cancel` through Flask's test client against a synthetic registered job, verifies its captured operation Event is set, and resumes matching. No isolated/AST route is used.

Additional **explicitly injected controls**, separate from the natural media results: `_track_person_dense` raises the existing `PipelineCancelled` type at its call boundary to test the ordinary wrapper's exception ownership; a tiny tracker factory with only `init()` supplies the Vit branch so its existing first-loop callback check can be exercised without loading a model. No actual person/Vit inference is claimed.

## Exact deterministic work observed

`grabs` counts actual `_grab_frame` invocations; `reads` counts actual `VideoCapture.read()` calls made inside the unchanged decoder; `matches` counts real `cv2.matchTemplate` calls; held counts are actual append-statement executions. These are deterministic work counts for these media/builds, **not elapsed latency or interrupt bounds**.

| Case | Total grabs / reads / matches / held appends | Work after cancellation: grabs / reads / matches / held appends | Result |
| --- | --- | --- | --- |
| steady, uncancelled | 15 / 22 / 42 / 0 | — | 15 positive-score samples |
| steady, cancel after match #1 | 15 / 22 / 42 / 0 | 13 / 19 / 41 / 0 | Exactly the uncancelled 15-sample output |
| steady, already cancelled at entry | 15 / 22 / 42 / 0 | 15 / 22 / 42 / 0 | Exactly the uncancelled output |
| natural loss, uncancelled | 3 / 4 / 6 / 14 | — | Reference score 1 plus 14 held samples |
| natural loss, cancel at first hold log | 3 / 4 / 6 / 14 | 1 / 1 / 3 / 14 | Exactly the uncancelled output |
| natural loss, cancel inside hold after append #1 | 3 / 4 / 6 / 14 | 1 / 1 / 3 / 13 | Exactly the uncancelled output |
| controlled dense-person cancellation exception | 15 / 22 / 42 / 0 | 15 / 22 / 42 / 0 | Exception swallowed; ordinary NCC returns all 15 |
| controlled Vit branch, precancelled | 2 / 2 / 0 / 0 | 2 / 2 / 0 / 0 | `PipelineCancelled` propagates at existing loop check |
| actual Flask NCC tracker, cancel after match #1 | 15 / 22 / 42 / 0 | 13 / 19 / 41 / 0 | Continued compute, cancelled report publication suppressed |

Every NCC/hold case performs **zero** calls to `cb.cancelled()`. The controlled Vit case polls once. Both uncancelled and precancelled missing-source/small-region cases return `[]`, perform zero frame grabs/reads/matches/held appends/callback polls, and explicitly release their one created capture once.

The normal NCC run executes 14 sampling iterations with three native matches each. The loss run executes two sampling iterations with three matches each, then seven held appends in each direction. Cancelling in the forward hold does not stop the later backward matching or held coverage.

## Existing entry, return, exception and ownership behavior

Pin source references below are export-relative line numbers.

- `openscrub.py:2466–2470`: callback logging is bound, capture is constructed, then failed open returns `[]`; there is no entry cancellation check. Too-small boxes return `[]` at 2487–2489. The reference-frame failure, clipped template too small and unreadable Vit seed also return `[]`.
- `2495–2505`: the person branch's `except Exception` catches `PipelineCancelled`, which is an `Exception` subclass at 3430. The dense helper has an existing cancellation raise at 2074–2075. The controlled boundary demonstrates the wrapper can swallow that signal and restart generic work. If dense samples have live fraction at least .5, `2509` returns them directly without a final cancellation check.
- `2534–2536`: `_hold_rest` appends until the time-window edge, without polling. Its edge-of-frame branch at 2527–2530 returns immediately; that is separate from actual mid-frame loss reproduced here.
- `2573–2575`: Vit's existing sampling-loop check raises `PipelineCancelled`; it neither returns `[]` nor returns partial samples. Its bootstrap reads happen before that check, as the controlled case shows.
- `2667–2714`: NCC's forward/backward sampling loops and scale sweep contain no polling. Successful output is sorted and returned. `2715–2716` encloses every return/exception after successful capture construction in the existing `finally: cap.release()`.
- `openscrub_web.py:1855–1877`: the background callback exposes the admitted lease's own operation Event to the real tracker. `/cancel` sets that Event before report-lock work, invalidates operation identity and replaces public tracking status (`1469–1509`). After tracker return, the guard at 1878–1880 suppresses output from that cancelled operation. The broad handler at 1924–1927 only updates a still-current attempt; it does not overwrite the already-replaced cancelled status. `_start_owned_thread` at 475–481 releases the lease in its existing outer `finally`, after the engine's capture `finally`.

The actual Flask case returns start200/cancel200 and immediately exposes tracking `done`, `added=0`, `error="cancelled by user"` while the blocked real tracker still owns one lifetime. Actual DELETE returns409 at that boundary. After resuming, the tracker completes the same remaining NCC work; the report remains byte-for-byte unchanged. The capture releases **once**, closes, and observes owner count1 when releasing. The background thread then ends, lease is released, owner count/work count become0, and actual DELETE returns200. Zero synthetic worker threads remain alive. This is evidence of correct existing cleanup and publication suppression, alongside missing cooperative compute checks.

## Smallest recommended follow-up

Keep the change in `track_manual_region`; no web rewiring, second capture-cleanup refactor, decoder worker/deadline scheme, frame-identity work, matcher change, or optional O02 work is needed.

Use the existing `PipelineCancelled` exception for every observed cancellation; do not turn cancellation into `[]` or a partial successful list. A local check can express `if cb is not None and cb.cancelled(): raise PipelineCancelled()`. The smallest coherent set of checkpoints is:

1. **Entry, before `VideoCapture(video)`**: an already-cancelled call does no decoder/model work. Deliberately define cancellation to take precedence over unusable input: precancelled missing-source/small-box calls raise; uncancelled unusable input still returns `[]`. A check as the first statement inside the existing `try` is a compatibility alternative if retaining one capture construction/release is required, but does not avoid that native open.
2. **Person handoff**: add `except PipelineCancelled: raise` before its broad failure fallback, and check immediately after a normal dense-helper return before deciding whether to return its samples. This covers both the swallowed exception and cancellation arriving during a completing helper. Keep ordinary non-cancellation failure fallback intact.
3. **NCC sampling-loop head, before time-bound evaluation and `_gray(t2)`**: poll each forward/backward iteration, matching the existing Vit loop's pattern. This stops repeated decoded-frame/template work at the next sampling boundary. The inner scale sweep has at most three variants, so per-scale polling is not required for the smallest scope; it may finish the current sample's bounded scale work before the next outer check.
4. **Held-coverage loop head, before each `out.append`**: poll every emitted held sample. The extra hold-internal schedule demonstrates why a sampling-loop check alone cannot stop that repeated work.
5. **Common successful generic-return boundary, before sort/return for each backend**: check once more so cancellation during the last backward held append does not leave the function as successful partial/complete work. Keep the dense successful-return check from point2. This is cooperative observation at the checkpoint, not an atomic cancellation/publication guarantee.

An entry check plus the two missing repeated-work checks is the core P10C fix. The person exception/return and final-success checks make its exception semantics consistent at the actual neighboring ownership boundaries. A one-time check immediately after model-factory return/before the generic seed read is reasonable if the intended contract also avoids that seed after cancellation during model resolution; it does not interrupt model resolution itself. There is no evidence here requiring polling inside the fixed three-scale sweep or changes inside `_grab_frame`/native calls.

## Focused regression cases for implementation

- Reuse both real marked media fixtures with default parameters; compare **all** uncancelled times, boxes and scores to the stored complete baseline arrays (15 steady live samples, and 1 reference+14 held samples). Preserve threshold, scale choices, cadence, ordering and coverage. Include `cb=None`/never-cancelled callback output equivalence.
- At the match-return boundary, require `PipelineCancelled` by the next NCC sampling checkpoint. If only outer polling is chosen, explicitly allow the remaining two scale matches in the current sample and require no later `_gray`/frame-grab calls. Repeat in backward traversal so both direction loops are exercised.
- Cancel at hold log and after one held append; require zero subsequent held appends at the selected loop checkpoint and no reverse-direction work after propagation. Add cancellation at the final backward append to exercise the successful-return check.
- Verify the declared early semantics: precancelled usable/missing/small inputs raise before capture creation if entry-before-open is chosen; uncancelled missing/small inputs remain `[]`. For every path that creates a capture, preserve release exactly once on success, early return, `PipelineCancelled`, and unexpected compute error.
- Keep a tiny controlled person-helper exception test proving `PipelineCancelled` propagates rather than restarting generic tracking; preserve fallback for an ordinary helper failure. Cover cancellation at a normal dense-helper return. These boundary cases need no detector downloads or inference.
- Repeat the actual Flask Event schedule against the real tracker: cancel status remains cancelled, no report samples publish, decoder closes before the worker lease releases, deletion stays409 until cleanup and becomes200 afterward, owners/work/thread count return0. The existing route and owned-thread wrapper should need no modification.

## Resources and limits

The script creates only two tiny AVI files, an empty model directory, and one synthetic job/report/options store in a `TemporaryDirectory` under `/tmp/openscrub-tracker-cancel-20261117/`. Writers release in `finally`; direct probes have measured one-time release assertions plus unmeasured defensive real-capture cleanup; the web gate always resumes and every created thread joins with an eight-second failure bound, including failing schedules. Synthetic files are deleted on context exit; JSON records the removed directory and confirms it no longer exists. Only the intentional full source export and SDD evidence remain. There are no child processes or background workers left running.

No elapsed-time speedup, memory benchmark, native inference/backend interrupt, native decode deadline, long-video latency or platform-wide claim follows from these counts. A native `VideoCapture` open/read, `_grab_frame` internal recovery/roll, a match call, a model factory, or an inference call can still block before Python can poll. Callback observation counts and eight-second harness failure bounds do not establish native interruptibility. P10A source-sample identity, P10B worker/deadline changes and optional O02 remain out of scope.
