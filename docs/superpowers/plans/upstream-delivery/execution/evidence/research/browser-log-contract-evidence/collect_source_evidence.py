"""Source-only collector. Never imports or executes OpenScrub product code."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE = '6ae212a35b094fc9466f1616afb2c5bb5c0497f8'
REPO = Path('/home/tahv0/src/OpenScrub')
OUT = Path(__file__).resolve().parent
EXPORT = Path('/tmp/openscrub-browser-logs-contract/source')
SPANS = {
    'openscrub_web.py': [(325, 376), (1060, 1071), (1793, 1794),
                         (2080, 2163), (2170, 2170), (2210, 2274),
                         (2301, 2325)],
    'tests/test_job_polling_browser.py': [(18, 83), (102, 132),
                                          (184, 193), (205, 212)],
    'tests/test_job_polling_node.py': [(16, 25), (119, 127), (143, 150)],
}


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


identities = []
excerpts = []
for name, spans in SPANS.items():
    payload = git('show', BASE + ':' + name)
    exported = EXPORT / name
    if exported.read_bytes() != payload:
        raise SystemExit('Pinned export mismatch: ' + name)
    identities.append({'path': name,
                       'blob': git('rev-parse', BASE + ':' + name).decode().strip(),
                       'sha256': hashlib.sha256(payload).hexdigest(),
                       'bytes': len(payload), 'export': str(exported),
                       'spans': spans})
    lines = payload.decode().splitlines()
    for start, end in spans:
        excerpts.append('\n## ' + BASE + ':' + name + ':' + str(start) + '-' + str(end))
        excerpts.extend(str(i) + '\t' + lines[i - 1] for i in range(start, end + 1))

(OUT / 'source-spans.txt').write_text('\n'.join(excerpts) + '\n')
(OUT / 'source-identity.json').write_text(json.dumps({
    'product_commit': BASE, 'source_only': True, 'product_execution': False,
    'scope': 'Three explicitly named product files; no native checkout reads',
    'files': identities,
    'requirements_not_product_evidence': [
        str(REPO / 'docs/superpowers/plans/upstream-delivery/03-packaging-and-review-features.md'),
        str(REPO / '.superpowers/sdd/README/browser-log-contract-brief.md'),
        str(REPO / '.superpowers/sdd/README/bounded-logs-contract-research.md'),
        str(REPO / '.superpowers/sdd/README/task-3-report.md'),
    ],
}, indent=2) + '\n')
print('Wrote compact pinned source spans and identities; no product execution.')
