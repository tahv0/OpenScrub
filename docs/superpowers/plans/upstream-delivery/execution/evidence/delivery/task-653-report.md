# Task653: bounded fourth-C01 core integration

Local integration record; no upstream PR or publication. Implemented in the already isolated native worktree `/home/tahv0/.codex/worktrees/c832/OpenScrub`, branch `integration/upstream-focused-core`.

- Exact reviewed base: `4b9bd7e576a8ae30369672b4b4722fc9752e233f`.
- Frozen, clean acceptance head: `117e41ac5ee857a6b367caf6ccbd479d78989ff2`.
- Runtime ownership: `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task653/runs`; four unique serial helper runs completed, no active helper lock or workload remains.
- Evidence: [task653-evidence](task653-evidence/README.md). Fresh independent spec/quality review and advancement of the working integration reference remain root-owned.

## Original-to-composed provenance

Whole commits were cherry-picked with `-x` in this exact order. Parent continuity, original trailers, existing prerequisite ancestry and preserved branch refs are in [provenance.json](task653-evidence/provenance.json).

| Owner | Original | Composed |
| --- | --- | --- |
| P11B runtime/test/recipe | `e96deb59e1b3c36585672be4c74d90eb6d0a49b5` | `9999f25af550f14b9971131d1f76bf2767c9c595` |
| P11B benign-prefix recipe correction | `952af20da205133886ba69799e134b86d1654137` | `77e51306eea8467bb2607d9df2b29eb2ec9b8cf8` |
| P11C reverse recall | `9d888708d08cccf6e5f0ec8c9cf81740d3868fa1` | `afe0fd414736df4efca2586dc5147d20fabb4753` |
| N12 first-scan warning | `17dfe5d575306dea395b680205038e606ad598a2` | `3a1dc0bd5aa864cec85d463f51a12168a04e0687` |
| Combined interaction regression | new, test only | `117e41ac5ee857a6b367caf6ccbd479d78989ff2` |

The original candidates and `integration/upstream-focused` at reviewed4b9 remain preserved. No original standalone prerequisites were repicked. P11D, D01 tooling and later G/R/P composition are absent from this range; approved P remains independent.

## Actual resolutions and owner preservation

P11B conflicted in `benchmark/README.md` and `pyproject.toml`; P11C conflicted in those same files; N12 conflicted only in `pyproject.toml`. Retained both complete guidance sections and C01's existing recursive private/tests/benchmark entries. Final metadata is byte-identical to base. No runtime conflict occurred. Existing `math` import was automatically deduplicated; `bisect_right` was added. Retained the P11B benchmark-fixture correction as its own original pick.

All conflict-stage diffs and original/composed range-diff details are retained in [resolution.patch](task653-evidence/resolution.patch), alongside [combined.diff](task653-evidence/combined.diff). No source file was wholesale replaced. The only changed top-level engine definitions are `merge_detections`, `reverse_pass`, and `run_scan`; the composed merge/reverse definitions exactly match their respective approved original function bytes. [Owner hashes](task653-evidence/owner-hashes.json) bind every engine top-level class/function at base/head and unchanged private/report/web/mask/cancel/smoothing fixtures. The existing P06/source/operation/lifetime/replay/report and P16A/B behavior owners remain intact.

## Combined regression and contracts

Existing tests retain chronological fallback, malformed-history errors, first support, reverse insertion priority/gating, mapping/count mutation, numeric semantics and full Detection fields. The independent first-warning controls exercise low-word first OCR with backtracking disabled, edge-free silence, normal backtracking, and sparse later scans.

Added only `tests/test_batch_integration.py::test_scan_reverse_onset_and_fragment_tail_preserve_partitioned_report`. The actual lossless12-frame160x96 FFV1 clip is decoded by production scan code. Controlled OCR observes four early near-misses before any remembered PII, four valid emails on the next scan, then four short `sample` fragments on each remaining scan. The early rows require reverse recall to establish onset0; the later fragments fail primary/recall matching because their lengths differ, while partial similarity supports tail extension through5/3. Two records enter each accepted/dropped merge, exercising the chronological index in both partitions. Assertions pin complete ordered Detection fields, stats, report enabled/zone-dropped rows, render state and source hash. Removing reverse results loses onset/original text; losing tail support truncates end/last_seen. No undetected supporting prefix was fabricated.

Ruling: this is verification of unchanged reviewed composition, so no artificial RED or runtime mutation was introduced. The user-selected bounded gate explicitly reserves the full suite for final whole-C01; no broad suite was run. The added test commit froze source before acceptance; its validity was established by the fresh checks below, with no post-freeze source edits.

## Exact verification

