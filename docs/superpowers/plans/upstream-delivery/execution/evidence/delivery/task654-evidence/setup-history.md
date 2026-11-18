# Setup/assembly attempt notes

These notes transcribe non-product setup failures visible in tool output; actual product/helper workload logs are under runs/.

1. Initial local admission attempted in the ordinary filesystem sandbox returned exit78, `Read-only file system: maintenance.lock`. The same unused ID was then admitted with already-authorized escalation before source writes. Private admission code/config/receipts are excluded.
2. The first N11 resolve/stage command used nonexistent `tests/test_literal_job_names.py`. `git add` returned128; `git cherry-pick --continue` refused the still-unmerged index. After staging the actual conflicted paths, the already-added `tests/test_job_filename_display.py` and whole patch committed with its `-x` trailer. No failed commit is counted as a successful pick.
3. Final compact collection emitted three expected `git show` missing-file diagnostics for combined fixtures before their introduction (`0d8df87` lacks both; `fb9d59b` lacks the .cjs fixture). Those revisions are intentionally omitted from fixture snapshots; collection exited0.
4. Package controller stderr retained from tool output (child build/install/installed logs are separately retained):

```text
/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:201: DeprecationWarning: Python 3.14 will, by default, filter extracted tar archives and reject files or modify their metadata. Use the filter argument to control this behavior.
  archive.extractall(root / 'extracted')
```

This is the accepted shared-helper extraction warning. The source build, extracted-wheel build, install, identity/defaults and all installed commands returned0; no helper modification/rebuild occurred.
