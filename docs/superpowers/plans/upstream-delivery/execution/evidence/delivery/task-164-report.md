# Task 164 — P16D editor live resize alignment

Status: **DONE**, pending the supervisor's fresh independent review. No publication.

## Exact source and scope

- Branch: `pr/editor-resize-alignment`; native worktree `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
- Reviewed base: `92124753736e287ac800af91f0ac96f3e96c01be` (P07a).
- Head: `47e9f6d5614365e00d899c87df6c209cd7aaabf6` — `fix(web): keep editor coordinates aligned on live resize`.
- Head has that exact base as its sole parent; native worktree clean after commit.
- Product edits confined to embedded editor JavaScript in `openscrub_web.py`. Added `tests/test_editor_resize.py`, `tests/editor_resize_server.py`, `tests/editor_resize_browser.cjs`; adapted the existing save-test host to provide ResizeObserver/video.load; added opt-in QA guidance to README.
- No engine, source/timeline route, save acknowledgement, audio decision, masking/padding default, project dependency, or package include change. Existing `tests/` sdist inclusion carries the new assets. No P02/P03/downstream stack, P10 exact-frame, P06D standalone raw-row roundtrip, P16C staging, quad feature, new framework/store, model/dependency download, original-checkout product/data change, push, PR creation, or external message.

## Behavior and ownership

The old editor sized its canvas and scalar only on image load or playback startup. Responsive media could then shrink independently, leaving production painting and inverse pointer input stale. `BE_VIEW` now belongs to one mounted editor/canvas, job/view generation, and editor object. A narrowly owned ResizeObserver measures the active image/video, validates finite positive loaded source/display dimensions, sets exact fractional CSS canvas dimensions and rounded DPR backing dimensions, and redraws immediately. Source→CSS X/Y mapping and CSS→backing X/Y mapping remain separate; inverse pointer mapping uses the same source→CSS transform. Ordinary strokes and handles retain their CSS sizes.

Pointers synchronize geometry before interpreting an event, so an event arriving before the observer delivery cannot use an old origin/scale. Invalid/unloaded/zero geometry clears the current transform and rejects edits. Image and video loads/switches synchronize the active element. Observer and stale image callbacks require the existing job/view/editor ownership plus the current canvas/mount. Panel close/replacement, openJob and deletion disconnect/invalidate the outgoing observer. No extra asynchronous frame work was introduced.

Replacing a transform ends the old gesture and releases its pointer capture. Applied source edits/offset conversions remain intact; only unfinished add/track preview anchors are discarded. The next pointermove cannot continue the old drag. Selection and retained manual/audio/save drafts remain owned by P07a.

### Adjacent playback prerequisite, explicitly authorized

The real playback acceptance initially timed out before any video transform existed. A retained probe showed `BE.playing=true`, `readyState=0`, `networkState=1` (idle), `preload="none"`, no media error, and MP4 support. The existing handler awaited metadata before calling play, while preload=none had not started loading. The supervisor explicitly authorized the smallest fix: install the existing metadata/error listeners, then call `v.load()` inside that same user-requested playback wait. The preload hint remains `none`; editor-open resource behavior is unchanged. Existing mount/job checks still guard the continuation. No error/timeout/playback redesign was added.

## TDD: actual full-PAGE RED → GREEN

Browser discovery found no Browser skill/plugin or browser tool. Used the explicitly authorized prepared regular Playwright fallback: Playwright 1.65.1, Chromium 159.0.8154.6 (`chromium-1255`), Node 22.22.1, headless Linux. Real Flask PAGE and media/frame/boxes/save/render routes; no replacement drawing function or miniature renderer. Screenshot and canvas getImageData measurements inspect production paint.

Initial owning RED ran on the native exact reviewed base **before production edits**:

```sh
cd /home/tahv0/.codex/worktrees/c832/OpenScrub
. /tmp/openscrub-task164/env.sh
export OPENSCRUB_PLAYWRIGHT_MODULE=/tmp/openscrub-save-as-20261116/node_modules/playwright
export OPENSCRUB_CHROMIUM=/tmp/openscrub-save-as-20261116/browsers/chromium-1255/chrome-linux64/chrome
export LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
OPENSCRUB_RESIZE_ARTIFACTS=/tmp/openscrub-task164/red python -m pytest -q tests/test_editor_resize.py
```

`red.log`: expected **1 failed**, `painted edge drift 167.8125 CSS px; visible target hit -1`. Fixture uses source offset `[20,12]`, so its source target is `[140,92,340,232]` rather than the zero-offset research fixture. Desktop canvas/image 640×360; live mobile image width326, stale canvas width640. This is the same owning defect documented by the retained research; the completed two-version matrix was not repeated.

After test expansion, final committed test/server/browser bytes were also run against a complete isolated `git archive` of the exact reviewed base. `rebind_red.py`, `final-red-binding.json`, `final-red.log`, and `final-red/results-1.json`: expected **1 failed in 1.89s**, the same **167.8125 CSS-px drift / hit -1** at the first live-shrink assertion. The candidate was not temporarily reverted. `committed-bytes.json` proves those test bytes equal the head and packaged tests.

GREEN full-page flow: open synthetic review→ordinary preview editor→desktop→live mobile shrink→grow→fractional CSS width→hit/move/corner/add→midgesture resize→hidden/zero/loading image→real playback resize→pause/scrub→close/remount→A→B→A→stale callbacks→real save/render→fresh page reload/reopen. The initial shrink/grow retains the original media/canvas, emits no load/frame/boxes request, and preserves box/time/override/add geometry exactly. No scrub/remount is needed to align it.

Independent expected edges use measured real-media bounds and known source box geometry, never BE_VIEW/BE.scale. Actual edges map opaque production canvas stroke pixels through its own CSS/backing geometry. A normal 2 CSS-px stroke extends about1 px around its path. Tests allow **2 CSS px** for stroke/raster rounding; backing resolution follows DPR and rounds to a whole backing pixel, without rounding stored source coordinates.

| State | Image CSS width | Canvas backing width DPR 1 / DPR 2 | Maximum CSS painted-edge error DPR 1 / DPR 2 |
| --- | ---: | ---: | ---: |
| Desktop | 640 | 640 / 1280 | 1 / 1 |
| Live mobile shrink | 326 | 326 / 652 | 0.812500 / 0.893835 |
| Desktop grow | 640 | 640 / 1280 | 1 / 1 |
| Fractional width | 487.375 | 487 / 975 | 1.022747 / 1.022747 |
| Live video mobile | 326 | 326 / 652 | 0.875115 / 0.981924 |
| Edited mobile | 326 | 326 / 652 | 0.875115 / 0.981924 |
| Saved fresh reopen | 326 | — / 652 | — / 0.920689 |

Visible-target hit is **0** at both DPRs. Browser runs include 1365×1000, 390×844 and 470×844 viewports. They confirm no page exceptions, correct OpenScrub title/meaningful body, no framework overlay, preserved embedded help/enlarged review preview, old observer disconnects and inert manually delivered stale callbacks/image.onload after close and job switch. Only console warning is Chromium's getImageData/willReadFrequently performance suggestion caused by the test's pixel reads. Playback may continue its existing periodic boxes requests; resize itself adds none.

Screenshots were inspected: `final-red/1-mobile-live-editor.png` visibly shows the displaced outline; `full-browser/1-mobile-live.png` shows correct mobile alignment and ordinary page content; saved-reopen screenshot shows the deliberately moved/resized region and newly added region. Full-page and canvas crops for all measured states are retained in both `full-browser/` and `installed-browser/`.

## Source-coordinate persistence and real SDR pixels

DPR 2 pointer edits (including a resize ending a live move, then a fresh deliberate move) select source region:

`[186.25789465247504,123.44236557312857,401.50787862272387,275.94235221462185]`.

Real save sends/persists content override:

`[166.25789465247504,111.44236557312857,381.50787862272387,263.94235221462185]`.

That is the exact existing `ox=20,oy=12` subtraction, with fractional precision retained. Real `boxes_at` on a fresh reloaded page returns the chosen source rectangle again. Added manual source rectangle is `[400.2500096213054,220.50001924261082,490.74998075738915,300.2500096213054]`; the unchanged backend's manual-content conversion truncates to `[380,208,470,288]`. The resize fix adds no rounding to that existing persistence behavior.

The actual application worker produces a 5810-byte SDR MP4 through the real render route. OpenCV decodes its actual 640×360 first frame. At independent source scanline y 172, dark mask edges are x 184..402, within the explicit3 source-pixel render/raster tolerance of the chosen region; the inner region is **100% dark**, and points8 px outside both edges remain bright. `render-pixels.json` and `render-frame.png` retain this oracle. The same exact packaged browser tests against installed-only wheel code produce the same geometry and decoded output evidence. This is coordinate acceptance; it does **not** claim P10 exact-frame or P06D standalone report raw-row preservation is solved.

## Verification commands and results

All artifacts are under `/tmp/openscrub-task164`. Native and installed assertions explicitly verify cwd/imports; original workspace is never a runtime import source. Prepared Python3.12.16/OpenCV4.14/pytest9.2/FFmpeg8.0.1 environment was reused. YuNet was copied from the existing cached model only; outward model fetches are rejected. Task roots isolate jobs/settings/models/cache/temp. HOME is never changed.

- Focused final (`focused-final.log`): same browser environment above, artifacts `green-final/`, `python -m pytest -q tests/test_editor_resize.py tests/test_review_save_failures.py` — **63 passed in 18.32 s**.
- **One full discovered suite**, after product source and behavior tests stabilized (`full.log`): same environment, artifacts `full-browser/`, bare `python -m pytest -q` — **197 passed in 96.64 s**. No skips/failures. This includes all root tests and 62 P07a save/audio cases plus actual resize browser acceptance.
- Python3.9 owning active-source (`floor.log`): source `/tmp/openscrub-python39-20261117/env.sh`; use task-local `hooks39`, `task164floor_isolation`, native source PYTHONPATH and task-local cache/tmp. `python -m pytest -q tests/test_review_save_failures.py test_openscrub.py -k 'review or audio or editor or help or job_video_stream'` — **74 passed,122 deselected in 14.33 s**. Actual Python3.9.25 and active native module hashes asserted before collection. The floor hook's permitted write root is Task164; no original Python39 harness/model/profile changed. Actual browser run is on Python3.12; this is a focused floor gate, not a full 3.9 suite.
- Offline build (`build.log`): source native env, `PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse python -m build --outdir /tmp/openscrub-task164/dist` — successful **sdist→wheel**, isolated local Hatchling 1.33.0, no downloads.
- `python /tmp/openscrub-task164/check_packaging.py` (`packaging-final.log`): exact sdist source/tests/browser assets and wheel product bytes, all packaged Python parses at 3.9 grammar, unchanged engine/project/dependencies/defaults; evaluated APP_JS→`node --check /tmp/openscrub-task164/app.js` passes.
- Prepared3.12 has no pip. Offline target install used that same3.12 Python with temporary `PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --no-compile --target /tmp/openscrub-task164/installed/site-packages /tmp/openscrub-task164/dist/openscrub-1.0.96-py3-none-any.whl`. Bootstrap Python3.14 was **not** run; temporary PYTHONPATH was removed for all installed checks.
- Installed-only exact sdist owning cases (`installed-tests.log`): isolated cwd, `--import-mode=importlib`, installed-hooks+installed target on PYTHONPATH, `task164installed_isolation`; same 74-case selection from extracted sdist — **74 passed,122 deselected in 11.95 s**. Product imports/hashes explicitly point to target site-packages, not extraction/native tree.
- `installed_smoke.py` (`installed-smoke.log`): actual installed `openscrub --help`; real installed `openscrub-web --http --host127.0.0.1 --port<ephemeral> --retain-days0`, homepage and empty job API; normal SIGTERM exit 0. Mask/pad/coverage defaults remain blur/8/tight for CLI and web args. All writable profile data stays under Task164.
- `installed_browser.py` (`installed-browser.log`): exact extracted packaged server/browser/verification test assets with source argument set to installed site-packages; production imports asserted there; full DPR 1/2 real-page pixel/pointer/lifecycle/save/fresh-reopen/render flow and decoded output passed.
- `check_committed.py` (`committed-bytes.log`): clean exact head/parent; all 9 frozen source/test/guidance files match commit, final RED tests, built package and installed product; `git diff --check` passes. No broad suite was rerun after commit because no source/test bytes changed.

Frozen identities are in `verification-source.json`, `packaging.json`, and `committed-bytes.json`. Product web SHA256: `29b6a1ab094c9af1efd42496064775994b130468cf027c5cc50920fd24bb0481`. Wheel SHA256: `5ccfe709c1f5a9a3af4d00e223356ce6d0cd2c76b430a65e46194371889f30ad`. Sdist SHA256: `b9854579a8317d6d55eb9140f27f47ba04b716743dde98bab5e714088bebcc09`.

## Iteration failures retained honestly

1. Owning baseline pixel/hit RED above is intentional and precedes implementation. Final exact test-byte rebind retains the same failure.
2. `focused.log`: expanded browser test timed out starting video; **62 save/audio cases passed**. `video-probe.log`/`video-probe/video-start-1.json` confirm the pre-existing preload-none deadlock. The named explicit-load prerequisite resolves it.
3. `green-playback.log`: full browser reached save but fixture had not started the actual worker, leaving phase queued_render. Corrected **test fixture only** with `web.start_worker()`. No product render issue inferred.
4. `green-render.log`: actual render succeeded, but saved-reopen pixel assertion compared total red paint of two boxes to only the original box. Corrected **test oracle only** to compare aggregate painted bounds to independently mapped aggregate source extents. Original one-box RED assertion remains identical in purpose and still fails on base. Exact fresh reopen now also reloads the page.
5. Early setup shell lacked unqualified python before sourcing the prepared environment; setup used python3 thereafter. A direct hatchling import probe failed because it is intentionally absent from the prepared runtime; the offline isolated build installed it from the existing wheelhouse. Neither was a product/test regression.

## Self-review and limits

Reviewed the complete diff, ownership paths, coordinate/offset conversions, test expectations, emitted JS, package manifest and committed-byte binding. Product change is narrowly located in an already large embedded-JS module; no unrelated restructuring. No remaining correctness concern was found. Observer invalidation and pointer freshness are covered by real callback/gesture transitions; retained P07a failures/newer-draft/audio cases pass.

Coverage is Chromium headless Linux desktop/mobile viewport at DPR 1/2, not native touch hardware or Firefox/Safari. DPR changes while moving a live browser between monitors were not tested. Canvas backing sizes round to device pixels; anti-aliasing/render integer rasterization have the stated tolerances. Source errors and unrelated exact-frame sampling remain outside scope. No new toolchain is required: browser regression is explicit opt-in when existing Playwright/Chromium paths are supplied. No external service was contacted or installed.
