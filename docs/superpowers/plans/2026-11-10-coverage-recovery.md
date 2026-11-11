# Saved-candidate coverage recovery implementation plan

Goal: provide a concrete recovery from a completed-but-rejected learning pass without
retraining, without weakening 99.5% coverage or overwriting saved review on failure.

Design / scope: retain the confidence gate and test five fixed outward margins
(0, 1, 2, 3, 5% of the raw mask bounding box's shorter side; extra radius capped at
32 crop pixels). Use the SAME conservative-quad function and selected margin in
validation and actual refinement. No claims about unseen-video safety. Do not
silently fall back to retraining. Existing candidate reuse requires an identical
freshly validated dataset fingerprint and source hash, plus artifact checksums.
The current source-bound human constraints remain authoritative on publication.

1. [x] Regression tests: small edge shortfall can be padded, gross error still
rejected, no predictions / no gain remain failures, inference once per example,
validation/render policy identical and bounded, cancellation checked.
2. [x] Per-pass structured coverage report with frame IDs, metrics, policy attempts
and a small set of comparison thumbnails; no video decode for diagnostics.
3. [x] Explicit recheck-saved-candidate mode and button. Existing worker ownership,
locks and transactional report publication remain. No CUDA training preflight
needed for reuse; ONNX loading still checked. Missing/mismatched model is an error.
4. [x] In-place coverage-results UI and bounded authenticated artifact endpoints.
No hard-coded job/pass IDs. Late responses cannot overwrite another job's view.
5. [ ] Test existing learning/preview/save flows, browser UI, full pytest audit;
publish only tested changes to integration/all-prs through a focused PR.

Review focus: stale/corrupt candidate, changed annotations or source, unsafe paths,
no hidden training on reuse, fail-closed publication, matching geometry, large
validation sets (stream image/mask calculations; bounded preview count), cancellation,
old candidates without extra recovery metadata, retained prior training exposure.

Execution: fresh local isolated reconstruction verified against current GitHub
blobs for learning_session.py, openscrub_web.py, video_learning.py and trainer.
Baseline: 65 passed, 1 skipped in learning/session/split tests; skip is absent ORT.

Execution update: 22 new checks and 78 focused checks pass locally, including
Chromium 1440x1000 and 390x844. Browser plugin absent; repository in-process
Flask bridge used for sandbox loopback restrictions. No GPU/actual user candidate
available. No independent reviewer agent available: diff/state paths manually
reviewed. Publication blocked: current GitHub connector exposes read actions only
and this container cannot resolve github.com. Delivering a patch, not claiming
a PR/merge. Full local suite audit recorded separately.
