# B03 mixed/core historical dispositions — completed production-source accounting

Pinned Austin: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
Pinned donor: `b4d0c75f25d91510fe1692f901d11853dc7db005`.
Source review: 2026-11-17 Helsinki time.

**All 180 mixed/core commits now have historical production-source dispositions, including all 48 merges; no SHA remains unexamined.** This closes this supplement’s historical production-source gap. It does not claim an exhaustive reread of every excluded-system test assertion or narrative document: three large introductions and two associated merges explicitly record selected meaningful support-test scope below and in the CSV. No new independent omission beyond N01–N14 was established. The retained behavior maps to existing P01–P18/O01–O05 ownership, with the specific P/O owners in each examined row. Source disposition is not extraction, reproduction, acceptance or delivery.

[core-history-dispositions.csv](core-history-dispositions.csv) has one row for every SHA in this supplement's exact subset. Each examined row records the actual first parent, changed production paths, the exact inspected production/support scope, first-parent hunk references, concrete behavior, disposition, owner, reason and remaining gate. The first pass left 59 rows explicitly unresolved. The continuation examined those rows individually and preserved every earlier disposition. No family was marked removed solely because its final artifact was excluded.

## Independently verified scope

The universe is the original 500-SHA `BASE..DONOR` ledger. Actual changed paths were recomputed with `git diff-tree SHA^1 SHA` for every SHA, including merges. The subset consists of first-parent deltas touching `openscrub.py`, `openscrub_web.py` or `zones_ui.py`: **180 commits, including 48 merges**. It is disjoint from every row of the complementary noncore-only historical supplement. No final-tree function/hunk disposition was counted as a whole historical commit examination.

| Coverage | Commits | Merges | Non-merges |
| --- | ---: | ---: | ---: |
| Exact assigned subset | 180 | 48 | 132 |
| Examined here | 180 | 48 | 132 |
| Still unresolved here | 0 | 0 | 0 |

| Disposition | Examined commits | Meaning |
| --- | ---: | --- |
| `mapped-owned` | 92 | Specific retained generic behavior or mixed split with an existing P/O owner. |
| `exclude-artifact-retain-contract` | 58 | Exact architecture is excluded; named ordinary behavior/lifecycle principles retain existing owners. |
| `historical-support-only` | 13 | Intermediate malformed merge repair or isolated harness/source-slicing compatibility change. |
| `already-upstream` | 7 | Pinned Austin source already implements the actual behavior, sometimes more strongly; not inferred from ancestry. |
| `removed-system-only` | 9 | All actual changed behavior and consumers are excluded, with no independent ordinary consumer found. |
| `superseded` | 1 | Actual descendant source contradicts the exact earlier manual-only preview prose. |

Thus 150 rows retain owning adaptation/reproduction gates; 30 have support-repair, source-subsumed, removed-only or superseded dispositions. These are commit counts, not independent bugs or PR counts. Against the untouched original inventory, the completed supplement covers 149 metadata/path/hunk-only rows, ten hunk-inventory rows, fifteen previously partial source rows, five source-compared rows and one probe-scoped row. The original evidence fields/counts were not rewritten.

The continuation resolved all 59 previously unresolved SHAs: 33 merges and 26 non-merges. It added no independent N finding and did not change the first pass’s 121 rows. Exact source reuse and limits are recorded per SHA, rather than inferred from commit titles or ancestry.

## Material historical accounting

### Ordinary output and acknowledged Save — P02/P06/P07

The explicit-action introduction `39b4ed8` and integration `a75f139` replace toggle ambiguity with idempotent named Blur/Keep visible actions, pressed state and all-member output changes. The source tests execute emitted actions against grouped sightings. Classification labels and archived examples are not prerequisites for that contract.

`3e92c90`/`b62523e` fence flush, Save ACK and render to the captured job/view, surface failed requests and keep review open. The 7,000-row browser/stress tests were read as intended assertions, including lost response followed by a newer gesture, server rehydration and delayed body-read timeout. They were not executed and do not satisfy S01–S06.

`5e96740`/`90e67b6` add dirty-choice version/ACK state, unload/navigation protection and independent output-choice backup after corner-save failure. The donor still clears all `BE.adds`, box/time overrides and `MAN` after a full ACK: output-choice revision alone does not establish protection for newer manual/box/time/audio drafts. This is the existing N14/P07 boundary, not a new omission. Keep Austin's existing recurring-name allowlist suggestions (`217f323` repairs their loss in the introduced journal shortcut).

