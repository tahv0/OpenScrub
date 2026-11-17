"""Check source-handoff artifacts only; never execute product code."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPORT = OUT.parent / 'browser-log-contract-research.md'
identity = json.loads((OUT / 'source-identity.json').read_text())
assert identity['product_commit'] == '6ae212a35b094fc9466f1616afb2c5bb5c0497f8'
assert identity['source_only'] and not identity['product_execution']
expected = []
for item in identity['files']:
    payload = Path(item['export']).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == item['sha256'], item['path']
    assert len(payload) == item['bytes'], item['path']
    lines = payload.decode().splitlines()
    for start, end in item['spans']:
        expected.append('\n## ' + identity['product_commit'] + ':' + item['path'] + ':' + str(start) + '-' + str(end))
        expected.extend(str(i) + '\t' + lines[i - 1] for i in range(start, end + 1))
assert (OUT / 'source-spans.txt').read_text() == '\n'.join(expected) + '\n'
required = ['README.md', 'commands.txt', 'claims.tsv', 'source-identity.json',
            'source-spans.txt', 'collect_source_evidence.py', 'verify_artifacts.py']
for name in required:
    assert (OUT / name).is_file(), name
text = REPORT.read_text()
assert not any(line != line.rstrip() for line in text.splitlines()), 'Trailing whitespace'
assert 'All steps below are **unrun**.' in text
assert 'P12B\'s epoch/snapshot schema is a proposed prerequisite' in text
paths = [REPORT] + [OUT / name for name in sorted(required)]
manifest = ''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path) + '\n' for path in paths)
(OUT / 'SHA256SUMS').write_text(manifest)
print('Artifact checks passed: 3 pinned source exports, exact excerpt ranges, report/evidence files; SHA256SUMS written.')
