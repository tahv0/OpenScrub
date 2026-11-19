# Reuse validation for unchanged fresh thumbnail reports

- Branch: `pr/thumbnail-validation-reuse`
- Base: `194864493962d9951cab482bde507d489f07c998` (thumbnail coherence/source-lifetime prerequisite)
- Reviewed head: `9bfb9d96865f0f67a58df868d5e167feb7b31212`
- Status: approved locally; submission follows its prerequisites.

Repeated metadata and cold-thumbnail reads validate every row and cumulative offset after parsing, even when the current generation already validated that report. Reuse its validation only for a fresh private snapshot with matching report/source stamps, generation and lifecycle fences, then recheck at selection. First/changed reports and ordinary snapshots still receive full validation. Windows and unknown platforms fully validate fresh reads; the POSIX fast path assumes an adequate filesystem change timestamp.

Preserve fresh parsing, complete row fingerprints, mutation ownership, warm JPEGs, pre-generation and upstream defaults. Share recipe identifiers in the existing private thumbnail module and put regressions under `tests/`. No retained report cache or new dependency.

Validation:

- Final head: 492 affected tests on Python 3.12.16 and 492 on Python 3.9.25, including real browser/lifetime cases; fresh offline package and installed Cheroot/defaults/CLI/updater checks.
- Real-route weak-stamp regressions first fail on the previous head, then reject invalid unselected rows and late offsets while retaining valid reads. Windows semantics are simulated; native Windows is unrun.
- Matched Linux observations at `ed58a34` before the platform-only narrowing: 100k cold crop 784→195 ms, metadata 2,514→1,915 ms and four cold crops 3,375→883 ms. No useful first-discovery/warm gain or memory improvement. Earlier full 896/477 suites stay at that head.

[Technical acceptance](../evidence/delivery/p08b-validation-reuse-acceptance.md) records exact inputs, samples, RSS, controls and source attribution. These synthetic results do not establish 4K, inference, Windows or GPU performance. The larger snapshot-cache proposal remains deferred.
