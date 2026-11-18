Spec compliance: ✅ Spec compliant for the dormant literal-matcher task at 3547f82c027323dba8e69e8aef7be62c88438d8b.

### Spec Compliance

- ✅ Exact footprint: the complete supplied diff adds only openscrub_internal/plate_search/__init__.py:1, openscrub_internal/plate_search/matching.py:1 and tests/test_plate_text_matching.py:1. The initializer is an inert docstring; the matcher imports only stdlib modules at matching.py:7. Root's independent state proof records clean source, 132 unchanged preexisting files and 158 preserved prior refs at task8031-supervisor-pre-review.json:4.
- ✅ Query contract: matching.py:17 validates the supported original ASCII alphabet before separator deletion/case conversion and enforces individual bounds; matching.py:78 enforces batch bounds, string-only delimiter splitting, blank-field handling, uniform mode and count before stable deduplication. matching.py:59 rechecks prepared-query invariants and preserves first occurrence of each (mode, text) pair.
- ✅ Match/result contract: matching.py:101 rejects unusable observations without coercion/truncation; matching.py:110 validates queries first, distinguishes complete equality from explicit entire-query containment and emits every matching unique query in order. matching.py:127 accepts Mapping evidence without geometry/origin filtering and wraps the identical original mapping. Frozen result fields and repr exclusions are explicit at matching.py:28, matching.py:41 and matching.py:51.
- ⚠️ Cannot verify from the diff: unchanged packaging configuration, updater nested-path handling and Docker directory-copy rules are outside these additions. The controller should retain its focused inspection recorded at task-8031-report.md:58. Supplied artifact hashes independently document package inclusion at task8031-evidence/artifact-binding.json:15; this review did not inspect unchanged product files or rerun packaging/updater/Docker workloads.
- ⚠️ Boundary: actual Python 3.9 product execution is evidenced, but building with the cached Python 3.9 tool bundle failed at task8031-evidence/runs/package-release-39/logs/sdist.log:24. The native-built wheel's actual 3.9 installed exercise satisfies the adopted product floor; no successful floor build is claimed. Frozen Windows availability and consumer/OCR/geometry/tracking/redaction behavior remain unverified and intentionally deferred at task-8031-report.md:64.

### Strengths

- ✅ matching.py:17 and matching.py:101 share the precise supported alphabet while separating invalid-query errors from observation nonmatches; matching.py:59 performs bounded, stable deduplication without introducing fuzzy matching, ranking or mutable registries.
- ✅ matching.py:110 makes the two matching semantics directly inspectable; matching.py:127 preserves complete caller-owned evidence without interpretation or copying. The module documents ownership/lifetime limits at matching.py:3.
- ✅ tests/test_plate_text_matching.py:16 begins meaningful public-interface assertions covering the prescribed bounds and normalization; the complete 271-line test addition also verifies explicit modes, ordering, query-validation priority, distinct regions, evidence identity, privacy and fresh-child import restrictions. No mocks substitute for matcher behavior.
- ✅ Supplied genuine RED evidence identifies the missing module at task8031-evidence/runs/red-312/logs/command.log:15 and records all 13 failures at line 233; later failures remain attributed to their original sources at task8031-evidence/runs/floor-39/logs/command.log:63, runs/floor-final-39/logs/command.log:91 and runs/full-final2-312/logs/command.log:209 under the same evidence directory.

### Issues

#### Critical (Must Fix)

- ✅ None found in the complete three-file diff.

#### Important (Should Fix)

- ✅ None found in the complete three-file diff.

#### Minor (Nice to Have)

- ⚠️ task-8031-report.md:47 records an existing controller tar-extraction deprecation warning. Validation output should be pristine; track an explicit, compatible extraction-filter choice in the owning controller task and retain the existing member-safety checks. This is a disclosed tooling issue outside the three-file product change, not a matcher defect or adoption blocker; do not change the controller in this task.

### Assessment

- **Task quality: Approved.** matching.py:17, matching.py:59, matching.py:110 and matching.py:127 implement the requested bounded literal semantics and identity-preserving result boundary with no blocking quality defect found.
- **Reasoning:** The small stdlib module has clear responsibilities, and the supplied final-source verification covers both the runtime floor and installed distribution. Approval is limited to literal matching and evidence retention, with the disclosed controller warning and deferred platform/integration boundaries above.
- ✅ Evidence checked, no workloads rerun: read the dispatch, brief, complete report, complete four-commit diff, root state proof, all 14 command-result records, artifact bindings, installed-exercise adapter/config, final floor/full/installed raw logs, native package logs and focused retained-failure excerpts. No changed source file was separately opened; no product file, environment, Git state or guard artifact was changed.
- ✅ Final actual evidence: task8031-evidence/runs/floor-release-39/logs/command.log:1 identifies Python 3.9.25 and source hashes; line 3 records 13 passed. task8031-evidence/runs/full-release-312/logs/command.log:2 identifies Python 3.12.16 and source hashes; line 11 records 573 passed. task8031-evidence/runs/installed-release-39/logs/command.log:1 binds all three installed module origins/hashes to the native-built wheel target under actual 3.9.
- ✅ Read-only SHA-256 checks of those final floor/full/installed logs matched commands-results.json and artifact-binding.json:40: 30c54c0e48ab3ad11335c678ec08131ed1c3babd265b2f79cf7bd3717ae3d7a6; ab2e5fdd17f0dba1a7c92b5d3ffa6eae0ec4a9dc578e9e71ba0519996e237ef1; 81fa55c60c1eb45046aeb4a71f08be8d29ff2dd2c227628320e40b9e9e28633a.
