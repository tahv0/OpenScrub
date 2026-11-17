# P12C source evidence manifest

Product source is pinned to `6ae212a35b094fc9466f1616afb2c5bb5c0497f8` (P03/P07a). No P12B implementation is included. Current planning documents supply requirements only.

- `source-identity.json`: full commit, Git blob IDs, whole-file SHA-256, named `/tmp` exports and captured source ranges.
- `source-spans.txt`: compact line-numbered excerpts, never a whole-repository copy.
- `collect_source_evidence.py`: source-only reproducible collector; checks the three named exports against Git objects without product imports/execution.
- `verify_artifacts.py`: checks excerpt/identity/report artifacts and generates their SHA-256 manifest; no product tests.
- `commands.txt`: bounded source collection and artifact-verification commands, including the unavailable `python` command and successful `python3` fallback.
- `claims.tsv`: source facts versus proposals and unrun runtime gates.
- `SHA256SUMS`: hashes of this evidence directory's other files and the report; generated after final edits.

Named full-source exports remain only at `/tmp/openscrub-browser-logs-contract/source/`. Artifacts contain source/synthetic contract text, not runtime job contents or copied environment state. There was no GitHits/web research because local pinned source answered the task. No branch/worktree changes, product execution, browser/server/tests/benchmarks, installations, models or user-data changes occurred.

Source work paused on supervisor request during Task113's exclusive comparison, then resumed on explicit release. Future measured acceptance requires its own exclusive slot; this manifest does not assert any memory, latency, browser or implementation result.