The `6de072b`–`f5195fe` history separates ordinary Save from render-intent journal deferral. The initial shortcut defers too broadly; the later code requires an explicit `defer_report_write` opt-in only when a render worker will materialize the report. **Save-only still publishes authoritative report.json before ACK.** Excluding the SQLite journal does not remove that durability contract or P06's requirement for all ordinary writers to share a transaction. These rows do not reopen superseded implementation mechanisms already resolved by the current P06/P07 work.

### Preview production, reading and scheduling — P05/P08/P09/P10

The actual `5e96740` delta and tests demonstrate two independent P05 contracts: temporary/replace publication preserves an already-open JPEG reader, and freezing response bytes prevents a Content-Length/stream race. A producer rename alone does not freeze HTTP response bytes. The added Cheroot tests were read, not run.

`9ea3fae`/`d15c69f` introduce a single read-only report snapshot with device/inode/size/high-resolution time identity, independent writer documents, a serialized-size ceiling and vault purge. Retain bounded revision discipline while preserving Austin's existing warm-JPEG fast path: the donor changes thumb handling to load report metadata before every hit. A 32 MiB serialized-size threshold does not bound Python object memory.

`d9e5d12` through `d66ae10` show concrete async cache races and repairs: freeze the revision before reading; pass expected identity into publication; reuse a validated source-bound document during row rebuild; and let cleanup evict only its own worker token. `6c41f74` and `6d5e8fd` add compact-cache relinking and journal reader protection. Their SQLite/Findings artifacts are excluded; the ordinary revision, stale-worker and plaintext lifetime principles remain P08/P10. `a833e3e` explicitly purges retained in-process JPEG leases on actual/deferred deletion and before vault encryption.

Preview policies are historically contradictory. `276532f` makes missing previews manual-only, `0372875` documents it, and `5820ea1` tests maxCold=0. Directly inspected descendant `aeb24ce` deletes that branch, documents automatic visible loading and changes the assertion to maxCold=1 with at most three cache reads. Therefore the exact manual-only prose is superseded. Useful explicit retry/button/cancellation behavior is retained separately, so the earlier mixed commits are not wholly discarded.

`aeb24ce`, `dc6bdda`, `312d91f` and `52274f3` retain lazy mounting, complete metadata/group membership, visible reranking, single cold decoding, bounded retries and ahead-of-scroll cache work. Fixed lookahead/page margins remain measured implementation choices. The donor retains HTML for pending cards and complete metadata; lazy DOM alone is not proof of bounded total browser memory.

`5d55f8e`/`2fac3e4` preserve normal short process deadlines and a separate explicit <=60s retry, validate exact source-space crop dimensions and inspect original PTS before crop. `496e017` converts to RGB before odd-coordinate crop, avoiding chroma-induced pixel differences. This remains existing P10 behavior, not a claim that the donor decoder is already an Austin endpoint or that its CFR test proves every source type.

### Mask fidelity and minimal geometry — P16/P17, downstream O05

The complete `8697c28` introduction and `539432c`/`a056dff`/`c79cb29`/`4a6675f` follow-ups were read with their support tests. They include N02 touched-2x2 HDR chroma union, N03 finite/degenerate polygon fallback, ordinary coverage/padding/face-shape alignment, pending-edit preview and renderer dense-winner selection retaining row indices. Compound holes, per-mask schema and changed dilation semantics are distinct choices. Region integer conversion remains outside the polygon catch; no complete invalid-box guarantee is inferred. The donor full-square HDR test is not independent proof of the sparse chroma regression already established by current research.

`e15c5eb` blocks pointerdown until indexed image and mask match, cancels stale add/drag anchors and keeps active valid dragging. `98c3231` mixes downstream narrow residual-text/active-range fixes with exact-frame identity, unchanged/legacy shape preservation on time edits and precise indexed times. Its from-start exact decoder is historical evidence, superseded by the bounded decoder contract; it is not proposed again as the current implementation.

The actual `ccff62f` integration adds ordinary Stop/Resume frame boundaries, partial-tail tracking/audio restrictions and quad rendering, but also malformed duplicate fragments directly removed by `32e48ce`/`66ceea8`. Its N01 initial-seek mechanism is not a new proposal: preserve the current P11A smaller sequential-grab direction and its failed-position/cancellation constraints. Do not cherry-pick the intermediate mixed engine file.

The early crop/modal/rotation series `7c0688f`–`47b0c77` preserves source/display coordinate transforms, finite convex in-frame validation, pointer routing, common-close ResizeObserver disposal and rigid rotation without clamping individual vertices. Training sample creation/automatic verified labels and blanket track quad copying are excluded. The later 409 series keeps definite rejection separate from uncertain ACK, preserves byte-identical replay IDs, limits same-image refresh, requires crop/baseline/source proof and retains newer draft versions. Dedicated Redraw/Findings/archive workflows remain excluded; retain only minimal P17/P07 contracts. `eedef89` retains existing N05 plain Detector wording and disclosure that grouped/seed corners do not optically track changing perspective, while custom checker score/group machinery is excluded.

