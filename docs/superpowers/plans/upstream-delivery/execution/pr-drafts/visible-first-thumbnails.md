# Prioritize visible review cards with bounded thumbnail work

Local candidate: `pr/visible-first-thumbnails` at `fe20dff7b73efb5afdbf3130e75a19c8b35ecba3`, based on reviewed P02/P07a `2ae3257b9752e2d976ff7a0d39955a13c133273a`. Independently reviewed; not published or merged.

Opening a large review currently creates a card and starts a thumbnail request for every group. This change keeps complete group metadata and choices while mounting at most 64 normal cards plus one focused exception. Four slots cover thumbnail fetches through full body consumption, prioritize the current viewport, and wait for obsolete operations to settle before admitting more work.

Whole-category, outside-zone and selected actions preserve complete hidden-member scope. Measured row spacers keep distant cards reachable; native range controls and ordered DOM preserve keyboard traversal. Local scrolling and resizing preserve editor/drafts without metadata reloads or saves. Retry budgets survive ordinary remounts and suspension of the same view. Disposal releases owned rows, spacers, bindings, timers and image URLs; restoration transfers only numeric retry history. The complete-ID refresh hook is ready for a separate filter feature.

Validation:

- Final source: 82 scoped scheduling/choice/save checks on each of Python 3.12 and 3.9, evaluated JS parsing, rebuilt extracted-sdist→wheel bindings, and installed actual HTTP with exact final script bytes.
- Focused Chromium: overlapping upward scroll with native Tab order, width repartition retaining the focused control, three controlled page-transition cycles with stable structure/exhausted retries, fresh-metadata reset and cleanup. One mid-window replay retained its exact group/pixel position. Actual BFCache navigation remains unobserved.
- The initial candidate at `0c2b98e` passed the full 212-test suite and the larger desktop/narrow/CSS-zoom matrix. Its 1,200-group/1,802-row fixture observed 56 normal cards plus one pin and four unsettled operations. Six small real responses separately covered three warm hits and three cold decoder opens. These counts do not establish latency or total-memory improvement.
- Initial real UI save/fresh reopen retained all 21 test rows and their choices/geometry/manual/audio fields; actual CPU-render pixels matched selected, kept and unrelated regions. Those complete flows remain bound to the initial head, with the final local fixes covered by the scoped checks above.

The standalone base still loses disabled rows after render (21→18) and needs the separate editor Play-start fix. P06D/P16D and the other combined ownership gates remain C01 checks. Browser abort does not prove native decoder cancellation; full metadata and numeric indexes remain proportional to the report.

[Implementation record](../evidence/delivery/task-9-report.md), [fix verification](../evidence/delivery/task-9-fix1-report.md), [initial review](../evidence/delivery/task-9-review.md), and [final scoped review](../evidence/delivery/task-9-fix1-review.md) retain exact source identities, failed probes, commands and limitations.
