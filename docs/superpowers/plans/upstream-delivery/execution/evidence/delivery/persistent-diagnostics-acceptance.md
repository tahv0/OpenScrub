# Optional persistent lifecycle diagnostics: local acceptance

The private candidate pr/optional-runtime-diagnostics is accepted at 9197df2ffe70ba9b9da11aef5af8fbcdd47a6628, based on the reviewed report/lifecycle prerequisite 12919c96c6f7558136b50d7b4d85e5e6b62f1971. Independent source specification and quality reviews pass; all six original findings are closed. This is a local extraction. Before an upstream PR, narrow or refresh it onto prerequisites Austin has accepted. It has not been published or combined into C01.

A service restart currently loses the previous worker's stage and failure classification. The default-off --diagnostics flag retains schema-built lifecycle facts rather than raw console or UI messages. The private openscrub_internal/diagnostics.py module has no web import or new dependency. The other changed paths are openscrub_web.py, tests/test_runtime_logging.py, docs/LOGGING.md and pyproject.toml.

## Behavior and retention

Records contain UTC times, generated session/action references, fixed event-specific enums and bounded finite counters. They exclude stable job IDs, filenames, paths, OCR or search text, tokens, arbitrary messages, exceptions and nested job data. Callback values are validated before state or marker mutation. Error classification is reduced to fixed values inside the exception handler.

Logs live in the service data root outside the job store and vault encryption. They can survive job deletion and vault lock until rotation or manual removal. Each accepted/generated event file is limited to 5 MiB, with two backups; each record, marker and the single temporary marker is bounded at 1 KiB. There is one exclusive writer. Finished or abandoned action handles release recorder state; old callbacks and cleanup cannot affect newer diagnostic actions. Active heartbeats occur no more often than once a minute and do not persist every progress callback.

Writer ownership covers recovery, marker writes, rotation, disabling and close. Unsafe links, reparse metadata, nonregular entries, multiple hard links or existing event files above the configured cap cause refusal without modifying that unsuitable content. Consequently, the retention cap describes recorder-managed files it accepts or produces, not arbitrary oversized files placed there externally. The fallback checks directory components from root through leaf. Controlled metadata regressions cover the Windows-specific branch on Linux.

Storage failure disables diagnostics and leaves operations running. Interrupt and exit exceptions release initialization resources and propagate. Vault shutdown precedes recorder close. An unclean marker establishes only that no clean close was observed; it cannot diagnose an OOM. Inactivity means no progress was reported. Records and markers are best effort, without fsync or crash durability.

## Synthetic event example

These actual records are from source revision `9197df2` using the configured service and a controlled synthetic missing-input boundary. They do not represent an installed worker-error exercise or a naturally occurring failure.

```json
{"schema":1,"time":"2026-11-19T19:33:32.455389+00:00","session":"5fba9b29f0c74c5c97b8f1ad2e60f74e","kind":"job_started","action_ref":"cf514e3a384747b4a377bfc069a63092","action":"scan","stage":"prepare"}
{"schema":1,"time":"2026-11-19T19:33:32.458650+00:00","session":"5fba9b29f0c74c5c97b8f1ad2e60f74e","kind":"job_finished","action_ref":"cf514e3a384747b4a377bfc069a63092","action":"scan","outcome":"error","error":"runtime_error"}
```

## Verification

| Gate | Source and result |
| --- | --- |
| Full discovered suite | 431 passed in 100.90 seconds on actual Python 3.12.16, frozen current head 9197df2; no skipped tests. |
| Affected suites | 86 passed on Python 3.12.16 and 86 on actual Python 3.9.25 at the same head, covering diagnostics, job lifecycle, vault cleanup and worker/watchdog ownership. This is not a whole-suite Python 3.9 result. |
| Default-size rotation | One current-head control emitted 103,002 events, approximately 15,759,306 bytes. It checked all 68,737 retained JSON records. Current/backup sizes were 31,087 / 5,242,851 / 5,242,851 bytes, each within 5 MiB. |
| Failures and ownership | Meaningful RED/GREEN controls cover hostile callback values, marker bounds, failed recovery, concurrent disable, exception-frame retention, callback/cleanup escapes, unsafe entries, oversized content, process-control exceptions and fallback reparse metadata. |
| Configured service | Current-head real loopback worker failure, exact restoration of the controlled missing synthetic input, fresh-process recovery, deletion and two SIGTERM stops passed. The filesystem failure was injected at the real engine boundary. |
| Earlier scoped controls | Cancel/retry with late diagnostic callbacks, real initialization SIGINT and successor ownership, and failed-stop/successor interleaving retain their cd631bb source pin. Web integration bytes are unchanged at 9197df2. These controls establish diagnostic ownership, not stale UI callback safety. |
| Packaging and installed service | Fresh offline sdist, wheel built from its extracted source, isolated installation, CLI/web help, actual installed default-off and opt-in lifecycle passed at 9197df2. All 39 Git-backed sdist members, 15 wheel payload members, 20 hashed RECORD rows and its unhashed self-entry matched; Requires-Python is >=3.9. |
| Page and source identity | Evaluated joined PAGE JavaScript passed Node syntax checking. All 128 source files matched Git before and after final validation; protected topic refs and stash were preserved. |

The native full run selected test_openscrub.py and the entire tests directory. Its cached pretrained fixture avoided model downloads; a scoped JSON-child adapter verified startup identity records and retained raw streams for the existing roundtrip test. No detector, model, training or output policy changed. The historical 409-test/default-rotation results at d342ac4 remain historical and are superseded for current acceptance by the fresh gates above.

Sdist SHA-256: fca964a740fc0436e540df7bf0cf17a2c8c8aae14fd4749a313747e2a2fbbaf3. Wheel SHA-256: c2e0713f824f78d2251671565d4ddbd4766eb3bc4694b742d0dd5720c4da1c54.

## Remaining limits and delivery

Native Windows junctions, ACLs, locking, rotation and frozen executables remain unverified. Container/PyInstaller inclusion is source inspection only. There was no browser benchmark, hard process-memory bound or arbitrary native-hang diagnosis.

An invalid-video research probe reached review rather than the expected failure; this is an unconfirmed engine-validation lead requiring its own Austin-baseline reproduction. An excluded harness probe imported the original checkout without a pre-import runtime inventory, so unchanged original runtime cannot be established from that probe. Neither is used as candidate acceptance evidence or silently treated as fixed.

[Prepared PR description](../../pr-drafts/persistent-diagnostics.md). P12B/P12C log-memory limits, upstream submission, C01 and application adoption remain separate.
