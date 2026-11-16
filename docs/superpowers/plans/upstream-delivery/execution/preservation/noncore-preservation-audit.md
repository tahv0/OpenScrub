# B03 non-core production-path preservation audit

Pinned upstream: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
Pinned donor: `b4d0c75f25d91510fe1692f901d11853dc7db005`.
Source review performed 2026-11-17 Helsinki time.

This supplement gives **42 distinct production/build/config paths an explicit
disposition** in [noncore-path-dispositions.csv](noncore-path-dispositions.csv).
It found **no additional independent preservation candidate beyond N01–N14**.
This closes the final-tree path-disposition gap for this assigned scope; it does
not complete B03, resolve intermediate-only commits, or reproduce proposed
changes on current upstream.

The initial assignment counted 41 paths after excluding the engine, web and
`zones_ui.py`. The existing core audit actually covers engine/web only, so the
scope was corrected to include `zones_ui.py`: **44 production paths minus the
two core paths = 42**. Its complete final diff has 27 zero-context hunks, 72
insertions and 69 deletions. These are separate from the prior 438 engine/web
hunks, whose audit was not repeated.

## Coverage and evidence

The CSV matches the `production-build-config` rows in
[preservation-paths.csv](preservation-paths.csv), excluding only `openscrub.py`
and `openscrub_web.py`. Each row identifies actual inspected source ranges or
functions, retained behavior and owner, donor lineage, excluded/already-upstream
boundary, dependencies, donor test evidence, and the remaining verification
gate. Its dispositions are:

| Disposition | Paths | Meaning |
| --- | ---: | --- |
| `adapt-owned` | 16 | Extract only the named behavior under an existing task, or update packaging as that feature ships. Whole donor files are not approved. |
| `exclude-artifact-retain-contract` | 6 | Remove the module/artifact; preserve already-owned ordinary behavior or lifecycle principles through the clean implementation. |
| `exclude-artifact` | 20 | Excluded feature/tool architecture; no new ordinary consumer established for its utility helpers. |

The six mixed excluded modules are `finding_previews.py`, `findings_web.py`,
`learning_session.py`, `review_journal.py`, `review_preview_index.py`, and
`video_learning.py`. Their contracts have explicit owners; exclusion does not
mean their entire introducing commits are removable.

Sources were read from `git show`, pinned `git diff`, function/import inventories
and selected local first-parent/path history. Temporary donor exports under
`/tmp/openscrub-noncore-audit-b4d0c75` supported source reading. No active native
implementation worktree was inspected. Removed modules received source-boundary
review, including substantive helper/workflow bodies named in the CSV; this is
not a line-by-line semantic proof of every excluded training function. Final
build/config diffs and the retained OCR, diagnostics, checkpoint and index/cache
boundaries were directly inspected.

The audit read the existing preservation and core supplements, CSV inventories,
P08–P18/O03/O05 cards and decisions/research. Donor tests were read as intended
behavior; **none were run**. Function-name inventories are identified as such
where bodies were not reviewed. No application import, unit suite, browser,
video decode/render, package/image build, Windows/GPU execution, scale benchmark
or network request was performed. No product code, Git state, runtime job,
dataset, checkpoint or weight was changed. Only this report and its CSV were
written in the SDD workspace; the existing ledgers remain unchanged.

## Retained contracts and exact extraction boundaries

### Checkpoints and ordinary report publication — P18/P06

`stop_review.py:18-72` contains the compact encoder and same-directory temporary
publication: flush, file fsync, best-effort restrictive mode, replacement and
temporary cleanup. `d9a96c3` supplies the later compact writer; `b198e0b` is the
integrated checkpoint helper. Keep the writer only if its owning P06/P18 design
needs it. It is not a complete transaction: callers must serialize the entire
read/apply/publish operation. Arrays are encoded in batches of 256 entries;
individual rows and already-retained documents are not memory-bounded by that
choice. File replacement is not a universal crash/power-loss guarantee.

`with_checkpoint`, `validate_resume` and `join_reports` (`75-198`) retain a
first-unprocessed `next_frame`, source hash/FPS/total/options, complete committed
prefix, absolute timeline arrays, suffix ID remapping, prior audio choices and
original provenance. The verifier history accumulation at `169-181` belongs to
the removed checker, not Stop & Review. Retain ordinary adopted geometry without
requiring training classification fields. The helper's source comparisons do
not replace current queue/settings/watchdog integration or actual decoder
positioning tests. The already-recorded N01 late-window smoothing seek remains
separate; the donor stop test's no-backtrack scan does not prove it.

`learning_session.preserve_render_review:918-940` confirms N06's ordinary
render/reopen contract: compare source and render timeline, then keep the complete
review row list instead of replacing it with enabled-only renderer rows. Copy
neither this training module nor its learning/refinement/verifier metadata just
to retain ordinary Keep rows and row identity. The prior N06 source-isolated
probe remains prior evidence; this pass did not run it again.

