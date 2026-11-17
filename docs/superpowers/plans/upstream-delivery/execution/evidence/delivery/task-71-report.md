# Task71 / P07a report

Status: DONE, local only. Latest fix commit `92124753736e287ac800af91f0ac96f3e96c01be` (fix round 1, detailed below). Initial implementation commit `786990d9102d41c0ec698d6f31fe798de66a049a` (`Bind review saves to job views and submitted edit snapshots`) on `pr/review-save-snapshots`.

Worktree: `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Exact supplied base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin baseline plus the separately reviewed two-line test-only prerequisite). No P01/A/D feature stack or P06A/P06D changes were imported. Product changes are confined to `openscrub_web.py`; test-discovery documentation and sdist inclusion are in `README.md`/`pyproject.toml`, and regressions in `tests/test_review_save_failures.py`. Original checkout product files and user runtime data were not changed. No remote publication.

## Trigger and resulting behavior

Baseline evaluated JavaScript and an actual Chromium interaction reproduced the defect before product edits. On a synthetic HTTP409 save rejection, the original code still requested `api/jobs/A/render`, emptied `MAN`, and removed the review/editor. Raw browser result:

```json
{"calls":["api/jobs/A/detections","api/jobs/A/render"],"manual":[],"audio":[{"t0":0,"t1":1,"mode":"mute"}],"editor":"editor removed"}
```

The original save also read mutable `CUR` after save/allowlist awaits and cleared current edit collections unconditionally. `beSave` replaced editor content after any outcome. Root causes were operation ownership, missing response checks, and conflating loaded display booleans with pending enabled choices.

Both buttons now enter the same guarded operation. Job ID, view generation, cloned enabled/manual/box/time/audio payload and the owning draft object are captured before requests. Save/render responses require successful HTTP status and valid JSON with `ok:true` and no `error`.409 / 423 / 500, network rejection, invalid JSON and body errors retain unacknowledged drafts and an actionable status; they never trigger render. The editor is retained on failure. Acknowledged unchanged map entries/additions are removed by value and addition identity, preserving newer edits and intentionally identical new regions.

Enabled display values remain separate from pending deliberate choices. Untouched loaded rows are omitted from save payloads. An explicit Blur/Keep/bulk choice is sent even when equal to its loaded value, then becomes acknowledged. LoadedTrue → submittedFalse → userTrue during the request retains a pendingTrue delta after false is acknowledged. Changed audio is sent; plain review and untouched loaded audio do not overwrite stored spans.

A successful save followed by a rejected/unconfirmed render clears committed manual additions before retry. The next Save cannot append those acknowledged additions again. New edits during save or allowlist await stop rendering and remain visibly pending. New edits during an already-submitted render request stay visible with explicit notice that the render used the submitted edits. Duplicate in-flight calls, including cross-button calls, are ignored.

## Ownership and integration contract

`VIEW_GEN` increments on **every** `openJob`, including A→B→A and reopening the current job, and when deleting the selected job. It is not incremented by normal polling or panel opening. P03 integration should preserve this monotonic view identity and capture it alongside job ID across publication boundaries.

`REVIEW_DRAFTS` is page-memory only. Switching jobs retains pending edits and in-flight ownership; returning to that job restores its drafts. A late acknowledgement reconciles its captured owner's unchanged submitted edits, but cannot initiate render for the revisited view or remove the current review. Failed old-job saves preserve drafts for revisiting. Browser reload/closing does not persist drafts. Deletion removes that job's cache entry.

Inactive views discard loaded enabled maps, raw boxes, box display arrays, timeline spans, suggestions and transcript data. Clean inactive entries retain only minimal bookkeeping/status and a fresh empty editor. Pending choices/additions/audio are not evicted. Fresh review loads overlay only pending enabled choices on current server values. No complete report/OCR/thumbnail cache or new workbench was introduced.

Narrow guards cover review/editor initialization, timeline audio publication, scrubbing and playback metadata/box responses, and two existing `refresh` publication boundaries. Outgoing editor media is paused. There is no polling rewrite, save timeout, request-abort cancellation claim, throughput claim, server transaction/locking change or new dependency/framework.

Allowlist suggestions remain the existing confirmation flow. Their extra await stays attached to the captured operation. Rejected allowlist updates are reported; their failure does not replay committed manual additions.

## Tests and commands

All commands ran in the managed worktree unless noted. Environment:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
```

