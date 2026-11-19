# Save As progress readiness on Austin v1.0.97

The prior reviewed revision of pr/save-as-progress-upstream-1097 at 9d494e6510028bbb5db08756ab183ba579a12cc7 is based directly on Austin main 50c5a9e03564983ea0bc2a7841824b1fffaf35e0, v1.0.97. Independent specification, source/evidence quality and PR-description reviews approve private readiness with no material findings. The original accepted ca0f2ce7458347afd2e6156a97df580b6623767a and its evidence are preserved. [HDR PR #23 merged](../../submissions/hdr-decoder-cleanup.md), and Austin endorsed focused contributions. A read-only upstream check on 2026-11-19 still identified50c5a9e. This paragraph describes the review before the layout follow-up.

## Submitted revision 0da66d1

[Save As PR #24](https://github.com/austinmabry/OpenScrub/pull/24) opened against Austin main at 50c5a9e, with the two Save As commits and four changed files. The submitted revision passed the full native suite on Python 3.12.16 with 161 passes, zero skips, and all three HDR cleanup cases. The owning suite passed all 24 tests on Python 3.9.25. A fresh offline sdist, wheel from extracted sdist and isolated installation passed. The audit matched 27 Git-backed sdist members, 13 Git-backed wheel members, 16 hashed RECORD entries and the unhashed self-entry. The installed 1.0.97 entry point served the video and report exports with the correct attachment names, sizes and bytes, then stopped cleanly on SIGTERM. The layout and save lifecycle checks below ran on the same web implementation.

## Layout follow-up at 0da66d1

The export groups now align side by side with space for both labels. On phones each direct download link sits below its Save As button. The review actions appear on a separate row. The browser check reproduced split download labels at 1120 px and asymmetric button/link placement at 390 px before the corresponding changes. Chromium passed the layout checks at 1120, 390, and 320 px and exercised live progress, finalization, completion and the direct-download fallback. The 24 owning tests passed on Python 3.12 at this revision. The independent source check covered the grid and action grouping, followed by browser verification of the narrower phone arrangement.

The browser checks exercised the rendered page through its visible controls, following [Austin's feedback on refactor-resistant tests](https://github.com/austinmabry/OpenScrub/pull/23#issuecomment-7018069624). The focused Node harness still extracts the production JavaScript between named functions, then asserts behavior against controlled picker and IO responses. Its source-selection approach can require maintenance if that code moves. The full-suite, Python 3.9 and package results below apply to 9d494e6. The historical browser run still describes the original transfer, with current layout and lifecycle behavior verified by the fresh Chromium check.

## Behavior and scope at 9d494e6

Add Save As for the redacted video and audit report, with destination selection and written/total feedback during long exports. Count bytes only after the destination accepts each write. A trustworthy unencoded response length enables a total and approximate remaining time; unknown lengths remain indeterminate. Stalls show waiting and discard stale estimates; end-of-stream shows Finalizing, and Saved follows successful close. Picker cancellation starts no request, errors offer recovery, and progress remains attached to the chosen job across polling and job switches. Direct Download remains available.

The PR changes only CONTRIBUTING.md, README.md, openscrub_web.py and tests/test_export_save_as.py (402 additions/12 deletions). The web code, Save As tests, README and zones UI match ca0f2ce byte for byte. Contributor instructions retain Austin's full-discovery command and HDR prerequisites while adding Node 18+ and build requirements. Upstream's engine version, HDR tests, tracker geometry assertion and pyproject packaging stay byte-identical to50c5a9e. No separate old tracker prerequisite or pyproject diff remains.

## Fresh verification at 9d494e6

| Gate | Result and boundary |
| --- | --- |
| Full native discovery | 161 passed in 74.47 seconds on actual Python 3.12.16/OpenCV 4, with zero failures, errors or skips. JUnit records every case, including all three HDR cleanup-module regressions and the 24 Save As cases. |
| Actual Python 3.9 | All 24 Save As cases passed on actual 3.9.25 in 2.01 seconds. This is focused coverage, not a full-application or installed-package Python 3.9 result. |
| Emitted page | Both evaluated PAGE script blocks passed Node syntax checking. Joined script SHA-256 07320211daf0a10b2fedd22550ee51c43c5d39e98f3a160657da259ddf4b0c25 matches the original browser-tested bytes. |
| Source identity | All 115 files matched frozen Git blobs before execution and after release. The prior170 refs, six protected heads, stash and original checkout status were preserved; only the new topic and create-only upstream evidence pin were added. |
| Distribution | Fresh offline sdist, wheel built from its extracted source and isolated install passed. All 27 Git-backed sdist files plus generated PKG-INFO,13 Git-backed wheel payload/license files,16 hashed RECORD rows and the unhashed self-entry matched. Version is 1.0.97 and Requires-Python is >=3.9. |
| Installed entrypoints/routes | CLI/web help, installed module origins/defaults, actual listening loopback startup, rehydrated synthetic-job video/report routes with exact bodies/attachment names/lengths, and SIGTERM exit0 passed. These are route checks, not a fresh browser or end-to-end media render. |
| Preservation | The new full suite passes Austin's corrected tracker assertion. The old157-pass/one tracker-log failure is historical and is not an accepted failure on this candidate. |

The canonical runs configured application state under owned runtime paths and used existing prepared dependencies, pinned Node and a cached pretrained YuNet fixture. No dependency/model downloads or shared environment modifications were required. These are cooperative test hooks, not an OS sandbox or a complete native-write inventory.

Sdist SHA-256 8a2c6222dfbdaa3ef60754906486bd86d0b5ef6de983bacf786d2e5c64aa6959 (535,102 bytes). Wheel SHA-256 1ae2c160c4827237835dfcb3f230a83fe180609d81def1008fe3f5f44131c861 (437,468 bytes). Complete source, test, preflight and installed identities remain in the retained local technical record.

## Reused browser evidence

The earlier scenario remains attributed to ca0f2ce. Identical web/routes/zones and evaluated script bytes justify reuse. Real loopback HTTP fed an OPFS writable through a controlled picker in headless Chromium and saved exactly268,435,456 bytes. At most one write was pending; the application reader was at most2,097,152 bytes ahead of accepted writes. Waiting and Finalizing preceded Saved, which followed successful close.

Maximum sampled JavaScript heap plus backing storage was 88,907,747 bytes, approximately84.8 MiB. This does not bound browser-internal network buffering or whole-browser RSS, establish throughput, or prove physical durability. The scenario was not rerun merely for freshness.

Native picker interaction, Windows permissions, other browser engines, multi-GB exports, physical disk durability and OpenCV 5 remain unverified. [Prepared PR description](../../pr-drafts/save-as-progress.md). Publication, C01 and working-version adoption remain separate.

With declared dependencies, Node 18+ and the test media prerequisites available, reproduce full discovery from the topic checkout:

    python -m pytest -q

The owning subset is:

    python -m pytest tests/test_export_save_as.py -q
