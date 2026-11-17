"""Validate recorded production-route observations without doing codec work."""
from pathlib import Path
import json
import hashlib

root = Path(__file__).resolve().parent
raw = (root / 'results.json').read_bytes()
data = json.loads(raw)
cases = {c['case']: c for c in data['cases']}
assert data['source_sha'] == 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
assert cases['warm_three']['counts']['report_open_read'] == 0
assert cases['warm_three']['counts']['report_json_load'] == 0
assert cases['warm_three']['counts']['jpeg_open_read'] == 3
assert cases['warm_conditional']['responses'][0]['status'] == 304
for name in ('parallel_cold_four', 'parallel_readonly_consumers'):
    assert cases[name]['counts']['report_json_load'] == 4
    assert all(r['status'] == 200 for r in cases[name]['responses'])

def thumb(case):
    return next(r for r in cases[case]['responses'] if isinstance(r, dict) and '/thumb/' in r['request'])

assert thumb('cold_one')['sha256'] == thumb('geometry_post_same_row')['sha256']
assert thumb('geometry_post_same_row')['sha256'] != thumb('geometry_forced_cold_control')['sha256']
assert thumb('geometry_forced_cold_control')['sha256'] == thumb('same_size_atomic_report_replace')['sha256']
assert thumb('same_size_atomic_report_replace')['sha256'] != thumb('atomic_replace_forced_cold_control')['sha256']
old = cases['same_size_atomic_report_replace']['previous_report_identity']
new = cases['same_size_atomic_report_replace']['report_identity']
assert old['size'] == new['size'] and old['mtime_ns'] == new['mtime_ns']
assert old['ino'] != new['ino'] and old['sha256'] != new['sha256']
assert thumb('atomic_replace_forced_cold_control')['sha256'] == thumb('normalized_source_switch')['sha256']
assert thumb('normalized_source_switch')['sha256'] != thumb('normalized_source_forced_cold_control')['sha256']
assert thumb('normalized_source_forced_cold_control')['sha256'] == thumb('source_atomic_replace_same_path')['sha256']
assert thumb('source_atomic_replace_same_path')['sha256'] != thumb('source_replace_forced_cold_control')['sha256']
assert cases['warm_with_corrupt_report']['counts']['report_json_load'] == 0
print(json.dumps({'status': 'PASS', 'case_count': len(cases),
                  'results_sha256': hashlib.sha256(raw).hexdigest()}, indent=2))
