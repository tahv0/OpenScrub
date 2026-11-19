# Optional sanitized lifecycle diagnostics

A service restart loses the preceding worker's last stage and failure classification. Add --diagnostics to retain small lifecycle records with generated references, fixed status values and bounded counters. It is off by default and excludes arbitrary logs, exception text, job IDs, paths, OCR and access tokens.

A private stdlib module owns the writer, bounded marker and rotation. Accepted event files are limited to 5 MiB plus two backups; active heartbeats are at most once a minute. Logs live outside job storage and vault encryption and survive deletion or locking until rotation/removal. Unsafe or already-oversized existing files are refused unchanged. Storage faults disable diagnostics without stopping work; process-control exceptions propagate after cleanup.

Validation on the reviewed revision: 431 full-suite tests on Python 3.12; 86 affected tests on each Python 3.12 and 3.9; real default-size rotation; configured service failure/fresh recovery/SIGTERM; offline sdist-to-wheel and installed default-off/opt-in lifecycle. Earlier cancellation/retry, SIGINT and ownership-interleaving controls keep their exact source attribution in the [acceptance record](../evidence/delivery/persistent-diagnostics-acceptance.md), which also includes a [synthetic event example](../evidence/delivery/persistent-diagnostics-acceptance.md#synthetic-event-example).

An unclean marker does not identify a crash cause. No fsync/crash-durability guarantee is made. Native Windows ACLs, junctions, locking, rotation and frozen executables remain unverified.

Private delivery status: accepted head9197df2 on reviewed prerequisite12919c9. This description is preparation material; refresh/narrow the prerequisite against Austin's accepted main before submission. No publication or C01 adoption.
