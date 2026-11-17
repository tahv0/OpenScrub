### Spec Compliance

- ✅ **SpecCompliant** for bounded Task653, base `4b9bd7e576a8ae30369672b4b4722fc9752e233f` → frozen head `117e41ac5ee857a6b367caf6ccbd479d78989ff2`. The four exact whole-commit picks retain their `-x` provenance and order, followed by the single new combined test commit. Evidence: `task653-evidence/provenance.json:1`, `task653-evidence/resolution.patch:1`, `task653-evidence/static_review.py:11`.
- ✅ The complete supplied nine-file diff contains only the approved P11B/P11C/N12 source/test/benchmark changes and the added batch regression. Runtime changes remain confined to `merge_detections`, `reverse_pass`, and `run_scan`; no extra runtime definition, dependency, G/R/P composition, rejected P11D, or D01 product change appears. Evidence: `openscrub.py:3038`, `openscrub.py:7202`, `openscrub.py:8164`, `task653-evidence/owner-hashes.json:1`.
- ✅ Actual guidance/metadata conflicts preserve both report-I/O and incoming benchmark guidance, recursive private/tests/benchmark inclusion, the Python>=3.9 floor, and unchanged metadata. Exact donor/composed range differences show only trailers, context/import offsets and the deliberate retention of recursive C01 entries. Evidence: `benchmark/README.md:356`, `task653-evidence/resolution.patch:1`, `task653-evidence/static-package.json:2`, `task653-evidence/static_review.py:41`.
- ✅ The changed engine-owner inventory and 13 unchanged file identities preserve prior raw/report/source/lifetime/replay/cancel/mask/smoothing owners; donor merge/reverse function equality is explicitly asserted in the recorded static verifier. Evidence: `task653-evidence/static_review.py:37`, `task653-evidence/owner-hashes.json:263`, `task653-evidence/static-review.log:4`.
- ✅ The new actual-scan regression covers the requested combined interaction in both accepted and zone-dropped partitions, with two records in each merge and complete Detection/order/stats/report/render-state/source-hash assertions. Independent no-backtrack warning and default-backtracking controls remain separate. Evidence: `tests/test_batch_integration.py:301`, `tests/test_first_scan_sanity.py:150`, `tests/test_first_scan_sanity.py:166`.
- ⚠️ Full discovered combined-suite, built/installed CLI/web, browser, later renderer/G/R/P and adoption acceptance remain outside this gate; static recursive inclusion is appropriate here because no new runtime/private module or packaging boundary was introduced. This approval does not establish those later results. Evidence: `task-653-brief.md:25`, `task-653-report.md:61`, `task653-evidence/static-package.json:1`.
- ✅ The supervisor's appended storage clarification controls the earlier headroom wording: ~802GB is guest WSL2 ext4 virtual availability only; Windows backing capacity is UNKNOWN and /tmp is a separate ~1.24GB tmpfs. Completed successful tests remain valid evidence; no physical allocation-budget claim follows. D02 remains separate. Evidence: `task-653-report.md:63`.

### Strengths

