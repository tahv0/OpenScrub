Title: Clarify scan-report assertion coverage comment

The scan-report test comment implied that dictionary equality pins each Detection row's key order. Narrow the wording to Detection fields, report-only values, and Detection list order. Every assertion and all executable code remain unchanged.

Validation: exact-base comparison confirms one comment-line replacement in one file, with unchanged mode. Complete AST equality including docstrings, non-comment token equality, Python 3.9 grammar parsing, and `git diff --check` pass. Runtime suites were not rerun for this non-executable change.

Local source commit: `bb4e129ae620f72a691971de1010d38d8cf661ad`, based on `17dfe5d575306dea395b680205038e606ad598a2`. Independent review is pending. This is a prepared description; no PR or publication was created.
