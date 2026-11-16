# PR evidence and description template

Use this during each task's E–L cycle. Keep detailed engineering evidence in the fork/planning record; write the final PR for a reviewer who has not read this conversation. Small fixes usually need a short explanation and validation. Performance, persistence and packaging changes need the extra details that substantiate their claims.

## Task record: fill while doing the work

| Field | What to record | When / why |
| --- | --- | --- |
| Task / PR family | P ID, or downstream O ID; final narrow title | E, update at D if scope changes; ties work to the preservation ledger. |
| Status | Investigating / reproduced / implementing / validated / draft / submitted / merged / downstream / closed | Every stage; prevents research from being mistaken for a finished fix. |
| Upstream base | Repository and full SHA | E and after rebase; results apply to this code, not an unspecified main. |
| Donor evidence | Commit IDs, exact useful behavior and excluded parts | E/S; mixed commits are evidence, not blanket cherry-picks. |
| User-visible trigger | Input/settings/action sequence and expected versus actual result | E; makes the problem assessable without knowing the fork. |
| Evidence level | Source inspection, isolated probe, historical fork result or actual integration reproduction | E/V; avoids claiming more verification than occurred. |
| What changes | Affected function/route/UI behavior and report/API fields | S/I/D; reviewers need the final implementation boundary. |
| Why this design | Alternatives considered and one concrete reason for the selected approach | S/D; explain real tradeoffs, not generic architecture preferences. |
| Structure change | Helper responsibility, consumers, import direction and why extraction is justified | S; avoid root clutter and unrelated reorganizations. |
| Dependencies | Exact prerequisite PR/commit, or independent | S/R; the base must not secretly be the full integration branch. |
| Defaults / compatibility | Existing defaults, legacy reports, CLI/browser/platform behavior | S/V; optional work must not change upstream's normal path. |
| Reproducer | Synthetic generator/test command, fixture parameters and seed | E; another contributor should be able to reproduce it. |
| Validation | Commands, actual results, tested SHA, browser/hardware and omitted checks | V; do not substitute historical test totals. |
| Performance | Raw samples, aggregate, report/media sizes, memory/I/O and environment | E/V; before and after must use equivalent workloads. |
| Packaging | Source, sdist, wheel, Docker, updater and applicable Windows import checks | V; moving a module is not complete when it works only in the checkout. |
| Maintainer feedback | Requested scope changes and final resolution | R; rewrite the body around the accepted final change. |
| Integration result | Merged commit or downstream/exclusion reason; dependent branches updated | L; prevents reintroducing duplicate/superseded fixes. |

For each validation row record **not run** when appropriate. A missing GPU/browser does not become a passing mocked test. Do not commit personal media, real reports, large generated files, credentials, raw OCR numbers or huge logs.

## Concise PR body skeleton

Replace the bracketed fields with actual facts after implementation. Delete sections that do not help assess that PR.

```markdown
[Concrete trigger] currently causes [observable behavior] in upstream
[base version/SHA]. This change [specific resulting behavior].

[One short paragraph explaining the implementation choice and any important
compatibility/fallback detail. Mention a helper extraction only if it helps
review the change.]

Reproduction:

- [Synthetic fixture or generator and exact command/action sequence.]
- [Expected versus observed result before the patch.]

Validation:

- [Exact targeted test command and actual result.]
- [Upstream suite and full sdist-to-wheel build result.]
- [Relevant real browser/HTTP/render/hardware exercise and result.]

[For performance: small before/after table with units, workload and hardware.]
[For compatibility: legacy report/default behavior and packaging evidence.]
[For material limitations: what remains untested or outside this change.]

Related: [link to the specific issue/discussion].
Based on [donor attribution where applicable].
Depends on [only if there is an actual dependency].
```

Keep the actual newlines when submitting. Prefer a structured tool field or a prepared `--body-file`; do not send an escaped single-line body. Preparing the draft does not authorize publishing it.

