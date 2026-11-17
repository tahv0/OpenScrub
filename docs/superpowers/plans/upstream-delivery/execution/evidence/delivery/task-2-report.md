# P01 implementation report: streaming Save As with byte progress

Date: 2026-11-16. Native worktree:
`/home/tahv0/.codex/worktrees/c832/OpenScrub`, branch `pr/save-as-progress`.
Base: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.

## Disposition

Implemented a local PR candidate with destination selection, streaming accepted-byte
progress, elapsed time, approximate remaining time, waiting/finalizing states and
honest direct-download fallback. No remote push, PR publication or external comment
was made. Local commit: `ca0f2ce7458347afd2e6156a97df580b6623767a`
(`Add streaming Save As with byte progress for exports`). The post-commit
worktree status is clean; only the five task-owned paths were committed.

All **24 new behavior cases pass**. The required combined suite and default pytest
discovery both produce **157 passed, 1 failed**; the sole failure remains the
unchanged baseline `test_track_person_size_jump_handoff` logging assertion. Full
sdist→wheel build, evaluated combined embedded-JS syntax, Python AST, rendered
Chromium interaction and real loopback HTTP checks pass. The existing root failure
was neither skipped nor changed. This is not a claim of an entirely green suite.

## Changed source

- `openscrub_web.py`: shared `export_filenames(job) -> tuple[str, str]`, additive
  `download_name`/`report_name` metadata, unchanged download/report route shapes;
  destination controls and export-local progress state in existing embedded JS.
- `tests/test_export_save_as.py`: Flask attachment/size checks and actual evaluated
  Save As JavaScript under controlled async picker/network/write/close/clock inputs.
- `README.md`: browser support, destination, progress and fallback description.
- `CONTRIBUTING.md`: root + focused test collection and the Node.js requirement.
- `pyproject.toml`: include `tests/` in the sdist; no new runtime module/dependency,
  entry point, version or release change.

Read `CONTRIBUTING.md`, relevant `CLAUDE.md` architecture/verification instructions,
the exact P01 brief, B01/B02 report and review. Used TDD, frontend validation,
systematic debugging and verification skills. The brief prohibits subagents, so
this implementer performed self-review and leaves independent review to the
supervisor; no nested reviewer was launched.

Supervisor scope correction: upstream has no pytest CI job to extend. Existing
release/image/installer workflows remain unchanged. Root + `tests/` collection is
explicit in contributor instructions and verified by default pytest discovery;
new tests ship in the sdist. No unrelated, knowingly red CI workflow was added.

## Donor comparison and usability trigger

Compared donor `2900930f41805cae3f38eab10f56347cd79f8a08` by Tuomas Aho with
current routes. Both already select the actual output suffix (e.g. MKV) rather
than forcing MP4. P01 shares this existing calculation between picker and HTTP;
it does **not** fix or claim an upstream extension-handling regression.

For the before capture, composed the donor's real `APP_JS` into the baseline page
shell with isolated synthetic job metadata. In real Chromium during a slowed
256 MiB HTTP transfer it showed a disabled **“Saving…”** button and **zero export
progress bars**, with no page errors. Real donor-surface download/report responses
were 200 with `Content-Length: 268435456` and `18` respectively.
Evidence: `/tmp/openscrub-save-as-20261116/donor-static-saving.png`,
`donor-browser.log`, `donor.cjs`, `serve.py`. This missing feedback in donor Save As
is the usability trigger; no measured transfer-speed improvement is claimed.

## Implementation behavior and review

Picker invocation occurs synchronously in the click handler before any network
await. Job ID, suggested filename, export kind and route are captured before the
picker resolves. Cancel causes no export fetch and restores previous feedback.
Each export is keyed by captured job/kind, can survive ordinary 900ms polling and
switching away/back, and late callbacks cannot display its progress on another job.
The existing refresh gets narrowly scoped job-ID guards around its awaits so
export names/controls cannot be populated by a response for another selected job;
this is not a general polling redesign.

