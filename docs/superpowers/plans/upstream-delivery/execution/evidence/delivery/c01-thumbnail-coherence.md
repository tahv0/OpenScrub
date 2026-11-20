# Thumbnail coherence in the clean OpenScrub build

The reviewed local staging branch `integration/upstream-focused-thumbnails` is at `681d82c05c682a6aca8e5d3766fe6afa4266678f`. It composes [P08A thumbnail coherence](p08a-thumbnail-coherence-acceptance.md) through `1948644` with the [vault checkpoint](c01-vault-source-continuity.md) `fe81f5d` and the existing virtual review scheduler.

## What changed and why

- A thumbnail and its validator refer to one coherent report and source generation. Both request reservations handle recovery of the job containing that source. A versioned request for an obsolete image returns a typed response that the review page can handle.
- The visible-first scheduler carries generation identity on image requests and retains its four slots through the bodies of old or aborted requests. Metadata recovery can rebind unchanged rows and complete groups. A changed group offers **Re-open review** and keeps the user's drafts.
- Lightbox failure status survives scrolling and stays visible until the current image decodes. A manual Retry owns its request while it is pending. Existing automatic recovery after a transient review-load failure continues to work.
- Optional pre-generation releases its leases when admission is refused. It uses the generation it selected before opening its decoder. A completed scan can still reach review or the normal render handoff when this optional work is unavailable.

Austin's discussion asked for focused long-recording improvements with synthetic reproductions. This staging branch provides combined ownership evidence for the standalone contribution. The [thumbnail PR draft](../../pr-drafts/thumbnail-coherence.md) records its focused upstream scope. [Upstream discussion](https://github.com/austinmabry/OpenScrub/issues/22#issuecomment-6903629797)

## Verification

| Source | Result |
| --- | --- |
| `681d82c` on Python 3.12.16 | 793 selected checks passed, including real Flask and Chromium, exact and strict track routes, vault, saves and renders, cache validation, polling, and review ownership. |
| `52e0be6` on Python 3.9.25 | 780 selected checks passed. The sole change at `681d82c` controls the order of a Chromium fixture outside this selection. |
| Offline package at `681d82c` | Matched 108 source-distribution members, 21 wheel members and 24 hashed wheel RECORD entries. Its wheel bytes match the package used for the installed HTTP probe. |
| Installed HTTP | Verified a current conditional 304, typed obsolete 409 during foreign recovery, and a fresh JPEG 200 after publication. The server exited cleanly. |

Independent source review approved the composed backend and browser behavior after the recovery, lifetime and retry fixes. The final Chromium fixture holds an old crop while the lightbox triggers recovery. Five focused runs on each Python version passed before the final combined run. Earlier incomplete runs remain attributed to their source and setup.

Compact logs, selection manifests, package receipts and a narrow-screen capture are in `.superpowers/sdd/README/runtime/c01-thumbnail-coherence/`. Local evidence covers the exercised Linux/WSL environment and synthetic inputs. Full discovery, Windows, Docker and representative long-video measurements remain separate.

The next stage is validation reuse for eligible unchanged reports. The exact visual editor follows the completed thumbnail stack.
