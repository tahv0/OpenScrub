# Local Task651 second-batch integration draft

Explicit Blur/Keep choices, resilient polling, no-op report saves and corrected core compatibility diagnosis are assembled on the reviewed first batch. Review drafts survive polling failures and newer edits; unchanged saves skip publication while preserving actual render/lifecycle admission. P02 choices now survive post-render P06D reopen with every raw row/index and audio/additive fields intact.

Five exact reviewed commits retain `-x`, including both B02b commits. Only overlap resolution plus separately described fixture/tooling corrections follow. Validation and exact base/head/provenance, real browser/media/package/floor evidence and one 100k interaction measurement are in task-651-report.md.

Local intermediate C01 draft only. No remote PR/publication, umbrella upstream PR, final C01 approval or C02 adoption. Supervisor independent base→head review required.

Base `aa07a0664ec0b9d3d592adba19e5e1e473e906ac`; final head `ac6496810b03d8b062ab9da150aeea1e62285fed`. Full tested head `4b4e24fc7f1f2866d3fa8852f36c4e31032c6ff9`: 697 passed/1 optional browser skip, affected browser separately passed; 376 focused; active 3.9 and installed/package checks passed. Final benchmark-only amendment preserves every runtime/test byte, refreshes counted-helper/package checks, and retains original 100k timings at their actual SHAs. Counts confirm both versions no-op 0 publications and changed saves 1. Original failed historical count expectation and recovery are explicitly retained in report.
