# B03 historical dispositions — noncore-only passes 1–3

Pinned Austin: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
Pinned donor: `b4d0c75f25d91510fe1692f901d11853dc7db005`.
Source review: 2026-11-17 Helsinki time.

This supplement now examines **320 commits** and gives each an exact SHA,
first-parent scope, hunk source references, disposition, owner, reason and
remaining gate in [history-dispositions.csv](history-dispositions.csv).
It allocates **no new independent N finding**. The useful generic contracts
have existing P/O owners; it does not repeat the 438 final engine/web hunk
review or the 42 noncore final-path dispositions.

**The noncore-only historical source subset is fully dispositioned: 320 of
320 commits, with zero unexamined subset rows.** This includes all 125 commits
with production paths, 195 support-only commits and 14 first-parent merges.
**B03 remains incomplete overall:** the complementary 180 core-touching
historical commits are a separate scope, and mapped behavior still requires
its owning implementation, reproduction and acceptance gates. Source closure
does not mean code was extracted, a proposed improvement works on Austin,
or tests passed.

## Exact subset and coverage

The universe is the existing 500-row `BASE..DONOR` ledger. For each commit,
the delta is `git diff SHA^1 SHA`, including merges. The noncore-only subset
contains commits whose production changes do not touch `openscrub.py`,
`openscrub_web.py` or `zones_ui.py`. Support-only commits are included. This
filter was checked independently against actual first-parent changed paths
for all 500 inventory rows, rather than trusting titles or family labels.

| Coverage | Commits | With production paths | Support-only | Merges |
| --- | ---: | ---: | ---: | ---: |
| Exact noncore-only subset | 320 | 125 | 195 | 14 |
| Examined here, cumulative | 320 | 125 | 195 | 14 |
| Not examined here | 0 | 0 | 0 | 0 |

The other 180 inventory commits touch at least one of the three excluded
core/template paths. They are outside this historical supplement, even when
their final source already has a function/hunk disposition. Consequently
exactly 180 of the 500 commits have no row here. This is coverage accounting;
the complementary core-history audit owns their historical disposition.

The 320 cumulative rows comprise:

| Supplemental disposition | Commits | Meaning |
| --- | ---: | --- |
| `mapped-owned` | 40 | Generic retained behavior or a mixed split has an existing owner. |
| `support-owned` | 60 | Relevant test/CI assertions must be adapted to the clean owning feature. |
| `exclude-artifact-retain-contract` | 96 | Exact architecture is excluded; the named ordinary contract survives. |
| `removed-system-only` | 104 | Actual changed artifacts and their consumers are excluded, with no retained ordinary consumer established. |
| `already-upstream` | 4 | Source-equivalent tests or pure test relocation already present in pinned Austin. |
| `historical-support-only` | 15 | COPY ordering or test-harness/indentation repair; no independent product behavior. |
| `superseded` | 1 | Exact intermediate assertion is contradicted by a verified descendant source replacement. |

Thus **196 rows retain owning implementation/test gates**; 124 receive an
excluded, source-equivalent, support-repair or superseded disposition. These
are commit counts, not bug or PR counts. The 104 removed-only rows were not
derived mechanically from path/family names. In particular, output-choice
journal changes, OCR snapshots, index revision fences, Windows scripts and
mixed docs have retained-contract rows instead of blanket removal.

The first pass examined 128 rows (51 production, 77 support, five merges).
The second pass appended **122 rows: all remaining 74 production commits,
48 directly related support deltas and all nine remaining merges**. Every
prior CSV row was kept byte-for-byte; second-pass rows say `Pass 2` in their
scope and evidence fields. The second pass did not redo first-pass SHAs.

The third pass appended **70 support-only rows**, keeping every prior 250
CSV row byte-for-byte. Pass-3 scope/evidence fields identify these additions;
no previously examined SHA was rereviewed or replaced. All actual introduced
or modified test/docs/CI bodies were read, with relevant consumers already
source-reviewed in the earlier passes.