The read/write loop awaits each destination write before adding its byte length or
reading the next chunk. It does not use `.blob()` or accumulate the response. Only
a valid safe-integer `Content-Length` from an unencoded/identity response becomes
a total; job metadata size is never used. Encoded, absent, negative, malformed and
unsafe lengths remain indeterminate. A reliable total mismatch fails before close.
EOF enters **Finalizing…**; **Saved** appears only after close resolves. Failures
cancel the reader/abort the writable as applicable, clear the timer and retain a
retry/direct-download message. Zero-byte completion and failed write/close paths
are covered.

A 250ms timer keeps elapsed time/status responsive while read/write/close is
pending. Active visual updates are throttled to 250ms per mounted export view;
phase transitions are immediate. Live announcements have a separate 2-second
cadence plus phase changes. Rate observations are coalesced into 250ms buckets
with one boundary observation and a rolling ten-second window; ETA starts after
three seconds. Five seconds without an accepted write shows **Waiting for data or
disk…** and removes ETA. Finalizing hides ETA. Numerator, denominator and rate use
the same decimal unit. Timing proposals otherwise remain unchanged.

Direct links remain available for both exports. Unsupported/insecure contexts show
the direct links plus browser-settings guidance. Direct clicks say **Download
started — see browser downloads**, hide the progress bar and make no local-save
completion claim. Existing human-review reminder, routes, report shape, face
margins, vault and job lifecycle remain unchanged.

Self-review inspected the complete product/test/docs diff, cleanup and cancellation
paths, response-length trust, job capture, timer/announcement behavior, packaging
and scope. Strengthened the Node harness so an unresolved async scenario cannot
exit successfully, and its progress attributes mirror browser semantics. No
blocking issue remains from this implementer's review. Independent review is not
claimed.

## RED / GREEN evidence

All artifacts below are under `/tmp/openscrub-save-as-20261116/` unless absolute.

- `red.log`: initial 21 cases fail before implementation for absent filename
  metadata/Save As function; no setup or syntax failures explain the RED state.
- `green-initial.log`: those 21 cases pass after the first implementation.
- `red-throttle.log`: visual updates happened inside 250ms (`3 != 2`);
  `green.log` passes 23 cases after per-view throttling.
- `red-rate.log`: sparse write observations incorrectly used a 13-second
  denominator (`7.5 KB/s` instead of `10.0 KB/s`);
  `green-rate.log` passes 24 cases after bounding the rate denominator/window.
- `green-harness.log`: **24 passed in 1.87s**, after the final async-completion
  guard and realistic progress-attribute behavior were added.
- Tests cover the required named regressions, MP4/MKV/no-suffix output, actual
  video/report headers and bodies, cancellation, picker/job switching, accepted
  writes/backpressure, known/unknown/encoded/invalid totals, waiting/stale ETA,
  finalization, zero output, mismatch, network/write/close/HTTP/body errors,
  repeat exports and independent visual/live-announcement cadence.

## Commands and complete verification

All application commands ran in the native worktree, with:

```bash
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
```

This reuses B01/B02's Python 3.12.16 + OpenCV 4.14.0.94 environment, pinned built-in
YuNet, isolated synthetic runtime paths and blocked model network fetches. It does
not establish current unconstrained OpenCV 5 compatibility or Python 3.9 runtime
coverage. No optional/custom training/workbench dependencies were installed.

