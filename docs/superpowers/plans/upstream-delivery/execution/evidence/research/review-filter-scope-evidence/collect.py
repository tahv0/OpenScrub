"""Reproduce source-only evidence. Does not import or execute product/donor code."""
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
REPO = Path('/home/tahv0/src/OpenScrub')
PIN = '92124753736e287ac800af91f0ac96f3e96c01be'
EXPORT = Path('/tmp/openscrub-review-filter-scope-20261117')
SPECS = [
    ('p07a', PIN, [(1132, 1148), (1978, 1978), (2080, 2115), (2150, 2170),
                   (2405, 2431), (2569, 2579), (2725, 2756), (2777, 2888), (2890, 2939), (2983, 3038)]),
    ('64afc3cc', '64afc3cc', [(5347, 5383), (5408, 5446), (5551, 5568),
                            (6150, 6313), (6339, 6343), (6537, 6539), (6568, 6589),
                            (6686, 6698), (7065, 7111)]),
    ('c3a8c7a5', 'c3a8c7a5', [(6101, 6175)]),
    ('8209a82', '8209a82', [(4284, 4288), (4316, 4364), (4515, 4526), (4567, 4577)]),
    ('a80a85d', 'a80a85d', [(4284, 4288), (4316, 4364), (4515, 4526), (4567, 4577)]),
]
manifest = []
for name, pin, ranges in SPECS:
    full = subprocess.check_output(['git', 'rev-parse', pin], cwd=REPO, text=True).strip()
    data = subprocess.check_output(['git', 'show', full + ':openscrub_web.py'], cwd=REPO)
    if name == 'p07a':
        assert data == (EXPORT / 'openscrub_web.py').read_bytes()
    lines = data.decode().splitlines()
    excerpts = []
    for start, end in ranges:
        excerpts.append('\n'.join('%5d  %s' % (i, lines[i - 1]) for i in range(start, end + 1)))
    dest = name + '-anchors.txt'
    (OUT / dest).write_text('\n\n'.join(excerpts) + '\n')
    manifest.append({'name': name, 'commit': full, 'source': 'openscrub_web.py',
                     'sha256': hashlib.sha256(data).hexdigest(), 'ranges': ranges, 'excerpts': dest})
(OUT / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

# Editorial fixture for the PROPOSED predicates; no implementation is being tested.
groups = [
    {'id': 'A', 'category': 'face', 'members': [0, 1, 2], 'effective': [True, False, True]},
    {'id': 'B', 'category': 'face', 'members': [3], 'effective': [True]},
    {'id': 'C', 'category': 'plate', 'members': [4, 5], 'effective': [False, False]},
    {'id': 'D', 'category': 'plate', 'members': [6], 'effective': [True]},
    {'id': 'E', 'category': 'email', 'members': [7], 'effective': [False]},
    {'id': 'Z8', 'category': 'face', 'section': 'outside-zones', 'members': [8], 'effective': [False]},
    {'id': 'Z9', 'category': 'plate', 'section': 'outside-zones', 'members': [9], 'effective': [True]},
]
cases = []
for category in ['all', 'face', 'plate', 'email']:
    scoped = [g for g in groups if category == 'all' or g['category'] == category]
    for output in ['all', 'blur', 'visible']:
        matching = [g['id'] for g in scoped if output == 'all' or
                    (any(g['effective']) if output == 'blur' else not all(g['effective']))]
        cases.append({'type': category, 'output': output, 'matching_groups': matching, 'count': len(matching)})
(OUT / 'proposed-predicate-examples.json').write_text(json.dumps({
    'status': 'Proposed semantics only; not an executed product test', 'groups': groups,
    'zone_rule': 'Z8 and Z9 each count as one card; preserve separate section and independent row actions.',
    'cases': cases,
}, indent=2) + '\n')
print('Wrote pinned source excerpts, hashes and proposed-predicate examples; no application executed.')
