# Isolated OCR worker for one inspected frame

`optional/detached-plate-search-worker` at `b0b5a917a4de543d6f717ce032c3405e7f3992c5` follows the [bounded detached plate OCR core](detached-plate-search-core-acceptance.md). It adds a read-only job-route operation on the current exact source sample.

| What | Why | When to deliver |
| --- | --- | --- |
| Pass the literal query to a local worker via stdin and revalidate the job, source and report snapshot before admitting the result. Enforce a single search slot and a work deadline. | A lookup can overlap a seek, source replacement, cancellation or another operation. Its boxes should apply only to the source frame the user asked to inspect. | Review as the route and worker slice before enabling the emitted-page control. |
| Retain the source lease while terminating an incomplete worker and its descendants. Remove the job-owned temporary directory after the group has stopped. | Tesseract can outlive an abruptly exited worker. Releasing the job or removing its files while OCR runs can leak artifacts or leave work around. | Exercise real restarts, timeouts, abnormal leader exits, invalid results and process cleanup. |

192 selected checks and 29 installed-wheel tests passed on each Python version, including actual local HTTP and stock Tesseract. The worker accepts one explicit frame per request. It returns approximate suggestions separately from report writes. The process group requires compatible POSIX wait and process-table access. A cleanup that is still proving the group has stopped retains ownership past the normal work deadline. The editor control and the distributed user guide follow this slice.
