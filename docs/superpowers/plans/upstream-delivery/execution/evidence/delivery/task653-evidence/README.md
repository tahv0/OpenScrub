# Task653 compact evidence

Base4b9bd7e576a8ae30369672b4b4722fc9752e233f → clean frozen head117e41ac5ee857a6b367caf6ccbd479d78989ff2. See [report](../task-653-report.md).

- `provenance.json`: exact ordered original/composed SHA map, parent chain and preserved named refs.
- `p11b-conflicts.diff`, `p11c-conflicts.diff`, `n12-conflicts.diff`: actual unresolved conflict stages; `resolution.patch`: original/composed range-diffs; `combined.diff`: exact reviewed product/test range.
- `frozen-identities.json`, `config-312.json`, `config-39.json`: expected Git-file hashes, actual C01 module inventory, task-owned runtime paths, prepared interpreters/environment and native prerequisite hashes. `helper-identities.json`: canonical081 helper identity.
- `selection.json`: exact absolute file/node selection. `discovery-312-command.json`, `acceptance-312-command.json`, `acceptance-39-command.json`: exact clean system-controller argv; matching controller logs retain complete raw output. `runs/*/{preflight.json,command.log}` retain compact per-run helper records.
- `owner-hashes.json`, `static-package.json`, `static-review.log`: base/head owners, recursive recipe membership, unchanged metadata/Python floor and Dockerfiles; no built/installed-package claim.
- `actual-fixture-identities.json`, `fixture-recipe-hashes.json`: actual generated media hashes and owning recipe identities. No media copied. `prepared-interpreter-metadata.json`: interpreter/distribution versions; no product imports during metadata inspection.
- `attempts.md`: all nonzero attempts and pre-freeze fixture correction. `prepare_config.py`, `run_selection.py`, `static_review.py`, `harvest_evidence.py`: exact task scripts; these do not alter shared tools/environments.

Reproduction uses a new unique run ID (existing IDs are never reused):

```sh
/usr/bin/python3 /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task653-evidence/run_selection.py 312 NEW_UNIQUE_ID
/usr/bin/python3 /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task653-evidence/run_selection.py 39 ANOTHER_NEW_UNIQUE_ID
```

Run serially with the original invocation's socket escalation for selected HTTP fixtures. No legacy PYTHONPATH controller, models, custom pytest plugin or stdout adapter is required. Reproduction is not a request to rerun accepted checks automatically. Final full-C01/package/browser/G/R/P gates remain root-owned.
