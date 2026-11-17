# Bound retained job messages and recover polling cursors coherently

Long scans kept every callback message, and separate slice/length reads could advance the browser past a message appended between those reads. Each web job now owns a locked, in-memory recent history capped at 2,000 entries / 512 KiB UTF-8 payload, with an 8 KiB cap per callback entry and fixed truncation suffix. Metadata and log responses use atomic snapshots with absolute cursors, base position, epoch and omission/truncation counters.

The P03 client validates complete snapshots and replaces its latest 400-entry display on stale, future or replacement-epoch responses; normal increments append once. Retry keeps the same history/epoch, metadata remains advisory, and existing polling deadlines/view ownership remain. A delayed thumbnail callback also keeps its original job owner when the registry entry is replaced. The private helper ships in wheel/sdist and all three Docker application COPY layers.

Validation: 244 tests pass in normal discovery; 53 owning tests pass on actual Python 3.9.25; 48 packaged owning tests pass against installed-target imports. Actual PAGE/browser checks cover overflow, increments, stale/future recovery, retry, replacement/recovery histories larger than the old cursor, and delayed bodies across view/job changes. Offline extracted-sdist→wheel, exact-source/private/test inclusion, installed CLI/default paths/listening Cheroot HTTP, source-updater nested delivery and evaluated JavaScript parsing pass.

Exclusive synthetic calibration retained all 3 warmups / 5 alternating paired observations per 12 scenarios. Candidate append medians 0.665–1.987 µs and full-history loopback medians 0.910–2.194 ms stay below the predeclared 100 µs / 50 ms local budgets. Append is slower than list append; the worst matched-response regression was +0.142 ms. Retained allocation traces stayed flat from 5,000→20,000 emissions in each workload. Full-history response sizes intentionally differ after eviction.

This bounds retained backend payload per job. Browser transcript retention, persistent diagnostics, total process memory and job-count bounds remain separate. Docker image execution and native Windows/frozen startup are unverified.

Base: `6ae212a35b094fc9466f1616afb2c5bb5c0497f8` (P03/P07a). Candidate: `2c7f2530893cb2ecd20dfe7803b6301ea34f9f9f`. [Verification and measurements](../evidence/delivery/task-1202-report.md).

Independent task review approved this standalone candidate with one minor optional test-artifact portability note. Final combined acceptance and publication preparation remain separate.
