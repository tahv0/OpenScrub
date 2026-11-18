Title: Clarify recovery-stage cleanup ownership comment

The recovery-required exit branch closes its ExitStack, but its comment said the report context was deliberately left open. Update the two comment lines to explain that closing the stack discards expendable report staging while required recovery backups, final paths, and the recovery descriptor remain discoverable.

Validation: exact-base comparison confirms a one-file, two-comment-line change. The complete AST including docstrings and non-comment tokens is unchanged; Python 3.9 grammar parsing and `git diff --check` pass. Functional suites were not rerun for this non-executable change.

Local source commit: `af862c8c9700b7b2b06426e4c4287e469fe28038`, based on `a132081f1e609ed19deb4477044ee1c9b77871cc`. Independent review is pending; this is a prepared description, with no PR or publication created.
