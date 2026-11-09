# Large Review Save Implementation Plan

**Goal:** Save large reviewed jobs without wasting the request deadline on JSON
pretty-printing or resending all unchanged decisions; never confirm before disk
publication, discard a new draft, or reinterpret default blur as a human label.

**Architecture:** Keep the existing synchronous, serialized report transaction.
Encode compact JSON in bounded array batches using the standard encoder, retaining
temporary-file + flush + fsync + replace semantics. Send sparse UI decision maps,
skip genuine no-op decision writes, and give only explicit review POSTs a bounded
120-second deadline with a slow-save status. Other requests retain 15 seconds.

**Stack:** Python standard JSON/Flask/Cheroot, production embedded JavaScript,
pytest/Node/Playwright. No new application dependency, schema or model change.

**Evidence:** User supplied visibility/label payload has 105,267/37,618 entries
(2,105,310 bytes compact). Payload alone has no server report or timing trace.
Local baseline POST with that payload and synthetic 48-vertex report: 20.51s,
including 16.08s atomic JSON writing and 3.87s reading. Do not claim this measures
the user's Windows disk or proves the only cause on their PC. Do not commit the
private payload or job identity to the repository.

## Review focus
- Encoding/fsync/replace failure preserves the old report; no premature success.
- Large lists are batch encoded, not a second whole encoded report in memory.
- New decisions during an in-flight save stay dirty and are sent next time.
- Explicit clear labels are preserved, default blur is never training feedback.
- Slow successful POSTs outlive 15s; a truly stalled save remains bounded/retryable.

## Tasks
- [x] Add failing serialization/large-save/sparse-payload/slow-response tests.
- [x] Implement compact batched atomic writer; no-op saves and stage timings.
- [x] Implement sparse decision payload and longer explicit-save deadline only.
- [x] Run targeted browser/regression checks and private-payload benchmark.
- [ ] Publish isolated PR against integration/all-prs, inspect full-suite/CI results.

No user recording or CUDA hardware is available. Regular Playwright is used:
Browser plugin absent. Local networking may require the existing Flask bridge;
real HTTP coverage must run in CI before a network-flow success claim.

## Execution record
- Failing tests observed for pretty/token-at-a-time encoding, no-op rewrites,
  complete UI payloads and a delayed browser response crossing the old deadline.
- Sparse baseline review found a corner-autosave label-clear regression. Added
  a failing test, then tracked the independently committed label before computing
  subsequent deltas. New gestures/explicit label clearing now pass.
- 12 new cases cover round-trip/batching, encode/fsync/replace failure, no-op
  retry, sparse defaults/clear, desktop/mobile edits during a save, 16.5-second
  save confirmation, deadline scope, 105,267-row real-HTTP transaction and
  clearing a label just written by corner autosave. No private payload in CI.
- Local benchmark using the supplied payload and identical synthetic reports:
  48 vertices: 20.51s -> 8.81s; atomic write 16.08s -> 4.79s. A separate Cheroot
  synthetic 105,267-row POST passed in 8.50s. Hardware/footage remain untested.
- Local targeted core regressions: 86 passed. New+corner/autosave checks:
  30 passed, 2 deselected (the heavy HTTP and slow-response cases ran separately).
- No independent reviewer tool available; the diff and transaction/state lifetimes
  were reviewed directly. Local Playwright uses the existing Flask bridge; CI
  must use actual HTTP. The actual Cheroot large-POST test ran locally as well.
