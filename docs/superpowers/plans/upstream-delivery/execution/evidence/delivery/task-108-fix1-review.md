### Finding Verdicts

- **Oversized integer raises uncaught `ValueError` and returns HTTP 500** — **ADDRESSED**. `openscrub_web.py:906` now catches `ValueError` around the same single decode, covering both the integer conversion error and its `JSONDecodeError` subclass. Job creation, copying and enqueue remain outside the catch. `tests/test_scan_options.py:26` adds the 4,301-digit integer to the existing actual-route matrix, exercising both multipart upload and server-path admission with the existing JSON400/no-durable-side-effects assertions.

### New Breakage in the Fix Diff

- None. The two-line fix changes only the decoding exception class and adds its regression payload; accepted object semantics and the separate object check remain unchanged (`openscrub_web.py:904`, `tests/test_scan_options.py:26`).

### Out-of-Scope Observations

- None.

### Verification

- Reviewed packaged fix diff once for `e34313e1b136254fb2777cabb385f2097a54935a..b26b6685b237ba1c4caffaaefb47b029a3205b51`; did not reread unchanged product source or rerun Git commands.
- Read the appended fix report and retained covering outputs: `fix1-green312.log` shows active-worktree import provenance and **38 passed in 0.14s** on Python 3.12.16; `fix1-green39.log` shows the same provenance and **38 passed in 0.19s** on Python 3.9.25. Neither output contains a warning summary.
- `fix1-build.log` records successful sdist→wheel creation and exact-active-source/tests/config inclusion checks. `fix1-installed-http.log` records installed oversized-integer multipart JSON400, valid `{}` HTTP200, cancel/delete HTTP200, empty store/queue and server exit 0. These are retained implementer outputs, not independently repeated package/HTTP checks.
- No tests were rerun: the reported actual-route RED and both complete focused GREEN matrices answer the original finding. The original 170-pass full-suite result remains attributed to the original head, not this fix head. No product/Git changes or nested agents; only this designated review document was written.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
