### Spec Compliance

- ✅ Spec compliant. The complete `17dfe5d575306dea395b680205038e606ad598a2..bb4e129ae620f72a691971de1010d38d8cf661ad` review diff changes only `tests/test_first_scan_sanity.py:105`, replacing the imprecise ordering claim with the requested fields, report-only values, and Detection list order wording.
- ✅ The surrounding dictionary/list equality at `tests/test_first_scan_sanity.py:106` checks fields and values while preserving list comparison semantics; the separate `list(document)` assertion at `tests/test_first_scan_sanity.py:114` checks top-level key order. The comment no longer implies that dictionary equality checks row key order. No assertion or executable source changes appear in the complete diff.

### Strengths

- `tests/test_first_scan_sanity.py:105`: concise, localized wording matches the assertion's semantics without expanding behavior, dependencies, or test scope.
- `task116-evidence/verify_comment.py:43` and `:66`: the retained proof requires exact base bytes with precisely the single comment replacement and the exact one-line delta. `:47` checks mode preservation, `:76` checks complete AST equality including docstrings, and `:88` checks non-comment token equality.
- `task116-evidence/proof-committed.json:4`, `:9`, `:25`, `:28`, `:29`, `:39`, and `:42`: the retained committed record names the required head, both source hashes, matching interpreter-specific AST digests, complete AST equality, Python 3.9 grammar parsing, equality of 1,786 non-comment tokens, and passing diff whitespace validation. The precommit record agrees on source hashes and static results.

### Issues

- Critical: none.
- Important: none.
- Minor: none.

### Assessment

**Task quality:** Approved.

**Reasoning:** The sole source change accurately narrows a test comment and is proportionate to the task. The complete diff and retained static proof support preservation of executable content and compatibility.

**Checked evidence and limits:** Read the complete review diff once, the task brief, implementer report, proof script, both proof JSON records, source-check notes, and hash manifest. Ran only the static `sha256sum -c SHA256SUMS` integrity check; all six retained evidence files matched. Nearby assertion context was complete in the diff, so no outside-diff product source was read. No Git commands, proof regeneration, product imports, tests, runtime/media/browser/build/model work, environment changes, or publication were performed. Ref preservation and committed/working equality are supported by the recorded proof (`task116-evidence/proof-committed.json:43`), not an independent live ref check. Full source snapshots and AST dumps are not retained in this evidence directory; exact-base comparison is established by the inspected proof script and its recorded results. AST digests are specific to the recorded Python 3.12.16 interpreter and dump options; the Python 3.9 evidence is a grammar check, not a Python 3.9 runtime test.
