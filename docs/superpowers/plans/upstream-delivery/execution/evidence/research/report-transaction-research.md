# P06B report transactions and lifecycle ownership

Research date: 2026-11-16. This is a source inventory and implementation design,
not a product change or a new concurrency-test result. Inspected pinned objects
`e21ebdf6e3ee46e6c65050dc956a9a3459152269` with `git show` into
`/tmp/p06b-openscrub{,_web,_vault}.py`; the active implementation worktree was not
read or changed. Its product sources equal Austin
`5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`; the intervening commit changes only
four lines in `test_openscrub.py`. All source line numbers below refer to these
pinned objects, not subsequent P06A changes.

Inputs: [P06/P07 plan](../../../01-core-ux-and-reliability.md),
[real-route baseline evidence](report-baseline-research/README.md), and the pinned
engine, web and vault sources. P06A has since been committed as
`c7cf1f02d98742e93a728e4b1e94d8c6bd02c318` and is under independent review;
the supervisor's selected next slice is P06D, then P06B. Those new product bytes
were not inspected in this pinned-baseline research.

## Decisions to implement

1. Keep P06A's shared `openscrub_internal.reports.atomic_report(path, report)` as
   publication only. Add a **web-owned per-job lock**, protecting latest read,
   payload application, ID allocation and atomic publication together. Do not put
   a lock around only `atomic_report`, and do not make the engine know about web
   jobs or a global path-lock registry.
2. Deliver P06D's complete-document render round-trip first if feasible. It must
   preserve raw review rows, order, disabled choices, unknown additive fields and
   audio metadata while passing only enabled `Detection` objects to rendering.
   Rendering legitimately updates output provenance and explicit CLI audio
   overrides. This fixes single-thread data loss; transactions solve a different
   problem.
3. For minimal P06B render concurrency, **reject review mutations while scan or
   render owns the job**, including `queued_render`. Set that phase under the
   same per-job lock as edit commits. Reject render/retry admission while tracking
   is running. Do not hold the report lock during inference, decoding, FFmpeg,
   normalization or output hashing. This policy avoids a render-completion merge
   API or publication callback solely for concurrency.
4. Tracking computes samples outside the lock, then locks, reloads the latest
   document, allocates `max(track)+1`, constructs/appends its rows and publishes.
   Its start check and `trackbg = running` assignment must also be atomic. Retain
   the existing one-tracker-per-job HTTP 409 behavior.
5. A report lock alone is insufficient for deletion, retention, vault transitions
   and shutdown. Introduce a small **web lifecycle admission guard** using the
   existing `VAULT_LOCK`, with active file-operation/background-operation counts
   and a deletion/shutdown admission flag. It does not hold `VAULT_LOCK` throughout
   ordinary work. Vault locking must refuse while owned work is active and check
   this at the same boundary that closes admissions. Encryption must never overlap
   an active report staging file.

No report schema revision, training state, Findings, journal, sections, database,
repository abstraction, multi-process locking or new UI mode is required.

## Exact writer and consumer inventory

