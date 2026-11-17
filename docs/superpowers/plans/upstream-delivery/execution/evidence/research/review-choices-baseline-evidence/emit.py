import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path('/tmp/openscrub-review-choices-20261117')
manifest = {}
for label in ('austin', 'draft'):
    source = ROOT / label
    namespace = {}
    for filename in ('zones_ui.py', 'openscrub_web.py'):
        tree = ast.parse((source / filename).read_text())
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    namespace[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    if node.targets[0].id == 'PAGE':
                        namespace['zones_ui'] = SimpleNamespace(ZONES_PAGE=namespace['ZONES_PAGE'])
                        page = eval(compile(ast.Expression(node.value), str(source / filename), 'eval'), {'__builtins__': {}}, namespace)
    # Same index replacements, with synthetic no-custom-category configuration.
    version = next(n.value.value for n in ast.parse((source / 'openscrub.py').read_text()).body
                   if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in n.targets))
    page = page.replace('%%MAXUP%%', '0').replace('%%FREEDISK%%', '0').replace('%%VERSION%%', version)
    (ROOT / (label + '.html')).write_text(page)
    manifest[label] = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                       for name in ('openscrub_web.py', 'zones_ui.py', 'openscrub.py')}
    manifest[label]['emitted_html_sha256'] = hashlib.sha256(page.encode()).hexdigest()
(ROOT / 'source-hashes.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
