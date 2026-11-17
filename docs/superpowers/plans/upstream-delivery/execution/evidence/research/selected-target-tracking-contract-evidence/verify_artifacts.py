"""Validate this source-only handoff's artifacts without importing product code."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess

ROOT = Path('/home/tahv0/src/OpenScrub')
BASE = ROOT / '.superpowers/sdd/README'
EVIDENCE = BASE / 'selected-target-tracking-contract-evidence'
REPORT = BASE / 'selected-target-tracking-contract-research.md'
manifest = json.loads((EVIDENCE / 'source-manifest.json').read_text())
checked = []
for item in manifest:
    data = Path(item['export']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    assert len(data) == item['bytes'] and len(data.splitlines()) == item['lines']
    blob = subprocess.check_output(['git', 'rev-parse', item['commit'] + ':' + item['path']],
                                   cwd=ROOT, text=True).strip()
    assert blob == item['blob']
    source_lines = data.decode().splitlines()
    actual = (EVIDENCE / item['excerpt']).read_text().splitlines()
    expected = []
    for lo, hi in item['excerpt_ranges']:
        expected.extend(str(i) + ': ' + source_lines[i-1] for i in range(lo, hi+1))
    assert [line for line in actual if re.match(r'^\d+: ', line)] == expected
    checked.append(item['path'])
followup = json.loads((EVIDENCE / 'control-followup-source-proof.json').read_text())
followup_file = EVIDENCE / followup['excerpt']
assert hashlib.sha256(followup_file.read_bytes()).hexdigest() == followup['sha256']
expected_followup = []
for item in followup['sources']:
    data = Path(item['export']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    lines = data.decode().splitlines()
    for lo, hi in item['ranges']:
        expected_followup.extend(str(i) + ': ' + lines[i-1] for i in range(lo, hi+1))
assert [line for line in followup_file.read_text().splitlines() if re.match(r'^\d+: ', line)] == expected_followup
integrity = json.loads((EVIDENCE / 'control-followup-integrity.json').read_text())
final_bytes = REPORT.read_bytes()
assert len(final_bytes) == integrity['final_bytes']
assert hashlib.sha256(final_bytes).hexdigest() == integrity['final_sha256']
assert hashlib.sha256(final_bytes[:integrity['original_bytes']]).hexdigest() == integrity['original_sha256']
appendix = (EVIDENCE / 'control-followup-appendix.txt').read_bytes()
assert final_bytes[integrity['original_bytes']:] == appendix
assert hashlib.sha256(appendix).hexdigest() == integrity['appendix_sha256']
assert integrity['original_is_exact_prefix'] is True
for script in EVIDENCE.glob('*.py'):
    ast.parse(script.read_text(), filename=str(script))
text = REPORT.read_text()
links = re.findall(r'\]\(([^)]+)\)', text)
for link in links:
    assert (REPORT.parent / link).exists(), link
required = ['Current C owners', 'prior_correction_id', 'Concrete bounded receipt proof case',
            'A delayed retry', 'Raw-index and draft limit', 'choice_context_eq',
            'Box/quad/mask boundaries', 'No optional temporal smoothing',
            'source_ref', 'same-request replay', 'unrun here', 'manual_creation']
for phrase in required:
    assert phrase in text, phrase
assert len(re.findall(r'^```', text, re.M)) % 2 == 0
assert not any(line.rstrip() != line for line in text.splitlines())
summary = dict(status='artifact checks passed', source_files=checked,
               exact_excerpt_lines=sum(sum(hi-lo+1 for lo,hi in i['excerpt_ranges']) for i in manifest),
               report=dict(bytes=REPORT.stat().st_size,
                           sha256=hashlib.sha256(REPORT.read_bytes()).hexdigest()),
               local_links=len(links),
               checks=['export sizes/lines/SHA256', 'immutable Git blob identity',
                       'exact numbered excerpts', 'collector/verifier static AST',
                       'local report links', 'required contract proof sections',
                       'balanced code fences', 'no trailing whitespace',
                       'follow-up exact source excerpts', 'original 45313-byte prefix hash',
                       'appendix/final-report integrity'],
               original_prefix_sha256=integrity['original_sha256'],
               followup_excerpt_lines=len(expected_followup),
               runtime='No product import/test/media/model/browser/build/benchmark ran.')
(EVIDENCE / 'artifact-verification.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
