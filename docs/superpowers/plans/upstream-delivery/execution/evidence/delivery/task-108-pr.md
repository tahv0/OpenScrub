Title: Reject invalid scan options before creating or queueing jobs

Invalid scan options now receive a clear JSON400 before a scan job is created or queued. Previously malformed JSON returned an HTML500, while JSON arrays, null, strings, numbers and booleans could be persisted and queued despite being unusable by argument preparation. The shared upload/server-path boundary now catches decoding `ValueError`, including malformed JSON and supported-runtime integer conversion limits, and requires an object, returning `{"error":"Scan options must be a JSON object."}`.

Omitted options still mean `{}`. Explicit objects, supported settings, nested unknown keys and existing defaults remain unchanged. The catch covers only JSON decoding; unrelated file/job errors retain their behavior. Framework multipart parsing/spooling remains outside the durable-job guarantee.

Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
Head: `b26b6685b237ba1c4caffaaefb47b029a3205b51`.
Branch: `pr/scan-options-validation`.

The product change is confined to `openscrub_web.py`. `tests/test_scan_options.py` adds 38 actual-route cases across both intake forms, including 4,301-digit integers, checking rejection without durable side effects and preservation of exact accepted options/input, selected argument defaults/settings and cancel/delete cleanup. `pyproject.toml`, `CONTRIBUTING.md` and `README.md` include the first branch-local tests directory in discovery, contributor commands and the sdist.

Validation:

- Initial owning RED: 28 expected invalid-input failures and 8 valid controls passing; initial focused GREEN: 36/36. Review-fix RED reproduced oversized-integer HTML500 on both routes (2 failed); current focused Python3.12.16 run: 38 passed.
- Full discovered suite at original implementation head `e34313e1b136254fb2777cabb385f2097a54935a`: 170 passed in 58.09s. The unchanged suite was not rerun for the scoped review fix.
- Current active-source Python3.9.25 check with explicit import provenance: 38 passed.
- Rebuilt current-head sdist→wheel using already installed tooling; archived source/tests/config and wheel source/floor metadata verified.
- Offline `--no-deps` installation into a fresh temporary target; installed CLI/web help passed and imports resolved to that target.
- Initial real source and installed cheroot HTTP pairs passed. Current rebuilt installed console HTTP path: 4,301-digit integer → JSON400, `{}` → 200, cancel/delete → 200. Job stores and registration were empty afterward; the harness drained stale queued work and the server exited0.
- Diff whitespace checks and self-review passed. No dependency/version changes, model downloads, browser work, report-transaction implementation, user data or external publication.

The change intentionally adds no per-key semantic validation. Admission/HTTP probes prevent worker execution and do not establish a worker failure or permanent leak. Detailed commands, initial environment/harness failures and their resolution, review-fix RED/GREEN, artifact hashes, exact requests and cleanup evidence are in [task-108-report.md](task-108-report.md) and `/tmp/openscrub-task108`. The reported review finding is fixed; scoped independent controller re-review is pending.
