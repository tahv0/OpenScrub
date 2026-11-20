# Stop & Review in the web app

The experimental control is off by default. The application topic documents supported scans and source and report guarantees in `docs/CHECKPOINT_CONTRACT.md`. The initial app slice is for supported POSIX H.264 MP4 sources with constant frame rate and QR or no automatic detectors. A paused job can be inspected and edited to its last processed frame. Resuming completes the scan before normal review and export. The ordinary plate search, tracker, mask, and rendering workflows remain available in their respective supported modes.

| What | Why | When to deliver |
| --- | --- | --- |
| Wire the optional scan setup to the actual worker. Stop on a whole-frame boundary, let acknowledged Cancel win before publication, and use the existing operation and report owners. | The control must stop a real scan and expose only frames accounted for by the checkpoint. The previous output stays on disk and cannot stand in for the new report. | After the engine, prefix reads, and restart prerequisites are accepted. First app PR in this series. Include real Stop, Cancel, restart, and completed scan cases. |
| Save bounded geometry, manual regions, audio and output choices. Return a report-generation token to authorize Resume. Apply row-bound release and replay verification to exact time edits after completion as well. | Resume must pick up the report the user actually saved. Earlier frame bounds must continue to apply to untouched rows. | After the worker and prefix reads. Give the backend change its own review and include lost acknowledgement, changed source, and stale token cases. |
| Show the processed prefix and wire Stop, Save and Resume to the browser. Keep pending edits when Save is uncertain. | The user can inspect the actual paused range and can retry a save without losing newer work. | After the worker and Save API contract. Give reviewers a browser reproduction with an actual stopped report and normal render after resumed EOF. |
| Recover a provable publication interruption on startup. | A process exit between report replacement and marker retirement should preserve a valid job. An ambiguous report must stay fenced. | Keep the recovery follow-up with the worker series. Exercise the old, new and unrecognized report outcomes independently before submitting the browser controls. |
| Persist original checkpoint settings before queue admission and stage checkpoint uploads before registering the jobs. | Resume needs the original scan settings after a restart. An options or upload write failure should leave the entire checkpoint upload batch unqueued. | Keep this as an intake follow-up in the worker series. Include storage fault injection, ordinary intake, and vault/lifetime checks. |

## Source and evidence

- Worker and setup: `86c9112`. Independent worker, real HTTP and Chromium selection passed 149 tests in each of Python 3.12 and 3.9.
- Save and Resume handoff: `61cc6df`. Supervisor ran 194 focused checks on each Python version. Completed exact reads and saves: `a6bb6af`, with 126 focused checks on each version.
- Paused controls and completed frame-bound acknowledgements: `afb0253`, including the lost-acknowledgement regression at `cbf194a`.
- Checkpoint setup keeps a permanent name allowlist scoped to ordinary name scanning. The worker repair at `4bbe514` has a real QR/no-detector regression and an ordinary-name control.
- Durable options and staged intake: `9f4bdb8`. The 142-test intake, lifecycle and vault-source selection passed on each Python version.
- Proof-based restart recovery: `pr/checkpoint-web-worker` at `2d136c5`, carried into the combined branch at `3325092`. Actual subprocess exits exercise both sides of atomic report replacement. Inconclusive or legacy marker evidence remains fenced.

These topics are available as local candidates. Their upstream drafts should refer to the accepted predecessor PRs and use the corresponding focused verification evidence.
