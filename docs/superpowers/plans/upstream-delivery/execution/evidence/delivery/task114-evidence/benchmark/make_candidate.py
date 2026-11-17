"""Create the disposable full-module P11D experiment from the exact base."""
import pathlib,hashlib,json,difflib
r=pathlib.Path('/tmp/openscrub-task114');p=r/'base'/'openscrub.py';s=p.read_text()
assert hashlib.sha256(p.read_bytes()).hexdigest()=='0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7'
a='''    mergeable = []  # Non-dense detections only
'''
b='''    mergeable = []  # Non-dense detections only

    # The local broad phase supports ordinary finite boxes and distinct
    # Detection objects. Unsupported data keeps the original traversal;
    # merely checking eligibility must not raise an otherwise unreached error.
    from bisect import bisect_left, bisect_right, insort
    from math import isfinite
    indexed = type(hold) in (int, float) and type(bridge_gap) in (int, float)
    seen_ids = set()
    for item in dets:
        if not indexed or type(item) is not Detection or id(item) in seen_ids:
            indexed = False
            break
        seen_ids.add(id(item))
        values = item.__dict__
        box = values.get('cbox')
        timestamp = values.get('t_start')
        if (type(values.get('category')) is not str
                or type(values.get('dense', False)) is not bool
                or type(timestamp) not in (int, float)
                or (type(timestamp) is float and not isfinite(timestamp))
                or type(box) not in (tuple, list) or len(box) != 4
                or any(type(v) not in (int, float)
                       or (type(v) is float and not isfinite(v)) for v in box)
                or box[0] >= box[2] or box[1] >= box[3]):
            indexed = False
            break
    del seen_ids
    by_category = {}
    births = {}
'''
assert s.count(a)==1;s=s.replace(a,b)
a='''        for m in reversed(mergeable):
'''
b='''        if indexed:
            endpoints = by_category.get(d.category, ())
            stop = bisect_right(endpoints, (d.cbox[2] + 12, float('inf')))
            candidates = []
            for candidate_index in range(stop):
                entry = endpoints[candidate_index]
                if entry[2].cbox[2] + 12 >= d.cbox[0]:
                    candidates.append(entry)
            candidates.sort(key=lambda entry: entry[1], reverse=True)
            candidate_order = (entry[2] for entry in candidates)
        else:
            candidate_order = reversed(mergeable)
        for m in candidate_order:
'''
assert s.count(a)==1;s=s.replace(a,b)
a='''                m.cbox = (min(m.cbox[0], d.cbox[0]), min(m.cbox[1], d.cbox[1]),
                          max(m.cbox[2], d.cbox[2]), max(m.cbox[3], d.cbox[3]))
                break
'''
b='''                old_left = m.cbox[0]
                m.cbox = (min(m.cbox[0], d.cbox[0]), min(m.cbox[1], d.cbox[1]),
                          max(m.cbox[2], d.cbox[2]), max(m.cbox[3], d.cbox[3]))
                if indexed and m.cbox[0] != old_left:
                    endpoints = by_category[m.category]
                    birth = births[id(m)]
                    position = bisect_left(endpoints, (old_left, birth))
                    endpoints.pop(position)
                    insort(endpoints, (m.cbox[0], birth, m))
                break
'''
assert s.count(a)==1;s=s.replace(a,b)
a='''            mergeable.append(d)
'''
b='''            mergeable.append(d)
            if indexed:
                birth = len(mergeable) - 1
                births[id(d)] = birth
                endpoints = by_category.setdefault(d.category, [])
                insort(endpoints, (d.cbox[0], birth, d))
'''
assert s.count(a)==1;s=s.replace(a,b)
(r/'candidate').mkdir(exist_ok=True)
(r/'candidate'/'openscrub.py').write_text(s)
patch=''.join(difflib.unified_diff(p.read_text().splitlines(True),s.splitlines(True),fromfile='base/openscrub.py',tofile='candidate/openscrub.py'))
(r/'evidence'/'candidate.patch').write_text(patch)
(r/'evidence'/'candidate-identity.json').write_text(json.dumps({'base_commit':'e21ebdf6e3ee46e6c65050dc956a9a3459152269','candidate_module_sha256':hashlib.sha256(s.encode()).hexdigest(),'candidate_patch_sha256':hashlib.sha256(patch.encode()).hexdigest(),'status':'disposable experiment; no adoption'},indent=2)+'\n')
print((r/'evidence'/'candidate-identity.json').read_text())
