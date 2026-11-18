# Task 6521 independent review

## Spec Compliance

**Verdict: Compliant.** Reviewed base `a3c3193e8dff41ec0588e66443398048a5c15ece` through head `c7f9dcc29affe5da363094b8646b3064966e52ed` against `task-6521-brief.md`, the full implementer report, and the complete supplied diff, read once.

The sole diff is in `tests/test_polygon_fallback.py`. The local helper checks both executables, performs one checked encoder query with a 10-second timeout, and compares exact encoder-name tokens. The fixture calls it before `mktemp` or raw writes. Only the query is inside the exception handler; fixture encoding, production render/paint calls, and byte assertions remain outside it. The diff leaves media dimensions/codecs/settings and all existing assertion bodies unchanged. The syntax added is compatible with Python 3.9.

The nine contracts cover missing ffmpeg/ffprobe, each missing required encoder, the libx264rgb near-match, nonzero query/OSError/timeout, and complete support. Missing-prerequisite contracts also invoke the real fixture wrapper with an unusable factory, so accidental fixture-root allocation would fail instead of satisfying the expected skip.

Retained RED logs show the required missing-ffprobe and exact-encoder cases failing with `DID NOT RAISE Skipped`, alongside the expected unavailable-query/control failures: eight failures and one pass. GREEN reports nine passes. Frozen native and floor logs report 557 passes each, without skips, using actual Python 3.12.16 and 3.9.25. Selected-node evidence includes the nine contracts and all 14 existing actual-media nodes, with distinct floor scratch. Config/preflight/runtime records agree on source, interpreter, tool, and helper identities.

All 22 evidence files match manifest byte counts and SHA-256 values. The current candidate source matches `6842b75029bba052ca88caac89f5520156dc09cb97a771a31043757100ffda33`; the current verification helper matches its recorded hash. Replacing only the new helper in memory with the mechanical ffmpeg-only extraction reproduces the retained RED source hash `39f59debeb43e421338108dc80bf6577c89d5917b5124e5a1eafa8733056418d`. This ties RED to the intended intermediate source rather than relying solely on its description. The local PR draft is present and accurately describes scope and validation.

**⚠ Cannot independently verify:** Historical clean-tree/ref preservation, all-other-tracked-byte equality, and recursive sdist inclusion are retained static-manifest assertions; this review did not repeat Git or packaging checks. Historical runtime execution is assessed from integrity-checked logs and identities, not replayed. These limits do not reveal a spec deviation. Results establish the prepared environments, not every possible ffmpeg build.

## Specific strengths

- Catch scope preserves real encoding/render failures as failures after prerequisite success.
- Exact token membership prevents libx264rgb from satisfying libx264, with a direct regression case.
- The complete-support control pins one bounded query; negative contracts pin early exit and named prerequisite reasons.
- The change remains a small local test helper with no production, dependency, cache/framework, or packaging changes.
- Retained raw RED/GREEN and both complete-file runs provide source-identified evidence without requiring another media run.

## Findings

**Critical:** None.

**Important:** None.

**Minor:** None.

## Task quality

**Approved.** The implementation satisfies the bounded prerequisite task, preserves existing real-media behavior/assertions, and has meaningful negative and positive coverage plus retained actual-runtime evidence. No further runtime check is recommended for this review.

## Review boundaries

No Git commands, source/index/HEAD/ref changes, runtime/media/package/browser/build replays, nested agents, controller changes, or publication occurred. The only write was this report. Candidate source bytes were read only for hash integrity and a bounded in-memory helper reconstruction: the concrete risk was whether the retained RED hash represented the requested mechanical extraction. No additional source context beyond the diff was displayed or crawled. The verification helper was read only to hash it. One review metadata command failed because `python` was unavailable; the same bounded hash check then succeeded with `python3`, without running tests or application code.
