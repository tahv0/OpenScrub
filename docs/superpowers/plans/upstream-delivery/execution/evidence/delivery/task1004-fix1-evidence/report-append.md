
## Fix round 1 — T1004-R1 error-body settlement

Latest status: **DONE_WITH_CONCERNS** — T1004-R1 is implemented and its assigned owner/shipping gates pass; the same reviewer's scoped `dcaa..d1f056e` closure remains pending. This section supplements the immutable original 17,313-byte report above. The earlier 620-test/PAGE/server-compatibility results remain attributed to dcaa; they were not rerun or relabeled as results at the fix head.

Original task BASE remains `07cfaa9539a2561c26b6f7280fae6702eb07137c`. Fix BASE is `dcaa0e5af6aedfca8685a3e64bea86ad0262f5c2`; final clean fix HEAD is **`d1f056e86fcae2dcfaa01bbc7f97e79ca662faaa`**, on `pr/exact-editor-ui`.

The full review (`task-1004-review.md`, SHA `24ca193c29f0d731cf7b0a9a73901c7fb95b6a3f1c3416329d73cdf510fad3cb`) found one Important item: non-success response headers caused `bePumpSamples` to throw before consuming the response body. Its finally block could start the latest wanted sample while the older error body remained unsettled. The original body-coalescing controls covered successful JSON bodies only.

The repair changes only the non-OK branch inside literal APP_JS: await `response.text()` through exhaustion or body-read failure, then throw the existing useful HTTP-status error. HTTP is checked before body interpretation; a non-JSON refusal is never parsed as JSON. The active slot remains owned across retired mounts until this await settles. There is no abort, decode, image URL allocation or change to the success/decode/playback/backend paths. Catching body-read failure preserves the original HTTP status while allowing normal settled cleanup and latest-wanted pumping.

Only `openscrub_web.py` and `tests/test_review_save_failures.py` change in this fix (57 insertions, 2 deletions total). All Python AST nodes outside APP_JS remain identical to dcaa; CSS, the ten runtime origins, defaults, engine/helpers, report/API formats and platform sources remain unchanged.

### Covering controls and exact source attribution

Two new test functions contribute 12 cases: HTTP409/423/500 × body exhaustion/body-read failure.

- `test_exact_error_body_retains_slot_across_mounts`: deferred non-JSON refusal; A1 has queued A2, then desired requests change through B and a new A mount. Error headers alone cannot start another fetch. No decode or URL is allocated. Only the latest A/.8 request starts after the old body resolves or rejects; the stale error cannot overwrite the new mount's status, and its subsequent exact sample becomes ready.
- `test_exact_current_error_body_settlement_keeps_http_status`: an active current failure retains the slot until its deferred body settles; no decode/URL occurs, readiness stays blocked, and the resulting status retains its HTTP code and explicit retry guidance even when body reading fails.

The existing HTTP response fixture now models `.text()` alongside `.json()`; production functions are not substituted. The complete prior 141 owner controls remain and pass.

| Stage | Product/test fingerprint and actual output |
| --- | --- |
| Genuine RED at exact dcaa product bytes | web SHA `33cd9d19ff9ea9542d14408be7840929dafd2b9bc6c8ae240fc7aab410d8cc32`; new test SHA `3ee8f7ab7a41639f85d6ad568aa4e5b01916a54424b4bbe7594ba908f506ecfb`; **12 failed, 141 deselected**, exit 1, 1.70s. Six failures assert premature second fetch; six assert premature active-slot clearing. No parser or harness error was counted as the behavior RED. Run `task1004-fix1-84b494de56c24532929be706ceca4ae0`, log SHA `bbbe563e0ca5fee63ba12870acf490622acd56bd93a1cfdc13c83a94895deea3`. |
| Actual Python 3.12.16 full changed JS owner | **153 passed**, exit 0, 19.55s. Run `task1004-fix1-0d22e7ca429b4f6996c49bbcd0824545`; log SHA `f822b59137ef1e62937f708fe4b3a46f8e19394986d39d4f3f3309a0f2cc458b`. |
| Actual Python 3.9.25 full changed JS owner | **153 passed**, exit 0, 21.57s. Run `task1004-fix1-e5af3ff6b0d6489390b45072682b025d`; log SHA `1a192eb2a27e0613ba7105c6b4a0fa599094bacc988201c9e481c2bb70e9de60`. |