### Local view predicates and optional OCR — P15/O03

The grouped sampler (`b86bfef`) contains a generic lesson: group before filtering so one representative still owns complete members/time span; unknown tracks remain independent. Its confidence-ranking/training policy is excluded. `8209a82` turns switching views into a local predicate with no Save, report fetch or editor replacement; hidden bulk membership and pending/failed drafts survive.

`c3a8c7a`/`fa46442` and `64afc3c` add status/type/output filters, complete-group counts, unmounted matches and mixed-output membership. Handled requires every member explicitly handled; default enabled=true is not review. Use ordinary P02 output actions for clean handled state, excluding classification labels/similarity/sampler machinery. Type/output predicates remain independently useful.

Actual first-parent merge `b22652c` includes more than a browser startup string: queue-time cheap file identity/nonblocking writer acquisition, deferred worker read/hash with before/after fences and publication revalidation. The tests forbid a full report read/hash in the queue request or state mutation on busy rejection. Preserve this under optional training-free O03, removing learning-session/phase and section dependencies. Published pretrained inference remains allowed.

## Source-backed closure and merge evidence

The seven already-upstream rows have actual source proof:

- `ea73eef`/`212da9b`: Austin `PhiMemory` uses separate alpha/digit buckets, insertion serials and compiled rapidfuzz batches; its first-match/gating rules already cover and strengthen donor Python-loop indexing/order fixes. These are behavior-subsumed decisions, not byte-identical-file claims.
- `d6e9efc`/`c874ade`: Austin's actual dash/slash regexes and `normalize_ocr_text` before recognition retain stronger normalization than the donor Tesseract-only hyphen helper, including the Unicode escape repair.
- `0610cd5`: Austin `text_scan_stride` contains the same two-local-cell threshold, high-motion half stride and quiet doubling despite a different helper name/input guard placement.
- The two upstream integration merges add APAC/decodable-audio gating, container-aware codec fallback, browser audio-lane mapping, explicit first-decodable transcription and encoder stderr diagnostics, plus the media-root containment before size lookup. All nonblank added production lines occur in pinned Austin except its superseded 1.0.88 version string; six complete audio-helper ASTs match exactly. Actual changed caller blocks were read too. This source comparison does not replace Austin’s newer render/intake behavior with the donor files.

The initial four removed-only rows are narrow actual consumers: `01e78fc` adjusts archive confirmation/tokens, `fe121e7` changes only confirmation representative/repair recovery, `fc925fa` dispatches saved custom-model finalization, and `b4d0c75` adds hash-bound custom-training lineage summaries/UI/API/tests. None changes ordinary report validation or pretrained inference. The continuation adds five equally narrow removed-only rows for custom model limit/recovery cases and private learning collector/decoder work whose actual consumers are exclusively excluded. Each has its own concrete source reason in the CSV. No user examples/checkpoints were inspected or removed.

All 48 examined merges use actual first-parent deltas. The original 15 merge examinations are retained unchanged. In the continuation, 28 rows record per-path full old/new blob endpoint chains through already source-dispositioned constituents, including support paths; each chain names its exact path, endpoint blobs and constituent SHAs. This verifies the actual first-parent merge content rather than relying on second-parent ancestry. Where constituent support scope is selected rather than exhaustive, the merge inherits that stated limit. The remaining integrations were directly read or compared at actual hunk/source level and their residual resolution changes explicitly inspected.

For the original pass, five (`b62523e`, `90e67b6`, `d15c69f`, `9389d21`, `a80a85d`) have byte-identical complete three-context-line patch exports to independently read constituents, with SHA256 proof recorded in the CSV. Other integrations were directly read or checked per actual changed-path added/deleted payload against a source-read constituent/range, with their distinct resolution/context/support changes directly inspected. This latter check is explicitly identified as changed-line payload equivalence, not full old/new blob identity. `a75f139` has a distinct preserved shaped-mask guidance style adjustment; `5820ea1` and `b22652c` were read in full. New merge test/CI/docs deltas for corner crop/rotation/recovery, background prefetch and filters were separately read rather than assuming constituent titles covered them.

## Continuation: large mixed introductions and remaining limits

The large introductions were split by actual changed behavior, not by title:

- `08f432b` (sections/progress): every production hunk, new section helper, trainer delta and package/container change was read. The ordinary portion fixes suspended transport/body deadlines, hidden-tab settled-flight freeze, generation-owned polling slots, wake/focus/pageshow/online recovery, independent selected-job polling, bounded log cursor/DOM, honest progress ages and preview revisions. The background tracker merges into the latest report under the writer gate, retaining the known N10/P06 contract. All section ownership, candidate approval/export, audio trims and strict section-only HDR/short-read checks remain excluded. These checks do not resolve ordinary N09. Full generic polling Node/browser/progress support source and targeted tracking/cache/output/source boundary tests were read. Remaining section-only test bodies and narrative docs were not exhaustively line-read.
- `1a101f6` (secondary verifier): every production hunk, complete new candidate/verifier modules and packaging changes were read. Its custom-model modes, durable selection, acceptance/filtering, checkpoint/range/render metadata and changed edit hooks have exclusively removed custom consumers. Ordinary human output choice, latest ACK and source/checkpoint contracts retain their owners. Selected same-value Keep/newer-ACK/render/checkpoint/range/package tests were read; the remaining custom-only assertions and narrative docs were not exhaustively line-read. Merge `12aad0c` has exact old/new blob chains for all 36 changed paths and inherits this scope.
- `aaeb71a` (confirmed Findings): every production hunk, all seven complete new helper modules, changed learning/model helpers, trainer and packaging configuration were read. Generic retained behavior includes escaped job names/detection text (known N11), distinct cache/cold request deadlines, exact source/display/crop relationships, bounded saved-image lifecycle, ordinary output choice/ACK semantics and avoiding an unused person-detector load during quad tracking. The compact-cache pre-generation replacement is the known N07 dependency; removing Findings must leave an ordinary preview producer. Training-free known-text OCR maps to O03 with bounded literal evidence, transformations, whole-number protection, cancellation/source/report publication and non-sensitive failure states. Its complete OCR hint/worker tests and manual/large-review/save/throughput/engine changes plus selected scan-hook/cache/confirmation boundaries were read. The durable archive, replay/revisions/tombstones, named trainer/lineage and classification workflows are excluded. Remaining custom-only assertions and narrative docs were not exhaustively line-read. Merge `82e5c1a` has exact old/new blob chains for all 62 changed paths and inherits this scope.

The earlier training/rescan introduction was also read completely, including helpers, tests, smoke, package and workflow source. Its ordinary full-review render preservation and failure restoration belong to the existing **P06D** work; deleting the training module must not delete that contract. Model-library introduction source similarly contains generic malformed/nonobject options rejection and failed setup cleanup, retained independently of its excluded custom archive protocol. The persistent logging introduction maps to existing **P12** opt-in allowed-field diagnostics; arbitrary UI/exception/stderr forwarding and donor plaintext defaults are not a privacy contract.

The exact mixed integration containing the Stop/Review web introduction was checked against both file blob endpoints and every changed/context line of the previously read constituent. Apart from offset/index headers, its only two source differences remove the malformed duplicate detection dict closure and duplicate box-editor object closure. Those resolution edits were explicitly read. Its eleven other paths have exact source-read blob chains. Initial seek mechanisms remain known N01/P11A research, not a renewed implementation proposal.

**No production-source historical SHA remains unresolved.** The support limits above are deliberate scope disclosures, not runtime evidence or proof of every removed feature’s test suite. Hunk references in the CSV inventory the actual delta; the `inspected_scope`, reason and evidence fields define which support source was actually read. Existing final-tree audits guided owner selection but were not used to automatically close unseen historical deltas.

Preserve Austin's newer defaults, privacy, PhiMemory batches, queue validation/settings recovery, watchdog, options/help and close-up face margins. No custom training, Findings, journal, similarity or sections belongs in the clean app. Optional published pretrained inference does not require preserving those systems. N01–N14/P/O gates and S01–S06 remain distinct from this historical source accounting.

Artifact validation independently recomputed the subset over all 500 SHAs; checked 180 unique rows, exact first parents, nonempty owner/reason/gate/evidence and source scopes for all 180 examined rows; confirmed the disposition/merge counts; and checked disjointness with the complementary supplement. Temporary scripts, patch exports and validation JSON are under `/tmp/openscrub-core-history`.

No app import, unit/browser test, package/image build, actual video decode/render, GPU/Windows execution, scale benchmark or network request was performed. Only Git-object source/patches and requested SDD audit evidence were read; the active native product tree and user job/model data were not used. Only this report and its supplemental CSV were written in SDD. The original ledgers, other supplements, product code and Git state were not modified by this pass.