### Diagnostics — P12

`openscrub_logging.py` has useful independent failure behavior: console plus
rotating file output, a non-throwing disk failure path, context-bound counters,
heartbeat/stall records, unclean-exit marker, fault handling and shutdown cleanup.
`b7bc417` and `.gitignore` donor `803f607` remain the existing P12 provenance.

The final donor is **not** the privacy contract. `JobLog.append:119-134` persists
arbitrary UI messages, `exception` retains arbitrary exception text, and the root
warning bridge forwards library records. Token substitution/credential regexes
do not establish that OCR text, query text, paths or tool stderr are safe. The
donor defaults to 10 MiB/five backups and a 30-second monitor; P12 instead proposes
an explicit opt-in allowed-field API and its own retention/heartbeat budget.
Fault files/markers must satisfy the adopted retention/privacy contract too.
Removing learning/model stage hooks must preserve Austin's existing worker
survival, watchdog and error behavior. Packaging and platform verification stay
inside P12, rather than becoming a separate blanket logger-import change.

### Training-free OCR search — O03

`plate_text_hints.py:33-98,189-432` is an independent matching/proposal core:
bounded literal hints, match strength distinct from OCR confidence, injected
reader, inverse rotation/mirror/perspective transforms, cancellation checks,
local Tesseract timeout and whole-region protection. Its full-frame/text-contour
partial-match rejection and 1280-pixel cap are existing O03 gaps. The donor test
at `test_plate_text_hints.py:155-167` explicitly expects partial rejection; it
cannot be copied unchanged as acceptance for the user's fragment-search goal.
The 1280×720 resolution test does not validate small text in 4K.

`plate_text_subprocess.py:102-325` (`74edee0`) stages sparse updates/additions and
keeps report publication in the parent after report hash, source and vault checks.
Hints are sent through stdin; child exceptions expose a failure class, not the
raw OCR message. Resource supervision, cancellation and process reaping are
useful O03 behavior. Its `/proc` RSS/available-memory implementation is Linux
specific; tests clamping a numeric budget do not prove real process memory or
descendant cleanup. Actual timeout, crash, restart, pressure and cancellation
exercises remain required.

The tip worker imports `learning_session` and `stop_review`, imports the web
search orchestration, assumes `phase == 'learning'`, and consults `_SECTIONS`.
`plate_text_web.py` eagerly imports Findings previews, learning, video learning
and video sections; it also flushes the journal before freezing search input.
All of these dependencies must be replaced with plain source/geometry inputs,
ordinary queue/cancel/progress and the adopted report publication interface.
`980db35`'s cheap queue-time file identity, `4610615`'s committed snapshot lesson,
bounded sampling/endpoints and no overwrite of changed reports remain useful.
Ordinary skipped detection windows and an adopted P18 paused prefix must still
bound searched coverage after sections are removed. Do not reintroduce sections
to obtain `video_sections._coverage_intervals`.

Proposals must remain suggestions in the user's optional assistance workflow;
the donor's default-enabled new OCR rows are not approval to change Austin's
ordinary redaction policy. O03 selection/continuation belongs with O02. Published
pretrained inference remains allowed; excluding custom trainer/model libraries
does not exclude O04's separately evaluated pretrained adapters.

### Preview/index/journal helpers — P08/P10 and existing owners

`review_preview_index.py` records actual file identity including device/inode,
size and high-resolution times; validates before/after derived publication; and
requires the expected source revision for asynchronous listing/row builds.
`2692d0c`/`a3d4dc1` distinguish listing freshness from expensive geometry-row
freshness. Preserve those principles in P08's bounded ordinary snapshots, with
source identity and lifecycle protection. Do not retain the SQLite index or its
training/verifier/section-rich public schema. Its full serialized listing is not
evidence that total retained/browser memory is bounded. Preserve upstream's
existing warm thumbnail no-report-parse shortcut.

`finding_previews.py` maps crop coordinates and separate x/y display scales,
keeps actual representative-frame metadata distinct from requested frames,
fetches only the selected JPEG after metadata filtering, rejects stale geometry
and report reconciliation, bounds retained bytes/items/time, and explicitly
clears retained plaintext on lock/delete. These are already P08/P10/S06 contracts.
`a11a392`'s incremental totals/seen-group optimization serves this removed scan
cache, so it is not an ordinary upstream performance PR. Neither this cache nor
its confirmation leases, persistent sample queue or relinking architecture is
needed to retain the principles. N07 already records why ordinary thumbnail
pre-generation must survive until a replacement is validated.

