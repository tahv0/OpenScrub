# Task 656 independent review

## Spec compliance

**✅ Spec compliant** for exact base `c205ef5379778f63313b519411a2d5e37d07cba5` and head `d1eeebd2b12645a7284344fb16ec589c8aba0ce7`.

Read the complete supplied `review-c205ef5..d1eeebd.diff` once, the task brief, full implementer report, local integration record, and compact evidence. The four required earlier reviews have approval verdicts; their retained SHA256 identities match the current review files. Those gates were not repeated.

Independently inspected SHA1-validated loose/packed Git objects without Git commands. The head has exactly the four required commits in order from the required base, with the exact original commit IDs in their `-x` footers. Each original/composed pair changes the same file with identical removed/added line sequences against its respective parent. This independently supports the retained patch-ID/provenance result and confirms preservation of the combined source rather than substitution from an older standalone candidate.

The exact base/head trees contain the same 169 tracked paths and modes. Only the four allowed files differ; the other 165 entries are identical, including defaults, PAGE/APP_JS, dependencies, packaging recipes and all other production/test/browser owners. All 169 frozen working-file SHA256 identities match the head objects. Direct read-only index inspection verified its checksum and all 169 stage-zero entries against those working bytes/modes. Worktree HEAD names `integration/upstream-focused-readiness`; it resolves to the reviewed head. All 154 resolved current refs match the retained inventory, including the original candidate/donor references, working integration reference at c205, and documentation reference at `6f055a4604563d1adc79da8264c3e56abd953fc2`.

Using the recorded prepared Python 3.12.16 only for static inspection, independently confirmed complete base/head AST equality (including docstrings) and non-comment token equality for all 15 root/private production Python files and the first-scan test. Serialization used `type_comments=True`, `annotate_fields=True`, `include_attributes=False`; token comparison excludes COMMENT/NL only. The retained AST/token hashes match. All 69 frozen Python files independently parse with Python 3.9 grammar. The sole production byte edit is the prescribed recovery-stage comment; the first-scan edit is also comments only. Current metadata and recursive test/private-package inclusion remain byte-identical to c205.

Every existing top-level test/helper/fixture definition in the two acceptance owners retains its complete base AST except the explicitly approved first prerequisite statement in `tiny_media`; that fixture's remaining AST is identical. The current combined `observe_render` and report/media oracle ASTs match both the base and recorded identities. Focused inspection across the diff cut-off confirmed `_render_into` / `_render_hdr_into`, current `frame` / `buf` locals, pre-write bytes, child/resource containment and decoded-output assertions retain their prior owner.

**⚠ Cannot verify beyond retained evidence:** this review did not observe the historical launch/escalation or replay tests, HTTP, media, packages, browser checks or benchmarks. Execution ordering, clean outer launch environment and original-call authorization are assessed from the retained commands/configs/logs and report, rather than independently reenacted. Existing package/build/installed-startup evidence remains attributed to c205; AST equivalence does not establish artifacts built from d1eeebd. These are explicit review limits, not identified spec deviations.

## Specific strengths

- `tests/test_live_preview.py:314`: the exact 1970/2100 date cases send date-only conditionals through the unchanged fixture's production `_serve` and real Cheroot sockets. Both responses use the existing complete JPEG/header oracle, case-insensitive absence of Last-Modified, and stable ETag checks.
- `tests/test_polygon_fallback.py:191`: prerequisite checks require both executables and exact libx264/libx265 names, bound the encoder query to ten seconds, and handle query failures before media allocation. Nine negative/positive contracts cover missing tools, exact-name rejection, failed/timed-out queries and the complete-support command/options. Calling the unwrapped fixture with `None` makes premature fixture allocation fail visibly.
- `tests/test_polygon_fallback.py:272`: only the reviewed prerequisite preamble changes. Actual generation/render/encode/decode failures remain ordinary failures after prerequisites succeed. `observe_render` at line 291 and the actual report-to-render oracle at line 356 remain intact.
- `openscrub_internal/render_delivery.py:188` and `tests/test_first_scan_sanity.py:105`: the imported comments clarify their existing ownership/assertion contracts without changing runtime code or test assertions.
- Evidence consistently binds the frozen source, actual interpreter, module origins, tools and complete two-owner workload. It clearly distinguishes this local assembly from upstream publication and retains the original c205 package attribution.

## Findings

**Critical:** None.

**Important:** None.

**Minor:** None.

## Task quality

**Approved.** The composition satisfies the narrow assembly scope, retains the reviewed behavior and owner boundaries, and has meaningful retained native/floor acceptance evidence. No concrete unanswered runtime doubt remains that warrants an additional bounded check for this review.

## Evidence and limits

Independently validated all 25 manifest entries and all 25 SHA256SUMS entries, including report/record, scripts, static proof, provenance, configs and complete logs. Canonical helper/hook/sitecustomize/README and ffmpeg/ffprobe bytes match the six pinned recipe identities; both interpreter executable hashes match their configs. Both frozen environments equal the earlier reviewed prerequisite environment. Frozen configs, preflights, actual runtime configs, full command logs and result records agree on head, all 169 source hashes, 12 active module origins/hashes, interpreter paths/versions and complete two-owner argv. Fixture identities are retained as metadata/hashes; no media was regenerated or copied by this review.

Retained complete results, corroborated by the actual full logs and their SHA256 identities:

| Workload | Result | Complete log SHA256 |
| --- | --- | --- |
| Actual prepared Python 3.12.16; both complete owners | 585 passed in 15.97s; zero skips | `9b4f624c19689bf97a57dc06f6bb9ae3d82d48ba1e8f4e11b5b039c9a251f203` |
| Actual prepared Python 3.9.25; both complete owners | 585 passed in 17.08s; zero skips | `6223f76db6911234fa97db343338a3a23bc2bd97e5807b3c2f1f17dddee7ee44` |

The source/parameter ownership supports the recorded 28 preview and 557 polygon cases, including two date-only HTTP cases, nine prerequisite contracts and 14 existing actual SDR/HDR media cases. These results establish the prepared Linux environments represented by the evidence, not universal encoder/platform availability or a new full-project/package/browser/benchmark claim. The harmless recorded metadata-path lookup failure is preserved separately from product results.

Review actions were read-only source/object/index/ref/evidence inspection and static parsing, with no Git commands, nested agents, workload replay or publication. Only this assigned review report was written; root retains control of working-reference advancement and documentation checkpointing.
