# Web owner for staged checkpoint publication

`pr/checkpoint-web-publication-owner` at `21ef5a7e2a3086562dfd17d26560f4cf10bab100` follows [initial checkpoint completion](checkpoint-first-completion-acceptance.md). It provides a private POSIX publication hook for a future scan worker that holds the existing per-job report lock.

| What | Why | When to deliver |
| --- | --- | --- |
| Validate the captured operation and generation, cancellation event, source owner and report target before replacing a staged checkpoint. | Once Cancel is acknowledged or a new operation takes over, older work must lose permission to publish. | After the isolated producer. Test the actual Cancel route, a superseded generation and a successful source/report generation notification. |
| Retain an owned regular file descriptor through rename and advance the output epoch only after successful replacement. | A failed stage or replace should preserve previous report bytes. The next source generation should name the actual installed report. | In the same prerequisite PR, with injected replacement, preparation and descriptor failures and no changes to ordinary job admission. |
| Report a post-replace notification failure distinctly and block further mutation until recovery. | Once bytes have been replaced, the worker must distinguish a committed report from a failed attempt. | Verify the in-process failure here. Persist and resolve that recovery state before routing user-facing checkpoint operations through the hook. |

On both Python 3.12 and 3.9, 130 selected checks and 13 installed checks passed. The selected run includes actual loopback report transaction tests. The owner tests exercise successful commit, superseded generations, acknowledged Cancel, stage/descriptor failures and the distinct committed-but-recovery-needed outcome.

The hook is scoped to POSIX same-job source ownership. It leaves source adoption and the paused/completed phase transaction to the future worker. The next web slices need durable recovery, bounded review and exact samples on the verified prefix, opt-in scan admission, reload recognition and Save followed by acknowledged Resume. The [web ownership sequence](checkpoint-bounded-decoder-acceptance.md#application-delivery-sequence) specifies those gates.