| Check | Actual result | Evidence |
|---|---|---|
| `python -m pytest tests/test_export_save_as.py -q -o cache_dir=/tmp/openscrub-save-as-20261116/pytest-cache` | 24 passed, exit 0 | `green-harness.log` |
| `python -m pytest test_openscrub.py tests/test_export_save_as.py -q -o cache_dir=/tmp/openscrub-save-as-20261116/pytest-cache` | 157 passed, same 1 baseline failure, 75.96s, exit 1 | `full-required.log` |
| `python -m pytest -q -o cache_dir=/tmp/openscrub-save-as-20261116/pytest-cache` | 157 passed, same 1 baseline failure, 73.12s, exit 1 | `full-discovery.log` |
| `python -m build --outdir /tmp/openscrub-save-as-20261116/dist-final` | sdist then wheel from sdist, exit 0 | `build-final.log` |
| AST parse changed Python; join both scripts from evaluated `web.PAGE`; `node --check .../evaluated-page.js` | pass, exit 0 | evaluated JS file; tool output |
| `git diff --check` | pass, exit 0 | tool output |
| Real Cheroot + Playwright Chromium scenario | pass, exit 0 | `browser.log`, `browser-results.json`, screenshots |

The exact existing failure is at `test_openscrub.py:2335`: no callback log contains
`size jump`. B01/B02 diagnosis showed the original target retained while a prior
held state suppresses that log. P01 does not change its test or tracker.

Final distributions retain version 1.0.96:

- `dist-final/openscrub-1.0.96.tar.gz`: 530,340 bytes, SHA256
  `45629ac9dc852131b4655e50512a459e2c4241af8d2aace4c2830314c2db5cc9`.
- `dist-final/openscrub-1.0.96-py3-none-any.whl`: 437,460 bytes, SHA256
  `513e3ae0efc3f9fd14aee7a1ffde1d4097b8de9c996353ecee0183de9dee4daf`.

Inspected archives: sdist includes the exact final `tests/test_export_save_as.py`;
wheel includes the exact final `openscrub_web.py`. Tests remain out of the wheel.
Earlier `dist/`/`build.log` also passed; `dist-final/` contains final shipped tests.

## Rendered/HTTP QA

Browser plugin not available; regular Playwright was explicitly authorized.
The flow under test was: `http://127.0.0.1:18484/` → synthetic rendered job →
Save As video/report → accepted-byte progress → finalizing → successful close,
including cancellation, failures, polling/job switching, repeated exports and
direct fallback.

Isolated QA tools: Playwright installed under `/tmp/openscrub-save-as-20261116`,
Chromium 159.0.8154.6 (Playwright browser v1255), with missing libnspr4 4.38.2,
libnss3 3.120 and libasound2t64 1.2.15.3 libraries extracted under that same `/tmp`
root. No system install or repository dependency/toolchain change was made.
`serve.py` runs real Cheroot/Flask with sparse synthetic output and synthetic JSON;
no user jobs, media, settings or model caches were used.

The browser injects a controlled picker boundary (including cancellation and delayed
selection) and returns a real browser OPFS writable, wrapping writes/close with
controlled delays/errors. This tests rendered app control flow plus real HTTP and
real File System Access writable behavior, **not interaction with an OS-native
Save As dialog**. Native picker UI acceptance, Windows folder permissions and
physical disk durability remain unverified.

| Browser check | Result |
|---|---|
| Identity | URL `http://127.0.0.1:18484/`, title `OpenScrub` |
| Meaningful page / no error overlay | Pass; app/editor/jobs/actions rendered |
| Console | No page errors; one expected `net::ERR_FAILED` from injected network failure |
| Desktop | 1365×950; controls, accepted-byte status, waiting, finalizing, saved and direct fallback inspected |
| Mobile | 390×844; document width 390px, export width 326px; no horizontal overflow; labels wrap readably |
| Picker cancel | Zero export requests; control re-enabled |
| Job switch during picker | Captured alpha name/route retained; beta receives no alpha progress |
| Network/write/close failure | Actionable failed feedback; cleanup and successful retry exercised |
| Data/destination stall | >5 seconds pending write; accepted count fixed, waiting text visible, stale ETA hidden |
| Normal polling / switch away/back | Export state retained; other job stays clear; saved state survives polling |
| Final close pending | Full byte count and Finalizing shown; no premature Saved |
| Repeated report exports | 18-byte actual output and repeated successful close |
| Unsupported fallback | Native browser download event; correct audit filename; honest started text and hidden progress |

