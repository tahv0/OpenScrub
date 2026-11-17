# Task 9 fix1 — DOM order and same-view restoration

Ready for scoped re-review. All three open Important findings are addressed locally; no publication/adoption, nested agents, unrelated candidate import, dependency/schema change, or broad runtime rerun.

- Fix base: `0c2b98e9e136abcd472bdda59cecaf546775ea4e`.
- Final head: `fe20dff7b73efb5afdbf3130e75a19c8b35ecba3` (`pr/visible-first-thumbnails`), clean native worktree.
- Changed files: `openscrub_web.py` and `tests/test_thumbnail_scheduling.py`.
- Evidence: [task9-fix1-evidence/](task9-fix1-evidence/README.md). Original [task9-evidence/](task9-evidence/README.md) remains unchanged.

## Local fixes

1. **DOM/Tab order:** `ReviewScheduler.orderNodes` reconciles actual row and card siblings to descriptor order. It inserts/moves other siblings around the actual focused subtree instead of detaching its focused ancestor. Width repartition still preserves the same card/control and restores focus when reparenting requires it. No node is reused for another descriptor. Upward overlapping windows and repartition now have logical DOM order and verified native Tab order.
2. **Owned structure:** disposal removes every owned row and spacer and clears their maps/arrays, in addition to the existing binding/URL/observer/listener cleanup. It leaves the section's explicit numeric height intact, avoiding a height collapse while the live root is suspended.
3. **Retry continuity:** page hide calls the existing local disposal owner with `{suspend:true}`. It retains only freshly copied numeric `failures`/`readyAt` records with `timer:0` for that exact view. Page show transfers those records to the new scheduler; its normal queue recreates live timers. Old bindings/controllers/timers are not transferred. Permanent disposal clears the history and prevents restoration; a genuinely new metadata incarnation gets a fresh retry map. No general suspension framework or new decision owner was added.

The existing complete metadata, EN/EDITS/drafts, selection, editor/save ownership, four unsettled browser fetch/body slots, and P15 complete-ID seam remain unchanged.

## Meaningful RED → GREEN

Four amended emitted-APP_JS tests were added in `tests/test_thumbnail_scheduling.py`:

- `test_upward_rows_and_width_repartition_keep_dom_order_and_focused_control`
- `test_pagehide_pageshow_releases_all_owned_rows_and_spacers`
- `test_pagehide_pageshow_preserves_exhausted_view_budget_without_old_bindings`
- `test_pagehide_pageshow_preserves_retry_deadline_and_recreates_only_live_timer`

The tiny DOM adapts insertion, containment, focus loss on moves and geometry primitives; product grouping/reconciliation/queue decisions remain the actual evaluated shipped JavaScript. It is not browser geometry proof.

Against the reviewed product head, the initial amended run was **8 passed / 4 failed**. It reproduced `[12,13,8,9,10,11]` versus `[8,9,10,11,12,13]`, abandoned row/spacer nodes, lost exhausted records, and a lost 600ms deadline. After each local change, the ordering and structural tests passed separately. Final scoped native run: **82 passed in 9.37s**. Applicable actual Python 3.9.25/OpenCV 4.14.0 run: **82 passed in 10.67s**. Both runs included all scheduling tests and the existing choice/save controls.

Exact commands (serial distinct basetemps, under the existing task-local guards):

```bash
. /home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/env.sh
python -m pytest tests/test_thumbnail_scheduling.py -q -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/fix1-red"
python -m pytest tests/test_thumbnail_scheduling.py -q -k upward -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/fix1-order"
python -m pytest tests/test_thumbnail_scheduling.py -q -k releases_all -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/fix1-structure"
python -m pytest tests/test_thumbnail_scheduling.py tests/test_review_choices.py tests/test_review_save_failures.py -q -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/fix1-focused"
# Later, without another concurrent pytest invocation:
export PATH=/tmp/openscrub-python39-20261117/venv/bin:$PATH
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export UV_PYTHON_INSTALL_DIR="$TASK9_ROOT/runtime/python"
python -m pytest tests/test_thumbnail_scheduling.py tests/test_review_choices.py tests/test_review_save_failures.py -q -p no:cacheprovider --basetemp="$TASK9_ROOT/tmp/fix1-floor39"
```

Logs are retained as `red.log`, `order-green.log`, `structure-green.log`, `focused-green.log` and `floor39.log`.

## Focused actual Chromium evidence

Browser plugin remained unavailable; prepared Playwright/Chromium fallback and task-local TMPDIR were reused. One warm-only fixture used actual candidate PAGE, Flask metadata and cached-JPEG routes: 180 ordinary groups plus two collapsed-zone rows. No cold decode, save/render matrix or latency workload was repeated.

