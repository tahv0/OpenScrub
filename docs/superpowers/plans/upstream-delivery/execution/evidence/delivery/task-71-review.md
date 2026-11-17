### Spec Compliance

- ❌ Issues found: the save snapshot/failure/acknowledgement requirements are substantially implemented, but clean audio can remain stale when another kind of draft survives a job revisit (`openscrub_web.py:2099`, `openscrub_web.py:2147`, `openscrub_web.py:2416`). This misses the explicit fresh-load requirement and can remove current saved audio spans on a later edit.
- ✅ Scope: browser ownership changes, regression tests, discovery configuration and packaging only; no server replay IDs, transaction changes, dependency/version changes or unrelated workbench feature appears in the exact supplied diff.
- ⚠️ Limits: lost-save-ack replay remains P07b work. P06A/P06D server corruption/roundtrip behavior is outside this branch; the finding below concerns a newly cached clean client value, independently of those defects.

### Strengths

- ✅ Both entry points use one guarded operation; job, view generation, owner and cloned payload are captured before awaits (`openscrub_web.py:2726`, `openscrub_web.py:2977`). A→B→A has a distinct generation (`openscrub_web.py:2154`; regression `tests/test_review_save_failures.py:118`).
- ✅ HTTP status, invalid JSON, body errors and missing success acknowledgements are checked centrally (`openscrub_web.py:2958`). Acknowledged maps reconcile by value, manual additions by identity and value; committed additions are cleared before a render failure can prompt retry (`openscrub_web.py:2971`, `openscrub_web.py:2992`; regression `tests/test_review_save_failures.py:131`).
- ✅ Deliberate enabled choices are separated from loaded display state, including explicit same-value choices (`openscrub_web.py:2861`). Newer box/time/manual/audio edits inhibit render and survive acknowledgements (`tests/test_review_save_failures.py:73`).
- ✅ Recorded evidence inspected: `full-suite-final.log` reports 172 passed; final build and parse logs show successful sdist/wheel, Python 3.9 grammar and evaluated-JS checks. The package-check script compares final source bytes. No full suite, build or browser rerun was performed for this review.
- ✅ Browser script/results support 18 scenarios, no page exceptions, and only deliberately injected HTTP/network console failures. Saved-report JSON contains the submitted enabled, manual, box, time and audio fields; actual-job JSON reports done/output; output-check script/results verify black pixels in the submitted manual region and a separate clear region. These checks do not claim metadata survives the known independent server rewrite.

### Issues

#### Critical (Must Fix)

- None found.

#### Important (Should Fix)

- **Clean audio remains stale when an unrelated draft is pending.** `openscrub_web.py:2147` clears fetched display data on departure, but `trimReviewDraft` (`openscrub_web.py:2099`) replaces the editor only when the entire job has no pending edits. Thus a pending enabled choice, manual addition, box or time edit keeps clean `audio`, `audioSaved` and `audioLoaded=true`. On revisit, `tlInit` (`openscrub_web.py:2416`) skips the fresh report's audio. Adding a span then submits the stale full list (`openscrub_web.py:2986`), potentially deleting current server redactions. A focused execution of the recorded actual evaluated APP_JS reproduced: load A audio `[0,1]`, retain only a pending enabled choice, switch B→A, return fresh server audio `[5,6]`, add `[7,8]`; client audio becomes `[0,1],[7,8]`. This is a new clean-state caching regression, not deferred replay or server roundtrip handling. Evict/reset clean audio independently of other pending draft kinds; preserve dirty audio. Add a regression for a pending non-audio draft with changed server audio on revisit. The existing clean-job test (`tests/test_review_save_failures.py:222`) clears every draft, so it misses this case.

#### Minor (Nice to Have)

- **Contributor instructions still skip every new regression.** `CONTRIBUTING.md:25` says the required pre-PR check is `python -m pytest test_openscrub.py -q`. That explicit file selection bypasses `tests/` despite the new default discovery configuration (`pyproject.toml:123`) and updated README. Change the contributor command to `python -m pytest -q` so the two guides agree.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The central save operation is coherent and has strong actual-JavaScript and browser evidence. Independent eviction of clean audio is needed before the revisit behavior can be trusted.

- ✅ Focused review checks outside diff context: contributor guide for the named discovery risk; `beFilter` continuation and `beHook`/time-edit mutations for the concrete addition-identity/replay risk; allowlist/render route success shapes for compatibility with strict `reviewPost` validation (`openscrub_web.py:1683`, `openscrub_web.py:1701`). No Git commands or product mutations were performed.
- ⚠️ Screenshot limits: failed-save controls remain present and actionable; mobile screenshot shows the reported canvas resize mismatch. Its baseline regression status remains unverified and outside this patch. Chromium/Linux only; no fresh browser/platform testing or full package rebuild was performed by this reviewer.
