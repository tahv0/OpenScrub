## Task 6521: check actual-media prerequisites before allocating fixtures

### What, why, when and constraints

Test-only follow-up to the accepted P16B optional-prerequisite minor, before focused upstream submission. Basea3c3193e8dff41ec0588e66443398048a5c15ece; root creates pr/polygon-media-prerequisites in the same managed source worktree after Task116 review. Preserve original pr/invalid-polygon-fallback/C01/all old refs. No production paint/mask/geometry/default/resource behavior, dependency, new frontend/toolchain, user-data or publication changes.

Only tests/test_polygon_fallback.py may change. Existing tiny_media fixture tests only shutil.which('ffmpeg'), but generates libx264/libx265 media and production paths also need ffprobe. Missing optional tools/encoders should skip clearly before raw media/root/output creation, while real encoding/render failures after successful prerequisite checks remain failures.

### Minimal interface and checks

Extract the existing ffmpeg-only guard into a small local require_media_tools() helper and invoke it first in tiny_media, before mktemp/raw writes. Keep this mechanical extraction behavior unchanged initially. Add bounded helper contract regressions for missing ffprobe and missing exact libx264/libx265 support, demonstrating real DID-NOT-SKIP failures before adding checks. Also cover missing ffmpeg and unavailable encoder-query/OSError with precise missing-prerequisite reasons; keep a complete-support control. If helper test needs different setup, retain the actual failure cause and ask root rather than fabricate RED.

Implement the smallest local checks: both tool executables present; one bounded ffmpeg -encoders query succeeds; actual encoder names include libx264 and libx265. Match names as tokens, so libx264rgb alone does not qualify as libx264. Skip only missing/unqueryable prerequisites with a clear name/reason. Do not catch ordinary media generation/render/byte-oracle failures. No generic capability framework/cache registry or new root helper is justified.

The helper is only test setup. Test doubles may supply tool availability/query output to pin skip-before-media behavior, but actual production render/paint/oracle calls stay real. Preserve all independent full-known-box/global-HDR/input and decoded-output assertions and exact fixture dimensions/codecs/settings.

### Verification and delivery

- [ ] Stabilize meaningful helper RED/GREEN without invoking missing tools or allocating media during missing-prerequisite cases; preserve complete raw failures/commands.
- [ ] Freeze clean candidate and run the complete owning tests/test_polygon_fallback.py on actual prepared3.12.16, with real tools present and all actual-media cases passing without skips. Do not rerun unrelated full project/browser/benchmark matrices.
- [ ] Run actual3.9 new helper contracts and existing actual-media owning nodes, with exact selected-source hashes and distinct helper-owned scratch. Node IDs derive from the actual source, not an imagined current C01 inventory.
- [ ] Verify only designated test path differs; all production/metadata/recipe bytes unchanged; Python3.9 grammar, diff check and existing recursive sdist test inclusion retained. No new package artifact claim for unchanged runtime/recipe.
- [ ] Self-review/commit and write task-6521-report.md/task-6521-pr.md plus compact task6521-evidence, preserving actual tool/source/fixture/command identities/failures and scope limits. No media/env/export/install/private execution-control artifacts. Root independent review before any later combined application or publication.

Use unchanged verification helper, actual prepared interpreters, clean environment/login:false, original-call escalation for owned socket/native fixture phases, no downloads/shared environment changes. Root supplies exact source/scratch and local phase budgets before dispatch. One source/runtime owner; no nested agents.

