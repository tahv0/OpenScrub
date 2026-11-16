# Upstream delivery execution record

Updated 2026-11-17 (Europe/Helsinki). User selected supervisor-led execution with GPT-6.1 Sol high implementers and subagents. This is a local delivery record, not an upstream PR body or a claim that the whole plan is complete.

## Preserved references

- Austin baseline verified through GitHub API: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f` (v1.0.96).
- Original `develop` / integration tip: `b4d0c75f25d91510fe1692f901d11853dc7db005`; archive ref `archive/integration-all-prs-2026-11-16`. Original code and runtime data remain untouched.
- Planning branch: `docs/upstream-delivery-plan`, initial plan commit `33fdabe73c8105b23980e53d7ac7aeca792ab205`.
- Native managed worktree: `/home/tahv0/.codex/worktrees/c832/OpenScrub`; reused sequentially for task branches. Current branch is recorded in the workspace ledger; do not infer it from this historical record.
- Detailed local evidence/recovery ledger: `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/`. No remote pushes, external messages or PR publication have occurred.

## Completed local candidates

| Task | Branch / commit | What / why | Verification and delivery stage |
| --- | --- | --- | --- |
| P01 | `pr/save-as-progress` / `ca0f2ce7458347afd2e6156a97df580b6623767a` | Preserve working streaming Save As; show accepted written/total bytes, progress, rate/elapsed/estimated remaining time and honest waiting/finalizing/failure states. | Independent review PASS/APPROVE. 24 new tests pass; root+feature 157 pass plus the known pre-existing logging assertion. Build/evaluated JS pass. Chromium real HTTP→OPFS saves exactly 256 MiB, with one pending write, job switching, stalls and close delay; desktop/mobile exercised. Local [PR draft](pr-drafts/save-as-progress.md). Not published/merged. |
| B02a | `pr/tracker-handoff-regression` / `e21ebdf6e3ee46e6c65050dc956a9a3459152269` | Replace a brittle log-message assertion with an explicit post-occlusion sample check; retain the actual geometric identity-protection assertions. Production tracker is unchanged. | Independent review PASS/PASS. Original test fails, correction passes, disabling only the size guard makes the corrected test fail on larger-target adoption. Full 134-test suite and sdist→wheel build pass. Separate [PR draft](pr-drafts/tracker-handoff-regression.md); suitable as the small test prerequisite before other submissions. Not published/merged. |
| P06A | `pr/atomic-report-publication` / `c7cf1f0` + `66787aa09a958154e81e75f9bdc54d9788feb843` | Shared same-directory atomic report publication preserves the last valid JSON on failed saves. Narrow vault cleanup compatibility handles a staging file that disappears after successful publication. | Independent review plus fix review approved. Original head: 147 full-suite passes, build/real HTTP/restart/synthetic scan-render/package/updater checks. Follow-up: 23 focused/root-vault passes, 21 installed-wheel passes, rebuilt sdist/wheel. Exact concurrency regression encrypts all remaining files and decrypts them unchanged. Local [PR draft](pr-drafts/atomic-report-publication.md). Full transaction/vault coordination remains P06B. |

Save As's OS-native picker was controlled at the browser boundary, with a real OPFS writer. Actual OS dialogs, other engines, Windows permissions and multi-GB files were not tested. Its successful 256 MiB run is a functional scenario, not a throughput benchmark or proof of constant whole-browser RSS.

## Baseline environment and limits

Task-local setup lives under `/tmp/openscrub-baseline-20261116`; source `env-opencv4.sh` for the compatible validation environment. Python 3.12.16, OpenCV 4.14.0.94, NumPy 2.5.5, FFmpeg 8.0.1 and Tesseract 5.5.0 were exercised. Dependencies/media tools were isolated; no system packages or custom training tools were installed. Built-in pinned YuNet and standard Tesseract language resources are pretrained inference dependencies.

The original unconstrained environment resolved OpenCV 5.0.0.93 and reported 116 passes, 14 failures and 4 errors with YuNet fetch blocked; its missing Haar fallback constructor is recorded. The OpenCV4+verified-YuNet comparison gave 133 passes and one brittle logging assertion before B02a. Because model availability also differed, the comparison does not isolate every dependency effect. No product requirement pin or OpenCV5 compatibility fix is included. Python3.9, Windows/GPU and container build verification remain outstanding where relevant.

## Preservation and scale evidence

B03 is in progress. Inventory covers 500 integration-only commits and 177 net changed paths. The final core diff now has source-backed dispositions for all 438 hunks, including 45 engine/115 web Python definitions and 150 embedded UI owners. Intermediate history and non-core verification remain open; counts are not a claim that every historical commit is semantically closed.

Useful additions found inside mixed training/section commits include late-window smoothing seek, HDR chroma coverage and invalid-polygon handling, ordinary report-row preservation, tracking publication concurrency, malformed upload options, decoder cleanup and filename HTML escaping. These require their owning regression/scope gates; training/workbench code remains excluded. Current Austin PhiMemory/privacy fixes, queue/watchdog/option recovery, help positioning and ordinary enlarged previews must remain authoritative.

Real loopback HTTP baseline evidence confirms destructive interrupted report writes, overlapping sparse updates losing a choice, and duplicate manual additions on identical replay. An actual 60-frame render plus fresh Flask reopen changes 10 ordinary rows into 7, losing disabled rows and shifting indices; audio suggestions/transcript also disappear, while audio redaction spans and enabled grouping/manual fields survive. These are separate correctness candidates.

Instrumented saves measured 1k/10k/100k ordinary reports. At 100k, 54,078,012 bytes: sparse median about 5.0744s, no-op 4.7366s (three warmups/five samples per scenario). The counter proxy adds overhead; these are not uninstrumented production latency or post-fix speedup claims. Raw scripts/results live in the local ledger's `report-baseline-research/`. Remaining S01–S06 browser/lifecycle/large-video gates are not complete.

## Next delivery work

Next is P06D review-document preservation through rendering, then P07a browser save snapshot/error handling before P06B introduces server busy-state rejections. P06B lifecycle ownership and latest-document transactions may be separate prerequisite PRs. P06C measured no-op/serialization savings and P07b request replay remain separate. P02–P05 and later P/O cards retain their scope. Read-only P11 research is testing late-window seek on real marked short-GOP and single-keyframe video; no performance improvement is claimed yet. No option changes upstream defaults.

For new local candidates, the reviewed two-line B02a test correction may be an explicitly declared common verification prerequisite; no other feature is thereby required. Before submission, refresh Austin's main and present each PR against its actual accepted prerequisite. C01 will test the selected combination; C02 adoption and external publication remain separate operations.
