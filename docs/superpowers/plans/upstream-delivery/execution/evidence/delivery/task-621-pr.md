# Protect active job files, selected render originals and shared store data

Phase-only busy checks missed saves, background decoding/tracking and streamed responses. Reserve in-process store/job lifetimes at admission and keep them through queued worker pickup, background/decoder cleanup and WSGI close. Vault transitions, delete and retention now share that boundary; partial transitions stay closed until explicit recovery.

Render also owns the actual canonical original selected from report provenance, even when its current video is a different normalized copy. Transfer that source into the queue lifetime and privately pin it through normalization so later provenance cannot redirect work to an unowned file. Preserve missing-original fallback and ordinary CLI/GUI selection; reject extant orphan/deleting job sources. Both allowlist methods now own their shared vault-tree file. Locked/recovery failures retain the displayed words and report through the existing note; acknowledged ready mutations keep their existing behavior.

Reviewed task base: `3795d49f6293baf7b8c35534862a4881447e1b16`.
Fix-round base: `4479b57612f4e5c463d31900f76277a5fcebb8a9`.
Final head: `c697d5a686d4dccbdf4f474567628d5d24e75a03` on clean `pr/job-file-lifetimes`.

Amended-source validation: **188 scoped Python3.12 regressions**, **36 new Python3.9 cases**, and **10 verbatim-reviewer/vault-cleanup checks** pass. Includes real render/HDR/audio, all nine configured Cheroot Range close schedules, source alias/normalization/fallback controls and evaluated emitted-JS refusal/success checks. Offline sdist→wheel, exact packaged/installed source and scope checks, updater inclusion and actual installed CLI/web/vault/allowlist startup pass. The earlier284-test full run belongs to the fix base; no amended-head full-suite claim is made.

Scope remains in-process. Other processes/external filesystem mutation are uncoordinated; idle references do not pin retention. Report transactions/latest-document safety, strict cancel/publication ordering and replay remain Task622/P07b. Backend cancellation latency and unavailable Windows/container/frozen/TLS execution limits remain documented.

Detailed evidence, RED→GREEN and scope of the four allowlist JS functions: [task-621-report.md](task-621-report.md), “Fix round1”. No remote publication or merge.
