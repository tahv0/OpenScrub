"""Source-only immutable exports and compact excerpts; no product imports."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path('/home/tahv0/src/OpenScrub')
PIN = '4b9bd7e576a8ae30369672b4b4722fc9752e233f'
OUT = ROOT / '.superpowers/sdd/README/runtime/selected-target-tracking-research'
EVIDENCE = ROOT / '.superpowers/sdd/README/selected-target-tracking-contract-evidence'
RANGES = {
    'openscrub.py': [(733, 751), (1433, 1445), (1926, 2058), (2100, 2190),
                      (2260, 2444), (2447, 2738), (3811, 3838), (3869, 3885),
                      (4058, 4088), (4269, 4317), (6118, 6128), (6352, 6449),
                      (8393, 8459), (8517, 8568)],
    'openscrub_web.py': [(450, 492), (870, 917), (1550, 1585), (1623, 1641),
                          (1664, 1694), (1806, 1929), (1933, 2060), (3290, 3320),
                          (3420, 3440), (3711, 3740), (3796, 3809), (3901, 3977)],
    'openscrub_internal/lifetimes.py': [(1, 71)],
    'openscrub_internal/reports.py': [(1, 43)],
}
OUT.mkdir(parents=True, exist_ok=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)
manifest = []
for name, ranges in RANGES.items():
    data = subprocess.check_output(['git', 'show', PIN + ':' + name], cwd=ROOT)
    exported = OUT / name.replace('/', '__')
    exported.write_bytes(data)
    identity = dict(commit=PIN, path=name,
                    blob=subprocess.check_output(['git', 'rev-parse', PIN + ':' + name],
                                                 cwd=ROOT, text=True).strip(),
                    sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                    lines=len(data.splitlines()), export=str(exported))
    lines = data.decode().splitlines()
    excerpt = EVIDENCE / (name.replace('/', '__') + '.txt')
    chunks = [json.dumps(identity, sort_keys=True)]
    for lo, hi in ranges:
        chunks.append('\n# ' + name + ':' + str(lo) + '-' + str(hi))
        chunks.extend(str(i) + ': ' + lines[i-1] for i in range(lo, hi+1))
    excerpt.write_text('\n'.join(chunks) + '\n')
    identity['excerpt'] = excerpt.name
    identity['excerpt_ranges'] = ranges
    manifest.append(identity)
(EVIDENCE / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(OUT / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Exported', len(manifest), 'pinned source files; wrote numbered excerpts and identities only.')
