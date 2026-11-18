### Spec Compliance

- ❌ Issues found: the full-cycle exact-sample ownership requirement is incomplete on HTTP failures. `openscrub_web.py:3418` skips the error response body, and `openscrub_web.py:3428` immediately releases the slot and pumps the next request. See T1004-R1 below.
- ✅ The remaining reviewed implementation matches the ordinary-editor-and-Track scope: exact input/readiness (`openscrub_web.py:3347`, `:3361`, `:3380`, `:3432`), atomic first geometry capture (`:3442`), open/playback/timeline fences (`:3523`, `:3595`, `:3736`), strict Track (`:3813`), paired draft submission/ACK (`:4337`, `:4353`, `:4390`) and explicit recovery (`:4297`, `:4309`, `:4315`). The policy validator uses the binding erratum's accepted `opencv-ffmpeg-zero-cfr-v1`, with the eight-field projection and an incorrect-policy negative control.
- ✅ Scope and boundary claims checked: comparing the archived BASE setup file hashes with frozen final file hashes yields exactly the seven paths in the supplied diff, with no removals; all 136 frozen final file hashes match the checkout. The complete diff changes web code only inside the literal `APP_JS` assignment (`openscrub_web.py:2966`). Engine/private helpers, dependency/default/platform files and the ten-module inventory remain unchanged. Literal APP_JS and APP_CSS hashes independently match the report. No extra runtime module or full-APP_JS extraction was introduced.
- ⚠️ Cannot independently verify live ref/index cleanliness without reopening repository state, which this review was instructed not to do. The archived `task1004-evidence/refs-preserved.json:1` reports only the new task ref and the authorized docs-ref advancement. Current live ref/index assurance remains with the controller's source freeze.
- ⚠️ Recorded execution establishes prepared Linux Chromium DPR1/2, Python 3.12.16 and affected-owner/server checks on actual Python 3.9.25. Windows/Docker execution, installed Python 3.9 packaging, HDR/touch behavior and real tracker quality are not established by this task's evidence; these limits are stated accurately and do not add requirements to this task gate.

### Strengths

- `openscrub_web.py:3380`, `:3432`, `:3442`: successful samples retain one owner through detached and displayed-image decode, use decoded dimensions/current transforms, and require strict evidence before a new mutation. Pending geometry keeps its first family across inspection; existing out-of-frame rows remain admissible while new Add/Track boxes have strict bounds.
- `openscrub_web.py:4353`: strict ACK rows are all validated before any edit kind clears. Original-owner identity and submitted-value equality preserve newer paired values; returned complete bases, including last_seen, advance the owned family. Current display reconciliation uses the current sample offset and refuses transplantation into another mount/context. `tests/test_review_save_failures.py:613`, `:626`, `:666`, `:714` exercise the relevant shipped functions.
- `openscrub_web.py:4309`, `:4315`, `:4390`: uncertain retries remain immutable; authoritative first rejection is distinguished from later uncertain rejection. Explicit abandon/discard rechecks ownership and values, removes only its selected owner/value, and preserves independent work. The implementation keeps these controls bounded beside the text-only status.
- `openscrub_web.py:3595`, `:3736`, `:3813`: playback, timeline gestures and Track capture their initiating owners and fence late continuations. Strict Track captures its source box, canonical time, window and seed synchronously. No backend token or tracking-quality claim is invented.
- `tests/editor_resize_server.py:56`, `tests/exact_editor_browser.cjs:56`, `tests/test_editor_resize.py:19`, `:82`: PAGE validation uses independent sequential-decode/PTS/marker/offset facts, actual route persistence, real SDR rendering and independent rendered-pixel checks. The separate-process reopen starts after the original server has been terminated and reaped. Test-only readback surfaces address the canvas warning without altering production painting.
- Evidence checked rather than regenerated: all 178 manifest rows pass size/SHA-256 checks, every archive hash matches, and the recorded source-bound final logs show 620 native passes and 141 actual-3.9 owner passes. Both PAGE browser logs/results and both separate-process reopen results have empty unexpected errors/warnings and no reopen writes. The deliberately refused render's HTTP409 diagnostic is retained separately. Inspected the mobile edited-canvas and exact DPR2 final screenshots.
- Shipping claims checked against final config, package identities and installed logs: sdist and wheel bytes/hash match the report; installed origins include all ten expected modules; installed defaults, strict/no-seed listening HTTP, exact PAGE substitutions and updater test bytes are recorded. The archived roundtrip adapter record identifies only its selected test and retained child stdout/stderr. No suite, browser or build was rerun for review.

### Issues

#### Critical (Must Fix)

- None found in this task-scoped review.

#### Important (Should Fix)

- **T1004-R1 — error bodies escape the page-wide sample slot.** `openscrub_web.py:3418` throws immediately when `fetch()` returns non-success headers. The only body await is the subsequent success-only `response.json()` at `:3419`. Consequently `finally` at `:3428` clears `EDIT_SAMPLE_IO.active` and starts the latest wanted sample even when the earlier HTTP409/423/500 (including non-JSON middleware refusal) body is still unsettled. For example: issue A1, queue A2, receive A1's error headers while its body is delayed; A2 starts without waiting for that body. Ownership guards prevent stale application, but they do not restore the required bound on unsettled fetch/body cycles, and there is no deterministic body cleanup on this branch. Await error-body exhaustion/failure before releasing the slot, retaining HTTP-first handling and useful status text; do not abort issued work merely to free the slot. Add a genuine focused regression with a delayed non-success, non-JSON body, latest-wanted replacement across mounts, and assertions that no second fetch starts until the old body settles and that no decode/URL is allocated. Existing `tests/test_review_save_failures.py:537` and `tests/exact_editor_browser.cjs:65` gate successful bodies only. This finding is established from source; no runtime was allocated in the metadata-only review window.

#### Minor (Nice to Have)

- None identified that needs a separate task finding.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The implementation is coherent across editor, save/recovery, playback, timeline and Track, and its recorded validation is substantial and correctly scoped. T1004-R1 violates the explicit full-cycle resource-ownership guarantee on the failure path and needs a focused fix and regression before this task gate can approve.

### Review Basis and Focused Checks

- Reviewed BASE `07cfaa9539a2561c26b6f7280fae6702eb07137c` → HEAD `dcaa0e5af6aedfca8685a3e64bea86ad0262f5c2`, using the entire supplied 1,929-line diff once; requirements were read before the report/diff. This is the sole task reviewer, covering ordinary editing and Track together, with no subagents.
- Concrete cut-context checks: the diff clips `beMount`'s transform update, `loadBoxEdit`'s generated controls, playback's rAF body and `saveAndRender`'s render fence. Read only those missing contexts at `openscrub_web.py:3489`, `:3543`, `:3633`, `:4408`; current transform, owner/serial and pending-edit fences are present. Other changed-source access was limited to hash/AST/line-location bookkeeping.
- Concrete unchanged-source risk check: confirmed current ACK display activity/offset semantics against accepted `job_edit_sample` at `openscrub_web.py:1778` and the strict ACK construction at `:2243`. The UI's canonical active-span rule and complete committed base agree with those routes. No broader source crawl or Git/diff commands were used.
- Evidence basis: `task1004-evidence/manifest.json:1`, `archive-sha256.json:1`, `commands-results.json:1`, final configs/preflight/logs, `PAGE/resize`, `PAGE/exact`, their separate-process results, package identities and installed logs. Original failed runs remain separately attributed; they were not counted as final acceptance or relabeled as backend regressions.
