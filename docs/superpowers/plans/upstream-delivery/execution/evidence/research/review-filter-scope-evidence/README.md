# Source-only P15 scope evidence

No application or donor code was executed. No browser/server was started. The JSON predicate fixture illustrates the **proposed contract**; it is not a product test result.

- `source-manifest.json`: exact ordinary/donor commits, SHA-256 hashes and excerpt ranges.
- `*-anchors.txt`: line-numbered relevant source excerpts at those immutable commits.
- `proposed-predicate-examples.json`: seven cards (five ordinary groups and two independent zone rows), their effective flags and the proposed type/output memberships/counts.
- `collect.py`: reproducible read-only Git-object collection; compares the ordinary source bytes with the complete pinned export before writing task-local evidence.

The full ordinary export is `/tmp/openscrub-review-filter-scope-20261117`, created using `git archive 92124753736e287ac800af91f0ac96f3e96c01be` read through Python's `subprocess.check_output`, then extracted with `tarfile` and `filter='data'`. The initial `python` command was unavailable; the same command succeeded using the existing `python3`. No environment change was needed. Donor source was extracted with `git show <exact-pin>:openscrub_web.py` into `/tmp/openscrub-review-filter-scope-20261117-donors` for focused text inspection. `cmp` confirmed the two earlier donor files are identical.

Evidence generation from the repository root:

```sh
python3 .superpowers/sdd/README/review-filter-scope-evidence/collect.py
```

Source inspection used `rg`, `nl -ba` and bounded `sed` ranges. Research inputs were the owning scope brief, P15 section, P09 section, `review-choices-baseline-research.md` and binding `task-20-brief.md`. The active native product worktree was not accessed. No full suite, baseline matrix, build, benchmark, model or inference run was repeated. No temporary processes require cleanup.
