# Spec Compliance

- ✅ Spec compliant for Task112/P11B, exact base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` through head `952af20da205133886ba69799e134b86d1654137`. The change builds one local chronological timestamp-reference list, validates rather than reorders history, and uses `bisect_right` without copying a history slice (`openscrub.py:3033`, `openscrub.py:3056`). The original updated `last_seen + .01`, bridge-gap, support, geometry, confidence and fuzzy predicates remain in the support walk (`openscrub.py:3059`).
- ✅ Exact built-in list/tuple rows and finite built-in numeric timestamps form a conservative index domain. Unordered, unsupported, malformed and nonfinite histories retain the original traversal; validating an unreachable malformed row only disables indexing rather than raising early (`openscrub.py:3038`). Single merged-region inputs avoid construction, and the list/generator lifetime is local to the merge (`openscrub.py:3034`, `openscrub.py:3057`). No history cap, matcher/default change, reverse-recall/candidate-priority rewrite, cache, dependency or version change appears in the six-file diff.
- ✅ Concrete full-record controls cover chronological/tuple/repeated/duplicate/boundary-equal histories, updated boundaries, caller order, missing/contradictory support, geometry/confidence, bridge stops, unusual numeric inputs, generator fallback, prior malformed exceptions and malformed rows beyond an earlier stop (`tests/test_tail_history_index.py:36`, `tests/test_tail_history_index.py:69`, `tests/test_tail_history_index.py:74`). Empty, dense-only and fuzz-disabled controls also assert returned records (`tests/test_tail_history_index.py:85`).
- ✅ The tiny controlled-OCR fixture executes real decoding, `run_scan` finalization and `write_report`, asserting complete detections and serialized report records (`tests/test_tail_history_index.py:95`). It establishes that integration boundary, not real-model throughput.
- ✅ The performance RED is the permitted exact-base work/cost evidence, not a fabricated unit failure (`task112-evidence/baseline-attribution.py:1`). The corrected sparse fixture has a benign prefix and the actual detector-boundary log checks prefix endpoints and every suffix row (`benchmark/tail_history.py:42`, `task112-evidence/sparse-detector-boundary.log:2`). Full-module measured calls include construction; three warmups/five alternating recorded pairs precede separate tracing/allocation runs (`benchmark/tail_history.py:1`).
- ✅ Retained JSON supports the scoped adoption claim: sparse complete-merge median 12.271633 → 3.384366 ms, tail visits 299,594 → 29, 10,000 timestamp references/85,176 list bytes, traced peak 2,552 → 88,964 bytes (`task112-evidence/final-comparison-detector-consistent.json:19407`). The original repeated control's 1.376538 → 1.403718 ms regression remains retained (`task112-evidence/final-comparison.json:19615`). Tiny-case gains, inference and all-finalization/scan throughput are not claimed.
- ✅ Packaging includes the owning tests and benchmark without changing runtime module membership (`pyproject.toml:119`). Final wheel metadata remains Python >=3.9. Retained installed smoke verifies CLI help, five Flask test-client endpoints and equality of complete parser defaults (`task112-evidence/package-smoke-isolated.log:4`, `task112-evidence/package-smoke-isolated.log:29`, `task112-evidence/package-smoke-isolated.log:36`).

# Strengths

- The initial lookup skips only rows the old predicate would reject; preserving that predicate inside the loop also preserves behavior after each supporting row advances `last_seen` (`openscrub.py:3056`, `openscrub.py:3059`). Duplicate ordering and contradictory/missing-support stop rules remain owned by the original walk.
- Exact-type/domain checks avoid speculative comparisons or unpacking errors during eager validation, with fallback instead of silent sorting or dropping malformed data (`openscrub.py:3038`). The one-region control has zero index entries/queries in both retained comparisons (`task112-evidence/final-comparison-detector-consistent.json:19615`).
- Tests assert literal complete Detection records, including confidence, offsets, track/person/poly and insertion order, rather than implementation dispatch or counts (`tests/test_tail_history_index.py:24`, `tests/test_tail_history_index.py:56`). They run against the active complete module and require neither Git nor a baseline checkout.
- Evidence keeps the original fixture/results and failed tooling attempts, identifies the detector-consistency correction, separates timing from tracing, and explicitly documents O(history) allocation and cumulative-RSS limitations (`task112-evidence/commands.md:24`, `task112-evidence/final-comparison-detector-consistent.json:19645`).

# Issues

## Critical (Must Fix)

- None found.

## Important (Should Fix)

- None found.

## Minor (Nice to Have)

- None identified that warrants a change to this bounded task.

# Checks and Verification Limits

- Read the supplied diff once in bounded slices. One additional focused read of `merge_detections` was necessary because its diff hunk omitted the function setup/definition of `mergeable` and ended mid-support-loop. That read verified the actual one-region construction guard and the unchanged support/return path (`openscrub.py:2921`, `openscrub.py:3034`, `openscrub.py:3059`). No broader product-source crawl was used.
- For the concrete risk that retained results came from different source bytes, independently checked all 113 retained base-export files against their recorded SHA256/Git-blob identities and all six final native files against final identities. Checked all 41 retained evidence-manifest entries. No Git command was run (`task112-evidence/base-identity.json:1`, `task112-evidence/final-source-identity.json:1`, `task112-evidence/SHA256SUMS.json:1`).
- For the concrete risk that timing equality or medians were merely report claims, independently checked every case's stored full base/head records, all eight warmup/recorded pair digests, separate instrumented-output digests and recomputed medians in both retained comparisons (`task112-evidence/final-comparison.json:1`, `task112-evidence/final-comparison-detector-consistent.json:1`). No measurement was regenerated.
- For the concrete risk that packaging/default evidence referenced an obsolete wheel, inspected the retained smoke recipe and results, checked final artifact hashes, all six runtime modules across native/sdist/wheel/installed bytes, and all six changed files in the final sdist. Independently confirmed the final wheel is byte-identical to the initial installed-smoke wheel (`task112-evidence/package-smoke.py:1`, `task112-evidence/package-fixture-final-identity.json:1`).
- For the concrete risk that test isolation replaced the algorithm under review, inspected the retained harness. Its substitutions concern model fetch/path and web-data isolation; it does not replace merge, matching, `run_scan` or report logic (`task112-evidence/harness/task112_isolation.py:7`, `task112-evidence/harness/sitecustomize.py:1`).
- Retained passing acceptance logs are clean: full discovered 153 passed, final focused 27 passed on 3.12, final focused 27 passed on actual 3.9.25, and final semantic controls 20 passed on exact base (`task112-evidence/full-discovered.log:4`, `task112-evidence/focused-head-final.log:2`, `task112-evidence/python39-focused-final.log:1`, `task112-evidence/semantic-base-amended.log:2`). No tests/builds/benchmarks were rerun for review.
- ⚠️ The full 153-case run used the earlier 19-case tail-test bytes; final test-only strengthening has focused/base coverage, not a final 154-case full-suite run. Runtime bytes remained unchanged, and this chronology is explicitly recorded rather than presented as final full-suite coverage (`task112-evidence/commands.md:42`). This is an accepted evidence limit, not a missing-runtime-validation finding.
- ⚠️ Timings are four deterministic Linux/WSL fixtures in an exclusive owned workload slot on an unreserved host. Five samples do not establish population latency, multi-platform behavior, a memory ceiling, default long/4K performance or real OCR throughput. The controlled-OCR integration and Flask test-client smoke do not establish a real-model scan benchmark, bound server or browser behavior (`benchmark/tail_history.py:1`, `tests/test_tail_history_index.py:95`, `task112-evidence/package-smoke-isolated.log:29`).
- ⚠️ Controller-supplied frozen-head/parent/clean-worktree verification is accepted; branch ancestry and live Git state were not independently rechecked because this review prohibits Git commands. This verdict is only the Task112 quality gate, with no whole-plan or publication approval.

# Assessment

**Task quality: Approved.** The local optimization preserves the original traversal contract and has meaningful complete-output controls plus source-bound retained evidence. Its adoption case is the bounded sparse-history merge saving, with the O(history) allocation, retained small regression and platform/end-to-end limits disclosed.
