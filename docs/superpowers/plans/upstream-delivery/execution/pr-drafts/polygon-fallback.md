# Use the known box when a silhouette polygon is unusable

Malformed or nonfinite polygon coordinates could stop rendering even when a valid detection box existed. Collinear or repeated points could instead produce a thin mask and bypass the existing fallback. SDR and HDR now share a small local validation helper and use their existing full-box redaction for unusable polygon data.

The helper checks point/box shape, finite mapping, int32 representability and integer noncollinearity. Valid concave, clipped and self-intersecting contours retain their pixels, including a usable bowtie with zero signed area. Requested fill modes, padding, report shape and encoder defaults stay unchanged. Resource failures still propagate.

Validation:

- Owning failures were reproduced before each fix; the evidence distinguishes fixture corrections and later container regressions.
- Full suite: 682 passes. Focused Python 3.12 and actual Python 3.9: 556 passes each. Inherited optional-model/fallback diagnostics remain documented.
- All 96 direct and eight actual SDR/HDR media controls match the baseline. Exact encoder-input checks are separate from decoded output comparisons.
- Offline source distribution/wheel, packaged source/tests and installed CLI/web startup pass.

Independent task review approved. Local branch `pr/invalid-polygon-fallback`, head `a3c3193e8dff41ec0588e66443398048a5c15ece`, base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. [Detailed evidence](../evidence/delivery/task-162-report.md) and [review](../evidence/delivery/task-162-review.md) retain exact commands and limits. The real-media checks load reports and call the actual renderers; complete pipeline integration remains C01. Invalid primary boxes, malformed outer report containers and output/resource lifecycle are separate scopes. Attach relevant evidence when preparing an upstream PR; nothing has been published.
