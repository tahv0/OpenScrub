# Scan options validation submitted upstream

[OpenScrub PR #25](https://github.com/austinmabry/OpenScrub/pull/25) was opened on November 20, 2026. It proposes `tahv0/OpenScrub:pr/scan-options-upstream-1097` at `43b505a1ad7a6cda8835cf353c7d39b67b765ca5` against Austin's `main` at `50c5a9e03564983ea0bc2a7841824b1fffaf35e0`. The initial GitHub check confirmed the two-commit, three-file comparison.

Upload and server-path intake now reject missing object shape or malformed scan options with JSON 400 before allocating durable job state. The branch retains the empty-object default and valid unknown keys. This is a standalone intake correction serving the focused bug-fix approach Austin requested. [Maintainer discussion](https://github.com/austinmabry/OpenScrub/issues/21)

The exact submitted source passed 177 tests on Python 3.12 and 40 focused tests on Python 3.9. The sdist and installed wheel passed the byte audit and 40 intake tests on each Python version. The [prior acceptance record](../evidence/delivery/scan-options-current-readiness.md) retains the earlier live service and decoder-depth reproduction.
