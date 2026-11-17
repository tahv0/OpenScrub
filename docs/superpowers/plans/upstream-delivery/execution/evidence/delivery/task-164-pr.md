# Keep editor painting and pointer edits aligned after live resize

Base: `92124753736e287ac800af91f0ac96f3e96c01be`  
Head: `47e9f6d5614365e00d899c87df6c209cd7aaabf6`  
Branch: `pr/editor-resize-alignment` — local draft only; not published.

Shrinking an open editor from640 px to326 px previously left the canvas and inverse pointer scale at640 px: the production outline moved167.8 CSS px away and clicking the visible target missed. A mount-owned ResizeObserver now keeps the active image/video, fractional CSS canvas/backing geometry, painting, and pointer mapping together. Resize ends an active gesture while preserving applied source edits and retained drafts; stale callbacks are invalidated on close/replacement/job switch.

The real playback flow also required an explicit `video.load()` after installing the existing metadata listeners: preload=none otherwise waited for metadata before starting a load. This happens only after the user presses Play. Source/content coordinate conventions, save/audio ownership, engine defaults and routes remain unchanged.

Validation: final regression fails on the exact reviewed base with real painted pixels/hit -1; GREEN covers desktop/mobile, DPR 1/2, fractional geometry, hit/move/corner/add, offsets, gesture transitions, hidden/loading media, real playback and stale callbacks. Actual routes preserve the intended source region on fresh page reopen and an actual decoded SDR render. Full discovered suite 197 passed; Python3.9 focused 74 passed; installed exact packaged focused 74 passed; offline sdist→wheel, emitted-JS parse, installed CLI/web and full packaged browser flow passed. Maximum corrected painted-edge error 1.023 CSS px with 2 px tolerance. Details and honest iteration failures: `task-164-report.md`.

Limits: Chromium headless Linux viewport QA, not native touch or Firefox/Safari; render raster tolerance3 source px. P10 exact-frame and P06D standalone raw-report preservation remain separate.
