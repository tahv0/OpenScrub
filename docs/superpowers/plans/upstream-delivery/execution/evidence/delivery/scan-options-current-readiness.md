# Scan-option validation on Austin v1.0.97

The private topic `pr/scan-options-upstream-1097` is based on Austin main `50c5a9e03564983ea0bc2a7841824b1fffaf35e0`. Its head is `43b505a1ad7a6cda8835cf353c7d39b67b765ca5`. The existing `pr/scan-options-validation` at `b26b6685` and its historical evidence are preserved.

## What and why

The shared job intake route rejects unreadable options and decoded values other than a JSON object with JSON HTTP 400, before creating a durable job, copying input, registering the job or queueing work. This covers multipart upload and server-path intake. An omitted value still means an empty object. Existing settings, unknown keys and defaults keep their behavior. Framework multipart buffering happens before this guard and is outside the claim.

The patch changes the web handler, README and route tests. Austin’s current discovery and sdist configuration already cover the tests.

## Verification and review

- Final frozen `43b505a` passed 177 tests on Python 3.12.16 with no skips. That includes the three HDR regressions and all 40 scan-option cases. The same 40 passed on Python 3.9.25.
- The first refreshed revision `18a0e87` passed 175 tests. Review identified the decoder-depth case. Before the decoder correction, two new route tests reproduced HTTP 500 with `RecursionError` on Python 3.9. Both passed after the fix. Python 3.12 rejects that particular payload through its object-shape check. The route fixture isolates the free-space measurement so the tests reach the intended boundary.
- The offline 1.0.97 sdist was extracted to build the wheel before isolated installation. The audit matched 27 source members, 13 Git-backed wheel members and licenses, and all 16 hashed wheel RECORD rows plus the self-entry. Tests and contributor instructions were present in the sdist.
- The installed service exercised both multipart modes using an oversized integer and the nested-array test input. Every invalid request returned JSON 400 with no jobs, files or queue entries. Each valid empty object returned 200 with one queue entry and correct options persistence. Cancel and delete passed. Because the test intentionally disables worker execution, it inspects and then drains the stale queue entry before clean SIGTERM shutdown. The installed check uses the real free-space gate and makes no inference or scan success claim.
- The first installed check reached its HTTP assertions but timed out during the second test server’s SIGINT shutdown. The harness reaped that process, then the isolated retry verified the service’s SIGTERM handler. The product source remained at `43b505a`.
- Independent source and evidence review cleared the decoder and fixture findings. The historical 170-test run at `e34313e` and 38 focused checks at `b26b6685` retain their original attribution. [Earlier delivery evidence](task-108-report.md).

A follow-up byte audit matched the sdist and wheel across both attempts. It also checked all 16 wheel members other than RECORD against the retry installation. This directly verifies the payload used by the passing HTTP test.

## Delivery

This is the next private scan-option candidate. The description is ready for review once Save As [PR #24](https://github.com/austinmabry/OpenScrub/pull/24) has had its review opportunity. [Prepared PR draft](../../pr-drafts/scan-options-validation.md).