Large transfer: a **256 MiB (268,435,456-byte)** synthetic MKV traveled through the
real video route with CDP data throttling (16 MiB/s configured ceiling) and injected
destination delays. The final corrected scenario observed about **55 seconds** of
progress, including its deliberate stall and close delay; this is a test scenario,
not a throughput benchmark. Final accepted bytes, progress maximum/value and actual
OPFS file size all equal **268,435,456**. At most **one write** was in flight; maximum
fetched-but-unaccepted data was **2,097,152 bytes**, exactly one observed maximum
chunk. `.blob()` was overridden to throw and was never used successfully. The
application retains a bounded rate history rather than file chunks.

Memory observation: 55 one-second CDP `Runtime.getHeapUsage` samples. JS used heap
ranged 3,033,652–29,785,564 bytes; backing storage 601,590–68,591,727 bytes; maximum
combined JS heap + backing storage was **88,907,747 bytes (~84.8 MiB)**. Embedder heap
samples ranged 5,677,840–128,792,920 bytes. These observations support the recorded
bounded application queue and absence of whole-response buffering; they are **not**
a measurement of total browser/process RSS, a proof of constant memory for every
file size, or a physical-disk allocation/durability guarantee.

### QA harness investigation

Initial browser run timed out at 30s because the timeout was passed in Playwright's
argument slot instead of options; corrected that invocation. A subsequent 120s
limit still did not complete. Added live phase/byte/memory sampling before changing
anything further: phase was Saving, 5,602,944 accepted of 268,435,456, with only one
3,000-byte chunk ahead and no failed/finalizing state. CDP throttling can yield
small chunks, and unconditional injected 8ms delay on each write made this QA
scenario extremely slow. The fix is **QA-only**: inject the 8ms disk delay per
256 KiB accepted interval while retaining the separate >5s pending-write pause,
real per-chunk writable backpressure, data throttling and delayed final close.
The resulting full 256 MiB scenario passed. No product workaround or speed claim
was introduced. Retained initial timeout logs and slow-harness sample alongside the
final results. A stale killed-run message can precede the final JSON in `browser.log`;
its final completed JSON, `browser-results.json` and exit 0 identify the passing run.

Reproduce the final browser path with the preserved scripts:

```bash
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
export PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers
python /tmp/openscrub-save-as-20261116/serve.py
# In a second shell with the same environment:
node /tmp/openscrub-save-as-20261116/browser.cjs
```

Remaining limits: browser picker boundary is controlled, only Chromium was run,
no real multi-GB export, no Safari/Firefox/native Windows/TLS deployment flow,
no whole-process RSS measurement and no Python 3.9 execution. Fallback was exercised
by removing picker support; the actual insecure-origin browser policy was not
reconfigured. The known root-suite baseline failure remains visible. Installing
the Browser plugin could improve later in-app validation but is not required by
this local candidate.

## Screenshot evidence

All screenshots contain synthetic data only and remain outside committed source.
Desktop captures preserve the full app viewport; some export text lies near the
bottom edge because the editor/jobs precede it. Mobile shows the complete action
area after scrolling. DOM/status assertions supply the exact text/byte evidence.

- Before donor: `/tmp/openscrub-save-as-20261116/donor-static-saving.png`
- Progress: `/tmp/openscrub-save-as-20261116/progress-desktop.png`
- Pending write: `/tmp/openscrub-save-as-20261116/waiting.png`
- Finalizing: `/tmp/openscrub-save-as-20261116/finalizing.png`
- Saved: `/tmp/openscrub-save-as-20261116/saved.png`
- Write failure: `/tmp/openscrub-save-as-20261116/failed-write.png`
- Mobile saved controls: `/tmp/openscrub-save-as-20261116/progress-mobile.png`
- Direct fallback: `/tmp/openscrub-save-as-20261116/fallback.png`
