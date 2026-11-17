# Combine readable report saves, HDR rendering fixes and tracker cancellation

Local intermediate assembly `ac6496810b03d8b062ab9da150aeea1e62285fed` → `4b9bd7e576a8ae30369672b4b4722fc9752e233f`; no publication or final C01/C02 approval requested.

Readable atomic reports now use the reviewed public encoder iterator/writelines path. HDR silhouette masking redacts every chroma cell touched by luma; malformed usable-box polygons fall back to requested full-box fill. Existing HDR partial cleanup closes the decoder pipe, and manual tracking stops repeated outer work at cooperative cancellation checkpoints while retaining capture/source ownership.

Five separate `-x` provenance picks plus one test-only integration commit. Real conflicts only cumulative benchmark/document/package intersections; no runtime correction. Combined HDR test oracles enumerate global cells without weakening SDR/luma/full-box assertions. Actual default-tight report→run_render checks combine sparse/malformed/rectangle/kept controls at exact real encoder input.

Validation: focused 3.12 **1,242 passed**; full **1,643 passed/1 optional browser skipped**; actual3.9 **1,242 passed**. Actual PAGE/HTTP/newer draft/no-op/render/fresh browser/interpreter/raw14-row/audio/additive/replay and every-frame video checks passed. Actual Flask native tracker cancellation proves closed capture under source ownership, delete409 then200 and zero owners/work/threads. Offline sdist→wheel, installed CLI/web/HTTP, exact packaged/native/helper bytes/defaults and evaluated JS parse passed.

Performance: Single100k interaction: no-op median +11.46% (retained concern); sparse −18.87%, bulk −17.22%. 48 uninstrumented+6separate counted HTTP200; complete reports/no-op metadata/export/commit/package identities verified. Exact SHAs retained; no selective rerun or general speed claim.

Limits: comprehensive P16C geometry/resource/staged-video publication and prior-output restoration remain separate; cooperative cancellation does not interrupt native calls. Linux CPU/Chromium/3.9 checks are bounded, not platform or detection/audio accuracy certification. Full details/provenance/failures/evidence: `task-652-report.md`; acceptance draft: `task-652-acceptance.md`.
