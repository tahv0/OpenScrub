# Source-only readiness evidence

`source-manifest.json` identifies exact standalone and combined commit/tree/blob/SHA-256 values, selected AST definition spans, planned web-identifier occurrence checks and hashes of the original SDD inputs. `source-excerpts.txt` contains compact numbered original-source ranges; line numbers always belong to their stated immutable commit.

Collection used read-only `git show <full-ref>:<path>`, `git rev-parse <full-ref>^{tree}` / `<full-ref>:<path>`, `git ls-tree`, `git diff` and `git grep` with explicit refs, plus Python3 stdlib `ast`, `hashlib`, `json`, `pathlib` and subprocess capture of those Git reads. Original SDD documents were read from their requested paths. A first `python` metadata invocation returned command-not-found; it executed no script and was replaced by `python3`. No product module was imported or evaluated.

These are source provenance/excerpts, not tests, runtime probes, race results or package acceptance. Product/native worktree, index, HEAD and refs were not changed. No source export, full media read/hash, dependency install/download, browser/server/build/benchmark, environment hook, native checkout access or subagent was used. Only the assigned report and this evidence directory were written. The source study's previous 28 captures were not replayed.
