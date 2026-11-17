"""Excerpt only existing verified immutable exports; no new Git/product collection."""
from pathlib import Path
import hashlib
import json

ROOT = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
EVIDENCE = ROOT / 'selected-target-tracking-contract-evidence'
manifest = json.loads((EVIDENCE / 'source-manifest.json').read_text())
source_by_path = {item['path']: item for item in manifest}
ranges = {'openscrub.py': [(6352, 6449), (8580, 8644)],
          'openscrub_web.py': [(1022, 1055), (1824, 1866), (1900, 1922), (2005, 2013)]}
chunks = ['Source-only follow-up; existing C01 exports only.']
items = []
for path, spans in ranges.items():
    source = source_by_path[path]
    data = Path(source['export']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == source['sha256']
    lines = data.decode().splitlines()
    chunks.append('\n' + json.dumps({k: source[k] for k in ('commit', 'path', 'blob', 'sha256')}, sort_keys=True))
    for lo, hi in spans:
        chunks.append('\n# ' + path + ':' + str(lo) + '-' + str(hi))
        chunks.extend(str(i) + ': ' + lines[i-1] for i in range(lo, hi+1))
    items.append(dict(path=path, export=source['export'], sha256=source['sha256'], ranges=spans))
output = EVIDENCE / 'control-followup-owner-excerpts.txt'
output.write_text('\n'.join(chunks) + '\n')
proof = dict(excerpt=output.name, sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
             sources=items, method='Existing immutable export reads only; no new Git export or product execution.')
(EVIDENCE / 'control-followup-source-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
print('Created follow-up excerpts from', len(items), 'existing verified exports.')