| Owner / baseline location | Read, apply and publish behavior | Required boundary |
| --- | --- | --- |
| Web scan `_run_job`, `openscrub_web.py:674-768`, especially `683-684` | `run_scan` returns fresh state; `openscrub.write_report(report.json, args, state)` replaces any earlier report. Retry reuses the same directory/report path. Then stats, normalized input and phase are updated. | Scan owns a job lifecycle operation through computation/publication. No editing/tracking during queued/scanning. Lock only final report publication and corresponding state transition; validate operation generation/cancellation before publishing. |
| Engine `write_report`, `openscrub.py:6287-6333` | Constructs a new provenance/render-state/detections document; optionally hashes output; writes JSON; chmods. Used both by web scan and render, plus CLI/GUI. | P06A supplies atomic bytes. Web callers supply job ownership. Do not hold the web report lock while hashing a large output. |
| Web `job_save_edits`, `openscrub_web.py:1290-1346` | One `_load_job_report`; sparse positional `enabled`, `box_overrides`, `time_overrides`; appends `manual`; replaces `audio_redactions` only if `audio` is supplied; writes full doc; derives allowlist suggestions. | Entire latest-read/apply/publish under job lock. Calculate response from that committed doc; no success until publish succeeds. Omitted fields retain their previous values. |
| Web tracking admission and background `_run`, `openscrub_web.py:1349-1437` | Unsynchronized running check/set. Detector initialization and `track_manual_region` run in a daemon thread. Reads report only after computation (`1394`); derives FPS/camera offsets, chooses track ID (`1398-1399`), appends rows and rewrites (`1424-1427`). | Reserve running state and background lifecycle ownership atomically before thread start. Compute outside report lock. Final latest-read, validation, ID allocation, geometry construction and append/publish in one transaction. Release reservation on thread-start failure and in worker `finally`. |
| Render admission `job_render`, `openscrub_web.py:1690-1701`; worker `770-779` | Phase check/set, `cancel.clear`, and enqueue are currently separate from edits/tracking. Worker builds `--from-report report.json`, calls pipeline, records output. Its later `load_report` is only a read: comment “refresh report with output hash” does not perform a second web write. | Admit/set `queued_render` under job lock. Keep gate closed through rendering and report completion, including errors/cancel finalization. Do not hold report lock for the pipeline. |
| Engine render preparation `run_pipeline`, `openscrub.py:8505-8567` | `load_report` reads/filter rows (`8514`), then reparses source for suggestions/transcript (`8516`) and audio spans (`8530`). Normalizes input and hashes it. Constructs render state with only enabled detections. | With writer rejection, no concurrent report mutation occurs between these reads. P06D should take one detached raw-document snapshot and derive render inputs from it; no web lock need be held through normalization/hash/render. |
| Engine render completion `run_render`, `openscrub.py:8431-8502`, especially `8498-8499` | Rendering returns, then `write_report` rewrites the source report because web args specify both `--report` and `--from-report` at the same path (`openscrub_web.py:477,551`). | Render owns exclusive mutation permission until final publication. P06D preserves the complete review snapshot. Writer rejection avoids a latest-document merge callback; a narrow final publisher hook still provides cancellation-generation validation without locking render/hash work. |
| Engine `load_report`, `openscrub.py:6336-6364` | Parses complete file, then omits disabled rows and constructs typed `Detection`s; keeps dense/track/person/poly. Does not preserve arbitrary row fields. | Suitable for deriving render inputs, not authoritative editable-document storage. Never read through this API, edit its typed rows and assume a complete review round-trip. |
| `_load_job_report`, `openscrub_web.py:1103-1105` | Opens and parses fresh JSON on every call. There is no server-side report-object cache in this baseline. | A mutation must call it **inside** the transaction. Read-only callers need a detached parsed snapshot and lifecycle protection while opening/parsing, then can release report lock before expensive media work. |
| GET detections / detframe / boxes / thumb, `openscrub_web.py:1132-1248` | Read fresh doc; generate JSON or use row/offset snapshot to decode/crop video. Thumbnails use positional `thumb2_<i>.jpg` cache paths; cache-hit thumbnail route does not read report. | Hold report lock only while acquiring snapshot, not decode/crop. Lifecycle ownership covers any cache/media writes and prevents deletion/vault from racing. Existing stale thumbnail invalidation is not solved by report transactions. |
| Scan thumbnail `_pregen`, `openscrub_web.py:686-750` | Independent daemon; reads report once, computes thumbnail todo, decodes and writes many files. Exceptions are swallowed. | Acquire/reserve background lifecycle ownership before launching. Snapshot report briefly; decode outside report lock. Cancel/delete must either wait for/refuse ownership or stop it cooperatively before removal. |
| Scan normalized-video provenance read, `openscrub_web.py:752-760` | Reads doc to update job video path. | Detached read during scan's existing owned operation; finish before phase becomes editable. |
| GET report `openscrub_web.py:1717-1724`; UI raw-report/audio hydration `2344-2347` | `send_file` serves source path, UI fetch parses full audit document. | Atomic publication supplies a complete version. Protect path open/lifetime from vault/delete; do not serialize an entire network transfer with report lock. See response-lifetime note below. |
| Restart/unlock `rehydrate_jobs`, `openscrub_web.py:3722-3819` | Reads disk report provenance to rebuild job metadata; registers under `JOBS_LOCK`. Reportless uploads become failed jobs. Skips already registered IDs; no persistent report cache. | Startup is single-threaded before worker start; unlock rehydration must stay inside the lifecycle transition until decryption/registration finishes. Initialize the same job lock/internal fields in **both** reportful/reportless constructors. |

There are no persisted report checkpoints, no quad-override edit route and no
separate server report cache at this baseline. `box_overrides` are four-number
rectangles (`1290-1307`); tracked `poly` is an engine/sample output, not a fourth
edit endpoint. “Next checkpoint” in the cancel docstring means cooperative
callback polling, not JSON checkpoint publication. Do not import donor-only
features to fill these nonexistent integration points. GUI (`openscrub_gui.py`)
passes an optional `--report` to the same engine and does not introduce a web
concurrent writer.

