# Task901 fix1 evidence

Fix base `afbd2078a292e4ba2ced55ffdc89fcacaa27502e`; fix head `081816d93d6aaa18944fc88f251040cf11d4135f`. Four tooling files changed; no product source or package rebuild.

- [Commands](commands.md) and [exact six runtime command arrays/results](runtime-commands.json).
- Authoritative final test bytes: committed `tooling/tests/test_verification.py`, identical to the copy beside original helper files in ignored `runtime/task901/fix1/red-baseline-tooling`. [Final actual3.12 RED](final-red312.log) and [actual3.9 RED](final-red39.log) each show 25 methods / 16 expected failing assertions against that original helper snapshot. [Final actual3.12 GREEN](final-green312.log) and [actual3.9 GREEN](final-green39.log) each show 25 passing methods against the fixed helper.
- Twelve `fixture-{file,child,module}-{source,installed}{312,39}.log` files retain actual successful workload output, selected module file origins and values, including direct-file sibling conflicts and module-cwd conflicts. They supplement complete unittest output.
- Six affected startup transcripts: [source3.12/defaults](source312.log), [source3.9/defaults](source39.log), [installed3.12 generated CLI](cli312.log), [installed3.9 generated CLI](cli39.log), [installed3.12 listening HTTP](http312.log), [installed3.9 listening HTTP](http39.log). Both listening server child logs are retained separately; both children terminate/reap with exit0.
- Four full frozen configs and six preflight manifests retain the unchanged reviewed product/source/interpreter/prerequisite identities. [Reused package identities](reused-package-identities.json) bind the already built sdist/wheel, whose bytes were rechecked; package building was not rerun.
- `red312-fixture-draft.log` retains an initial escaped-newline fixture mistake. `red*-diagnostic-draft.log` retain overly specific expected diagnostic wording subsequently corrected. `red*.log`, `i1-green*.log` and `green*.log` retain intermediate meaningful RED/GREEN before strengthening module-origin output. No draft is relabeled as authoritative final evidence. Initial Task901/review logs remain unchanged.
- `identities.json` binds committed helper/test/documentation bytes, the baseline snapshot and compact evidence files. Runtime/export/install trees remain excluded.

I1/I2 are the fixed boundaries; deferred Minor M1 and root-owned fresh review/next-task adoption remain outside this fix execution.
