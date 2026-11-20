# Vault source continuity in the clean OpenScrub build

The reviewed local branch `integration/upstream-focused-vault` is at `fe81f5d835fe4032d30052087a7c0254a76559a8`, on the [strict tracking checkpoint](c01-strict-seeds.md) `514159d`. Its three product files match the accepted [standalone vault changes](vault-source-continuity-acceptance.md) through `0788899`. The added integration test starts Track from the inspected frame after a real vault lock and unlock.

Vault encryption and restoration replace physical files. Verified transitions preserve the logical source and its inspection context across that replacement. A changed or unverified file still needs a fresh observation. Active readers and workers keep their lifetime reservation through cleanup, so the vault waits before removing their files.

## Verification

| Scope | Result on `fe81f5d` |
| --- | --- |
| Previous session, Python 3.12.16 and actual Python 3.9.25 | 326 selected checks passed on each, including vault, strict tracking, exact sampling and recovery, prepared media, lifetimes and report transactions. The results are recorded in the previous session transcript. |
| Independent review | Approved. The reviewer also exercised foreign-source cancellation cleanup and confirmed the vault stays busy until that cleanup finishes and the report remains intact. |
| Fresh resumption check | All 41 vault continuity tests passed on each Python version. The regression confirmed inspected seed index and pixels, preserved report rows, expected coordinates and released lifetime owners after lock and unlock. |

The fresh check used the retained clean temporary checkout at `/tmp/openscrub-c01-vault-frozen` and the restored Python interpreters and FFmpeg from the strict tracking checkpoint. The two logs are in `/tmp/openscrub-c01-vault-recheck.UKVhYm/`.

The recovered vault checkpoint is the base for thumbnail coherence. That integration has its own tests for stale validators, held image bodies and preservation of review state. Combined packaging, browser and long-video validation belong to the later integration gates.
