# Portable scan checkpoint contract

The reviewed local P18A candidate is `pr/portable-scan-checkpoints` at `4661b8acb4789c142a0febdd87c22046b4666e51`, based on `d31939a`. It preserves the report-format part of Stop & Review in the private `openscrub_internal/checkpoints.py` module.

The helper validates a paused report's exclusive frame boundary, source and normalization identity, effective settings, and finite frame arrays. A continuation keeps the full raw prefix, including disabled and manual rows, unknown fields and audio choices. It appends only applicable suffix rows with fresh IDs and invalidates stale export provenance.

Review reproduced a dead end for a reported frame count that was later verified. The repair allows verification to advance for the same count and identity, rejects downgrades, and persists the verified state. A completed continuation still requires separate proof that the scanner accounted for the full verified range.

## Verification

- 136 checkpoint and report checks passed on each of Python 3.12.16 and Python 3.9.25, including the local HTTP transaction checks.
- A fresh sdist and wheel contain the helper and schema documentation. The 73 checkpoint tests passed on each interpreter against the extracted wheel.
- Independent review approved the source and the count-verification repair.

The compact evidence is in `.superpowers/sdd/README/runtime/portable-scan-checkpoints/`. Engine capture of complete source and settings identity, the whole-frame stop boundary, scroll alignment, resume publication, and the visible controls belong to P18B and P18C. This candidate is a prerequisite for that work.
