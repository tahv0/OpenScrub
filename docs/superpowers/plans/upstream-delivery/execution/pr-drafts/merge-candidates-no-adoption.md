# Merge-candidate index: no PR proposed

The tested sorted-left index made complete merge calls slower in all eight predeclared cases, by 2.7–148.5%, and increased Python allocation peaks. In the larger separated-email case, final predicate visits fell from 115,440 to 29,040 while total time rose from 26.820 to 37.257 ms. Guards, prefix traversal, list maintenance and ordering costs erased the proposed benefit.

No product, test or package patch is adopted. Native base and final head remain `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. Independent review approved this evidence-backed closure with no findings. The remaining merge-history cost is still open; this result does not reject every possible future algorithm.

Both actual modules, all eight timing distributions, complete common output/mutation/identity snapshots with per-run equality checks, and corrected isolated 40+40 behavioral controls are retained. The report distinguishes controlled merge inputs from actual reverse/video output, Python allocations from RSS, and the protections actually used during measurement. Conditional scan/source-frame/full/floor/package acceptance was not reached after the cost gate failed.

[Detailed report](../evidence/delivery/task-114-report.md) · [Independent review](../evidence/delivery/task-114-review.md) · [Evidence](../evidence/delivery/task114-evidence/README.md)
