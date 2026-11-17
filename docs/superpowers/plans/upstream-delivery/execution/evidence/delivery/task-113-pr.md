# Index reverse recall candidates by length and digit type

Post-scan reverse recall currently revisits every remembered key for each eligible OCR word. Build one lazy local length/type index from the current mapping and restore insertion order across eligible alpha buckets. The existing predicate still chooses the first eligible fuzzy winner, including an earlier fuzzy key before a later exact key. Concrete malformed data retains original-order fallback and errors.

A deterministic 500-scan heterogeneous/unmatched history reduced reverse plus merge median from 51.924 to 9.248 ms. Same-length candidate work remains unchanged. The final repeated control regressed 0.204 ms in reverse and 0.166 ms (+6.0%) in reverse plus merge; the earlier complete matrix also observed a 1.1% same-length combination regression. Both complete matrices and all outputs are retained. This is bounded post-scan evidence, not inference/end-to-end/default/4K throughput. The local index retains O(M) references/serials until return.

Validation: 174 full tests; 46 focused tests on Python 3.12 and actual 3.9; 40 exact-base and installed-wheel behavior contracts. Controlled OCR exercises actual scan/reverse/merge/report with accepted and zone-dropped output. Offline sdist → wheel, exact source/test/benchmark binding, installed CLI/web/default smokes passed. No dependencies/defaults/forward recall/merge traversal changed.

Base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`; head `9d888708d08cccf6e5f0ec8c9cf81740d3868fa1`. P11A/B/D remain independent. Full evidence, failure disclosures and limitations: [task-113-report.md](task-113-report.md), [manifest](task113-evidence/manifest.json).
