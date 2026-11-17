"""Append the supervisor-requested source-only comparison, preserving original bytes."""
from pathlib import Path
import hashlib
import json

ROOT = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
EVIDENCE = ROOT / 'selected-target-tracking-contract-evidence'
REPORT = ROOT / 'selected-target-tracking-contract-research.md'
ORIGINAL_BYTES = 45313
ORIGINAL_SHA256 = '9217d6cb3b941ec6872eb77f8ff4539e921b3b4c7cb8eae7da43a66d697fc65a'
original = REPORT.read_bytes()
assert len(original) == ORIGINAL_BYTES
assert hashlib.sha256(original).hexdigest() == ORIGINAL_SHA256
appendix = (EVIDENCE / 'control-followup-appendix.txt').read_bytes()
with REPORT.open('ab') as stream:
    stream.write(appendix)
final = REPORT.read_bytes()
assert final[:ORIGINAL_BYTES] == original
proof = dict(original_bytes=ORIGINAL_BYTES, original_sha256=ORIGINAL_SHA256,
             final_bytes=len(final), final_sha256=hashlib.sha256(final).hexdigest(),
             appendix_bytes=len(appendix), appendix_sha256=hashlib.sha256(appendix).hexdigest(),
             original_is_exact_prefix=True, status='source-only recommendation; root has not adopted')
(EVIDENCE / 'control-followup-integrity.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps(proof, indent=2))
