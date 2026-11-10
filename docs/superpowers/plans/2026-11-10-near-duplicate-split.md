# Near-duplicate-aware video-learning split

Goal/spec: prevent connected Train & rescan export from emitting cross-split
near-duplicates rejected by the existing segmentation dataset validator. Preserve
all source annotations, label eligibility, leakage checks and quality gates.

Architecture: before exact-file deduplication, build connected components of
whole existing track groups using exactly the validator's 64-bit dHash <=2 rule.
Three disjoint hash-block buckets provide complete candidate lookup. Assign any
component touching an original or previous training group to training; otherwise
keep it held out. Preserve cumulative accepted-model training-group exposure,
including groups temporarily absent from feedback. Snapshots keep original IDs.

Files: learning_session.py, test_learning_split.py, docs/VIDEO_LEARNING.md.
Python >=3.10; no new dependencies, Docker changes or model modifications.

Ruling: prefer training for mixed components, not randomly reassigning the cluster.
Reason: the next accepted pass may warm-start from weights exposed to that group.
Cost: fewer independent validation examples; retain the existing count refusal.

Review focus: transitive chains; exact duplicates skipped during export; repeated
track sightings; label-independent image overlap; removed/reintroduced training
groups. Cover actual export and validator, not only an isolated helper.

- [x] Reproduce the user's error text with genuine saved synthetic PNGs.
- [x] Observe original source failing new collision/history checks.
- [x] Add component split and accepted-training history without deleting feedback.
- [x] Keep original byte deduplication and validator unchanged.
- [x] Check distinct groups, minimum counts, input immutability and stable ordering.
- [x] Run real connected session control flow with synthetic model stages.
- [ ] Complete unfiltered suite and remote CI, recording baseline failures.
- [ ] Review final diff and publish only to integration/all-prs after verification.

No user crops or second-PC GPU access. A hash match is the existing conservative
similarity policy, not proof of object identity. No full GPU training claim.