- `tests/test_batch_integration.py:301` uses a meaningful oracle: early strings contain `#` rather than `@`, so they cannot seed the primary email matcher; valid later emails seed memory; subsequent `sample` fragments are far outside forward/reverse candidate-length windows but are literal partial matches for tail support. Reverse recall therefore supplies onset0 and the original near-miss text, while tail support supplies last_seen5/3 and end2.3. This avoids the prior invented supporting-prefix problem. Relevant production boundaries: `openscrub.py:381`, `openscrub.py:790`, `openscrub.py:819`, `openscrub.py:1007`, `openscrub.py:2936`, `openscrub.py:7202`.
- `openscrub.py:3048` retains chronological fallback and existing first-support semantics; `openscrub.py:7202` preserves insertion priority, category/name gating and malformed-data fallback. Focused tests pin complete records, mutations, numeric semantics, ordering and failure behavior rather than merely asserting nonempty results. Evidence: `tests/test_tail_history_index.py:39`, `tests/test_reverse_recall_index.py:32`, `tests/test_reverse_recall_index.py:123`.
- `task653-evidence/acceptance-312-controller.log:1` and `task653-evidence/acceptance-39-controller.log:1` retain exact helper argv, frozen head, native prerequisite hashes, actual interpreter versions and ten imported C01 module identities. Both complete outputs end in119 passed and exit0, with no skips, warnings or other test noise. The discovery log explicitly includes the new node and reports119 collected (`task653-evidence/discovery-312-controller.log:122`).
- `task653-evidence/config-312.json:1`, `task653-evidence/config-39.json:1` and `task653-evidence/SHA256SUMS:1` bind source/config/evidence identities. A reviewer read-only check confirmed identical 62-file/10-module inventories and current frozen file bytes; all40 compact manifest entries verified. Actual combined-fixture hashes agree across both completed acceptance runs (`task653-evidence/actual-fixture-identities.json:1`).

### Issues

#### Critical (Must Fix)

- None found in the bounded reviewed range.

#### Important (Should Fix)

- None found in the bounded reviewed range.

#### Minor (Nice to Have)

- None requiring a Task653 change. The authoritative storage clarification already resolves the earlier misleading inference (`task-653-report.md:63`).

### Checks and Limits

- Read the brief, report including appended clarification, local PR record, and supplied diff once in four nonoverlapping chunks (lines1–320,321–640,641–960,961–1244). Read original conflict records, range-diff resolutions, provenance/static verifier and results, selection/configs, complete discovery/preflight/acceptance controller logs, recipe/fixture identities and runtime-idle record. No Git command, product import, test, build, benchmark or browser execution was run by this reviewer.
- Named focused source check—detector-consistent fixture: inspected unchanged email regex/matching and PhiMemory normalization/forward recall boundaries, plus the merge/reverse function portions cut off by supplied diff context. The missing portions establish first-record retention, tail partial-match support and original-word Detection construction; no changed hunk was reread separately. Evidence: `openscrub.py:381`, `openscrub.py:758`, `openscrub.py:925`, `openscrub.py:2936`, `openscrub.py:3087`, `openscrub.py:7263`.
- Named focused helper check—logged default job path versus owned workload path: inspected `docs/superpowers/plans/upstream-delivery/execution/tooling/verification_hook.py:96`. It prints/asserts defaults before redirecting jobs/models/app paths into the run; the source-default path in DEFAULT_PATHS is not the workload's final storage path. No helper modification was made.
- Ran `sha256sum -c SHA256SUMS` in `task653-evidence`: all40 entries OK. Ran a standard-library-only read-only identity check of the two configs/frozen inventory/current62 file hashes,126 recorded top-level owner-map keys/changed-owner set, and the two combined-fixture hash entries: passed. No runtime probe was needed because code and existing acceptance evidence resolved the concrete interaction risks.
- Reviewed static checks substantiate40 recursive private/test/benchmark members and unchanged private COPY in three Dockerfiles without claiming a built artifact. Recorded pytest durations are ordinary test output, not performance evidence (`task653-evidence/static_review.py:48`, `task653-evidence/static-package.json:1`, `task-653-report.md:61`).
- The first bounded evidence filename listing used rg without hidden/ignored-file overrides and returned1; the immediately corrected exact-directory listing succeeded. One oversized fixture-identity display was truncated; a focused JSON read confirmed both relevant combined-fixture entries. Neither was a product failure or a reason to rerun acceptance.

### Assessment

**Task quality: Approved — QualityApproved.**

**Reasoning:** The composition preserves the reviewed source owners and actual metadata/guidance resolutions, and its added detector-consistent regression exercises the combined reverse-onset/tail/report behavior in both scope partitions. The frozen identity records and clean119-test runs on actual Python3.12.16 and3.9.25 support this bounded gate; later whole-C01 acceptance and host physical-capacity verification remain explicitly unclaimed.