## Existing locks, lifetime gaps and possible overlaps

`JOBS_LOCK` is a non-reentrant `threading.Lock` (`openscrub_web.py:276`). It guards
registry changes and selected queue/cancel/retry checks, not report content or
most phase writes. `enqueue` acquires it itself (`627-636`), so calling enqueue
while already holding `JOBS_LOCK` deadlocks. Worker validation holds it only
through assigning `WORKER.current`, then releases before `_run_job` (`657-668`).
One queue worker serializes its own scan/render actions, but request handlers and
tracking/thumbnail/retention/vault threads run independently.

`VAULT_LOCK` is another non-reentrant lock (`3189`). Only setup, unlock and
`_vault_lock_now` take it (`3242,3286,3303`). Ordinary job handlers and report
writers do not. Current vault routes/watchers release `JOBS_LOCK` before taking
`VAULT_LOCK`; there is no existing joint report/vault lock protocol. `UPD_LOCK`
(`3102`) owns update status, not job files; retain its independence.

Concrete allowed overlaps today:

- Two sparse POSTs load the same doc and overwrite each other; proven through
  threaded real HTTP in the baseline evidence. Atomic replace changes the failure
  from partial JSON to complete stale JSON.
- Manual/audio/time/box saves can overwrite tracker rows or vice versa. Tracker
  read timing is late, but read/apply/write is still unprotected.
- Two simultaneous tracker POSTs can both pass the running check. Their workers
  can allocate the same `track` ID and overwrite each other's appended rows.
- Saves and tracker commits are accepted during queued/scanning/rendering. Scan
  or retry can replace the report; render reads several versions and later
  rewrites a stale report. Render admission itself races another render POST.
- `job_delete` (`984-1029`) checks active phases under `JOBS_LOCK`, releases it,
  removes files, then pops the registry entry. It ignores tracking, thumbnail
  generation and in-flight saves. A retained job dict can still be used after
  deletion. Windows retry/marker handling does not close this race.
- `retention_sweep` (`3824-3837`) deletes old directories without any active-phase
  or tracking/file-operation check. It can race scan/render as well as edits.
- Vault lock/auto-lock checks only queued/scanning/rendering/queued_render
  (`3219-3225,3497-3505`). A new admission can occur between the check and
  encryption. Tracking/in-flight edits are absent from busy checks. The request
  hook's unlocked check (`857-863`) is a check, not a lifetime guard.
- `_vault_lock_now` encrypts then clears the key (`3240-3248`); unlock sets the key
  **before** decrypting and releases `VAULT_LOCK` before rehydrating (`3303-3307`).
  Job requests can therefore observe unlocked state while decryption is active.
- Vault `encrypt_tree`/`decrypt_tree` (`openscrub_vault.py:163-185`) remove **every**
  `*.tmp` as a crash leftover. They can unlink an active P06A staging file. A
  different suffix alone is insufficient: encryption would then treat the staging
  file as ordinary plaintext to encrypt. Prevent overlapping tree transitions.
- Shutdown `_vault_lock_atexit` (`3251-3267`) checks only phase; it can encrypt
  while a tracker/save/thumbnail daemon is active. SIGTERM directly calls it and
  `os._exit` (`3886-3893`); there is no daemon join or mutation drain.

Engine cancellation polling exists in scan/render/normalization and the ViT
manual-tracker loop (`openscrub.py:7598,3987,4195,6547,2574`). Web tracking supplies
an `L` callback with only `log` (`1373-1375`), so inherited `cancelled()` always
returns false (`openscrub.py:3450-3451`). Polling is not uniformly present in every
tracker backend, so commit-time invalidation remains necessary even after fixing
the callback.

## Small implementation contract

### Per-job report/state transaction

Create one `threading.RLock` and internal operation generation per job in
`new_job` and both `rehydrate_jobs` constructors. A small web helper can initialize
them consistently; no lock is serialized in options/report/public metadata.
Initialize synthetic test jobs the same way. Use a stable lock on the job object;
never replace it when clearing ordinary review state.

The job lock protects report transactions, mutation admission, `trackbg` ownership,
render/scan/retry phase transitions, and generation invalidation. Progress/log
updates can retain their existing lightweight behavior. A small context/helper
is enough; keep field-specific edit application in the existing handler.

For a save:

1. Parse the request body before acquiring the report lock where this does not
   depend on report contents; enter lifecycle ownership before touching job files.