`findings_web._cold_frame/preview:110-242` separates tolerant timestamp evidence
from an exact source-bound crop and rechecks the source after decode. Its token,
archive conflict, source-repair and confirmation machinery is excluded. Retain
the P10/P17 source/geometry contracts through minimal ordinary paths; P17 does
not adopt a dedicated off-frame Redraw workbench.

`review_journal.py`'s row/group precedence and separate source-anchor fields show
why later output edits and independent geometry must survive, but P02/P06/P07
already own that requirement. Its SQL ACK/snapshot marker/recovery protocol,
classification propagation and journal read/count caches have no remaining
consumer. Excluding the module does not remove P06's requirement for every
ordinary writer to share a proper report transaction, or P07's newer-draft,
replay and navigation protection.

### Build, dependency and Windows setup — P13/P14 and feature packaging

CPU `8fb396a`, CUDA `7063167`, Intel `bcda47f` add compatible-context pip cache
mounts and position the refresh before source COPY. Austin already has heavy
dependency/model layers, provider checks and scheduled security refreshes.
Measure those deltas. Preserve current package/runtime/model choices, current
image names and forced refresh behavior. Do not transplant the donor CUDA ORT
1.20.2 pin, optional trainer venv, retained tagged dependency image architecture,
or long root COPY lists. `.dockerignore` `9753212` keeps local secrets/media/
weights/caches out of build contexts without authorizing deletion of that data.

`scripts/build-windows-cuda.ps1:47-67,96-123` contains P14's existing `7bc2336` /
`7c47815` active-context handoff and error checks. The local docker-driver
restriction exists to resolve a retained local image; require it only if the
adopted minimal helper actually needs it. Preserve environment/location cleanup
and check external exit codes. Tip `96a3a50` also forces the training Compose
overlay: discard it. Likewise, `compose.windows-cuda.yml` defaults to training=1
and a retained dependency tag, while the test Compose file uses HTTP,
`--retain-days 0` and example D-drive paths. None becomes Austin's default.
Loopback exposure, read-only media and explicit host-path configuration may be
useful in the chosen supported setup, subject to the owning P14 tests.

`Dockerfile.cuda.inference`, its generator, shared-layer JSON, image audit and
Windows audit/parallel-image helpers remain excluded experiments. Their safe
errors, output-directory creation and parser-directive fixes have no separate
ordinary consumer. P14's real registered-model GPU execution gate is not met by
provider registration/package visibility or by the PowerShell command mocks.

`pyproject.toml` and the Windows spec must change with each adopted feature.
Keep current Python >=3.9, entry points and dependency/privacy defaults. Remove
the trainer force-include and blanket removed-module lists. Distribution imports
must work outside the source tree with removed modules unavailable; test a wheel
built through the sdist, containers and applicable updater/frozen Windows paths.
This is owning-feature validation, not a new packaging rewrite or platform
execution claim.

### Standalone scan setup template — O05 and retain Austin

The `zones_ui.py` net diff adds optional Plate coverage controls at donor
`204-210`, `plateCoverageChanged:1123-1127` and options at `1181-1184`.
The default remains Full plate; retain only O05's optional full/narrow setting,
nonnegative margin and truthful SDR/VFR/localization limitations. Keep this
downstream. The donor checks the margin even when its input is disabled in Full
mode (`1129-1132`); the owning extraction must test blank/stale inactive values
and ordinary full-mode behavior, not introduce an unrelated default scan block.

Exclude Findings navigation and custom learned-model selection. Explicitly keep
Austin's newer ordinary template behavior that the donor removes: checkbox
width/tap layout, advanced help, ONNX engine choice, plate threshold, Specific
text controls/category/empty-input validation/serialization, actionable custom
category errors, restored invalid-select fallback, and removal of the no-op
dense-faces control. These are retain-upstream decisions, not newly discovered
donor fixes. No whole-template donor copy is justified.

## Remaining closure work

No new N identifier was allocated. This is positive preservation accounting for
existing P/O contracts, not evidence that all donor code is appropriate upstream.
Excluded archive/model/dataset helpers received a remaining-consumer check;
utility hardening in a removed feature does not independently create a new task.

The 500-commit ancestry ledger remains unchanged and separate. Net-file source
dispositions cannot resolve intermediate/reverted-only improvements or merge
resolutions. Each applicable intermediate behavior still needs its own source
scope, owner/exclusion and evidence; source classification does not upgrade a
whole commit to verified or delivered. S01–S06, actual current-upstream route/
browser/render reproductions, resource/lifecycle measurements, owning package/
platform checks and upstream acceptance remain open.

Artifact validation for this pass checked exactly 42 unique CSV paths against
the inventory, nonempty fields, the 16/6/20 split and the independently counted
27 template hunks. This validates the audit artifact structure only.