Regression tests use AST evaluation of the actual Python `APP_JS` string and Node VM execution of its actual functions with deferred HTTP responses. They do not substitute a miniature save implementation. Only unrelated startup I/O, DOM primitives and network timing are shimmed. Node-free installations skip these JavaScript tests; no npm dependency was added.

Before implementation:

```sh
python -m pytest tests/test_review_save_failures.py -q -o cache_dir=/tmp/openscrub-task71/pytest-cache
# 20 failed, 4 passed in 28.86s after test-harness startup correction
```

The retained `/tmp/openscrub-task71/red.log` is the corrected deferred-request run: **20 failed, 4 passed in 28.86s**. Initial test-harness startup invoked an unrelated model-panel initializer; that harness was corrected before collecting meaningful RED. A watchdog ensures unresolved deferred scenarios fail instead of silently passing when Node exits.

Incremental RED→GREEN evidence:

- Initial 24 save regressions:24 passed (`green-initial.log`).
- Audio-load/unchanged-audio additions:2 failed, 32 passed (`red-load.log`); both fixed.
- Clean inactive cache/revisit:1 failed, 35 passed (`red-trim.log`); fixed.
- Self-review playback publication/metadata:2 failed, 36 deselected (`red-playback.log`); fixed.

Required named files present on this branch:

```sh
python -m pytest test_openscrub.py tests/test_review_save_failures.py -q -o cache_dir=/tmp/openscrub-task71/pytest-cache
# 170 passed in 61.13s, before the final 2 playback regressions
```

`tests/test_large_report_io.py` is absent from this independent base. The final full discovery run includes the final 38 save/editor cases and all 134 baseline cases:

```sh
python -m pytest -q -o cache_dir=/tmp/openscrub-task71/pytest-cache
# 172 passed in 58.76s
```

Raw final log: `/tmp/openscrub-task71/full-suite-final.log`. No failed or skipped cases in that run. `git diff --check` exited 0. Build/parse:

```sh
python -m build --outdir /tmp/openscrub-task71/dist-final
#Successfully built openscrub-1.0.96.tar.gz and openscrub-1.0.96-py3-none-any.whl
python /tmp/openscrub-task71/parse_build.py
#openscrub.py Python3.9 parse OK
#openscrub_web.py Python3.9 parse OK
#zones_ui.py Python3.9 parse OK
#evaluated APP_JS Node parse OK
#sdist root + tests regression sources included; exact final source bytes verified
#wheel exact final source bytes verified
```

Raw logs: `build-final.log`, `parse-build-final.log` in `/tmp/openscrub-task71`. Python3.9 was checked with `ast.parse(feature_version=(3,9))`, not a Python3.9 runtime. Runtime suite used the supplied Python3.12/OpenCV4 environment.

## Real browser and real engine evidence

Browser plugin/skill unavailable in the tool catalog; regular isolated Playwright/Chromium was used as authorized. No browser dependency changes. P01's installed tooling was reused read-only; all new scripts, screenshots, logs and runtime data are Task71-owned under `/tmp/openscrub-task71`.

Target flow: full OpenScrub page → select synthetic job → ordinary review or box editor → edit/save → failure, pending state, retry, or acknowledged render.

```sh
#Task-local synthetic video/report/server, real Flask routes and worker:
python /tmp/openscrub-task71/serve.py
#http://127.0.0.1:18487
PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers \
LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu \
node /tmp/openscrub-task71/browser.cjs
python /tmp/openscrub-task71/check_output.py
```

Final `browser-final.log` / `browser-results.json`: **18 scenarios passed**, title `OpenScrub`, URL `http://127.0.0.1:18487/`, nonblank true, framework overlay count 0, page exceptions `[]`. Resource console warnings were the deliberately injected409 / 423 / 500/network failures (including retry cases); no unrelated application exceptions. Browser interaction exercised real Blur/Keep, Add box with its existing prompts, timeline audio-span drawing and both Save buttons. Deferred scenarios cover newer enabled/manual/audio edits, duplicate submission, A→B→A late acknowledgement/rejection, allowlist await, render-failure retry. Desktop 1365×1000 and mobile 390×844 screenshots were inspected; status and buttons remain readable and usable.