Against the untouched original CSV, the 320 rows were 314 `investigate`,
three `PR` and three `removed-system-only`; prior evidence was 314
`metadata-path-hunk-inventory`, three `source-inspected-subset` and three
`path-inventory`. Pass 3 accounts for 70 additional formerly metadata-only /
investigate rows. The original **463 metadata-only / 469 investigate** counts
are deliberately unchanged pending supervisor reconciliation by exact SHA.
These source dispositions do not classify every removed family as harmless,
or imply that all 500 historical commits are complete.

## Retained behavior and boundaries

### Inference-only Windows handoff — P14

The chain is source-distinct, and selecting its latest commit is unsafe:

- `0dc7155c61` introduces the retained CUDA/PyTorch dependency-image helper,
  training=1, fingerprinting and hard-coded `default` builder. The image
  architecture is excluded. External exit checking, BuildOnly behavior and
  environment/location cleanup are reusable only with a retained helper.
- `7bc23366bb` and first-parent merge `776245a75f` use the active Docker
  context's builder rather than forcing `default`. Their mock/static tests
  cover context selection and rejection of a nonlocal driver. The local
  driver restriction serves daemon-local retained tags; it is required only
  if the chosen inference helper has that need.
- `7c47815eca` (#65) explicitly selects `docker --context` for inspect,
  direct Buildx, Compose build and startup. **Compose receives no
  `--builder`; direct dependency Buildx still does.** Its tests exercise
  cold/warm helper paths, BuildOnly and ordinary start. Preserve the
  context/Compose compatibility under P14 while excluding the retained tag,
  training defaults and fingerprint machinery.
- `96a3a500a9` (#89) adds the training Compose overlay to both build and start
  through one array, plus corresponding docs/tests. That exact delta is
  removed-only. It does not supersede the useful inference context fix.
- `da50a6e7ca` (#80) creates the explicit audit output's parent directories
  and adds a mock/CI check. The only consumer is the excluded CUDA image
  audit helper; generic mkdir handling does not justify that architecture.

PowerShell parsing and command mocks are intended evidence, not a real
Windows/Docker/GPU run. P14's registered-model GPU inference gate remains.
Austin's normal image names, runtime pins, exposure and retention defaults win.

### Cache/security refresh and packaging — P13/P18/P12

`8fb396aaec`, `70631678f6`, `bcda47fb1b` and #56's actual first-parent delta
add per-variant pip cache mounts and move the existing security refresh after
heavy dependencies/models and before source COPY. Preserve the existing
forced `SECURITY_REFRESH` path, current package/provider/model choices and
scheduled updates. The CUDA trainer-venv changes and subsequent tagged-image
architecture are excluded. `9753212d71` excludes local secrets/media/weights/
caches from the build context; it authorizes no deletion of local artifacts.
The static tests in `ca383005a4` are useful layout checks, not measured builds.

`075042d7f7`, `2a3b90c7f6`, `7382a86227` and `df3adf19b9` distribute the
checkpoint helper in wheel/sdist or CPU/CUDA COPY and add early import/syntax
checks. Retain owning-feature installed-startup tests. `5bd01bbc80` only
reorders `stop_review.py` and `openscrub_logging.py` in the same COPY list to
satisfy a contiguous-string guard; it does not change the packaged module set.

`803f60735c` adds `/logs/` to Git exclusions. P12 remains opt-in, bounded and
allowlisted; ignoring a log directory does not make arbitrary UI/exception/OCR
messages safe to persist. The synthetic OCR token probes added by `ae6f1f28e9`
are test diagnostics, with no authorization to become production log fields.

### Checkpoint preservation — P18/P06

The entire introduced `b198e0b3ae` helper and `1284d04689` test module were
read. Preserve whole-frame/first-unprocessed checkpoints, source hash/FPS/
total/timeline validation, complete reviewed prefix, suffix track/person ID
remap, audio/provenance, restart and no publication of incomplete output.
The early writer uses indented JSON; the later compact writer is a separate
lineage already covered by the final-source supplement. Atomic replace does
not serialize competing read/apply/write transactions.

The actual synthetic scanner test uses `--categories none`, `--no-backtrack`
and scrolling off; the worker test stubs `run_scan`. Neither establishes N01's
dense-smoothing prefix-read bound, actual VFR frame identity or long-video
performance. Training labels/sample archives are not prerequisites for the
ordinary geometry/Keep-row checkpoint contract. P18 must preserve Austin's
current queue generation, validation, settings and watchdog behavior.

### Optional OCR and revision fences — O03/P08/P10

`980db35074` avoids full-report reads/hashing in the queue request, uses a
nonblocking busy-writer response, pins cheap file identity and checks it on
both sides of the worker read. The worker hashes the frozen bytes and checks
report/source again before publication. `c6d4034da0` expressly tests no queue
read/hash and no state/report mutation on busy rejection. Keep this under
optional pretrained/local OCR assistance; remove training phase/session and
section dependencies. `4610615248`'s journal snapshot call is excluded, but
the committed-choice snapshot requirement survives O03/P06. Ordinary skipped
scan windows and an adopted P18 paused prefix still constrain searched frames.

`2692d0ca0b` distinguishes cached listing freshness from expensive row/geometry
freshness. `a3d4dc1315` adds caller-provided expected identity, preventing stale
in-memory rows from being tagged with a newer report revision. `6f333f6a74`
checks identity before and immediately before legacy preview-relink publication.
Keep these existing P08/P10 contracts through ordinary bounded caches, while
excluding the SQLite index, training-rich public schema and Findings relinker.
Read tests in `8aa0a188dd`/`b9a193a2ac` substantiate intended separation and
asynchronous behavior; they have not been run.

### Sparse saves, explicit output and filters — P02/P06/P07/P09/P15

`99351d8eee` and `939f93b841` distinguish untouched baseline state from an
explicit same-value human Blur action, then require an acknowledged repeat to
be sparse/no-op. Preserve that ordinary output/replay distinction; remove
checker override/clear-label encoding. `07b1e027ba` waits for both DOM status
and in-memory explicit choice before Save, without retrying lost clicks;
`fa88b44943` repairs the introduced indentation. These are test lessons, not
new behavior candidates.

`9bab0efc91`, `1b457e5fcd`, `c887ac583e` and their actual tests/docs preserve
batch/row chronology and independent geometry. Keep that P02/P06/P07 contract
without journal ACKs or human-classification propagation. `22d25ed6eb` and
`3284eb1b85` explicitly correct the deferred-publication claim: only
render-intent opt-in can defer; **Save-only still publishes report.json before
ACK**. Excluding the journal must not turn acknowledged ordinary Save into an
uncommitted background operation.

The P15 status/type/output tests and docs were read through `fc117b77f1` and
`99d3d40d1e`. Retain view-only predicates, complete-group counts, mixed-output
membership, hidden/unmounted choices and object/draft identity. Handled status
requires adopted ordinary explicit output semantics; default enabled=true is
not human review. Similarity renderer changes only supply a predicate
composition lesson; the similarity workbench is excluded.

The history contains conflicting preview policies. `0cecd6dd08` changes the
test to require maxCold=0; its descendant pinned-tip
`test_review_performance.py:330` requires maxCold=1 for visible misses. The
ancestry to `8710a7cb13` was checked, and tip
`test_preview_throughput.py:234,271` explicitly tests automatic visible loading
and bounded retry. Thus the exact `0cecd6dd08` assertion is superseded.
`93bea3ef21` also contains useful bounded retry/cancellation work and is mapped
as a split, not wholly discarded. `docs/CONFIRMED_FINDINGS.md:72-79` still
describes manual-only missing previews (and an old 64MiB budget), so donor
prose is not a reliable acceptance oracle. Clean P09/P10 docs must match the
adopted bounded implementation; this is not an independent new task.

## Closures require actual source evidence

Four already-upstream rows are based on source, not merge ancestry:

- `495e5197fe`: all seven newly added top-level test/fixture definitions for
  server-path containment, APAC audio, lane/container behavior and encoder
  errors have identical attribute-free AST in pinned Austin.
- `402510acff`: only moves the model-registry document-refresh test; its AST
  is identical in Austin.
- `09179ecf0d` and `18d9b68ae3`: added PhiMemory no-history-iteration and
  insertion-order tests have identical AST in Austin.

Donor OCR tests using `_normalize_ocr_hyphens` or
`_adaptive_text_scan_stride` were not called exact upstream equivalents.
Austin's actual `normalize_ocr_text:74`, Tesseract use at 102 and
`text_scan_stride:7130` already retain the stronger normalization/local-motion
contracts. Their relevant synthetic assertions are test adaptation work,
without restoring obsolete APIs or donor backend behavior.

The recovery/roundoff series `4680396b19` through the named-model recovery,
`02f8e3f2dc`, `f2457e4240`, their tests/docs and #86 is genuinely excluded.
Actual new functions operate on named training `run.json`, frozen corpora,
candidate hashes, held-out verifier assessment and training publication.
Tip call-site search confirms `_RUN_METADATA_LIMIT`/`_run_metadata`/
`finalize_retained`/`_heldout_proposal_box` consumers remain in those systems.
It does not change ordinary report metadata limits, normal job retry or a
published pretrained model adapter. P17's separately owned manual geometry
tolerance is not implemented by the removed held-out helper. No user training
data, checkpoints or weights were inspected or removed.

## First-parent merge evidence

All five first-pass merges were scoped against the first parent. Exact Git blob
endpoints were compared for every changed path with the already source-read
constituent range; this is stronger than assuming a topic title proves the
merge's effects. The CSV includes all first-parent hunk references.

| Merge | Source-read first-parent contents and endpoint evidence |
| --- | --- |
| `36636c473a2c3edd60c7344bce08ee2cfa0f1809` (#56) | Dockerfiles, ignores/workflow/docs/cache tests match `8fb396a`/`7063167`/`bcda47f`/`9753212`/`1874bfc`/`5a2323e`/`1112595`/`ca38300`; also includes `887b06e` timeout and combined `07b1e027..fa88b44` choice-test repair. |
| `4152d3eee5719de9c021c2629449630c6ec591fd` (#60) | Tagged dependency image/Compose/script/tests plus parser/docs: exact path endpoints match `7626768`, `3a04967`, `0dc7155`, `cf9b915`, `cba6f7b..4ca8843`, `3a98004..a580c35`. |
| `776245a75fb42809ecfcf05a7eccb60f86645cf9` (#61) | Active context code and static/mock tests/docs/CI match `7bc2336`, `2704018`, `6bc025c`, `74bd082`, `d81d523..f114a2f`. |
| `7c47815eca36d63b08e1b3cc291489e999ec5446` (#65) | Entire first-parent patch was read directly: context-only Compose fix plus distinct excluded retained-image defaults/docs/mock changes. |
| `6f2ab4c60eb6bb12c6e175998208a66737a1087c` (#86) | Exact old/new endpoints equal reviewed verifier/export/docs/test ranges `02f8e3f`, `f2457e4`, `d9f4499`, `f1e849e`, `bc4eb82..d1a42ae`; no generic engine/web/template delta. |

## Second-pass production closure and support evidence

Pass 2 source-read every remaining noncore-only production delta, including
actual introduced functions and support hunks within those commits. Exact
consumer searches were made against the pinned donor objects. It closes the
historical production-path scope for this **noncore-only subset**, while
at that checkpoint retaining 70 unexamined support-only rows and all owning
behavior gates. Pass 3 below closes that remaining source scope.
This does not cover production hunks in the separately scoped 180 core-touching
commits. No new independent N identifier or task was allocated.

Pass 2 dispositions are 53 `removed-system-only`, 48
`exclude-artifact-retain-contract`, 16 `support-owned`, three
`historical-support-only` and two `mapped-owned`. The 66 rows retaining an
ordinary contract or test gate do not approve importing an excluded module.
Examples and actual consumers matter more than their commit titles:

- **Training-only bodies were checked.** `f865a8e68a` introduces the entire
  reviewed-example YOLO exporter; `f3eb49bf7d` the complete optional CUDA
  trainer/candidate publication tool. Their coordinate, atomic-file, split,
  ONNX-smoke and path helpers have no remaining ordinary consumer.
  `1cc2835d62` changes only the dataset collector's corrected-crop geometry;
  `a815b1a4d0` only the isolated trainer launch/preflight;
  `31e68f3b92` only trainer validation budgets/shared-memory overlay; and
  `5de246fdf0` only training split/exposure history. Their corresponding
  integration merges have byte-identical **complete first-parent patches**,
  not merely similar subjects. Ordinary P17 coordinate tolerance remains
  independently owned; these helpers are not prerequisites for it.
- **Model-library hardening stays scoped.** `7f4999c47d` adds a validation
  digest LRU, sanitized errors and a seekable temporary-upload adapter. The
  actual changed tests cover this custom-refiner library's refresh, vault,
  restart and ZIP upload boundaries. Tip consumers of `_validate_onnx` are
  that library and custom candidates. O04 published pretrained adapters are
  still allowed, but this fork-specific library is not automatically their
  implementation.
- **Preview identity survives architecture exclusion.** `14c964123b` /
  `bf4083b8be` reconcile actual stored frames with tracked intervals and
  reject ambiguous geometry; `abb1976563` reports the shown representative
  rather than the requested synthetic row. `a123d530a4` / `b134527709` pin
  an immutable displayed JPEG even if a newer exact sample appears;
  `dd617204a8` separates frame-source identity from disposable JPEG keys;
  `ac6620f033` repairs a legacy explicit-null source-hash fallback; and
  `1b17010871` gives expanded crops distinct keys instead of overwriting
  bytes named by an existing key. These refine P08/P10/P17, without importing
  persistent Findings reconciliation, archive approvals or SQL storage.
- **Resource fixes in the removed cache are not ordinary performance PRs.**
  `a11a392631` maintains incremental SQL totals/seen groups, and
  `080a69f70f` / `e4fd7e7fa9` / `afbacf1841` repair schema/rollback/page-limit
  behavior. Actual callers belong to the removed scan-time image store.
  Tests in `3feb539286` likewise measure that store. N07's ordinary thumbnail
  strategy and the existing P11 cost lesson remain; no new P11 task is created.
- **Journal removal does not erase output intent.** The entire initial
  `7ad56a2fac` journal and `f4f75a1452` confirmation/corner integration were
  read. Preserve ordinary durable ACK, independent row geometry, identical
  replay and later-edit precedence under P02/P06/P07. An explicit same-value
  Blur/Keep action must remain distinguishable from untouched default state
  and an acknowledged repeat. This needs no custom label, archived example,
  handled status or journal-only ACK. The pass-1 same-value/save-only
  publication boundaries remain authoritative.
- **Diagnostics are a contract, not the confirmation system.**
  `a0e5c62ca5` / `58661a8f53` / `32522207ee` introduce slow-stage timing,
  a test threshold and removal of report-size metadata. Actual stage tests
  include logger failure without changing the successful save receipt.
  Retain only P12's opt-in bounded allowed fields and nonthrowing behavior.
  Removing a field in this donor trace does not certify the logger's wider
  messages or exception payloads as privacy-safe.
- **Display and geometry approval remain separate.** `d6b164f499` crops
  verified original pixels before transport, preserves full dimensions and
  source identity, and gives explicit retries a bounded longer deadline.
  The actual odd-coordinate full-frame/crop equality, PTS, unchanged-draft
  and no-implicit-output tests belong to P10/P17/P16.
  `b6e7ef7107` / `9ae00efc6d` allow view-only clipped off-frame pictures while
  rejecting unsafe geometry writes; clipped pixels do not validate a mask.
  The corrected test syntax/type handling is separate historical support.
- **Dedicated Redraw remains excluded.** The bodies introduced by
  `49618e4747`, then single-frame/replay fences, metadata-only state,
  async source hash, one-frame candidate/prewarm and saved-state endpoint
  were all read. Keep exact-source, frame-local manual geometry and
  nonstale publication contracts under P17/P10/P08/P06/P07. Do not import
  the dedicated repair routes, archive workflow, journal anchors, report
  schema or automatic classification. The donor's 48MiB single-frame
  candidate is a per-job check; it does not prove aggregate memory or
  complete lock/delete cleanup by itself.
- **Issued pixels require bounded plaintext lifetime.** `07632ac3bc` retains
  issued JPEGs with byte/item/time limits; `9c2578f8dd` gates retain against
  vault encryption. Donor tip call sites clear retained bytes in ordinary
  lock/delete paths. These remain P08/P10/P17 lifecycle requirements for
  whatever ordinary cache is adopted. The tests read in `70be0ea25c` /
  `503eb8bd8a` include a later repair to a vacuous success assertion;
  `clear_retained` appearing in `co_names` still does not establish runtime
  ordering/race safety. No lease architecture is required just to obtain
  the contract.

The full `d32b5b0dc3` smoke/setup introduction is mixed retained support:
explicit/idempotent Blur/Keep, matched masks/frames, exact streamed download
bytes and cancellation/fallback, installed startup and completed-job recovery
have P owners; compound holes/narrow fixtures are optional boundaries.
`9f63f6e766`'s complete `tools/check_cuda.py` executes the resolved plate model
and requires profiled CUDA nodes with fallback disabled. That is useful P14
acceptance evidence, unlike a provider/import-only smoke. Its historical ORT
pin is not permission to downgrade current Austin. Loopback/read-only mount
ideas do not make HTTP, retention=0 or D-drive paths product defaults.

The audit/generator introductions are now source-closed for this subset:
`a61d0aa5a8`, `cd42f0c126`, `ed6bb3224e`, `66362f79cf`, `2333934360`,
`39ac81f526` and their repairs/tests/docs/CI exclusively serve the excluded
parallel audit/shared-image/generated-image experiment. The generated image
still packages workbench modules. Parser-directive, newline and output-folder
repairs do not independently justify that architecture. The helper's GPU
smoke checks imports/device visibility, not registered-model execution. P13
security refresh and P14 inference-only/context contracts remain independent.
Likewise all actual bodies/support in the gallery/bulk-training #79 change
operate on confirmed example revisions, overlays and custom training scopes;
they do not implement ordinary P15 filtering.

### Additional first-parent merge checks

| Merge(s) | Actual source evidence |
| --- | --- |
| `10857936bb`, `b0c322d9cb`, `4d413e395e`, `266942f9a8` | Complete first-parent patches are byte-identical to source-read `1cc2835d62`, `a815b1a4d0`, `31e68f3b92`, `5de246fdf0`, respectively, including changed docs/tests. |
| `8c3ee3c1939bbdb97745fcfc432a60ecceb06370` (#73) | Every changed path's exact old/new blobs match reviewed trace implementation `a0e5c62..3252220` and test `3868969..a7aead0` ranges. |
| `f2789662e9cebd74a1cfdaa87ebf3d586a80c30b` (#74) | Every changed path's exact old/new blobs match `73021c2..3a8f4bf`, test `e83c6e0..0735426` and CI `fd286a8`. |
| `f8184111652c4873dc546831a4224517802dd262` (#78) | Every changed path's exact old/new blobs match reviewed audit/wrapper/manifest plus `0d85065`, `7844497`, `a2bea8e`, `a0c253f` tests/docs/CI. |
| `31847fa4ee8507c9b2cb7c009a4725aa66ac231b` (#79) | Exact old/new blobs match reviewed constituents on six paths. `findings_web.py` includes already-integrated off-frame context, so whole-file endpoints differ: the complete first-parent web diff was read, and its ordered added/removed lines exactly match `474b5010f8`. No merger-only ordinary behavior was inferred away. |
| `b18db3e00147eb47b12b8cf067948117f21a81e3` (#81) | All eight changed paths' old/new blobs match reviewed generator/generated recipe/helper and `a50d4c0`, `a6d2892`, `9e78d71..7372041`, `5402f4f`, `fa57980` tests/docs/CI ranges. |

## Third-pass support closure

All 70 formerly unexamined support-only commits now have specific rows:
16 `support-owned`, 33 `exclude-artifact-retain-contract`, 12
`removed-system-only` and nine `historical-support-only`. Thus 49 additional
rows retain owning assertion/adaptation gates; 21 are source-closed excluded
artifacts or harness repairs. No pass-3 commit changes production paths or is
a merge. Every first-parent test/docs/CI hunk was read; a family label was not
used as a substitute for source evidence.

The mixed training/model support was split explicitly. `29c1adba74`'s complete
workflow/spec/tests mainly verify the excluded custom-refiner manifests,
ZIP/ONNX validation and pinned model copies, but installed-package proof,
paused-prefix/resume and reviewed Keep/quad assertions survive under the
owning features. `259543cffc` only tests that library's validation digest LRU.
The complete early trainer workflow, training guide and dataset/trainer tests
(`ed6360f8ca`, `a014db1c9c`, `f3ae9cea5b`) have no ordinary consumers; their
path/integrity/geometry helper assertions do not require new product tasks.

`9be518c6a8`'s smoke is explicit evidence for **same-value ordinary output
intent**: it sends `verified_labels={}` and `output_choices={i:True}`, checks
`output_choice_explicit`, then requires an acknowledged repeat to clear the
pending maps. `e94827a133` independently tests ordinary Blur/Keep on a large
review, geometry/draft retries, exact regenerated artifact bytes after restart
and filtering without losing drafts. Preserve these under P02/P06/P07/P15/
P16/P17 without custom labels, archive writes, handled status or journal ACKs.
The separate required corner CI job in `84715aa1ed` preserves coverage while
isolating its process; an ignore in the shared suite is not removal of tests.

The journal-overlay adaptations are not evidence that ordinary Save may ACK
before report publication. Initial journal crash/snapshot tests retain useful
P06/P07 restart/conflict assertions, while archive-rebind/collector-only fixture
repairs are source-closed. Ordinary output saves can remain independent during
an unrelated failure, but render must wait for acknowledged geometry. The
classification blocker panels and negative-classification draft discard policy
are excluded. In particular, **ordinary Keep must not silently discard a dirty
polygon** just because a donor Not-a-plate branch did so.

The source/recovery test sequence is mapped to P07/P08/P10/P17, not a new
confirmation architecture. `78168170a2`, `cd1e43ce36`, `b251b8ccbd` and
`1287447c55` distinguish definite pre-write rejection/new attempt ID from lost
ACK/same ID, bound retries, and protect newer geometry/source identity.
`006a3bd564` tests the explicit-null provenance fallback. Exact-frame fixtures
in `ffb5696098`/`d46f5c8916`/`2b4d2fd0e2` distinguish cached neighbor frame300
from requested299, show the actual source and never silently transplant a
pending polygon. Classification/archive assertions remain excluded.

The full dedicated-repair test bodies were read as mixed evidence. Preserve
source-verified frame-local geometry, sibling/output independence, idempotent
replay, nonblocking source verification, bounded preview work, and saved
geometry independent of JPEG eviction. Exclude the repair workbench/routes,
SQL anchors/state endpoint, automatic output reset and training approval flow.
Early unconditional disk-eviction409 expectations must be reconciled with the
later already-reviewed retained-issued-pixel tests; disk eviction alone is not
proof that displayed bytes are unavailable. No actual cache/runtime test ran.

The final support sequence further narrows recovery safely:
`62f7389b59` permits **display for explicit review** of changed crop/baseline on
the same verified source/frame/box, while denying automatic old-shape
confirmation; an uncertain pending save cannot silently rebind.
`f22588379e` requires new human geometry when the current detector box differs
and retains the old draft rather than auto-importing its corners.
`ef08ac5139` only corrects the extracted helper boundary. These actual later
assertions, rather than the earlier stricter display fixture in `12d8b42fcb`,
are the final source evidence. P17 still owns ordinary manual correction;
this creates no independent N task or dedicated repair-workbench requirement.

## Validation and remaining work

Artifact checks confirmed the independently derived 320-commit subset,
**320 distinct subset SHAs**, exact first-parent identities, nonempty scope/
source/owner/reason/gate fields, all actual hunk references, and the counts
above. The CSV SHA set equals the subset exactly; none of the separate 180
core-touching commits is included. Appenders verified that each checkpoint's
prior CSV bytes remained unchanged. Attribute-free AST and Git-blob comparisons
are static source checks only. No app import, unit suite, browser, package/image
build, real video decode/render, GPU/Windows run or scale scenario was executed.

The initial inventories/counts, core/noncore supplements and product/Git state
were not modified. Only this report and its supplemental CSV were written in
SDD; helper scripts/patch exports were placed in `/tmp`. No network operation,
real job/model data access, issue/PR publication or other external action was
performed. The native worktree was not used.

Noncore historical **source-disposition uncertainty is now zero unexamined
rows**, while the 196 retained-contract/test rows still carry their named owning
gates. Overall B03 closure still requires reconciliation with the separate
180-commit core-history scope and owning implementation/reproduction/acceptance/
S01–S06 gates. Neither final-path exclusion nor this complete noncore supplement
is a claim that the full 500-commit audit or runtime verification is complete.
