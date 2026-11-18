import ast
import json
from pathlib import Path
import subprocess

root = Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
base = 'b70d42011168192cdf7a9ef93a5e9419a92a1cdb'
head = 'ac0f5e4661701e954e04dbc95eb00d9317c04cc6'
test = 'tests/test_live_preview.py'
def git(*args):
    return subprocess.check_output(['git', '-C', str(root), *args])
assert git('rev-parse', 'HEAD').decode().strip() == head
assert git('status', '--porcelain') == b''
assert git('diff', '--name-only', base, head).decode().splitlines() == [test]
paths = git('ls-files', '-z').decode().split('\0')[:-1]
for name in paths:
    assert (root / name).read_bytes() == git('show', head + ':' + name), name
    if name != test:
        assert git('show', head + ':' + name) == git('show', base + ':' + name), name
before = ast.parse(git('show', base + ':' + test).decode(), feature_version=(3, 9))
after = ast.parse((root / test).read_text(), feature_version=(3, 9))
existing = [ast.dump(node) for node in before.body]
retained = [ast.dump(node) for node in after.body if getattr(node, 'name', None) != 'test_http_ignores_modified_since_without_last_modified']
assert existing == retained, 'existing tests/fixtures changed'
new = [node for node in after.body if getattr(node, 'name', None) == 'test_http_ignores_modified_since_without_last_modified']
assert len(new) == 1
recipe = (root / 'pyproject.toml').read_text()
assert '"tests/",' in recipe.split('[tool.hatch.build.targets.sdist]', 1)[1]
assert 'requires-python = ">=3.9"' in recipe
subprocess.run(['git', '-C', str(root), 'diff', '--check', base, head], check=True)
print(json.dumps({'head': head, 'base': base, 'clean': True, 'only_change': test, 'other_tracked_files_byte_identical': len(paths) - 1, 'existing_owner_ast_unchanged': True, 'python39_grammar': 'pass', 'diff_check': 'pass', 'sdist_tests_recursive_inclusion': True, 'requires_python': '>=3.9'}))