Both GREEN invocations were prospectively bound development states before the clean fix commit; their web and test bytes exactly match d1f056e. Final web SHA is `422ed86c602be624f17ac6f2ef7e607121552afcaff0801ce23ffc467dc02a09`; evaluated APP_JS SHA is `f841e636aead565afcd716c1ec8694eb44e389a73c0ca67d2cd0b1e75d28e322`. Test SHA is unchanged between RED, GREEN and final package. APP_CSS remains `6c324da4b20e83eb740a31150ec8d166c326c49fd8914bec09e4abe2f79b3220`.

Canonical commands, with SOURCE/RUNTIME/VERIFY abbreviations defined above:

```text
/usr/bin/python3 VERIFY --config RUNTIME/fix1-red-312.json run -- -B -u -m pytest SOURCE/tests/test_review_save_failures.py -q --tb=short -k error_body
/usr/bin/python3 VERIFY --config RUNTIME/fix1-green-312.json run -- -B -u -m pytest SOURCE/tests/test_review_save_failures.py -q --tb=short
/usr/bin/python3 VERIFY --config RUNTIME/fix1-green-39.json run -- -B -u -m pytest SOURCE/tests/test_review_save_failures.py -q --tb=short
/usr/bin/python3 VERIFY --config RUNTIME/fix1-package-312.json package
```

### Final shipping gate and retained attribution

The frozen native Python 3.12 offline package gate passes at d1f056e: run `task1004-fix1-1cd1061244c54db38fb45c31b67aefde`, every build/install/default/CLI/installed adapter action exit 0. Installed-adapter log SHA is `7fa688633136acb2efd13c7aff2bbf6fdac4b5a299968346fde13dd8f6198a88`.

- Sdist: **626,648 bytes**, SHA `770c2af3575d7e0ad05bc038ae0e6eeb1bf0de9803d9a00b524725493f723d74`.
- Wheel built from that extracted sdist: **464,269 bytes**, SHA `f23859d612b82c1036c05ddb837dccaccf70f77d863e65fc1b41ad8e93dedc7f`.
- Offline/no-deps/no-compile installation, ten installed origins/defaults/CLI, strict and legacy listening HTTP, malformed/stale seed refusal without publication, exact APP_JS/CSS/PAGE and runtime custom-category substitutions, and updater test bytes all pass. The changed owner-test SHA is present in the sdist/updater proof. Metadata remains Python `>=3.9`.
- Recorded installed empty-custom PAGE SHA is `96f4c48f3cf1a229115f4ae17dd1d48b12c97d158d3be49ae04ee1394e786870` including the observed dynamic guest-disk field. The original corrected adapter is preserved; a separately pinned fix adapter selects the new APP_JS identity file.

As assigned by `task-1004-fix1-brief.md`, this isolated failure-branch closure uses the full affected JS owner on both actual interpreters plus the frozen package gate. No normal 620-test/PAGE successful-body run, heavy DPR replay, floor-server replay, new browser/platform claim, dependency/environment/model download or shared controller change was introduced. Earlier successful-sample/pixel/render/Track results and their limitations retain their dcaa attribution.

All original **182 compact-evidence files remain byte-for-byte unchanged**. The original report prefix SHA remains `8d91b56bf30631a33943f92e9cf973de64b8ccb5b3b2ac1e449d41601e276989`; the original PR is retained as `task-1004-pr-before-fix1.md`. New compact evidence lives only in `task1004-fix1-evidence` with its own manifest, archive hashes, exact diff, prospective configs, raw RED/GREEN/package logs and adapter/test inputs. All earlier refs remain; during this fix only the task branch advances from dcaa to d1f056e, and the docs ref stays cf044937.

The same reviewer must inspect the scoped fix range before adoption. No source composition, publication, push, merge or user-version adoption occurred. Source/runtime are released after the final report phase completes.
