## Task 164: keep editor painting and pointer geometry aligned after resize

### Global constraints

Preserve Austin mask/padding defaults, Python>=3.9, P07a view/editor/draft ownership, source-space boxes and existing content-space offsets. No training/workbench, new UI framework/dependency, quad feature, new source/timeline API, broad responsive redesign or competing decision store. Tests under tests/. No original-checkout/user-data changes, publication or subagents.

### What, why and when

The actual full-page comparison in `editor-resize-baseline-research.md` reproduces the same defect on upstream+B02a and reviewed P07a: a 640px image shrinks to326px while the canvas and cached scale stay640/1, causing158CSS-pixel painted-edge displacement and a missed pointer hit. Ordinary redraw fails; scrub/remount recovers. Read that report and reuse its retained real media/server recipe, without rerunning the complete two-version research. This separate correctness prerequisite can later support P17 corners; it does not fix P10 wrong-frame sampling.

Supervisor creates `pr/editor-resize-alignment` from exact reviewed P07a `92124753736e287ac800af91f0ac96f3e96c01be` in the native worktree before dispatch. No P02/P03 or unreviewed downstream feature is implicitly included.

### Implementation contract

1. Keep a small mount-owned transform for the currently visible image/video and existing editor canvas. Synchronize canvas display/backing geometry and source/display mapping on real element-size changes, then redraw immediately without image reload, scrub, server request or editor remount. Use a narrowly owned ResizeObserver or justified equivalent; no global rendering framework or unrelated observer.
2. Drawing and inverse pointer input use the same measured transform, including fractional CSS sizes and backing-store/display ratios. Preserve source-space boxes, manual additions and content-space overrides with the existing ox/oy conversions. Resizing alone must not edit geometry/time, add/delete rows, save, or change actual render masks. Do not silently round stored source coordinates to display pixels.
3. Read only finite positive loaded source and displayed dimensions. Hidden/unloaded/zero-size media must not publish an invalid scale; pointer edits remain unavailable until a valid current transform exists. Switching image↔video and normal playback start/stop/scrub uses the active media, not a hidden element's stale size.
4. Observer callbacks and any coalesced frame work are owned by the mounted editor/job/media. Disconnect/invalidate on panel replacement, job switch and editor teardown; old callbacks cannot repaint or clear a new editor. Keep P07a async image/box ownership and pending drafts intact; no new view generation or save acknowledgement changes.
5. If resize occurs during an active pointer gesture, end that gesture before replacing its transform. Preserve already-applied source-space edits; discard only an unfinished temporary drawing preview, without inventing a new manual row. The next deliberate gesture starts from the current mapping. Do not apply the next pointermove using an old origin/scale and cause a jump.

### Evidence and delivery

Add meaningful emitted-JS ownership/geometry checks where appropriate and actual full-PAGE browser regression in tests/test_editor_resize.py or the existing browser convention, without requiring a new frontend toolchain. RED must observe production painted pixels and missed target hit after live shrink; no replacement drawing implementation. GREEN covers initial/shrink/grow with no scrub/remount, inverse hit/move/resize/add, nonzero offsets, fractional sizes, unchanged stored coordinates on resize, active-gesture transition, image/video switches, hidden/zero size, and stale observer after close/job switch. Exercise desktop/mobile viewport and at least one DPR2 browser context with independent source→CSS expected pixels, stating normal stroke/rounding tolerance and backing-resolution limitations honestly.

Use the existing synthetic real media/report and actual frame/boxes/save routes to show pointer editing after resize persists the intended source coordinates; reopen and one actual SDR render verifies the chosen region remains aligned. This is coordinate acceptance, not a claim that unrelated P10 exact-frame or P06D standalone render roundtrip issues are solved. Preserve help and enlarged preview, P07a save/audio cases; no unrelated UI matrix.

After source stabilizes run focused/relevant regressions, one full discovered suite, emitted-JS parse, sdist→wheel/source/tests inclusion, installed CLI/web smoke and applicable active-source Python3.9 cases. Use the existing browser and prepared isolated environments; no downloads/models. Artifacts `/tmp/openscrub-task164`. Native/Git writes may use already-authorized require_escalated.

Self-review, commit and write task-164-report.md/task-164-pr.md in this SDD workspace: exact base/head, visible trigger, same-source before/after pixel/pointer evidence, source-coordinate roundtrip, scope/limits and commands/results. No publication or nested agents.
