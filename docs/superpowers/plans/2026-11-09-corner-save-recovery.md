# Permanent corner-save recovery
Goal: correct definite rejected-write retry, inclusive source-boundary handling,
and visible navigation to unsaved edits, without touching detector/training logic.
Base: integration/all-prs a80a85d, isolated archive checkout.

1. Add failing API cases for exact 4K boundary, rounded left/right edge, truly
   outside frame, no report/sample mutation on rejection and duplicate receipts.
2. Add production-JS tests for HTTP400 followed by newer coordinates (including
   edits made during request), and preserve same ID for ambiguous network failure.
3. Add browser cases: hide failed card in 10% view -> Save -> show failed finding
   -> corrected drag -> saved -> reopen, with same DOM/no lost draft.
4. Implement narrowly in openscrub_web.py. Polygon vertices use continuous
   [0,width] x [0,height]; only six-decimal normalization error is snapped.
   Actual outside points get corner-specific coordinates. Never blindly clip
   a real out-of-frame quad, or turn propagated shapes into verified samples.
5. Run all focused cases, UI/save/cache/learning regressions and complete CI.
   Review diff, publish PR to all-prs only and merge verified head. No main edits.

Risks: lost committed responses, stale token conflicts, changed source, new edit
while older request pending, hidden failed cards, boundary crop cache misses,
training samples at edges. Tests must keep unknown-write idempotency intact.
