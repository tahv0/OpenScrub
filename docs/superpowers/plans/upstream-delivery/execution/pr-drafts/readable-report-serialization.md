# Reduce time spent writing large review reports

Changed saves write the complete readable report. Feed the same public JSON encoder iterator to the staging stream with `writelines`, avoiding a Python write call for every JSON piece. This changes one expression in the existing shared publisher; formatting, encoder errors, private staging, flush/fsync, replacement and cleanup stay the same.

This follows P06C.1 on `3457efac574d74a7d2377cbc0d44bb0b87462c3a`; candidate `4a62e49d2f0896b737081cc92e1f92e9bcaee93f` is independently reviewed. The measured local HTTP medians were:

| Report rows | Sparse change, before → after | Bulk change, before → after |
| --- | --- | --- |
| 10,000 | 497 → 382 ms | 489 → 381 ms |
| 100,000 | 5,315 → 4,298 ms | 5,584 → 4,558 ms |

Changed saves improved by 18.37–23.12%. The unchanged-save control at 100,000 rows was slower: 1,029 → 1,132 ms (+9.97%). Its full spread is retained, and unchanged code/work counts do not establish the cause. Each comparison used three warmups and five alternating recorded samples on a shared host; this is no general latency or capacity guarantee. A more complicated aggregation candidate gave essentially the same early result and was not adopted.

Verification passed 168 focused, 456 full and 159 actual Python 3.9 tests, offline sdist→wheel and installed CLI/web checks. Actual engine writes, render/reopen, complete expected report bytes and atomic failure behavior were exercised. All 108 main HTTP requests passed; separate counts confirm one encoding/publication for changes and none for unchanged saves. Tests preserve behavior without requiring a particular method dispatch.

At 100,000 rows, observed peak worker RSS changed by +108 KiB for sparse saves and −3,652 KiB for bulk saves. A separate case with a 12-million-character encoded token produced identical bytes and a +68 KiB sampled peak difference. Sampling does not prove a hard memory ceiling, and fewer Python calls do not establish fewer system calls. Browser/response behavior is unchanged; this task does not certify other platforms or the assembled application.

The [implementation report](../evidence/delivery/task-632-report.md), [independent review](../evidence/delivery/task-632-review.md) and [raw measurements](../evidence/delivery/readable-report-serialization/measurement/results.json) retain exact commits, commands, every sample, memory boundaries and failed harness attempts. Local draft only; no publication.
