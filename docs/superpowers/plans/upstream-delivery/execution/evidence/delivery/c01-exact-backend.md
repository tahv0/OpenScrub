# Exact-frame backend in the clean OpenScrub build

The local staging branch `integration/upstream-focused-exact-backend` is reviewed at `7e19159ef7077af60a7ec6ed60e9f830bbefbed7`. It builds on the reviewed clean application `b4fc209570d3e3a81be251dfc55aa71a24ad7b82` and composes the accepted [exact-frame backend](task-1001-final-acceptance.md) through `335435e1e1120de9e6773656b7dfdfabf220e27b`. The app and package still identify this base as v1.0.96. Austin's v1.0.97 reconciliation is part of the later combined gate.

## What changed and why

- An exact-frame request binds the returned JPEG and editor geometry to the selected scan source, indexed frame and raw report. Source preparation and final acceptance check the containing job when another job owns that file. A conflicting publication, replacement or recovery state refuses the stale request.
- Geometry saves check the sampled source and target geometry before writing. Existing choice-only saves and manual identities continue to work. An identical edit takes the existing no-op path. A successful render advances the report publication epoch after the video and report commit together.
- Cancellation rechecks the captured scan operation before ordinary review or automatic render handoff. Recovery can suppress optional thumbnail work while allowing the completed scan to reach the normal review or render decision.

The diff changes three product files. The checked engine, vault, package and updater files and shipped page assignments match the clean base. The backend is in place for the subsequent strict tracker seed and editor stages. The browser still uses the existing editor. This stage uses the existing dependencies and pretrained model configuration.

## Verification on the staging branch

| Source | Verification | Result |
| --- | --- | --- |
| `7e19159` | Frozen source on Python 3.12.16 and actual Python 3.9.25 | 33 focused checks passed on each. Coverage includes stale source during sample and strict save, same-source concurrent report updates, exact and legacy index handling, failed and successful delivery, no-op saves, cancellation, thumbnail recovery and callback ownership. |
| `7e19159` | Offline sdist, wheel built from the extracted sdist, isolated install | 95 Git-backed sdist members, 20 Git-backed wheel members, installed payloads and all 23 hashed wheel RECORD entries checked. The metadata declares Python >=3.9. |
| `7e19159` | Installed Flask app over loopback HTTP with synthetic media and a seeded report | Sample, strict geometry and manual save, replay, a real ten-frame render and report reopen in a fresh interpreter passed. Reopen checked disabled rows, audio, manual identity and preserved report fields. |
| `c5afff6` | Node checks of shipped JavaScript | 58 passed for polling, thumbnail scheduling and review filters. The same page source assignments were verified byte-for-byte at `7e19159`. |

The first independent review found held-save source retirement, conflicting aliases for strict rows, a signalled cancellation handoff, and thumbnail publication during foreign-source recovery. It also caught a change to the messages shown for legacy manual saves. The repair preserved actionable legacy messages. The follow-up review found that recovery before thumbnail admission could still fail the completed scan. The final scoped review approved `7e19159` after the admission fix, with all four Important findings addressed.

The wider `7fbdff0` run recorded 347 passed, one failed and six deselected on Python 3.12. Its single failure was a controlled JobLog fixture missing the scan source in its report. The corrected fixture passes in the final selection on both interpreters. The 163-check Python 3.9 run belongs to `7fbdff0`. The interim `c5afff6` run recorded 172 passed, one thumbnail-admission failure and five loopback setup errors. The final loopback installed check ran with socket access. Full combined discovery, current Chromium, Windows, Docker and long-video performance remain open.

The local execution directory is `.superpowers/sdd/README/runtime/c01-exact-backend/`. The controller logs `last-native-controller.log`, `last-floor-controller.log`, `supervisor-node-controller.log` and `last-package-controller.log` contain the commands, frozen inputs and results. `package-audit.json` and `supervisor-accepted-source-audit.json` record the package and source comparisons.

## When this reaches Austin

The staging branch is a local integration checkpoint. The [standalone backend draft](../../pr-drafts/exact-editor-samples.md) describes its contribution scope for an Austin-based review. Refresh the actual upstream base and declared prerequisites before submission. Present the synthetic reproductions and observable route behavior with the relevant PR.

The [strict tracker seed checkpoint](c01-strict-seeds.md) now composes `6fde5ad` with the clean build's cancellation, report publication and source ownership. Vault continuity and thumbnail generation have their own combined gates before the editor and Track switch. Optional blur and confidence policy remain in their own [delivery plan](../../../04-optional-assistance.md).
