# Serialize accepted review edits and validate worker report publication

Two successful overlapping review saves could erase one accepted choice. Serialize each job's fresh read/apply/atomic publish, merge tracking into its latest report with ID allocation inside that transaction, and close edit/tracking gates before scan/render queue submission. Retain the reviewed source-input pin, complete P06D documents,0600 atomic staging and existing CLI/GUI defaults.

Prepare Task621 lifecycle/source ownership outside report locks; admit prepared tickets under report lock → short JOBS_LOCK; release leases after leaving the report lock. The optional engine `write_report(..., publisher=None)` / `cb.publish_report` boundary constructs and hashes outside the lock, then validates final web operation identity before publishing. Cancellation promptly signals its captured operation's own Event and invalidates only that identity before acknowledgement, preserving newer attempts and legitimate pre-ack commits. Report download metadata/open now share one generation.

Prerequisites: reviewed Task621/P06B.1 lifecycle/source/allowlist fixes and P07a browser refusal/draft handling. JavaScript/defaults/dependencies/version remain unchanged.

- Base: `c697d5a686d4dccbdf4f474567628d5d24e75a03`.
- Head: `f2cdf4813c86296644911f3f0b09bfc56d3e03c5` (local only; clean `pr/report-edit-transactions`).
- RED: actual-route initial regression command `python -m pytest -q tests/test_report_transactions.py` produced7 failures/1 pass on base; subsequent controlled single-case REDs reproduced late cancellation targeting a newer retry, deleted stale-ticket cleanup, queue-time Event clearing, and stale prepared source/operation admission. Logs: `/tmp/openscrub-task622/*red*.log`.
- Final Python3.12: `python -m pytest -q --basetemp /tmp/openscrub-task622/stabilized-full-tmp -o cache_dir=/tmp/openscrub-task622/cache` → **354 passed in97.93s**. Includes34 transaction regressions, configured Cheroot sockets, synthetic HTTP save→tracking-stub→real render→reopen, cancellation construction/hash/replace schedules, lifecycle/atomic/roundtrip/browser regressions.
- Actual Python3.9.25: exact-worktree imports verified; focused `python -m pytest -q tests/test_report_transactions.py --basetemp /tmp/openscrub-task622/python39/stabilized-pytest-tmp` → **34 passed in2.61s**. Packaged Python3.9 grammar also passes; these are separate checks.
- Offline isolated sdist→wheel build passed. Exact packaged/committed/installed bytes, inclusion, Node syntax and unchanged defaults/source-selection/JS verified. Actual installed CLI help/web defaults, Cheroot entrypoint, vault/allowlist lifecycle and SIGTERM exit0 passed. Full evidence: [task-622-report.md](../evidence/delivery/task-622-report.md) and `/tmp/openscrub-task622`.

Limits: one web process; no cross-process locking or Windows/macOS/container/frozen/TLS runtime claim. Cancellation waits for a committing report transaction and cannot interrupt arbitrary native I/O or undo prior commits. Final-video atomic replacement/prior-output preservation remains P16C; this hook guarantees report and terminal-state publication only.
