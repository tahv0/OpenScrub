# Make manual additions safe to retry after a lost save response

A save can commit a manually drawn region even when its response never reaches the browser. Retrying previously appended the same region again. Give each completed Add box draft a retained UUID and persist its normalized creation data in the report. A repeated creation succeeds without adding a row or resetting later box, time or Keep edits.

The server compares the ID with immutable creation data, since the current row may already contain later edits. Conflicting or ambiguous reuse returns JSON HTTP 409 and leaves the whole request unapplied. Older clients that omit an ID retain their existing append behavior. Different IDs can intentionally create equal geometry.

This change depends on the report transaction and browser save-snapshot prerequisites. It adds no lock, journal, database, model or dependency. In-memory drafts still do not survive a browser reload; the caller must retain the identified request for durable replay. IDs do not resolve stale indexed edits after a replacement scan. Skipping unchanged report serialization is a separate performance change.

Validation at the committed source:

- 394 full-suite tests, 239 focused lifecycle/transaction/save checks and 37 focused Python 3.9 cases pass.
- Actual Chromium Add box, scrub, move, resize, retime and Keep interactions survive delayed/lost acknowledgements and another lost retry, with one row per intended ID.
- A real render and fresh server process retain immutable creation, current choices, row order and additive metadata; replay over HTTP adds nothing. Output pixels were sampled on the first decoded frame.
- Offline sdist-to-wheel build, packaged-source agreement, installed CLI/web/vault startup and unchanged defaults pass.

The response failures were injected after real HTTP commits; physical transport disconnection and other browsers/platforms were not tested. See the [implementation evidence](../evidence/delivery/task-72-report.md) and [independent review](../evidence/delivery/task-72-review.md).

Local branch: `pr/manual-addition-replay`.
Base: `f2cdf4813c86296644911f3f0b09bfc56d3e03c5`.
Head: `12919c96c6f7558136b50d7b4d85e5e6b62f1971`.
No push, upstream submission or merge has occurred.