The normal synthetic check uses a two-second 640×360 fixture and an actual engine-generated report/render state with synthetic review detections. The POST was forwarded through real HTTP; its saved report was read **before render** and verified: only deliberate enabled delta, one appended manual region, changed box coordinates and time bounds, and both audio spans. Then a real x264/box render reached `phase:done,has_output:true`; its output was downloaded and decoded. The submitted manual box covers a textured area: source ROI mean 124.9341 / std 107.3105; rendered ROI mean 0 / std 0. An unrelated clear area remains bright. This establishes actual submitted geometry/output correctness without claiming the independent server fixes.

The first normal-render harness checked output availability immediately after its browser polling and saw `has_output:false` while the worker later finished. Verification was corrected to poll fresh live job JSON and require both done and output availability. Its initial fixture also used invalid `cpu`/`black` option names, which the server sanitized; the final fixture uses valid `x264`/`box`. These were harness corrections, not product polling/engine changes. Raw initial failure remains `browser.log`; final evidence is `browser-final.log`, `actual-job.json`, `actual-saved-report.json`, `actual-output.mp4`, `actual-output-check.json` and `output-check.log`.

Screenshots: `browser-red.png`, `failed-save.png`, `newer-pending-desktop.png`, `newer-pending-mobile.png`, `actual-render-done.png` in `/tmp/openscrub-task71`. An editor overlay scaling issue was observed after resizing an already-open editor; its regression status is unverified. Exact steps for P16: open the editor at 1365×1000, complete a deferred save while adding newer drafts, then call `page.setViewportSize({width:390,height:844})` without reloading or scrubbing and capture the full page. The image scales down while canvas box outlines retain their earlier scale. Evidence: `newer-pending-desktop.png` and `newer-pending-mobile.png`. No pinned-baseline resize reproduction was performed and no resize change is included in this patch. Chromium/Linux only; Firefox, Safari, native Windows/macOS and real device interaction were not tested.

## Self-review and remaining limits

Self-review inspected captured state/await boundaries, equality reconciliation, both entry points, allowlist handling, clean cache eviction, deletion, loader publication and actual output evidence. It found and fixed the playback cross-view publication path with two failing regressions. No nested agents or remote review/publication were used, as dispatched. Final managed worktree is clean after the local commit.

**P07b remains necessary:** if the server commits a manual addition but the save acknowledgement is lost/invalid, retaining that unacknowledged draft cannot make retry idempotent. This branch has no `manual_id`, replay deduplication or restart replay contract. That differs from successful save acknowledgement followed by render failure, which is covered and does not resubmit committed manual additions.

**Known independent baseline server defects remain:** report-write failure corruption (P06A) and render report rewriting that drops disabled rows/audio metadata (P06D). The normal check validates all edits in the pre-render saved report and manual output pixels; it does not assert those metadata survive render or conceal their known failure. Server-side report index stability, concurrent writers and lost-response replay are not solved here. No save deadline or assertion that request abort cancels a server commit was added.

## Fix round 1 — independent clean audio eviction

Review input: [task-71-review.md](task-71-review.md), Important finding “Clean audio remains stale when an unrelated draft is pending.” Status: addressed in separate local commit `92124753736e287ac800af91f0ac96f3e96c01be` (`Refresh clean review audio independently of pending edits`), parent `786990d9102d41c0ec698d6f31fe798de66a049a`. The managed worktree is clean; no amendment, nested agents, publication, server change or replay-ID work.

The finding was reproduced against the actual evaluated `APP_JS`: audio `[0,1]` remained cached across A→B→A when any one of enabled/manual/box/time/editor-add drafts was pending; a fresh server list `[5,6]` was ignored, and adding `[7,8]` would submit the stale list. An unrelated in-flight save also pinned that clean audio. This was a client caching defect independent of P06 server report behavior.

