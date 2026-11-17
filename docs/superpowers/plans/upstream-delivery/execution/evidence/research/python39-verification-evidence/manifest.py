from pathlib import Path
import hashlib
import importlib.metadata as md
import json
import os
import platform
import sys
import sysconfig
import tarfile
from packaging.tags import sys_tags, parse_tag

root = Path('/tmp/openscrub-python39-20261117')
out = root / 'manifests'
out.mkdir(exist_ok=True)
sha = lambda data: hashlib.sha256(data).hexdigest()
tags = list(sys_tags())
tag_set = set(tags)
packages = []
for dist in sorted(md.distributions(), key=lambda d: d.metadata['Name'].lower()):
    wheel = dist.read_text('WHEEL') or ''
    wheel_tags = [line[5:] for line in wheel.splitlines() if line.startswith('Tag: ')]
    compatible = any(parse_tag(tag) & tag_set for tag in wheel_tags)
    assert compatible, (dist.metadata['Name'], wheel_tags)
    packages.append({'name': dist.metadata['Name'], 'version': dist.version,
                     'requires_python': dist.metadata.get('Requires-Python'),
                     'wheel_tags': wheel_tags, 'compatible_with_this_python': compatible,
                     'native_extensions': [str(p) for p in (dist.files or []) if str(p).endswith('.so')],
                     'direct_url': json.loads(dist.read_text('direct_url.json') or 'null')})
(out / 'packages.json').write_text(json.dumps(packages, indent=2) + '\n')
(out / 'resolved-versions.txt').write_text(''.join(d['name'] + '==' + d['version'] + '\n' for d in packages))
with tarfile.open(root / 'source-3795d49.tar') as archive:
    files = {}
    for member in archive:
        if member.isfile():
            content = archive.extractfile(member).read()
            actual = (root / 'source' / member.name).read_bytes()
            assert content == actual, member.name
            files[member.name] = sha(content)
(out / 'source-files.sha256').write_text(''.join(v + '  ' + k + '\n' for k, v in sorted(files.items())))
info = {
    'status': 'infrastructure usable; limited smoke only, not full Python-floor acceptance',
    'source_commit': '3795d49f6293baf7b8c35534862a4881447e1b16',
    'source_tree': 'f1670ddc872a906851f2caa568f559eb9e9c2373',
    'source_archive_sha256': sha((root / 'source-3795d49.tar').read_bytes()),
    'source_file_count': len(files), 'source_files_unchanged_since_export': True,
    'python': sys.version, 'executable': sys.executable,
    'base_prefix': sys.base_prefix, 'prefix': sys.prefix,
    'platform': platform.platform(), 'sysconfig_platform': sysconfig.get_platform(),
    'soabi': sysconfig.get_config_var('SOABI'),
    'compatible_tag_count': len(tags), 'compatible_tags_first_30': list(map(str, tags[:30])),
    'python_distribution_url': 'https://github.com/astral-sh/python-build-standalone/releases/download/20251031/cpython-3.9.25%2B20251031-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz',
    'dependency_index': 'https://pypi.org/simple',
    'temporary_validation_constraint': 'opencv-python<5',
    'constraint_is_shipped_metadata': False,
    'core_requirements_source': 'pinned pyproject.toml; requirements.txt was not used because it includes optional spaCy',
    'extra_requested_dependencies': ['pytest', 'build', 'hatchling'],
    'all_installed_wheel_tags_compatible': True,
    'native_wheels_from_python312_reused': False,
    'reused_readonly': ['/tmp/openscrub-baseline-20261116/bootstrap/bin/uv',
                        '/tmp/openscrub-baseline-20261116/tools'],
    'runtime_profile': os.path.expanduser('~'),
    'model_files': list(map(str, (root / 'runtime' / 'models').glob('*'))),
    'build_artifacts': {p.name: sha(p.read_bytes()) for p in (root / 'dist').iterdir()},
    'limitations': ['Linux x86_64 WSL2 only', 'no full test suite', 'no positive-face/GPU/platform-wide claim',
                    'no optional/training dependencies or model downloads', 'Flask test-client API smoke; no bound-port server claim',
                    'latest Python-3.9-compatible resolutions under the validation-only OpenCV cap; no arbitrary pins',
                    'initial restricted-network DNS denial; authorized task-local network setup then succeeded',
                    'sandbox denies socket creation; outward policy checked via direct audit event']}
(out / 'environment.json').write_text(json.dumps(info, indent=2) + '\n')
print('Manifest complete:', len(packages), 'packages;', len(files), 'unchanged source files;', len(tags), 'supported tags')
