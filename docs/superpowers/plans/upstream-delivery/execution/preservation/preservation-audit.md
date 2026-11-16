# B03 preservation audit — inventory and focused source findings

Date: 2026-11-16. Upstream: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
Donor: `b4d0c75f25d91510fe1692f901d11853dc7db005`.

**Status: exhaustive commit/path inventory; incomplete semantic audit. Do not mark B03 complete.**
The [core semantic supplement](core-semantic-audit.md) adds final engine/web
function dispositions and strengthens the render-row preservation finding with
a second source-isolated probe; its coverage does not resolve whole commits.
All 500 integration-only commits have a ledger row, family, disposition, exact
first-parent provenance and evidence level. There are 438 non-merge commits and
62 merges, and 177 net changed paths. This is not a claim that all 500 changes
have been read line by line. In particular, 463 rows are only automated
metadata/path/hunk inventories; their family labels are navigation aids, not
source-verified conclusions. 469 rows retain `investigate`, including six
source-inspected candidates needing further reproduction or scope decisions.
These counts are commits, not independent bugs or proposed PR counts.

Read against the existing P01–P18/O01–O05 cards, not only issue #22. The audit
did not modify those planning files. The findings below are suggested ledger
additions/refinements for their owning task. No product changes, checkout
changes, commits, downloads, real runtime data or publication were performed.
The S01–S06 scale scenarios remain outstanding; the one small synthetic probe
below is not a replacement for them.

## New or insufficiently explicit preservation candidates

