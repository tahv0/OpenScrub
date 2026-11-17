# Keep job polling single-flight, bounded and recoverable

Base: `92124753736e287ac800af91f0ac96f3e96c01be`  
Head: `6ae212a35b094fc9466f1616afb2c5bb5c0497f8`  
Branch: `pr/resilient-progress-polling`

Repeated same-view polls could duplicate log lines, roll progress backward, or remain stuck consuming an unfinished JSON body. Polling now owns one metadata→log cycle per existing job/view, checks HTTP status, races the complete request/body against15000 ms plus cancellation, and recovers with visible polling-specific feedback and capped retry delays. Old callbacks cannot control a newer view/cycle/timer.

The healthy timer now runs900 ms after cycle completion, so request duration adds to the start-to-start interval. Failure delays are900/1800/3600/7200/10000 ms, capped at10000 ms and reset after success/new view. Switch/reopen/delete and lifecycle stop cancel obsolete polling; visible/focus/pageshow/online bursts coalesce into an immediate refresh. Recovery sends no scan/retry/render mutations.

Empty/shrunk server log lengths reset the authoritative cursor and recover through the existing route, preserving initial last400 lines and scroll behavior. A separate phase/initiation eligibility token fences only automatic review publication after a newer phase or review initiation; slow same-phase loads and intentional done-phase Re-open review remain supported. Automatic initialization failures are caught and retryable without occupying metadata/log polling.

P07a view/draft/save/audio/editor ownership and value-equality ACK reconciliation are preserved. No new log API, view identity, dependencies, save deadline or global-list scheduling rewrite. Contributor test commands now include the full discovered suite.

Validation:

- Focused emitted-JS/full-PAGE/P07a set:84 passed.
- Full discovered pytest:218 passed.
- Prepared Python3.9 active-source applicable checks:86 passed,131 deselected.
-18 Chromium schedules, including actual HTTP headers plus held metadata/log JSON bodies, view switches, error recovery, review phase changes, lifecycle wakes, Austin help/enlarged preview/editor interaction. No unhandled page errors; recorded ERR_FAILED/503 console diagnostics, with a nonblocking scenario-specific filter precision follow-up documented.
- Evaluated PAGE joined-script parse; full sdist→wheel using existing3.9 Hatchling; exact source and test inclusion; local-wheel install and3.12 installed CLI/web/Cheroot HTTP smoke passed.
- Baseline RED proofs recorded; self-review complete. Detailed commands/evidence: `task-3-report.md`; artifacts: `/tmp/openscrub-task3/`.

Limits: JavaScript deadlines pause during suspension and cannot force uncooperative transport termination. Controlled visibility/wake tests do not prove native OS timing. Automatic detections and independent global-list requests retain their separate network behavior. Browser plugin absent; existing authorized Playwright/Chromium fallback used. No publication; independent task review approved; combined integration pending.
