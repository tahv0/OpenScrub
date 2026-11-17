O02 selected-target source-only contract evidence, 2026-11-17

Product pin: 4b9bd7e576a8ae30369672b4b4722fc9752e233f
Repository used only for immutable Git reads: /home/tahv0/src/OpenScrub
Full export scratch: ../runtime/selected-target-tracking-research (not packaged here)

Reproduction (from original repository):
  python3 .superpowers/sdd/README/selected-target-tracking-contract-evidence/collect_sources.py
  python3 .superpowers/sdd/README/selected-target-tracking-contract-evidence/verify_artifacts.py

collect_sources.py runs only git show/git rev-parse and standard-library text/hash/file operations.
verify_artifacts.py checks export identities, exact numbered excerpts, static script syntax,
local report links and required contract proof sections. It does not import product code.
artifact-verification.json is evidence of those artifact checks only, not semantic/runtime acceptance.

Exact commands used to inspect: cat/sed/rg over named adopted reports, brief and immutable
exports; git show/ rev-parse via collector; git status --short (read-only, original checkout).
Initial source export used the same stdlib/Git mechanism before retaining the collector.
No native checkout read or mutation; no donor/P16D export; no product changes, tests,
browser/model/media execution, benchmark, network/download/install, Git commit or publication.
No exclusive measurement slot was announced during this collection.

Files ending .py.txt are numbered source excerpts, not runnable product files.
The manifest records source path, commit, blob, SHA256, byte/line counts and excerpt ranges.
Prior O01/P10/P10C evidence is referenced by the report, not copied/reinvestigated here.

Focused control-record follow-up (new recommendation, root adoption pending):
  collect_control_followup.py reads only the existing verified exports and creates
  control-followup-owner-excerpts.txt / control-followup-source-proof.json.
  append_control_followup.py appended control-followup-appendix.txt once after
  asserting the original report was exactly 45,313 bytes at its recorded SHA256.
  The append script intentionally refuses to reappend to an already extended report.
  control-followup-integrity.json records original/final/appendix hashes and sizes.
  verify_artifacts.py now validates the exact original prefix, appendix/final hashes
  and all 272 additional numbered source lines. No product/runtime work was added.

Final source-only artifact verification:
  python3 .superpowers/sdd/README/selected-target-tracking-contract-evidence/verify_artifacts.py