At **1365×950 / 7 native columns**, the downward window contained IDs 77–132. An upward overlapping move produced ordered IDs 63–118, retaining 42 overlapping IDs. Native Tab traversed `bb77,kb77,bb78,kb78,...,bb82,kb82` exactly. At **1020×900 / 5 columns**, width repartition preserved the exact focused control; DOM stayed ordered and native Tab traversed `bb70,kb70,...,bb75,kb75` exactly. The screenshot shows the real retained focused action and natural card text.

A descriptor was exhausted through **four actual intercepted browser fetch failures**. Three controlled hide/show replays each changed:

| State | Rows | Spacers | Cards | Retry failures | Active listeners / observers / URLs |
| --- | ---: | ---: | ---: | ---: | --- |
| Before | 6 | 4 | 42 | 4 | 7 / 1 / 41 |
| Hidden | 0 | 0 | 0 | 4 | 0 / 0 / 0 |
| Restored, each of three cycles | 6 | 4 | 42 | 4 | 7 / 1 / 41 |

Owned map counts matched actual DOM counts; old cards were disconnected and new bindings differed. No fifth failure attempt occurred. All retry timers were zero for the exhausted descriptor. A new actual metadata load then reset its history to zero and successfully loaded the preview. Final permanent cleanup had zero rows, spacers, cards, bindings, timers, listeners, observers, URLs and active operations, with no duplicate revocations. Maximum unsettled browser operations remained four. Page JS errors were zero; the four expected intercepted network failures are recorded separately.

The first focused browser invocation passed the ordering/restoration assertions but its final cleanup counter read `REVIEW_SCHED.sections` after `disposeReview` had intentionally set the global to null. This **harness failure** is retained in `browser-first.log` / `browser-first.json`. The counter now inspects the captured disposed owner; `browser-final.log` completes with exit 0. Product source did not change for this harness correction.

At the supervisor's additional focused request, a mid-window anchor check retained **group 77 at −199px exactly**, with **scrollY 4445** and **document height 8478px** before, during and after suspension. Hidden rows/spacers were zero. No further product change was necessary; retaining the explicit section height avoided a collapse in this measured case. See `anchor-before.log` and `anchor-last.json`.

These lifecycle checks replay `PageTransitionEvent` with `persisted:true` against the real rendered page. **Actual BFCache/history navigation was not observed or claimed.** The anchor result is this measured controlled viewport/case, not a guarantee about every platform's history restoration.

## Final source/package/installed binding

- Web SHA-256: `435ee74b112635a9694333fafc9460b3f454d371760f3aba1c4d4fa4875e4563`.
- Evaluated PAGE SHA-256: `8dc91cdf482ba9117777aa3723695477d54925223099bac11d2c610c91aa1483`.
- APP_JS SHA-256: `1d0608598dfd24cd912c90cf810ded4942ba50f918fe82074413827c9ef39d94`.
- Actual `node --check` of final AST-evaluated APP_JS passed.
- Offline actual-3.12 sdist build, extraction and **wheel build from that extracted sdist** passed. Existing task-local cached build tools were reused; no dependency/model download or shared environment mutation.
- Exact runtime bytes, owning/choice/save test inclusion, registries, entry points and Python >=3.9 were rechecked. Sdist: 543,417 bytes, SHA `01b8153cae1fc87305295a644a655c9860524d9430405ed9ece4f2dd579de080`. Wheel: 442,508 bytes, SHA `7968982ac10e73865e49a5f676abbebf38a64498329bf95b1d455e13c66c214d`.
- Wheel installed `--no-index --no-deps` into the separate fix1 target. Installed import/PAGE identity assertions passed with editable checkout paths excluded. Actual listening HTTP `/` returned 200 and contained the **exact final APP_JS bytes**; `/api/jobs` returned 200 with an empty job list. Dynamic serve-time disk values explain why the complete HTTP body hash differs from the PAGE template hash.
- All verified source/test/package hashes were checked unchanged immediately before commit. Native `git diff --check` passed and the final worktree is clean.

Build commands were the same offline process with paths under `runtime/task9/fix1/{build-source,sdist,dist,installed}`; exact executable scripts and complete logs are retained. Both fix1-owned servers were stopped after their PIDs/command lines/cwd were checked, and ports **18513/18514 closed**.

## Retained boundaries

No full suite or unrelated browser/layout/save/render matrix was rerun for this local fix. The original full/required **212** and real save/reopen/render evidence remain bound to **0c2b98e**, not this final head. Current final-head scoped validation is **82 native + 82 actual Python 3.9**, the named Chromium regressions, parse and rebuilt installed/package checks.

No unresolved local finding is known from self-review; formal scoped re-review is still required. Original P06D after-render row loss, P16D ordinary Play startup and all combined P03/P08/P15/P01/P06/P16D C01 gates remain unchanged. No speed/memory/native-cancellation or actual-BFCache claim is added.
