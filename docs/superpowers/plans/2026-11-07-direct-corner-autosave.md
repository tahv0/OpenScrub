# Direct corner autosave implementation plan

Goal/spec: the user's tested workflow should be drag a corner on the existing
finding card and continue reviewing. Remove rotation, expansion, edit/save/done
controls and the track checkbox. Always apply this UI's edits to the same track.

Architecture: keep cached source pixels and normalized track geometry. Bind four
handles when the preview loads; validate completed gestures; debounce changes
and serialize autosaves. Show only saving/saved/error feedback (Retry on failure).
Pending writes must finish before review navigation or rendering. Protect tab
closure while unsaved. Do not render or restart video decoding on each move.

Tech: existing Flask/Python, embedded JavaScript/canvas, pytest, Playwright.
Target: integration/all-prs, not main. No framework/dependency/scan changes.

Review focus: delayed responses during another drag; multiple cards writing one
report; lost response/retry; pointer cancellation/invalid convex geometry; rapid
edits must not accumulate contradictory training labels for the same source frame.
Track propagation remains approximate across changing perspective; only the
manually edited frame is a verified sample, not all propagated frames.

- [x] Add failing API tests for track-wide autosave, retry idempotency and latest
      sample replacement; browser test for direct drag/no extra controls.
- [x] Replace expanded editor with direct handles and debounced single-flight
      autosave. Retain failed drafts, expose Retry/Reload only on failure, and
      flush before changing job/panel or saving the review.
- [x] Add opt-in autosave request IDs and replace the same frame's previous
      autosave training sample. Retain explicit single-frame API compatibility.
- [ ] Test production JS races, actual browser mouse/keyboard/touch, cancellation,
      saving, cache behavior, navigation, backend suite and syntax.
- [ ] Review diff, publish verified PR and merge to integration/all-prs.
