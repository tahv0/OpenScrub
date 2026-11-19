# Reject invalid scan options before creating jobs

Malformed options could return an HTML 500. A JSON array, null, or another non-object could be accepted and queued even though scan preparation expects an object.

Both upload and server-path intake now return a JSON 400 if options cannot be decoded or do not form an object. The check happens before job creation, input copying, registration, or queueing. Omitted options still use an empty object. Valid settings, unknown keys, and defaults keep their existing behavior. Multipart upload buffering remains part of the framework.

The route tests assert the actual response and inspect the job store and queue. The Python 3.9 regression reproduced the decoder depth exception on both intake paths before the fix. It now returns the same JSON 400 as other invalid options.

The final revision passed 177 tests on Python 3.12 with no skips and all 40 scan-option cases on Python 3.9. A fresh offline sdist and wheel passed the package audit. The installed live service returned JSON 400 for both invalid cases on both intake paths with no durable job state. It admitted a valid empty object, handled cancel and delete, and shut down cleanly through SIGTERM with workers disabled for the test.

Private head: `43b505a` on Austin `50c5a9e`. [Verification and source attribution](../evidence/delivery/scan-options-current-readiness.md).
