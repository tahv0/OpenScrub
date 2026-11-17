# Source-only exact-editor evidence

2026-11-17. These are immutable source excerpts and document/source identities, **not new runtime evidence**. Task162 owns native/product execution. No source import, decoding, model, test, build, browser, benchmark or network command was run for this handoff. No prior decoder feasibility run was repeated.

Product commit: `12919c96c6f7558136b50d7b4d85e5e6b62f1971`.
Tree: `ed743d1b79b8b3ebf8d7f65aa11a12cf0894360e`.

Verified directly with read-only `git rev-parse` / `git ls-tree`, not a working-tree export:

| Product source | Git blob |
|---|---|
| openscrub.py | `9a9c82d7eb8075510e5c2dbbbe63be3c943a399f` |
| openscrub_web.py | `137091183f66e99350153b38ce060b02f95e55f0` |
| openscrub_internal/lifetimes.py | `992adfb357631f69792f22e437a3b1d61e2a7ca8` |

[source-git-identities.txt](source-git-identities.txt) also identifies the two source test files and package declaration. [input-documents.sha256](input-documents.sha256) records the authorized brief and three required prior studies as read. The P10A card was read at the authorized supervisor path `docs/superpowers/plans/upstream-delivery/02-large-video-performance.md:180–200`; it is absent from this Git pin, as confirmed by a failed read-only `git show`. It is a requirements document, not product evidence.

Every excerpt retains **original pinned source line numbers**, produced with `git show <commit>:<path> | nl -ba | sed -n '<ranges>'`. Discontinuous ranges are intentional; no product file was executed. Read-only Git source commands and shell text selection/hash commands were the only source inspection mechanism. Only the named handoff Markdown and this evidence directory were written.

| Excerpt | Original file / relevant owners |
|---|---|
| [web-ownership.txt](web-ownership.txt) | openscrub_web.py: P06 admission/source selection, operation/report lock, scan report-before-source interval, response release and rehydration |
| [lifetimes.txt](lifetimes.txt) | openscrub_internal/lifetimes.py: complete small existing owner/lease/iterable module |
| [web-sample-save.txt](web-sample-save.txt) | openscrub_web.py: indexed/tolerant readers, box geometry, latest save/manual replay and tracking admission/publication |
| [engine-seeds.txt](engine-seeds.txt) | openscrub.py: tolerant timestamp rounding, person/Vit nearby initialization, NCC template read, propagation anchors and repeated forward prime |
| [web-editor.txt](web-editor.txt) | openscrub_web.py: BE/value ACK ownership, independent image/boxes, pointer mutation and Track payload |
| [engine-report-render.txt](engine-report-render.txt) | openscrub.py: Detection fields, canonical renderer coordinates, input provenance/hash, raw-report preservation/reopen |
| [manual-replay-tests.txt](manual-replay-tests.txt) | tests/test_manual_addition_replay.py: existing replay/atomic rejection/normalization contracts, source only |
| [prepared-source-race-test.txt](prepared-source-race-test.txt) | tests/test_report_transactions.py: existing source-preparation vs normalization race contract, source only |
| [package.txt](package.txt) | pyproject.toml: Python>=3.9, unpinned OpenCV and existing whole internal-package inclusion |
| [normalization-relation.txt](normalization-relation.txt) | openscrub.py: existing CFR encoding flags/actual scan source/provenance, rate-only probe and count/cache limitations; added for the source-only supervisor amendment |
| [scan-adoption.txt](scan-adoption.txt) | openscrub_web.py: existing post-report normalized adoption and phase/error/finally boundaries; added for the source-only supervisor amendment |

`SHA256SUMS` records the exact retained evidence files, and `report.sha256` records the handoff report. Their integrity is a document/source check only. The report's acceptance schedules are proposed and unrun; previous actual measurements retain their original report/pin/environment. No new accuracy, latency, source-byte immutability, cross-platform decoder or integrated route/UI guarantee follows from these excerpts.

The supervisor appended an adoption clarification after the source handoff. `supervisor-document-amendment.json` retains the prior/current report hashes and verifies the original report is an unchanged prefix. `report.sha256` now names the current document; no source or runtime evidence changed.
