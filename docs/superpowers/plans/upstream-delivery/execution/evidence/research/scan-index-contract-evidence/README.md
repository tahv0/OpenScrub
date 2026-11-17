# Source-only evidence manifest

Product commit: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
Tree: `795af785b672d397d2e287b5b963c10dcc4dbdf8`.

Files ending `-lines.txt` are `git show <commit>:<path> | nl -ba | sed -n '<selected ranges>p'` excerpts. Numbers are the original complete-file line numbers, not excerpt line numbers. No excerpt was executed or imported.

- `openscrub-e21ebdf-lines.txt`: Detection/PhiMemory, overlap, complete merge/reverse owners, ordinary scan/visual-gap/report call sites.
- `openscrub-web-e21ebdf-lines.txt`: web run_scan → write_report publication boundary.
- `test-openscrub-e21ebdf-lines.txt`: existing forward-memory, dense-merge and tail-support tests, inspected as source only.
- `requirements-large-video-performance.md.txt`: working-tree requirements copy, **not** a file in the product commit. P11B/C/D are at lines 233–259. SHA-256 `a45146ea4322465cb994f8f976e88e1d84a9f519a86a16fcb3f2aa5ab4431c81`.

Verified Git blob identities: `openscrub.py` = `f02b4d018fb0de9f906ad16d5b8b9b172dfde293`; `openscrub_web.py` = `61589a6ebe0950ea5b0364e6d27dec01e3346e3b`; `test_openscrub.py` = `49f4daf5ffb0be34b86a0edbd39a812ab2cd30e7`. Identity was read with `git ls-tree` and `git rev-parse <commit>:<path>`, not inferred from the active checkout. No export or runtime environment was needed.

Other read-only queries were pinned `git grep -n` for `reverse_pass`, `merge_detections`, `boxes_overlap`, memory construction/add/cached access and report ownership; `git ls-tree -r --name-only` for full-module/test boundaries; and `git log -1 --format=fuller <commit>` for prerequisite identity. The attempt to `git show <commit>:docs/superpowers/plans/upstream-delivery/02-large-video-performance.md` returned that the file is absent in the pin; the report distinguishes its working-tree requirements identity accordingly.

Read prerequisites: `../scan-index-contract-brief.md`, `../scan-history-baseline-research.md`, `../tail-history-source-plan.md`. Earlier probe results were not rerun or repackaged as new evidence. This folder contains source evidence only: no work-count execution, timing, test, media, browser, build, model or application-import result.