2. Lock the job; revalidate live job identity and writable phase, including any
   deletion/invalid-operation token. Allow ordinary review/done and existing
   failed/cancelled reports; return a clear 404 when there is no report rather
   than the current unhandled `FileNotFoundError`/500.
   Reject queued/scanning/queued_render/rendering with explicit HTTP 409.
3. Load the newest committed doc, apply exactly the supplied sparse fields and
   append manual rows, then `atomic_report`. Keep every unknown field untouched.
4. Produce `total` and `suggest_allowlist` from the committed snapshot; unlock.
   A failed parse/application/publication never returns `{ok:true}`.

For tracking, atomically check writable phase and existing running state and
reserve a lifecycle background operation **before** starting the thread. Capture
the job identity and operation generation. Detector construction/video tracking
remain outside the report lock. Override `L.cancelled()` to consult cancellation
and captured-generation validity. When samples are ready, lock and check identity,
generation, cancellation and writable phase again; reload latest doc; compute FPS,
offsets, track ID and rows from this version; append/publish; only then expose
`trackbg.done/added`. Allocating the ID before this final transaction is incorrect
even if the final append reloads the report. On cancel/stale completion, publish
zero rows and a clear terminal tracking status; all exits release lifecycle
ownership. Use identity comparison of the status/reservation object if needed so
an old thread cannot overwrite a later attempt's `trackbg` status.

Respect the lock order when reserving: acquire the lifetime token before entering
the job lock, check/set running under the job lock, then transfer that already
reserved token to the successfully started thread. On refusal/start failure,
release it after unlocking. Do not acquire a new `VAULT_LOCK` reservation while
holding the job lock. Keep the token until worker cleanup actually ends; assigning
`done`/`cancelled` phase or status is not sufficient to release it early.

`max(track)+1` means the existing report's integer track domain and preserves its
current semantics. This is process-local allocation, not a persistent globally
unique-ID service. P07 `manual_id` replay application must later execute within
this same latest-document transaction; it should not add a second independent
load or lock boundary.

### Render ownership and P06D integration

Render POST locks the job before checking phase, tracking and setting
`queued_render`; it clears cancellation and enqueues without taking `JOBS_LOCK`
recursively. If an edit wins the lock first, render uses that committed version.
If render wins first, the edit gets 409 and must retain its browser draft. The
gate starts at queue admission, not when the worker eventually reads the report.
Repeat render POSTs preserve existing “already in progress” success behavior.

Keep the gate through the entire pipeline and terminal publication. A cancelled
render must remain noneditable until its worker actually exits; setting only an
early public cancelled phase would reopen the writer race. A retry or render
cannot begin while an old tracker owns the job, even if its cancellation flag was
set. Render POST while tracking returns 409 rather than silently omitting a track
whose request had already been accepted.

With this policy P06D's detached raw review snapshot can be rewritten at completion
without overwriting concurrent edits, because none are accepted during render.
No latest-document merge callback is needed for that policy. Keep P06D's
document merge/content rules separate from concurrency: preserving full rows is
required even when the render has no overlap. If product behavior later requires
edits during rendering, that is a larger policy change: acquire a render snapshot
under lock and merge **only** render-result provenance into the latest doc under
a final transaction, while explicitly recording which edit snapshot produced the
output. Merely wrapping stale completion publication in a lock would still lose
edits. Do not add that mechanism in this minimal P06B slice.

Scan/retry uses analogous ownership: phase closes writer admissions before
queueing; final report publication occurs only for the still-current operation.
Cancellation can arrive after `run_scan` returns, including during final hashing.
For the strict cancellation contract in the tests below, use this narrow concrete
integration: add optional keyword-only `publish` to engine `write_report`, default
`None` resolving to P06A `atomic_report`; construct/hash the doc first, then invoke
`publish(path, doc)`. Add default `Callbacks.publish_report(path, doc)` that simply
calls `atomic_report`, and pass it from `run_render` to `write_report`. Override it
in `WebCallbacks` to take the job lock, validate the captured operation generation,
live identity and cancellation, then atomically publish. Web scan completion
passes the same bound publisher directly to `write_report`. Invalid ownership
raises `PipelineCancelled` before publication. CLI/GUI use the unchanged default
publication behavior. Preserve P06A's restrictive `NamedTemporaryFile` permissions
(0600); the supervisor confirms P06A removed the old post-publication chmod.
Do not add it back in the publisher hook. This P06A detail was supplied by the
supervisor rather than inspected from the active implementation worktree.

