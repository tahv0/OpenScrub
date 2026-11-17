# P09 contract source anchors

Source-only collection, 2026-11-17. `git show`/`git diff` read immutable objects; no checkout, product import or runtime observation. Original `openscrub_web.py` line numbers are retained. No new baseline was run.

| Identity | SHA-256 |
| --- | --- |
| reviewed P02/P07a `2ae3257b9752e2d976ff7a0d39955a13c133273a`, `openscrub_web.py` | `af3b9e97b55deefa5bdeb372f66ed545d34c0517ce3df2f5e7a4870bedad4a8f` |
| comparison P03 `6ae212a35b094fc9466f1616afb2c5bb5c0497f8`, `openscrub_web.py` | `5c975b08b81bccb79661bac10e68ac286ac1f45aa3560b39517db4f0cc19aae0` |
| P02 `tests/test_review_choices.py` | `e0c18159987ad6f91ca5faa72864193af6fceffdd9515191f4de51b84b8b088d` |
| P02 `tests/test_review_save_failures.py` | `35e2d0d4a0cb19eec169b3fc5571ff6a148fdc344d57fd3124ed8272804dd6d4` |

- [Browser anchors](p02-browser-anchors.txt): actual grid/image sizing, drafts/generation, teardown, poll entry, editor/lightbox, grouping/rendering, setters/retries/selection and saves.
- [Server anchors](p02-server-anchors.txt): independent pre-generation and its source-selection ordering, complete detections response, warm/cold thumbnail route.
- [P03 comparison](p03-comparison.txt): compact first 272 lines of the source comparison, including polling ownership and the beginning of review changes. This is a cross-pin comparison, not a proposed patch; P03 here lacks P02 controls/indexes.

Retained runtime evidence remains in `docs/superpowers/plans/upstream-delivery/execution/evidence/research/review-scheduling-baseline-evidence/`: `source-hashes.json`, `verification.json`, `browser-summary.json`, `cold-and-exploratory-notes.json`, `http-payloads.json`, `environment.json` and source excerpts. Its baseline is `e21ebdf6e3ee46e6c65050dc956a9a3459152269`; its small P07a case is `92124753736e287ac800af91f0ac96f3e96c01be`. Those are different from the design pin above. See the adjacent research report for the bounded future measurement recipe and limits.
