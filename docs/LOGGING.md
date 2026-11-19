# Optional lifecycle diagnostics

Start `openscrub-web --diagnostics` to retain small sanitized lifecycle records.
Diagnostics are off by default. The private `openscrub_internal.diagnostics`
module is separate from the UI log so that callback messages, exceptions,
paths, access tokens, OCR text and other job content never enter the records.
Records use generated session and action references and cannot be used as a
stable link to a job. They contain only fixed lifecycle values and bounded
progress counters. No root logger, requests, library messages or telemetry are
captured.

The service writes `logs/runtime.jsonl` in its data root, outside the job
store and vault encryption. The active file is limited to 5 MiB with two
backups (up to 15 MiB total). Records can survive job deletion and vault lock
until rotated away or manually removed. The service attempts private file
permissions where supported. Windows profile ACLs should be configured for
the user; native Windows ACL behavior has not been validated here.

Only one service can write these files at a time; another live service runs
without diagnostics. A bounded `running.json` marker indicates that no clean
close was observed. It cannot identify a crash cause, and inactivity means
only that no progress was reported. Storage errors disable diagnostics without
stopping work. Records and the marker are best effort, with no fsync or crash
durability guarantee.
