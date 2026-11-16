# Retrieve only needed dense-smoothing frames

Late dense tracks currently retrieve every prefix frame even though onset matching uses only a short gray-cache span. Keep sequential decoding and use `grab()` outside needed spans, with capture release on success, EOF, error and cancellation. Frame indices, cache tolerance/eviction, matching, report fields, default masks and periodic cancellation checks remain unchanged.

On generated 610-second, 256×144 H.264 clips with detections at 600 seconds, full-module measurements gave median smoothing times of 5.531 → 1.797 seconds with GOP30 and 5.480 → 1.387 seconds with one keyframe. Each used three warm-ups and five alternating samples. 18,001 reads become 17,872 grabs plus 129 reads; all 129 source markers and all 38 Detection records match. Codec prefix decoding still occurs. These shared-machine measurements do not establish a general 4K or cancellation-latency guarantee.

Validation: 154 tests pass, including 20 focused frame/output, cache, EOF/fault and cleanup regressions; the full sdist-to-wheel build passes. Marked-video default renders match all 130 decoded frames, and a synthetic Tesseract scan/report/render succeeds. README and CONTRIBUTING collect both test locations; the sdist includes the new tests. `benchmark/dense_smoothing.py` supplies the repeatable full-module comparison.

Local comparison: `e21ebdf6e3ee46e6c65050dc956a9a3459152269` → `f19be5fe3b9176e568ea7bf761493bd267fee95e`. The base contains only Austin's pinned runtime and the separate tracker-test assertion correction. Refresh the upstream base before submission; no other feature branch is required.