This hook is needed for the final lifecycle check, **not** a mechanism to merge
concurrent edits: render-active writer rejection still owns that policy. It also
keeps output hashing/document construction outside the report lock. No callback
is added to the stdlib atomic helper itself, and no web lock leaks into the engine.
An alternative that keeps direct engine publication must relax the strict
cancellation claim; locking only after `run_pipeline` returns is too late.

### Lifecycle guard and lock order

Use existing `VAULT_LOCK` to serialize **admission decisions and vault tree
transitions**, not every report transaction. Maintain internal active ownership
counts and a deleting/shutting-down gate. A small context plus explicit background
reservation/release methods is sufficient; no general storage/service layer.
Use a store-wide total for vault decisions and per-job counts for deletion;
intake before `new_job` has an ID still contributes to the store-wide total.

An admission takes `VAULT_LOCK`, briefly takes `JOBS_LOCK` to resolve/check exact
job identity, checks vault transition/deletion/shutdown state and increments the
ownership count, then releases both. Only afterward may it acquire the job report
lock. It must release the report lock **before** releasing ownership, because
release takes `VAULT_LOCK`. This guarantees:

```
admit: VAULT_LOCK -> JOBS_LOCK; release both
work:  job.report_lock -> optional short JOBS_LOCK identity check
       release job.report_lock
exit:  VAULT_LOCK (decrement ownership)
```

Never acquire `VAULT_LOCK` while holding a report lock or `JOBS_LOCK`. Never wait
for a thread or join a worker under any of these locks. Never hold `JOBS_LOCK`
across JSON I/O, hashing, FFmpeg, encryption or `enqueue`. Vault transition busy
checks use `VAULT_LOCK -> JOBS_LOCK`, release `JOBS_LOCK`, then encrypt/decrypt under
`VAULT_LOCK`. Waiting report transactions retain an active lifecycle reservation,
so a vault attempt returns busy rather than entering their files.

Concrete integration:

- The save handler holds ownership through publish; read-only report routes hold
  it while acquiring their detached report snapshot. Background tracker and
  thumbnail reservations persist through their last file access, not merely the
  request that started them. Worker scan/render owns it for its full operation;
  queued phases also remain a vault busy reason between request and worker.
- New-job creation, render and retry admission must use the same gate, so a busy
  check and starting encryption cannot admit new work between them. `new_job`
  writes `options.json` and creates directories, so guarding only report writers
  would miss an existing tree writer.
- Delete admission, under `VAULT_LOCK`, checks no queued/running phase and no
  outstanding file/background owners; refuse with 409 while busy. Close that
  job's admission gate before releasing the lock. Then invalidate its operation
  generation under the report lock and perform the existing reap/marker logic.
  Late holders of a job dict fail identity/gate validation. Retry cleanup threads
  operate only on condemned directories and remain coordinated with vault tree
  transitions. Do not hold a report lock across the existing sleep/reap retries.
- Retention must call the same deletion-admission primitive, skip busy jobs and
  mark/retire jobs consistently. Preserve marker handling and age policy. Startup
  marker cleanup occurs before work starts; runtime retention and delete retries
  need lifecycle ownership. Age alone cannot authorize racing live work.
- Manual lock, auto-lock and shutdown share **one** guarded busy check; include
  ownership counts and background tracking/thumbnail work, in addition to phases.
  Return 409 for manual lock, defer auto-lock, and preserve an honest “not locked,
  work still active” shutdown diagnostic when busy. Do not invent daemon-join
  guarantees in this report PR.
- Unlock must retain closed admissions until decryption and `rehydrate_jobs`
  finish; publish unlocked state/key only after successful completion. Calling
  rehydration after releasing the transition guard creates another admission gap.
  Setup needs the same transition protocol when creating/enabling the key.
- A failed encrypt/decrypt transition must remain closed to job mutations until
  recovery/unlock completes, because some paths may already be transformed.
  `VAULT.key is not None` alone is not sufficient to express that transitional
  state. A small internal transition flag is sufficient; no persisted state model
  is proposed here.

Response lifetime matters separately from detached JSON: `send_file` may retain
an open FD after the handler returns. For `/report`, read immutable bytes while
owned and return those bytes with original attachment name; report-sized buffering
is already required by edit routes and avoids retaining a mutable pathname/FD.
If maintaining streaming is important, retain lifecycle ownership through the
WSGI response iterable's close, with a tested exactly-once release on errors and
disconnect. Video/download/cache send-file paths need that streaming lifetime
option to claim whole-job vault/deletion safety. An `after_request` decrement
alone is too early. This is an application lifecycle concern, not a reason to
hold the report lock over network transfer. Preserve Range and Content-Length
behavior; test the actual configured WSGI path before selecting the response-close
mechanism. Ordinary status/log requests need no file-lifetime lease.