All shell calls used `login:false`. The controller was explicit `/usr/bin/python3`, with legacy `PYTHONPATH`, pytest hooks/options and task hook variables removed; workloads use config-pinned prepared interpreters. Canonical helper bytes match reviewed `081816d93d6aaa18944fc88f251040cf11d4135f` exactly. [Configs](task653-evidence/config-312.json) declare62 selected Git-file hashes and10 real C01 module identities, including the private parent plus `lifetimes`, `reports`, `opencv_compat`; the independent P inventory was not reused. All selected/imported test fixtures, recipes, metadata and registries are hashed. Cached native ffmpeg/ffprobe/tesseract prerequisites have explicit hashes; prepared dependency versions are retained separately.

| Unique run | Result |
| --- | --- |
| `collect-312` (helper preflight only) | exact source/default/import validation passed |
| `discovery-312` |119 tests collected |
| `acceptance-312` |119 passed, actual Python3.12.16 |
| `acceptance-39` |119 passed, actual Python3.9.25 |

The identical bounded selection is full `test_tail_history_index.py`, `test_reverse_recall_index.py`, `test_first_scan_sanity.py`, `test_dense_smoothing_io.py`, `test_manual_tracker_cancel.py`, `test_batch_integration.py`, plus `test_openscrub.py::test_track_person_size_jump_handoff` (B02a geometric oracle). This covers the incoming contracts, P11A needed-frame/cancel/release behavior, P10C ordinary-tracker controls, existing scan/preview/cancel/source leases, HTTP save/replay/fresh reopen, raw report fields and exact SDR/HDR default-coverage input. No standalone browser/media matrix was repeated. Socket escalation was supplied at each original mixed-selection invocation. Existing actual HTTP fixtures own ephemeral loopback ports and teardown; all119 tests passed without skips or warnings on both interpreters.

Exact argv and complete raw helper output are retained under [evidence](task653-evidence/README.md). Run-local profile/models/jobs/cache/TMPDIR/pytest directories were helper-owned; initial actual-filesystem headroom exceeded802GB. No model fixture was required, so no YuNet seed/plugin was used. The unchanged pure-stdout roundtrip testcase was not selected; batch report/HTTP controls provided the relevant coverage, so no child-output adapter was used. [Fixture hashes](task653-evidence/actual-fixture-identities.json) cover actual generated media without copying it; [recipe hashes](task653-evidence/fixture-recipe-hashes.json) identify the source recipes.

Static verification passed: `git diff --check`; exact ancestry/trailers; unchanged metadata/Python>=3.9; recursive sdist membership of40 private/test/benchmark files; unchanged private COPY in all three Dockerfiles; unchanged reviewed helper; clean native worktree. No runtime/private module or recipe boundary changed beyond files already included recursively, so a new package/install/startup build was unnecessary at this intermediate gate. See [static-package.json](task653-evidence/static-package.json) and [static-review.log](task653-evidence/static-review.log).

## Attempts, review and limits

No acceptance, discovery or preflight failure occurred. Three expected cherry-pick conflicts returned exit1 and were resolved as described; their original conflict diffs remain. Two read-only exploratory bundles attempted to read not-yet-applied or original-checkout-only paths and returned nonzero; these were navigation errors, not product failures. [attempts.md](task653-evidence/attempts.md) retains the details. A final evidence-only status check initially assumed directory listing order and failed; comparing sorted names resolved it without changing source or runtime checks. The combined fixture's accidental whitespace typo was corrected by amending its test-only commit before manifest freeze or product execution; no failed run was discarded.

Self-review checked the full base/head diff, original/composed runtime hunks and exact function identities; confirmed merge fallback/support and reverse priority/gating bodies are unchanged, N12 is limited to deriving sanity pixels when `small` is absent, recursive packaging/guidance owners remain, and the combined oracle depends on both paths. No unresolved implementer finding or deferred minor.

This establishes bounded combined correctness on the named prepared CPU environments. Test-reported durations are ordinary pytest output, not a timing/throughput/RSS/accuracy result. No performance slot, benchmark replay, detector-accuracy claim, download, environment/helper edit, user-data migration/deletion, publication or branch integration occurred. Full discovered combined suite, final package/installed CLI/web, browser integration, G/R/P rendering/publication/resource composition and subsequent adoption remain later root-selected gates.

## Supervisor storage-layer clarification (2026-11-18)

The earlier802GB headroom wording refers only to Linux statvfs/df availability inside the WSL2 ext4 virtual filesystem. It does not establish physical Windows backing-volume headroom. Root rechecked both raw counters and mounts after the user corrected this inference: the guest reports about802.77GB (747.64GiB), while /tmp is separate tmpfs with about1.24GB available. Windows automount/interop are explicitly disabled and no host drive query is exposed, so physical backing capacity is UNKNOWN. Raw preflight counters remain preserved as observed; no claim of verified802GB physical allocation budget should be made. All named core tests completed successfully; this clarification changes no runtime/test result. This storage-layer clarification is a verification limit; it does not change the application or the completed acceptance evidence.
