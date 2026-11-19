# Optional preview decoder threads: accepted locally

Reviewed branch: pr/optional-preview-decode-threads at 5ef9e644c3a80e72c8116ee2e5c49f8664f7fbcf, directly based on Austin main 5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f. Independent specification and quality review passed after a test-only correction; no findings remain. This candidate is private.

The [qualified decoder comparison](../research/p10b-decoder-thread-comparison.md) found a memory/seek tradeoff. This contribution exposes that choice through --preview-decode-threads 0/1/2/4. Default 0 calls the original VideoCapture(path) without capability probes. Explicit settings request FFmpeg constructor thread parameters and require an opened capture with matching readback. Unsupported constructors, missing capabilities, unopened captures and ignored counts release the rejected capture and fall back once. Unexpected validation errors release the capture and propagate.

One private helper in the existing web module serves frame previews, metadata, compare frames and thumbnail pregeneration. Existing seeking, crop, fallback-frame and release logic remains with each caller. Scan, rendering, tracking, PAGE and global thread settings are unchanged. No new runtime module or dependency is introduced.

| Gate | Source and result |
| --- | --- |
| Meaningful baseline regression | Initial owning tests: 17 failed, one passed on the unmodified base because the helper and option were absent. |
| Final owning checks | 21 passed on Python 3.12.16 and 21 passed on actual Python 3.9.25 at 5ef9e644. |
| Default preservation control | Injected premature capability lookup produced the expected two failures for absent and explicit-zero configuration. Tests also observe each real consumer's factory call and restore CLI configuration. |
| Full discovered suite | Historical 7557d45: 153 passed and one unchanged tracker-log assertion failed. Neither engine nor that assertion changes in this candidate. The separate correction is included in HDR PR #23. |
| Real consumers | Historical 7557d45: synthetic CFR H.264 first/middle/end BGR, odd crop, metadata, JPEGs and end walk-back match default for explicit 1/2/4. Actual OpenCV 4.14 readbacks were 16/1/2/4 on both interpreters. |
| PAGE and installed delivery | Historical 7557d45: evaluated PAGE equals baseline, joined JavaScript passes Node checking; offline sdist-to-wheel and configured installed loopback service with mode 2 pass. A page-only harness mapping correction followed successful consumer checks; no consumer results were relabeled. |
| Final package | Rebuilt sdist contains the corrected test. The complete wheel is byte-identical to the earlier wheel, and all 16 hashed RECORD entries verify. |

The correction from 7557d45f6acfb4a8c0251a04f0c6ee9e3045cf62 changes only tests/test_preview_decode_threads.py; all 113 other tracked files match. This supports the specifically attributed reuse above. It does not turn the historical full-suite result into a fresh passing suite.

Final sdist SHA-256: 07d7f6b1e0a388f392a5c946900228d82adc503971889e79169e7636f6d41d72. Wheel SHA-256: 8228c9c9e00b8271184a3a48f6ee21e50ae672f9ec0f567467b755a42718fd92.

These checks cover Linux CPU, OpenCV 4.14 and small synthetic CFR H.264 media. Windows, GPU, other codecs, VFR/HDR and long production files remain unvalidated. Backend support is detected at runtime. The setting establishes neither a hard RAM bound nor application-wide speedup, exact tolerant-route frame provenance or native-call cancellation. The parent worker/deadline work remains open.

[PR description](../../pr-drafts/preview-decoder-threads.md). C01 composition and working-version adoption remain separate.
