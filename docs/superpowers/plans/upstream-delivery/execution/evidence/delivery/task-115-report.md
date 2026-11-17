# Task115 / N12: first-OCR sanity without backtracking

Implementation is committed locally and ready for the supervisor's fresh review. No publication, merge, adoption or next task was performed.

- Exact base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
- Candidate head: `17dfe5d575306dea395b680205038e606ad598a2` (`fix: keep first OCR sanity check working without backtracking`).
- Branch/worktree: `pr/no-backtrack-scan-sanity`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`; product worktree clean after commit.
- Final runtime SHA-256: `413a4b0758219b5ed700e8feddb2e0a02a992c36b8a4a4dbfd9045c81eb72f82`.
- Final test SHA-256: `90d8b3162cc052d90a70171fed1ef5d3ce98ce06776799f8792b88d7c6aab802`.
- Final pyproject SHA-256: `72c987559a66acf7626f8d257e1159739467930696099758248aa215214ae35c`.

## Trigger, cause and repair

An ordinary text-category scan using `--no-backtrack` leaves the tracking thumbnail `small=None`. If its first processed OCR scan returns zero, one or two words, the existing sanity check nevertheless passes `small` to Canny. Exact-base controlled-inference integration reproduced all three cases using real lossless FFV1 video decoding and actual `run_scan`; OpenCV 4.14 returned `None` from Canny and the density comparison raised TypeError at base `openscrub.py:8034`, before scan/report completion. This is now actual exact-base RED evidence; the earlier Task113 prototype observation remains separate.

The repair changes only that existing guarded owner: reuse the existing grayscale thumbnail when available; otherwise lazily derive a local half-resolution grayscale sanity image from the current decoded frame using `BT_SCALE`. It does not assign to `small`, enable backtracking, populate its buffers or add per-frame preparation. Canny 60/180, the strict density>.02 threshold, warning text, OCR-present/first-scan/fewer-than-three guard, parser/defaults, Detection/report schema, decoder and normal resource-release flow remain unchanged. No exception suppression, model, dependency, helper package, reverse/merge change or benchmark was added. The only packaging change explicitly includes the new test file in the sdist; standard discovery already collects it.

## Controlled pipeline contract

`tests/test_first_scan_sanity.py` has seven cases. Only `make_ocr` is controlled, returning an ordinary OCR object with `read`; decoding, Canny, primary email detection, reverse confirmation, merging, `run_scan` and `write_report` are real. The 12-frame 160x96 FFV1 videos decode byte-for-byte to the synthetic source. The independently measured 80x48 sanity images have edge densities **0.35833333333333334** for seeded busy pixels and **0.0** for a flat frame, on opposite sides of the existing strict 2% threshold. These establish the fixture's intended warning/non-warning behavior; equality at exactly 2% is not a measured fixture claim.

- Disabled backtracking + first OCR counts 0/1/2: completes with the unchanged deliberate warning exactly once; counts 1/2 include the primary email `alice@example.invalid`.
- Disabled backtracking + flat frame + one word: completes silently with the same full email result.
- Default enabled backtracking + low-word-count busy frame: keeps the deliberate first-scan warning.
- Disabled backtracking + initial three words, and initial three words followed by later sparse one-word scans: completes without starting a sanity warning.

Every case asserts the complete returned state (all Detection fields, tracking fields, timeline/bands, digest, stats, audio and dropped lists), complete JSON Detection records/enabled choices, render state and report provenance/settings. Runtime-dependent timestamp/path/version/hash values are explicitly validated or derived independently. The expected single email spans 0.0–2.3s, `last_seen=5/3`, box (8,8,78,28), confidence .99, non-dense, IDs -1. Six primary hits plus six existing reverse confirmations produce 12 raw hits, one merged region, zero recalls, one remembered string. Warning messages are captured and asserted, keeping deliberate QA output quiet.

## Verification

All application runs asserted their actual import source before collection/execution. The prepared venvs were not changed. Task-only copied isolation hooks retarget models/settings/jobs/profile/temp/cache beneath `/tmp/openscrub-task115`, block outside writes and outward model/network fetches, and remove editable checkout paths for installed-only checks. Cached YuNet was copied locally and verified at 232589 bytes/SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`. Python 3.14 bootstrap files supplied pip temporarily; that interpreter was never executed and bootstrapPYTHONPATH was removed from installed checks.

