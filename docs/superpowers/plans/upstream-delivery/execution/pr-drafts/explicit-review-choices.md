# Make review output choices explicit and show mixed group state

Repeated card clicks currently reverse output, and mixed groups display only their representative's value. Add separate **Blur** and **Keep visible** actions that retain the requested output and show exact full-member current state. Mixed groups expose both actions unpressed; uniform groups show the corresponding action pressed. Both stay enabled and preserve focus.

Reuse P07a's setter/draft and value-equality acknowledgement ownership. Clarify category-local appearance scope; refresh a card after any member edit while preserving existing editor row/group semantics. Keep category, marquee and outside-zone bulk scopes unchanged, with explicit wording and a truthful neutral zone summary. Add eight emitted-JS regressions and correct contributor guidance to include standalone web tests.

Base dependency: reviewed P07a `92124753736e287ac800af91f0ac96f3e96c01be`. Candidate: `2ae3257b9752e2d976ff7a0d39955a13c133273a` on `pr/explicit-review-choices`.

Validation: 204 discovered tests passed; 70 focused output/P07a cases passed; prepared Chromium verified pointer, native Tab/Enter/Space, retained focus/pressed state, real editor/marquee/Escape, enlarged previews, 390px layout/help and native touch scrolling with zero app/console errors. Real UI choices→real save→fresh pre-render review preserved all thirteen synthetic report rows and all non-output fields; real CPU render decoded enabled, kept and unrelated regions correctly. Full sdist→wheel build, exact source/test inclusion, packaged Python 3.9 grammar, focused Python 3.9 checks and actual installed CLI/web smoke passed. One Python 3.9 report test initially hit its environment's temp-root audit and passed when retried under the allowed root.

This branch intentionally predates P06D: actual render still drops disabled rows during report rewrite. Full after-render review preservation is the separate P06D/C01 combination gate. No server/engine/lifecycle code is changed here. No new decision store, handling/learning states, dependency, inference or model download.

Detailed evidence: [retained delivery report](../evidence/delivery/task-20-report.md); executable harnesses, logs, screenshots and decoded frames: `/tmp/openscrub-task20`. Draft only; no publication.

Independent task review approved spec and quality with no findings. The declared after-render combination gate remains open for these UI controls.
