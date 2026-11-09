# Learning collection decoder implementation plan

Goal: eliminate the interactive preview's 10-second deadline from training collection without silently substituting nearby frames or skipping verified samples.

Architecture: production collection uses a single bounded, cancellable FFmpeg stream over sorted unique source frames. Decoded ordinals plus integer PTS verify the report timeline. Existing injected readers remain supported. Training progress describes collection independently of epochs. No model, annotation schema, runtime dependency or original-video changes.

- [x] Reproduce preview-helper coupling, redundant/out-of-order reads, missing progress and cancellation in test_learning_collection.py.
- [x] Add streaming decoder in learning_session.py: one process, bounded pixel queue, independent stall guard, explicit EOF/timeline errors and child cleanup.
- [x] Sort/deduplicate collection reads, expose progress, index constraints by frame, and clean unpublished crops after failure. Keep explicit labels and prior review authoritative.
- [x] Wire perform_learning to production reader rather than the preview helper.
- [x] Test real encoded long-GOP footage, delayed/stalled decoding, cancellation, failed publication and collector integration. All 20 new cases pass locally and in full-source CI run 42714300204.
- [ ] Complete the standard full-suite, Docker and synthetic training PR audit and record exact results before integration. Never alter main.

Review focus: duplicate source frames; contradictory labels in one track; frame zero/nonzero stream origin; cancellation while stdout is blocked; failure after some new crops but before feedback publication. No NVIDIA/Windows/user-footage test is claimed. Dedicated local regression run: 105 passed, one skipped for unavailable ONNX runtime; real HTTP CI does not use the local browser sandbox bridge.
