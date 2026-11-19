# First upstream contribution: HDR decoder cleanup

**Status: [Austin upstream PR #23 merged](https://github.com/austinmabry/OpenScrub/pull/23) on 2026-11-19 at 18:22:38 UTC.** Merge commit: 7d83af32de0f0fbfcb3b5349e3bb0050b9b2500d. The submitted topic was tahv0/OpenScrub:pr/hdr-decoder-cleanup at ded411cbec308333d1416ae3d58b4f6e918d7849, against Austin main5d3a15a. The user's submitted title and description remain authoritative.

The user submitted it manually after the initial connected-app creation returned403. GitHub CLI access now works, and subsequent connected-app reads independently confirmed the merge. This historical creation failure is not evidence of a current CLI access problem.

[Austin's feedback](https://github.com/austinmabry/OpenScrub/pull/23#issuecomment-7018069624) supports the small, focused PR approach. He reports checking the 137-test suite, package build, failing cancellation/write-error tests when the two-line fix is removed, and preserved geometry protection in the revised tracking test. His only future note is the success test's dependence on finding a line in render_hdr source. He plans release-note credit.

The final local audit checked all 114 source files, the two-commit chain, five changed paths and two production lines. Local Python3.12/3.9 and historical full/package results retain their attribution in [readiness](../evidence/delivery/hdr-decoder-pr-readiness.md). The [prepared description](../pr-drafts/hdr-decoder-cleanup.md) remains preparation evidence rather than the exact submitted body. The separate test-only prerequisite is now merged through this PR; it needs no duplicate submission.

The latest read-only main check identifies 50c5a9e03564983ea0bc2a7841824b1fffaf35e0, v1.0.97, following the merge. Save As is next for private refresh against that actual baseline. Austin's feedback has arrived; another push or PR remains a separate publication action. C01 and application adoption remain separate.
