Make ordinary manual additions safe to replay

A save can commit a manual region and lose its HTTP acknowledgement; retrying previously appended the same region again. Give each completed ordinary Add box draft a retained UUID and persist its server-normalized immutable creation data in the existing report transaction. Identical retries succeed without appending or resetting later indexed box/time/Keep edits; incompatible or ambiguous ID reuse rejects the entire request with JSON409. Missing IDs retain legacy append behavior.

Requires reviewed Task622/P06B.2 and existing P07a draft acknowledgement handling. No new locks, identity store, acknowledgement protocol, persistence layer or dependency/default changes. Unchanged serialization performance (P06C), source-bound quad/tracker features and general report revisions remain separate. Reload still loses in-memory drafts; replacement scans are outside the identity guarantee.

Validation:394 complete-suite tests;239 focused transaction/lifecycle/save/roundtrip tests;37 new actual-route cases on Python3.9; actual Chromium successful/lost delayed acknowledgements with indexed edits and a second lost retry; actual render/fresh-process HTTP replay; offline sdist→wheel, exact packaged source/3.9 grammar, installed CLI/web defaults and entrypoints. Response loss was deliberately injected after real HTTP commit, not a physical network disconnect.

Base: `f2cdf4813c86296644911f3f0b09bfc56d3e03c5`
Head: `12919c96c6f7558136b50d7b4d85e5e6b62f1971`
Local branch: `pr/manual-addition-replay`; no push or publication.
