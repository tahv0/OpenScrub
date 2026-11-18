# Add isolated literal plate-text matching helper

Add a dormant, stdlib-only helper for already recognized candidate text. Full mode requires entire normalized equality; fragment mode matches only the complete explicitly supplied literal. Bounded ASCII query validation, stable mode-aware deduplication and privacy-safe representations accompany frozen results that retain the complete original observation mapping by identity.

Exactly three files are added. Every existing application/default/schema/dependency/package/version file is unchanged; no OCR, search, UI, selection, tracking or redaction integration is introduced.

Validation on final `3547f82c027323dba8e69e8aef7be62c88438d8b`:

- Actual Python 3.9.25 matcher suite: 13 passed, including fresh stdlib-only import/full/fragment exercise and negative blocker controls.
- Actual Python 3.12.16 full regression with existing prepared fixtures: 573 passed.
- Offline Python 3.12 sdist → wheel from extracted sdist → no-deps install: passed; exact private-package bytes and test inclusion verified.
- Actual Python 3.9.25 exercise of that installed wheel outside checkout, with source paths excluded: passed.
- All 132 existing tracked files match accepted base byte-for-byte.

The full report retains the genuine initial RED and all earlier floor/full/toolchain fixture failures with exact attribution. The prepared build-tool bundle requires Python >=3.10; this build used actual3.12, and installed product compatibility was separately proved on actual3.9. Frozen Windows packaging and consuming OCR/tracking/redaction integration remain later work. Independent spec/quality review is Approved with no blocking findings; the existing archive-warning Minor remains with D01. This is a locally accepted optional prerequisite; no upstream PR was created.
