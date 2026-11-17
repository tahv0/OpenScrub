# Avoid rewriting unchanged review reports

Empty, same-value and repeated manual-addition saves currently re-encode, fsync and replace the complete report. The handler now compares the final values of touched fields after its existing normalization and validation, and skips publication when the data is unchanged. It still reads the current report under the existing transaction and returns the same acknowledgement.

Real edits publish once through the existing atomic writer. Missing fields, numeric types, signed zero, audio replacement and manual-addition conflicts retain their current meaning. No browser, default, dependency or serializer changes are included. No-op saves preserve exact bytes and file metadata; they also stop incidentally refreshing the directory timestamp used for retention.

Validation: 440 tests, 96 focused Python 3.9 tests, actual browser acknowledgement/failure/save-and-render scenarios, fresh-process HTTP reopen, and offline packaging/installed startup checks pass. Independent review found no issues.

Alternating loopback HTTP measurements used three warmups and five recorded samples per version and case:

| Report rows | No-op median before | After |
| ---: | ---: | ---: |
| 1,000 | 46.24 ms | 5.27 ms |
| 10,000 | 481.03 ms | 61.75 ms |
| 100,000 | 5.414 s | 1.189 s |

The 100k report contains 69,956,372 bytes. Separate instrumentation confirms one fresh report parse and no encoding/staging/fsync/replacement for unchanged saves. Changed-save controls retain one publication: their 100k medians were 1.3% slower for sparse edits and 4.4% slower for bulk edits; sampled bulk worker peak RSS increased about 3.7 MiB. These shared-host, warm-cache results support the no-op improvement, with no claim of faster changed saves or general latency guarantees. [Detailed evidence](../evidence/delivery/task-631-report.md) retains all samples and limits.

Depends on the reviewed report transaction and idempotent manual-addition changes. Local branch: `pr/unchanged-report-saves`; base `12919c96c6f7558136b50d7b4d85e5e6b62f1971`, head `3457efac574d74a7d2377cbc0d44bb0b87462c3a`. Not published.