Cancel should set its `Event` immediately, before waiting for a report lock, then
invalidate the operation generation under that lock. Old background computations
must not become valid when a later render/retry clears the reusable Event. The
cancel response can wait for a currently committing JSON transaction to finish;
its completion establishes the boundary after which invalidated work cannot
publish. It must never wait for a whole render/inference operation. A publication
that completed before cancellation linearized remains valid; cancellation need
not undo a committed review edit. Final worker phase/error cleanup must confirm
the same operation identity so obsolete completions cannot reset newer state.

The HTTP acknowledgement boundary is the generation invalidation under the same
lock used by the final publisher, **not** the initial `Event.set()`. Thus cancel
arriving after publisher validation but during fsync waits for that publication,
then invalidates and acknowledges. If cancel acquires the lock first, the later
publisher rejects. A final Event check alone would leave a check-to-replace race
and cannot support “no obsolete publication after cancel acknowledgement.” This
stronger semantics can briefly delay the cancel HTTP response by one report
serialization/fsync; the event still reaches compute promptly. Holding the lease
through all actual cleanup also keeps vault/delete busy during that delay.

Shutdown must not synchronously reacquire a non-reentrant lifecycle mutex already
owned by the signal-receiving thread. Retain an explicit, bounded busy/failure path
in SIGTERM handling, or arrange shutdown work after leaving any such critical
section. A timeout is not authorization to encrypt files still in use. This needs
a deterministic test of the hook, not a process-kill test that risks user data.

## Minimal delivery slices and intermediate risks

### P06A temporary-cleanup fix versus broader coordination

The P06A reviewer reported an additional concrete interleaving while this report
was being finalized: vault tree enumeration captures `.report-*.tmp`, the atomic
writer replaces/removes it, and subsequent unconditional `os.remove` raises
`FileNotFoundError`, aborting lock before key forgetting. The reviewer owns the
focused execution proof; this report did not reproduce it. Ignoring ENOENT fixes
that exception but not a staging file created after tree enumeration or a save
that recreates plaintext after encryption completes. The supervisor selected the
bounded P06A fix: ignore only `FileNotFoundError` for vanished temporary entries,
retain ordinary source-file errors, and add a deterministic regression. Broader
encryption/publication coordination remains explicitly P06B work. This report does
not claim the cleanup tolerance establishes vault lifecycle safety.

If a separately reviewable coordination slice is useful before full stale-edit
transactions, the following boundary is coherent:

1. Use the existing `VAULT_LOCK` for a **complete web report publication**
   (creation of staging file through replace/cleanup), and for complete vault
   lock/unlock tree transitions. Inside the publication guard, recheck locked or
   transitioning state before calling `atomic_report`. A blocked request whose
   old admission check succeeded must fail after a completed lock; a mutex without
   this second check is insufficient.
2. Use a small web publisher, routed through the optional engine publisher hook
   described above for scan/render. The default engine/CLI publisher remains
   `atomic_report`; it must not import web vault state. Save/tracker call the same
   web publisher. Hashing and report document construction stay outside the vault
   publication critical section. Report reads can acquire the vault guard for
   open/parse and recheck there, releasing it before applying edits/computing.
3. Keep latest-read and publish as **separate** guarded operations in this small
   slice. That deliberately does not promise stale-edit preservation; P06B adds
   the per-job transaction covering both. Two complete stale saves can still
   overwrite each other, exactly as before P06A.
4. Move the busy decision into the same vault transition guard. Put new-job file
   creation/queued admission, render/retry queued admission and tracker running
   reservation under that gate as well; include running trackers in vault busy
   checks. Otherwise accepted computation can begin between check and encryption.
   Unlock keeps admissions closed through decryption/rehydration and only then
   advertises unlocked state. Do not recursively acquire existing non-reentrant
   `VAULT_LOCK`: use a private already-locked transition/publisher primitive where
   appropriate.
5. Test actual save staging versus lock in both orders: publisher already holds
   guard (lock waits, then encrypts complete committed report), and lock already
   holds guard (save cannot stage and fails 423 after transition). Also test a
   request that loaded before lock, then tries late publication. No `.tmp` failure,
   partial JSON or plaintext report may remain after successful locking.