| ID | Finding and donor | Proposed destination | Evidence and remaining gate |
| --- | --- | --- | --- |
| N01 | Late-window dense-track smoothing decodes the prefix unnecessarily. Mixed `ccff62f` adds a verified initial seek to `first_needed` inside `smooth_dense_tracks`; it is unrelated to its plate labels/quads. | P11 investigation for an independent long-video improvement; P18 must retain the necessary no-prefix-decode behavior. It can apply to ordinary late detection windows even without Stop & Review. | Compared current upstream and donor function bodies, then exercised their actual AST with a fake decoder. Upstream read 17,873 frames before first useful gray at 600s/30fps; donor read 1 with simulated successful seek, 17,873 after simulated failure. Real-video identity, seek cost, fallback state and end-to-end timings remain unverified. |
| N02 | `8697c28`, titled compound masks, changes native HDR silhouette chroma coverage from nearest resize to the union of all touched source 2×2 cells, including odd origins. Current upstream already has ordinary silhouettes and retains the resize implementation. | Explicit P16 candidate, separate from compound holes, narrow masks, training and quads. | Source-distinct implementation inspected. Needs sparse/edge luma-mask regression and real HDR render reproduction. The donor's full-square `test_hdr_odd_origin_covers_every_touched_chroma_cell` may pass the old resize path too; do not count its existence as proof of this regression. |
| N03 | The same `8697c28` validates finite polygon/box coordinates and catches invalid/degenerate geometry, falling back to a full box. Upstream's existing silhouette conversion lacks this exception boundary. | Separate P16 reliability candidate if synthetic ordinary-report inputs reproduce a failure. | Source inspected. Separate input validation/fallback from new `poly_holes`/`mask_pad` schema and changed dilation semantics. NaN, infinity, malformed points and invalid boxes need isolated then actual-render tests. No current failure asserted. |
| N04 | `7e5c7b4` improves the distinction between a detector proposal and the actual Blur/Keep output through legends, effective-shape overlays and output colors. The commit is mixed with learned filtering and classification UI. | Consider the small generic subset under P02/P16, or close explicitly as optional UX. | Source inspected; no browser reproduction. Preserve pending-edit colors and actual render coverage without copying checker badges, training labels or the expanded workbench. Acceptance is not established. |
| N05 | `eedef89` (#90), dominated by custom plate-checker scores, also adds useful plain detector wording and explicit disclosure that plate-corner editing/grouping does not track perspective through every frame. | P17 documentation/UI contract; O02 where tracking is offered. | Source inspected. The P17/O02 cards already forbid blindly propagated quads, so this is a concrete donor-hunk refinement rather than a newly discovered behavior requirement. Keep the disclosure while excluding checker models/group-score machinery. |
| N06 | `db9a142`, titled connecting review to training, snapshots/restores review data around `run_pipeline` rendering. This is mixed with training-specific invalid-output gates. | P06/P07 compatibility investigation: ordinary render must retain saved review/report fields. | Inspected worker hunk, not all learning code. Determine whether current upstream's load/write-report contract already preserves every ordinary field. Do not import `learning_session.preserve_render_review` solely to obtain the behavior. |

N01 is the strongest new measurable control-flow finding. Its original donor
hunk is small, but that intermediate commit also contains broken merge
fragments subsequently repaired by `32e48ce`/`66ceea8` and others. Extract the
final behavior against Austin; do not cherry-pick the mixed intermediate
commit. The late-window seek must use upstream's existing verified `_seek_cap`
contract, with a test ensuring that an unsuccessful seek leaves fallback
decoding correctly positioned. The synthetic adapter deliberately does not
prove that last property.

Reproduce the source-isolated probe from the repository root:

```sh
python3 .superpowers/sdd/README/probe_dense_smoothing_prefix.py
```

Raw output is [dense-smoothing-prefix-results.json](dense-smoothing-prefix-results.json).
It records decoder operations, not measured time, actual OpenCV reads, PTS
accuracy or application throughput. The original functions are extracted from
the pinned Git objects without importing application/runtime dependencies.

## Covered findings that should not become duplicate omissions

| Family | Reconciled evidence and extraction boundary |
| --- | --- |
| P01/P02 | `2900930`/`39b4ed8` are already named. P01 additionally requires new byte-progress feedback; donor Save As alone does not satisfy it. |
| P03/P04 | The generic subset in `08f432b` includes bounded log responses, consistent cursor acknowledgement/reset, activity timestamps and preview revisions. Strip section/learning status. ETA follow-ups remain separate from Findings image caching. |
| P05/P07 | Examined `90e67b6` first-parent delta and constituent `5e96740`. JPEG atomic producer replacement and frozen response bytes are separate necessary fixes; save versions, job/view fencing and pending-choice UI are generic. Do not conflate them with corner conflicts. |
| P06/P07 | Examined `4fd88af` first-parent delta (including `d9a96c3`). No-op guard, compact bounded writer, sparse browser deltas and stage timings belong to existing cards. Manual addition replay is not made idempotent by skipping unchanged enabled choices. Acknowledged save must preserve existing `suggest_allowlist` behavior; `217f323` repairs a journal shortcut, not an independent upstream bug. |
| P08–P10 | Revision-fenced background work and retained source identity are applicable principles from the fork's index/cache work. `496e017` is an exact-crop follow-up: convert to RGB before odd-coordinate crop. Its donor decoder is not an upstream endpoint and must be adapted under P10. Do not port all of `review_preview_index.py`, Findings or confirmation leases. |
| P11 | `a11a392` changes only fork-only `finding_previews.py`; preserve the cost lesson, not that removed cache. N01 supplies a different concrete upstream code path to investigate. |
| P12 | Runtime diagnostics are already mapped. Donor request error/reason strings and exception text are not automatically privacy-safe; keep the task's explicit allowed-field contract rather than transplanting every logging hook. |
| P13 | `.dockerignore` exclusions in `9753212` are already covered by the detailed card. Existing upstream dependency/model layers and security refresh remain authoritative. |
| P14 | `7bc2336` active Docker-context/local docker-driver selection and its tests refine the existing Windows handoff card. The larger tagged dependency-image architecture is excluded; retain the actual context fix only when the adopted inference helper needs it. `da50a6e` fixes directories for the excluded audit helper; `96a3a50` deliberately enables a training overlay and is not an inference fix. |
| P15 | Type/output/status filters already have owners. Keep only statuses present in ordinary upstream reports, and preserve hidden drafts/groups. Similarity grouping and learning samplers are not prerequisites. |
| P16–P18 | Existing donors remain mapped. Integrated implementations are in `ccff62f`, `6020d22`, `b198e0b`, later repairs/editor changes and their packaging follow-ups; early issue SHAs alone are insufficient extraction bases. P18's donor test scans with categories `none` and `--no-backtrack`, so it does not validate N01's dense-smoothing read bound. |
| O03/O05 | `74edee0` supervised OCR subprocess and `a6419cc` one-pass component counting are already explicitly covered. `a6419cc` is not a new omission. Preserve them on their optional branches, independent of generic contributions. |

## Production-path coverage and dependency risks

The path inventory divides all 177 changed paths into 44 production/build/config
paths, 77 tests, 38 documentation paths, 13 CI paths and five developer tools.
This path count describes the final tree difference; commit rows also retain
intermediate/reverted paths. The CSV uses `production-build-config` broadly,
including standalone build/audit scripts; it is not a claim that all 44 ship in
the application.

| Paths/family | Destination and risk |
| --- | --- |
| `openscrub.py`, `openscrub_web.py`, `zones_ui.py` | Mixed primary extraction surfaces; never classify an entire file or all training-titled commits as removable. Engine final-diff hunk/function inventory was inspected; web final-diff hunk inventory plus the named focused diffs were inspected. Full semantic review of every web hunk is still pending. |
| `stop_review.py` | P18 checkpoints; generic compact/atomic writer can belong to P06 if justified. Preserve strict source/timeline and reviewed-prefix contracts without treating the whole module as prerequisite for every PR. |
| `openscrub_logging.py` | P12 optional diagnostics only. Learning/model log hooks are removable; runtime lifecycle hooks must retain upstream watchdog/error behavior. |
| `plate_text_hints.py`, `plate_text_subprocess.py`, `plate_text_web.py` | O03 downstream. Pure matching/process-control pieces can survive, but web orchestration imports `learning_session`, `video_learning`, `video_sections`, `finding_previews` and `stop_review`. Its current import graph cannot ship after removing training/sections; use the O03 decoupling contract. |
| `confirmed_findings.py`, `findings_training.py`, `findings_ui.py`, `findings_web.py`, `learned_models.py`, `learning_candidates.py`, `learning_session.py`, `plate_verifier.py`, `video_learning.py` | Exclude custom training/example library/checker systems. Their introduction commits also modify core worker/render/vault/save paths (notably `db9a142`, `aaeb71a`); those mixed hunks require separate dispositions. |
| `finding_previews.py`, `review_preview_index.py`, `review_journal.py`, `review_similarity_ui.py` | Exclude the expanded workbench architecture. Port only proven ordinary-review fixes to existing upstream paths. `6d5e8fd` explicitly adds journal-read vault protection/cache clears: that exact journal code is removed-only, but any new P08/P10 cache must retain vault/deletion lifecycle protection. |
| `video_sections.py`, `section_workflow.py` | Removed section workflow; engine trim/audio/ownership/source-range changes predominantly serve sections. Generic report publication and queue changes in mixed core commits still need review. Do not silently add section export to P18. |
| CPU/Intel/CUDA Dockerfiles, `.dockerignore`, `.gitignore` | P13/P14/P12 as applicable. Final CUDA donor combines cache refresh, older ORT pin, named dependency stage and optional trainer install. Strip training and re-evaluate pins against current upstream; copying the final file violates the clean baseline. |
| `compose.windows-test.yml`, `compose.windows-cuda.yml`, `scripts/build-windows-cuda.ps1` | Minimal P14 inference handoff/context behavior only. Remove training defaults and retained-image assumptions. Current donor's latest helper explicitly adds training overlay (`96a3a50`), so tip selection is not safe. |
| `Dockerfile.cuda.inference`, `docker/audit_cuda_image.py`, `docker/cuda-shared-layers.json`, `docker/generate_cuda_inference.py`, `scripts/audit-windows-cuda.ps1`, `scripts/build-windows-cuda-inference.ps1` | Excluded experimental parallel image/audit architecture, as detailed P13/P14 cards require. Generic helper error handling does not justify introducing the excluded architecture. |
| `compose.windows-training.yml`, `requirements.training.txt`, `scripts/download_training_checkpoint.py`, `scripts/prepare_plate_dataset.py`, `scripts/train_plate_seg.py` | Remove custom training machinery; retain existing runtime data independently. No deletion of data/weights authorized. |
| `pyproject.toml`, `windows/openscrub.spec` | Owning-feature distribution changes only. Donor lists/force-includes removed trainer/workbench modules; do not copy the final lists. New helper packaging must accompany each shipped fix. |

At donor tip the web module imports training, Findings, journal, similarity and
OCR orchestration eagerly. A clean application cannot simply delete the named
files. Every retained helper must accept plain inputs/callbacks or use the
existing owning module, and installed-startup tests must prove the removed
modules are not imported. This reinforces the existing C01 contract.

Background index/cache lifetimes deserve special attention across `6ce3406`,
`8d19537`, `d66ae10`, `6c41f74` and source-retention changes `07632ac`–`a833e3e`:
the problem is stale work publishing against a new source/report or plaintext
surviving lock/deletion. These rows remain investigate unless their specific
upstream replacement is reproduced. Source hash, decoded frame identity,
thumbnail cache key, report revision and human approval are distinct identities;
keeping a cache lease is not permission to reapprove changed pixels.

## Current upstream guardrails: whole-file donor copying regresses newer work

There are 18 commits on the upstream-only side. Beyond the already-known OCR
privacy and PhiMemory implementations, the current base contains queue-setting
validation/recovery (`4f863f3`), Specific text (`7556ff9`), cross-word custom
regex/empty-match rejection (`f807d85`), regex-injection validation (`f2573f2`),
plate threshold UI (`c276e07`), advanced help (`a6c73d2`), removal of a no-op dense
faces control (`bbe8938`) and close-up face margins (`9f71cd2`). These remain
Austin's implementations. The final donor diff also removes ONNX engine choice,
select-recovery/UI details and newer option/queue guards from the current base.

The source comparison directly shows donor VERSION `1.0.89` against upstream
`1.0.96`, donor weaker hyphen-only/Tesseract normalization against upstream's
all-adaptive-engine dash-and-slash normalization, and donor per-string memory
loops against upstream's compiled rapidfuzz batches. Ancestry is provenance;
neither a fork merge nor an integration test count permits restoring these
older implementations. N01/P18 and P12 worker changes must preserve current
`qgen`, option persistence/restart and watchdog behavior when adapted.

## Machine-readable evidence and remaining closure work

- [preservation-commits.csv](preservation-commits.csv): exactly one row per
  `BASE..DONOR` commit, full SHA/parents, provisional family, disposition,
  evidence, narrow evidence scope, touched paths, production paths, hunk scope
  navigation and explicit first-parent diff basis. `PR` means a proposed task
  destination, not reproduction, acceptance or delivery. A source-inspected
  subset never certifies every hunk of that commit.
- [preservation-paths.csv](preservation-paths.csv): all 177 net changed paths.
- [preservation-counts.json](preservation-counts.json): counts and explicit
  incomplete semantic-audit/scale-baseline flags.
- [collect_preservation_ledger.py](collect_preservation_ledger.py): deterministic
  inventory generator plus explicit manually reviewed hunk records. Run with
  `python3 .superpowers/sdd/README/collect_preservation_ledger.py`.

Next closure work is semantic review of the 463 inventory-only rows grouped by
family, with priority on mixed core edits, first-parent merge resolution and
the cache/vault/source identities above. Resolve each applicable behavior to a
specific P/O task or explicit exclusion; do not mechanically convert a family
prefix into removed-system-only. Read the 77 changed test paths as donor
evidence and extract only behavior-relevant regressions into `tests/`.
Complete S01–S06 on the real baseline and publish no issue/PR until requested.
Before W5, the unresolved semantic rows and candidate gates here must either be
closed with evidence or remain visible as outstanding cutover work.

Validation of these artifacts: regenerated the 500-row/177-path inventory and
ran the isolated probe. No app tests, browser tests, build, actual video render,
GPU/Windows run or scale benchmark was performed by this audit agent.
