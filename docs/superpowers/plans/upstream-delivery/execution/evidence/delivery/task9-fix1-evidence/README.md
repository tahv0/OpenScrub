# Task 9 fix1 evidence

Fix base `0c2b98e9e136abcd472bdda59cecaf546775ea4e`; final head `fe20dff7b73efb5afdbf3130e75a19c8b35ecba3`. See [fix1 report](../task-9-fix1-report.md) for covering tests, exact commands and results. This archive is separate from the preserved [original evidence](../task9-evidence/README.md).

## Final results and identity

- `results/identity.json`, `source-identities.json`: final native/runtime/test source hashes and precise prior/full-suite boundary.
- `logs/red.log`: four meaningful emitted-JS failures against the reviewed product head (8 old pass/4 new fail), reproducing DOM insertion order, retained structure, lost exhausted retry history and a lost deadline.
- `logs/order-green.log`, `structure-green.log`: individual local corrections, each one passed / 11 deselected.
- `logs/focused-green.log`: **82 passed in 9.37s**, scheduling + existing choice/save controls.
- `logs/floor39.log`: actual Python 3.9.25/OpenCV 4.14.0, **82 passed in 10.67s**.
- `logs/browser-final.log`, `results/browser.json`: actual Chromium upward overlapping-window/native Tab, width repartition/focus, three controlled hide/show cycles, exhausted retry continuity, new-metadata reset and complete cleanup.
- `logs/anchor-before.log`, `results/anchor-last.json`: the supervisor-requested additional **passing** mid-window controlled anchor/extent check. This is not a failing RED log; no additional source change was needed. Group77 remained at−199px, scrollY4445 and document height8478 throughout.
- `logs/js-parse.log`: successful Node parsing of AST-evaluated final APP_JS.
- Build/install/package logs and `results/package-check.json`: offline sdist extraction→wheel exact runtime/test/registry/Python-floor/entry-point binding.
- `logs/installed-http.log`, `results/installed-http.json`: real installed HTTP, exact embedded final APP_JS and asserted installed PAGE/source imports without editable native checkout paths.
- `results/cleanup.json`: only the two checked fix1-owned PIDs stopped; ports18513/18514 closed.

Web SHA: `435ee74b112635a9694333fafc9460b3f454d371760f3aba1c4d4fa4875e4563`; PAGE SHA: `8dc91cdf482ba9117777aa3723695477d54925223099bac11d2c610c91aa1483`; APP_JS SHA: `1d0608598dfd24cd912c90cf810ded4942ba50f918fe82074413827c9ef39d94`.

## Focused browser boundary

Browser plugin remained unavailable; prepared Playwright/Chromium fallback was reused with TMPDIR set before import. The only fixture is 180 ordinary groups/two collapsed-zone rows using actual PAGE/Flask metadata and cached JPEG routes. It uses no cold decoder or render work. Viewports:1365×950 (7 native columns), then1020×900 (5 columns). The first window IDs77–132 moved upward to ordered63–118 with42 retained overlaps; native Tab sequences match complete descriptor order. The exact focused control survives repartition.

One preview exhausts four actual intercepted fetch failures. Each of three controlled transitions goes6rows/4spacers/42cards →0/0/0 →6/4/42; all restored states still have four failures and no fifth attempt. Owned row/spacer counts equal actual DOM counts. Hidden listeners/observers/URLs/timers are zero; restored counts remain7/1/41/0. New metadata resets the budget; permanent cleanup records zero owned structure/work and no duplicate URL revocations. Four unsettled browser operations remain the observed maximum. Page JS errors are zero; four expected intercepted network console errors are listed separately.

These checks explicitly replay `PageTransitionEvent` with `persisted:true`. **They do not observe actual BFCache/history navigation.** The mid-window anchor result is one measured controlled case, not a cross-platform history-restoration claim.

`browser-first.log` / `browser-first.json` retain the first focused invocation's harness error: its final counter read the intentionally null `REVIEW_SCHED` after disposal. All preceding structural/retry/key/focus assertions passed. The corrected counter reads the captured disposed owner; the complete final focused invocation passed. No product change was made for this harness correction. The screenshot was visually inspected and complements native input/assertions.

## Reproduction and isolation

Use the existing task9 environment/isolation hooks and shared read-only prepared tools. Mutable fix1 build/install/browser/log/result paths are under `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/fix1`; the guarded fixture uses the separate task-owned `runtime/fix1-server` job directory. No original product runtime/user data or shared environment was changed. Native/base ownership is supervisor-controlled: pin the fix head before reproducing.

`serve.py` starts the actual candidate on18513. `focused.cjs` runs only the named browser regressions; `anchor.cjs` is the additional focused anchor check. `installed_smoke.py` starts the final installed wheel on18514 and `http_smoke.py` checks actual HTTP/source identity. `cleanup.py` verifies exact command lines/cwd before stopping only those two owned processes. Its final closure log is retained. No dependency/model download, benchmark, full suite, or unrelated save/render matrix was rerun.

Build commands use actual3.12 with cached task9 build tools, `python -m build --no-isolation --sdist`, extraction, then `--wheel` from the extracted sdist. The install uses `--no-index --no-deps`. Package binaries, environments, media, source-export and installed trees are excluded; source/package identities, scripts, logs and compact actual result records remain.

The original full/required212 and real save/reopen/render evidence still belongs to0c2b98e. Do not relabel it as final-head validation. P06D post-render row preservation, P16D ordinary Play startup and combined C01 gates are unchanged; formal scoped re-review remains pending.