`trimReviewDraft` now clears equal `audio`/`audioSaved` and resets `audioLoaded` independently of other pending edits. Dirty audio, including additions, removals and modified spans, remains recoverable. A small operation-owned `audioInFlight` flag protects a user toggle-back that happens to equal the old baseline while a different audio list is being submitted; saves that did not submit audio do not pin clean audio. On a failed/unacknowledged audio save, `audioSaved:null` means the baseline is uncertain, so the current whole-list intent stays pending and is deliberately resubmitted. This covers loaded B → submit A → user returns to B → response fails/lost, where merely matching the old baseline must not discard B. It does not claim manual-addition idempotence or infer server cancellation/commit status.

Twenty-four new actual-JavaScript cases cover five unrelated draft kinds with fresh clean audio, all five with dirty add/remove/modify audio, an unrelated in-flight save, acknowledgement of an audio toggle-back, and network/423 outcomes followed by audio-intent retry. Existing acknowledgement, toggle-back, HTTP failure, view ownership and duplicate-submit cases remain included.

Exact commands (supplied OpenCV4 environment, managed Task71 worktree):

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python -m pytest tests/test_review_save_failures.py -q -o cache_dir=/tmp/openscrub-task71/pytest-cache
# RED before fix: 6 failed, 54 passed in 6.69s
python -m pytest tests/test_review_save_failures.py -k 'audio_toggle_back_survives_unacknowledged' -q -o cache_dir=/tmp/openscrub-task71/pytest-cache
# Additional RED before fix: 2 failed, 60 deselected in 0.27s
python -m pytest tests/test_review_save_failures.py -q -o cache_dir=/tmp/openscrub-task71/pytest-cache
# GREEN after fix: 62 passed in 6.85s
python -m build --outdir /tmp/openscrub-task71/fix1/dist
# Successfully built openscrub-1.0.96.tar.gz and openscrub-1.0.96-py3-none-any.whl
python /tmp/openscrub-task71/fix1/parse_build.py
# openscrub.py Python3.9 parse OK
# openscrub_web.py Python3.9 parse OK
# zones_ui.py Python3.9 parse OK
# evaluated APP_JS Node parse OK
# sdist root + tests regression sources included; exact final source bytes verified
# wheel exact final source bytes verified
git diff --check
# exit 0
```

Raw evidence: `/tmp/openscrub-task71/fix1/red.log`, `red-audio-retry.log`, `green.log`, `build.log`, `parse-build.log`; exact source bytes were compared with the rebuilt sdist/wheel. The broad root suite was not repeated for this narrow browser-state fix, as dispatched. The earlier 172-pass full-suite evidence applies to the initial reviewed commit; the latest 62-case targeted run includes the earlier 38 cases plus these 24. No new engine/server concern arose.

Focused real browser validation used the actual full OpenScrub page, real job links, editor opening, timeline audio drawing and Save button, with report-response versions and save outcomes controlled through Playwright routing. Browser plugin remains unavailable; authorized isolated Chromium/Linux fallback, 1365×1000 viewport. The synthetic server/runtime stayed task-local.

```sh
python /tmp/openscrub-task71/serve.py
PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers \
LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu \
node /tmp/openscrub-task71/fix1/browser.cjs
# 12 scenarios passed
# URL http://127.0.0.1:18487/, title OpenScrub, nonblank true, overlays 0
# page exceptions []
```

The five clean-audio cases retained their unrelated pending edit, loaded current server audio on revisit, then submitted the current span plus the new timeline span. Dirty add/remove/modify cases submitted the retained user list. A deferred non-audio save refreshed clean audio; deferred audio saves followed by success, 423 rejection or network loss all retained a toggle-back as the next deliberate audio intent. No scenario started a render after its rejected save. Console resource failures were the injected 423/network outcomes; no unexpected page exceptions. Evidence: `fix1/browser.log`, `fix1/browser-results.json`, `fix1/fresh-audio-revisit.png`, `fix1/audio-toggleback-retry.png`; screenshot inspected with controls and actionable status present.

Self-review checked independent cache eviction, same captured editor object across late acknowledgements, the distinction between an audio versus non-audio in-flight save, dirty empty-list/removal preservation, uncertain-baseline retry and shipped source bytes. No additional product scope was added. The Minor contributor-command issue remains deferred for final readiness review per dispatch. Existing P07b and P06A/P06D limits above remain unchanged.
