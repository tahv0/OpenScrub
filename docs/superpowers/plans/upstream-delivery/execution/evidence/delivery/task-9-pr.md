# Prioritize visible review cards with bounded thumbnail work

Local PR draft only. Base `2ae3257b9752e2d976ff7a0d39955a13c133273a`; current head `fe20dff7b73efb5afdbf3130e75a19c8b35ecba3` on `pr/visible-first-thumbnails`. Fix1 range: `0c2b98e9e136abcd472bdda59cecaf546775ea4e..fe20dff7b73efb5afdbf3130e75a19c8b35ecba3`.

Large reviews currently mount and request every group. This candidate keeps complete grouping/choices authoritative while mounting at most 64 normal cards plus one focused exception. Measured grid rows/spacers make distant groups reachable, native range controls provide explicit keyboard traversal, and four unsettled browser thumbnail fetch/body slots prioritize the current view while old operations drain.

Category/zone bulk and selected actions retain complete hidden-member scope. Retry budgets, target/root/view fences and URL/listener cleanup belong to the scheduler; local movement preserves editor/drafts and performs no metadata/save/editor reload. The documented `refreshReviewVisibleSet({jobId,viewGen,matchingCardIds})` seam accepts complete matching IDs for future P15; no filters or new decision store are added.

Fix1 reconciles actual row/card DOM order around the focused subtree, removes every owned row/spacer during disposal, and preserves only numeric retry counts/deadlines across suspension of the same view. Native Tab/width focus and three controlled page-transition replays now pass without structure growth or renewed exhausted attempts. A measured mid-window controlled replay preserved group77/pixel−199 and scroll/document extent. Actual BFCache navigation was not observed.

Final-head validation: **82 scoped native and 82 actual Python 3.9 checks passed**, emitted JS parsed, offline extracted-sdist→wheel exact runtime/test bindings passed, and installed actual HTTP contains exact final APP_JS. The retained original **212-test full/required runs and real UI save/fresh reopen/render pixels belong to 0c2b98e**; those unrelated gates were not rerun for this local fix. Fix1 evidence retains the meaningful four-case RED, one corrected browser cleanup-counter harness failure, and final passing focused browser results.

The original 1,200-group/1,802-row matrix observed at most 56 normal cards plus one pin and four browser operations; tiny real routes separately recorded six body completions, three cache hits, three cold misses and three decoder opens. These are original-head observations, with no latency improvement claim. Standalone P06D row loss (21→18 after render) and P16D Play startup remain C01 prerequisites; the original playback ownership probe explicitly loaded native media.

See [task-9-report.md](task-9-report.md), [fix1 handoff](task-9-fix1-report.md), [original evidence](task9-evidence/README.md) and [fix1 evidence](task9-fix1-evidence/README.md). Ready for scoped re-review; no publication/adoption.