| Check | Actual source/runtime | Result |
| --- | --- | --- |
| Exact-base RED, counts 0/1/2 | Exported exact base; Python 3.12.16/OpenCV 4.14.0 | 3 intended failures, 4 deselected; actual Canny-boundary TypeError |
| Exact-base default/three-word controls | Exported exact base; Python 3.12.16 | 3 passed, 4 deselected |
| Final new integration tests | Native candidate; Python 3.12.16 | 7 passed |
| Owning scan/reverse/backtrack/report controls | Native candidate; Python 3.12.16 | 28 passed, 113 deselected |
| Normal full discovered suite, valid sequential run | Native candidate; Python 3.12.16 | **141 passed**, 55.21s |
| Actual supported floor, same owning controls | Native candidate; Python 3.9.25/OpenCV 4.14.0 | **28 passed**, 113 deselected |
| Installed wheel, same owning controls/tests from extracted sdist | `/tmp/openscrub-task115/installed/openscrub.py`; Python 3.12.16 | **28 passed**, 113 deselected |
| Offline packaging/defaults/interface smoke | Wheel built from extracted sdist, installed under task root | Exact changed-source/test inclusion and installed module-byte checks; Requires-Python>=3.9; full parser defaults equal exact base; both installed CLI help commands exit 0; five Flask test-client GETs return 200 |
| Self-review | Final diff and `git diff --check` | Small local owner; no whitespace errors; only 3 product/test/package files changed |

The five installed Flask test-client routes are `/`, `/api/jobs`, `/api/models/face`, `/api/model_status`, `/api/vault`; empty jobs was asserted. This covers the unchanged installed interface, not a bound-port or browser session. No unnecessary repeated full suite was run after final source/tests stabilized: the first attempt was invalidated by a harness collision and one sequential normal rerun supplied the valid full result.

Artifacts: sdist `openscrub-1.0.96.tar.gz` SHA-256 `6c2c53214cc438ab96619a68ca37e07f94a54e5530afeae683eda1a8c7dbcfb7`; wheel `openscrub-1.0.96-py3-none-any.whl` SHA-256 `2c894e6da04329b51d087c45d8e8265a21c9bff1912104a85298e63de1c35a5a`. Both remain under the task temp root, not in retained evidence.

## Failed attempts, self-review and limits

All preliminary failures are retained honestly in `task115-evidence/failed-attempts.md` and their original logs (large logs gzip-compressed):

1. Initial base command launched from native cwd was stopped before collection by the source assertion. Corrected empty-temp cwd supplied valid exact-base RED.
2. Initial post-repair fixture expected six raw hits and failed five assertions (two cases passed). Existing reverse confirmation makes the correct literal 12. Only the fixture expectation changed; final seven-case assertions passed.
3. First full attempt yielded 137 passed/four setup errors after an overlapping base-control invocation reused and cleaned its basetemp, deleting the active fixture video. This is harness interference, neither product RED nor a full pass. The valid full run was sequential; subsequent floor/installed tests used distinct task-local basetemp directories and ran serially.

Self-review checked realistic regressions: the original missing fallback fails the three RED cases; disabling warning density logic fails the busy/flat controls; applying the warning after first scan or at three words fails the corresponding controls. Production backtracking flags/buffers, normal cleanup and report owners are unmodified. No supported-input contradiction was found. Coverage is Linux/prepared Python 3.12 and focused Python 3.9, OpenCV 4.14; new integration uses controlled OCR inference and synthetic media, with no OCR-model quality, prevalence, throughput or broader-platform claim. Fresh independent review remains the supervisor's next gate.

Compact retained evidence: [task115-evidence](task115-evidence/), including commands, copied isolation/env scripts, import/source/package identities, all outcomes and failures, installed smoke script/JSON, compressed patch and evidence checksums. No media, build export, installed tree, models or environment tree was retained there.
