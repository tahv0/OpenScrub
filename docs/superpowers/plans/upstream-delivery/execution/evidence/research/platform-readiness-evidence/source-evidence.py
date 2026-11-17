import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path('/home/tahv0/src/OpenScrub')
out = root / '.superpowers/sdd/README/platform-readiness-evidence'
ref = '5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f'
patterns = {
    'Dockerfile': ['FROM ', 'prefetch_models.py yunet', 'ARG SECURITY_REFRESH', 'RUN echo'],
    'Dockerfile.intel': ['FROM ', '--device /dev/dri', 'OpenVINOExecutionProvider', 'ARG SECURITY_REFRESH'],
    'Dockerfile.cuda': ['FROM ', "grep -viE", 'onnxruntime-gpu', 'paddlepaddle-gpu==', 'numpy==', 'pip uninstall -y opencv', 'CVSRC=', 'rm -rf "$SITE/cv2"', 'CUDAExecutionProvider', 'ARG SECURITY_REFRESH'],
    'docker/Dockerfile.opencv-cuda': ['ARG OPENCV_VERSION', 'FROM ', 'numpy==', 'git clone', 'opencv_contrib.git', 'CMAKE_INSTALL_PREFIX', 'OPENCV_EXTRA_MODULES_PATH', 'BUILD_LIST=', 'WITH_CUDA=', 'OPENCV_DNN_CUDA=', 'WITH_CUDNN=', 'CUDA_ARCH_', 'COPY --from=build', 'CVDIR=', 'cp -r "$CVDIR"'],
    '.github/workflows/docker-image.yml': ['cron:', 'runs-on:', 'platforms:', 'file: Dockerfile', 'SECURITY_REFRESH=', 'cache-from:', 'cache-to:', 'RAW="$(git describe', 'git checkout "$RAW"'],
    '.github/workflows/windows-installer.yml': ['runs-on:', 'python-version:', 'shell: cmd', 'windows\\build_installer.bat', 'Inno Setup 6'],
    'windows/build_installer.bat': ['PyInstaller', 'onnxruntime-directml', 'DmlExecutionProvider', 'ISCC', 'needs Python'],
}
sources = []
for path, needles in patterns.items():
    cmd = ['git', 'show', f'{ref}:{path}']
    result = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    matches = [dict(line=i, text=line) for i, line in enumerate(result.stdout.splitlines(), 1) if any(needle in line for needle in needles)]
    sources.append(dict(path=path, ref=ref, command=cmd, returncode=result.returncode, sha256=hashlib.sha256(result.stdout.encode()).hexdigest(), selected_lines=matches))
local = []
for path, first, last in [
    ('docs/superpowers/plans/upstream-delivery/03-packaging-and-review-features.md', 49, 78),
    ('.superpowers/sdd/README/task-61-report.md', 135, 150),
]:
    lines = (root / path).read_text().splitlines()
    local.append(dict(path=path, line_range=[first, last], selected_lines=[dict(line=i, text=lines[i-1]) for i in range(first, last+1)]))
for path in ['.superpowers/sdd/README/task-1-artifacts/environment.json', '.superpowers/sdd/README/task-1-artifacts/environment-opencv4.json']:
    local.append(dict(path=path, data=json.loads((root / path).read_text())))
compose = subprocess.run(['docker', 'compose', 'version'], capture_output=True, text=True, timeout=10)
result = dict(pinned_ref=ref, sources=sources, local_sources=local, compose=dict(command=['docker', 'compose', 'version'], returncode=compose.returncode, stdout=compose.stdout, stderr=compose.stderr), limits='Only permitted P13/P14 cards, Task61 platform limits, Task1 environment JSON and pinned Docker/workflow/Windows sources. No product worktree read or broad source audit.')
(out / 'source-anchors.json').write_text(json.dumps(result, indent=2) + '\n')
for path in Path('/tmp/openscrub-platform-readiness-20261117').glob('*.py'):
    shutil.copyfile(path, out / path.name)
print(json.dumps(dict(source_count=len(sources), local_source_count=len(local), compose_returncode=compose.returncode, pinned_ref=ref)))
