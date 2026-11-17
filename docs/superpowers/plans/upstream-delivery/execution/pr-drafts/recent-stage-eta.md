# Estimate stage ETA from bounded recent progress

Long scans retain an optimistic ETA when a fast early prefix dominates the whole-stage average after a sustained slowdown. Estimate remaining stage time from monotonic progress samples over the latest 120 seconds, retaining one crossing-interval predecessor. Use the whole-stage rate during startup, prefer recent history after 20 seconds, and smooth with 0.35 previous / 0.65 new estimate weights.

A mature stalled window returns null instead of reviving the historical rate. Stage changes, completion and counter regressions reset estimator state. Public nullable ETA seconds, progress mapping/precision, defaults, callback API and existing browser fallback remain intact. Add controlled-clock/worker regression tests and minimal shipped-test discovery guidance.

A controlled 600-second 10-unit/s prefix followed by 180 seconds at 1 unit/s leaves 3,820 units: upstream estimates 476 seconds; this change estimates 3,823 seconds. This demonstrates estimator response, not inference acceleration or promised prediction accuracy.

Validation:

- Full discovered Python 3.12 suite: 159 passed; focused active-source Python 3.9: 25 passed.
- Controlling slow-tail RED reproduced upstream's 476-second estimate; focused GREEN: 25 passed.
- Offline isolated sdist→wheel build; exact source/test inclusion; extracted-source focused suite: 25 passed.
- Wheel-installed CLI/web entrypoints and actual HTTP routes smoke passed with isolated runtime data.
- Playwright/Chromium real job metadata and emitted ETA text passed at scan→render→completion on desktop/mobile. No JavaScript errors; expected missing synthetic-preview 404s only.

Windowing and smoothing lag abrupt changes; callback silence cannot refresh ETA. Existing browser fallback remains a separate consumer. Linux/Chromium and synthetic controlled stages were tested; real-model performance and other platforms are outside this change.

Provenance only: recent-rate idea from `0b2e3d1d8ec702bfa1a3a26e2c278f15b3bc69aa`, smoothing weights from `367148d54efaef7e49498d96ef17507f38408f64`. Diagnostics/preview changes excluded. No publication or upstream acceptance claimed.

Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`
Head: `d129e23e5fe144edb8bbd5675809c1877cfe4d0f`
Branch: `pr/recent-stage-eta`

Full evidence: [retained delivery report](../evidence/delivery/task-4-report.md); temporary artifacts: `/tmp/openscrub-task4`.

Independent task review approved the implementation. Two minor evidence-harness suggestions are retained for the next applicable QA use; no runtime blocker was found.