## Performance evidence table

| Scenario | Before SHA | After SHA | Input size/config | Before | After | Samples / caveats |
| --- | --- | --- | --- | --- | --- | --- |
| Sparse save | Fill | Fill | Rows, JSON bytes, motion-history length, changed rows | Measured | Measured | Include request/serializer/IO scope. |
| Cold thumbnails | Fill | Fill | Resolution, duration, codec/GOP, requests | Measured | Measured | State application-cache state and exact-frame check. |
| Warm thumbnails | Fill | Fill | Same fixture | Measured | Measured | Upstream already has a disk-cache fast path. |
| Source-only image rebuild | Fill | Fill | Image variant, builder, same refresh arg | Measured | Measured | Distinguish local mount cache from CI layer cache. |

Do not report only a speedup ratio. Include bytes/rows/time units, relevant memory and correctness results. If a fix is primarily correctness rather than speed, say so. A microbenchmark improvement is not automatically a whole-video improvement.

## Current research that can inform descriptions

- **P01:** Upstream already computes real output suffixes. Lead with destination selection, streaming and visible bytes-written/total progress. The donor worked for the user but only showed “Saving…”. Include throttled-transfer progress, approximate ETA, delayed finalization, failure and unknown-total/native-download fallback evidence; claim no download speedup without measurements. Progress ships with this PR, not as a later scan-ETA task.
- **P03/P07:** Upstream uses mutable browser job state across awaits. Capture a concrete delayed-response example; do not claim the fork's 15-second save timeout exists upstream.
- **P06A:** The isolated write-failure probe leaves invalid JSON, but the submission needs the real route regression and a tested fix. Atomic replacement and overlapping-edit preservation are different claims.
- **P06B:** The controlled overlapping-save probe loses one sparse edit. Document the writers covered by the transaction lock and whether concurrency is only in-process.
- **P06C:** The local minimal 100k-row probe took about 1.074 seconds. It is neither a realistic long-video HTTP benchmark nor a post-fix result. Do not reuse the fork's 20.5s/8.8s values as upstream before/after numbers.
- **P07:** Identical manual saves append twice in the probe. Describe new-client stable-ID replay behavior and legacy compatibility only after real HTTP/restart checks.
- **P08:** Warm disk thumbnails already skip parsing; report cold-miss gains and invalidation separately.
- **P13:** Upstream already has heavy-layer caching and security refresh. Describe only the measured additional cache/ordering improvements and the cache persistence actually tested.
- **P17/P18:** Describe manual exact-frame geometry or checkpoint/resume behavior clearly. Neither implies new model training or support for precise arbitrary-shape tracking.
- **O01–O05:** These are downstream proposals with acceptance questions. Do not describe them as features Austin already requested or approved.

## Before asking Austin to review

- [ ] The title/body describe the final diff, not the original conversation or abandoned approaches.
- [ ] The branch is based on Austin's current main or an explicitly named small prerequisite.
- [ ] One coherent problem/feature is addressed; generic fixes do not depend on optional downstream modes.
- [ ] The body identifies what, why and the actual validation, with synthetic reproduction and measured claims where needed.
- [ ] Any module move is justified, import/package paths are checked, and new tests are collected by the supplied command/CI.
- [ ] Defaults, legacy reports and existing privacy fixes remain intact for upstream contributions.
- [ ] Limitations and unrun checks are accurate; all completed-work statements have evidence.
- [ ] Donor credit and the relevant [issue #22](https://github.com/austinmabry/OpenScrub/issues/22) discussion are linked without dumping the entire experimental history into the PR.

## After review and merge

Record the merged upstream SHA, reconcile any amended implementation with the donor ledger, rebase dependent branches, and remove duplicate patches from the assembled branch. Keep a deferred/rejected proposal documented with its reason; do not quietly reintroduce it through another PR. Run affected integration checks after the actual merge result, especially when Austin rewrites part of the implementation.
