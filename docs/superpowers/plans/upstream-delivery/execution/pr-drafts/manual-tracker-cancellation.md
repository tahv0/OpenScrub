# Stop repeated manual tracking work after cancellation

Ordinary template tracking could keep reading frames and matching after cancellation, and the person-helper fallback could swallow `PipelineCancelled`. Add checks before capture acquisition, after helper/model resolution, at NCC sampling-loop boundaries, before held-coverage appends and before successful return. Propagate cancellation through the existing helper fallback.

The change adds 15 lines inside `track_manual_region`. Uncancelled matching, thresholds, sampling, output order and the existing capture cleanup remain unchanged. In the recorded forward-match fixture, work after cancellation drops from 13 grabs, 19 reads and 41 matches to zero grabs/reads and the two remaining matches in the current scale sweep. This is cooperative cancellation; a running native call can still finish before Python checks again.

Validation:

- Full stored outputs for steady and naturally lost targets remain equal, including all 15 samples.
- Actual Flask cancellation preserves report bytes and returns deletion409 while work or cleanup owns the source; capture closure precedes lease release, then deletion returns200.
- Full Python 3.12 suite: 419 passes at unchanged product bytes. After test-only Python 3.9 tracing and reader-retry corrections, final focused25 and actual Python 3.9 owning168 pass. The evidence distinguishes those test identities.
- Rebuilt source distribution/wheel, packaged source/tests/defaults and installed CLI/web startup pass.

Independent task review approved. Local branch `pr/manual-tracker-cancellation`, head `2004b22002b8317c26ea508ff8187acbcd0cfab2`, base `12919c96c6f7558136b50d7b4d85e5e6b62f1971`. [Detailed evidence](../evidence/delivery/task-110-report.md) and [review](../evidence/delivery/task-110-review.md) retain commands, controlled helper/Vit boundaries and limits. Attach the relevant recipe/results when preparing an upstream PR; nothing has been published.
