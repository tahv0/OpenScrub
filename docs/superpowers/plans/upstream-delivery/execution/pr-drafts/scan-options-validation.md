# Reject invalid scan options before creating or queuing jobs

Malformed scan options previously returned an HTML500; JSON arrays, null, strings, numbers and booleans could be saved and queued even though argument preparation needs an object. The shared upload/server-path boundary now returns JSON HTTP400 before any job creation, input copying, registration or queue work. It also handles the supported Python runtimes' integer-conversion limit.

Omitted options still mean `{}`. Valid objects, supported settings, unknown keys and defaults are preserved. The catch covers only JSON decoding; unrelated file errors and per-key behavior stay unchanged. Normal framework multipart buffering remains outside this durable-job guarantee.

Validation: the original implementation passed 170 full-suite tests. The final decoding fix passes all 38 intake cases on Python 3.12 and 3.9, plus rebuilt sdist/wheel source checks and actual installed Cheroot HTTP rejection/valid-create/cancel/delete checks. Both intake paths cover the 4,301-digit integer that exposed the review finding. The full suite was not repeated for the two-line fix.

The product change is a small guard in the existing route. Supporting changes add actual-route tests and include them in discovery, contributor instructions and the sdist. No model, dependency, report-transaction or option-default changes are included. These admission tests do not claim a reproduced worker failure or permanent storage leak.

See [implementation evidence](../evidence/delivery/task-108-report.md) and [scoped fix review](../evidence/delivery/task-108-fix1-review.md).

Local branch: `pr/scan-options-validation`.
Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin plus the test-only tracker prerequisite).
Head: `b26b6685b237ba1c4caffaaefb47b029a3205b51`.
No push, upstream submission or merge has occurred.