This is a coherent **report publication/vault** slice, not a claim to fix
all pre-existing job-file lifecycle races. Background thumbnail writers, streamed
handles, retention/delete and shutdown still require the lifecycle ownership
slice below before claiming whole-job safety. If P06A acceptance requires that
broader claim, it must absorb the lifecycle foundation rather than merely tolerant
temporary cleanup. The later counter-based foundation avoids serializing every
report through `VAULT_LOCK`; replace this temporary global publication critical
section with owned admissions once it lands, retaining the same safety contract.

### Full delivery sequence

1. **P06A:** atomic bytes, its existing failure tests, and the selected vanished
   temporary-entry cleanup regression/fix. It does not promise overlapping-update
   preservation or vault lifecycle safety. Other staging/publication interactions
   remain vulnerable until the coordination slice above or full lifecycle
   ownership is included; state that limitation explicitly.
2. **P06D:** preserve complete report content on render/reopen and its exact audio
   override/provenance semantics. Derive all render inputs from one detached raw
   document if changing this path anyway. This can merge independently, but
   render still overwrites concurrent edits until P06B's mutation gate.
3. **P06B lifecycle foundation:** job operation admission/deletion/vault/retention/
   cancellation generation and background ownership, including response lifetime
   where file routes are protected. Preserve behavior/defaults except concrete
   busy rejection. It may be a prerequisite PR if too large for review alongside
   sparse-save locking. Ship with real-route lifecycle tests; do not claim sparse
   update preservation yet.
4. **P06B transactions and worker gate:** per-job latest-read/apply/publish, tracker
   final append/ID allocation, scan/render admission/publication ownership. Can be
   one PR with item 3 when the changes remain small; otherwise require the
   lifecycle foundation as a dependency. A narrower branch locking only saves
   and tracking is reviewable research but is **not** the completed P06B contract:
   render, deletion and vault can still invalidate its correctness.

P07 browser draft/snapshot/replay safety follows the transaction contract. The
server's new 409 gate must leave browser drafts pending; never let `saveAndRender`
interpret JSON from a rejected save as permission to render. No performance/no-op
optimization belongs in these slices.

## Deterministic production-route tests

Use synthetic ordinary reports, a temporary `JOBS_DIR`, full imported Flask app,
per-thread clients or a loopback threaded WSGI server, bounded Events and explicit
thread joins. All route/application parsing and actual atomic publication remain
real. Stub costly inference/tracking/encoding at their computational boundary;
do not replace the save handler with a miniature reimplementation. Include at
least representative real-socket cases; pure Flask clients do not establish
configured server/response-close behavior.

Do not reuse the baseline's two-party barrier **inside** `_load_job_report`: after
correct serialization only the first request can reach it, so that test deadlocks.
Instead pause the first publisher after its read, observe the second request at
the report-lock acquire attempt, and then release the first publisher. A test-only
instrumented lock can signal that acquire attempt while retaining real locking
semantics; no production test hook is required. Use Events rather than sleeps as
the ordering proof. Record mutation-generation/publication events if useful.

| Regression | Controlled schedule and assertions |
| --- | --- |
| `test_overlapping_sparse_saves_preserve_both_choices` | Pause first save before real atomic publication; start second POST disabling a different index and observe its lock attempt. Release first. Both return 200; final choices both false, untouched fields equal. Also assert no second report load occurred before first committed. |
| `test_overlapping_combined_edits_preserve_independent_fields` | First request changes box/time and adds manual row; second updates audio plus an unrelated enabled choice. Force same queued-lock overlap. Assert all changes plus old suggestions/transcript/unknown fields survive, exactly one manual row appended, response totals/suggestions correspond to each commit. Audio remains whole-list replacement when explicitly supplied. |
| `test_tracking_commit_reloads_latest_manual_and_audio_edits` | POST real `/track_object`; fake `track_manual_region` blocks after entering compute and returns fixed samples. While blocked POST manual/audio/time/box/choice changes and await 200. Release tracking. Poll real `/track_status` to terminal state. Assert tracking rows, earlier manual addition and all edits survive, IDs/geometry use current report. Repeat inverse commit order by pausing a save at lock attempt while tracker commits. |
| `test_two_tracking_requests_have_one_owner` | Simultaneously release two real POSTs from a start barrier; instrument admission lock attempts and keep fake compute blocked. Exactly one 200 and one 409; fake compute invoked once. No status replacement or leaked lifecycle reservation. Complete accepted run, then start/finish another real tracking request and assert its ID exceeds first's ID and all earlier rows/edits survive. This preserves existing single-tracker policy while covering ID freshness. |
| `test_tracker_allocates_id_in_commit_transaction` | While tracker computes, commit a legitimate synthetic prior track through the tested owner/helper before releasing it (or complete an earlier queued tracker in a focused publication-boundary test). Assert allocation sees newest max ID. This supplemental boundary test is not evidence that two simultaneous trackers are an intended supported route behavior. |
| `test_render_admission_serializes_with_save` | Save wins lock: render request waits, then fake pipeline observes updated input. Render wins lock: save returns 409, report unchanged, no draft success assumed. Repeat for queued render before worker begins and running render. Repeat render POST retains already-in-progress semantics. |
| `test_render_refuses_running_tracker` | Block tracker compute; real render POST 409 and no queue entry. Finish tracker; render POST accepted and renderer sees newly committed rows. Reverse: tracking POST during queued/running render gets 409. |
| `test_cancel_is_responsive_during_render_and_prevents_late_publish` | Fake renderer waits outside report lock; real cancel POST returns before fake work is released and sets callback event. Release fake work through the real cancellation/publication boundary; verify no obsolete completion/report/provenance publication after cancel acknowledgement. Do not mock away the final owner validation. |
| `test_cancelled_tracker_cannot_publish_after_event_clear` | Block compute, cancel via route, record generation change, then arrange a later allowed operation to clear the reusable Event. Release old compute; no appended rows or overwritten newer tracking status. Tracker ends cleanly and releases busy ownership. Verify later tracking/render succeeds. |
| `test_delete_refuses_owned_work_then_prevents_resurrection` | Pause save publication or tracker/thumbnail compute. DELETE returns 409 while owned; after owner ends, DELETE succeeds. Force a stale captured job reference/completion to resume after removal and assert no file/directory/report recreated. Test marker/retry path with first reap failure and no revival on rehydrate. |
| `test_retention_skips_active_job_and_reaps_after_release` | Set old job directory mtime; pause owned tracker/save/scan. Invoke real retention sweep; files and registry remain. Release work, invoke sweep again; existing age policy removes job and stale operation cannot recreate it. |
| `test_vault_lock_cannot_remove_active_report_staging` | Enable vault with synthetic key; pause actual atomic helper after staging exists but before replace. Real lock route returns 409; staging and prior report remain; release save and assert 200/valid JSON. Lock succeeds afterward; fresh job mutation returns 423. Unlock/rehydrate restores exact committed doc. |
| `test_vault_admission_closes_check_then_encrypt_gap` | Pause real tree encryption after transition admission; start save/new-job/render/track requests. They must not enter file work. Finish encryption: requests fail locked, no plaintext recreation or success acknowledgement. Pause unlock decryption likewise; requests cannot enter until all files and registrations are ready. Include encryption/decryption failure recovery state. |
| `test_autolock_and_shutdown_honor_background_owners` | Run the shared single-step transition decision with owned tracker/thumbnail (without a 30-second watcher sleep). Manual returns busy, auto-lock defers, shutdown logs skipped lock without encrypting. After release, transition works. Inject already-held lifecycle mutex in shutdown hook to prove bounded return/no self-deadlock. |
| `test_stream_close_releases_lifecycle_ownership` | Real HTTP Range/download/report requests with consumption paused; lock/delete remains busy until response closes. Then close normally and via disconnect, assert exactly-once release and subsequent transition succeeds. Preserve expected bytes and Content-Length. Needed if the lifecycle slice claims streamed-file protection. |

Also retain P06A failure injection: second waiting transaction must proceed after
first serialization/flush/replace failure; previous JSON stays valid, first gets
failure, lock/counts release, second committed edits survive. Different jobs must
be able to acquire their report locks independently; pause A's publication and
complete B to catch accidental global serialization. Tests must end with zero
active ownership and no surviving threads; a timeout is a failed assertion, not
an accepted flaky result.

## Evidence limits and remaining implementation choices

The existing evidence proves sparse lost updates and single-render content loss;
this source pass establishes allowed overlaps, not their measured occurrence
rate. No new socket, tracker, vault or Windows execution was performed here.
P06A's actual helper details and P06D implementation are concurrent work and were
not inspected. Recheck exact integration points after those branches land.

The WSGI iterable close mechanism must be selected/tested against actual server
configuration; handler teardown is insufficient. All tracking backends need
audit for cancellation polling/resource release, but stale-result rejection is
mandatory regardless. Existing positional thumbnail cache invalidation and
rehydration's `output.mp4` assumption remain separate known limits. CLI/GUI
processes targeting a live web job directory are outside the in-process guard;
make no cross-process safety claim.
