# Source this script before task-local Python 3.9 checks.
export PATH=/tmp/openscrub-python39-20261117/venv/bin:/tmp/openscrub-baseline-20261116/tools/usr/bin:$PATH
export LD_LIBRARY_PATH=/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu/pulseaudio${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export TESSDATA_PREFIX=/tmp/openscrub-baseline-20261116/tools/usr/share/tesseract-ocr/5/tessdata
export PYTHONPATH=/tmp/openscrub-python39-20261117/harness
export PYTEST_PLUGINS=python39_isolation
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTEST_ADDOPTS='-o cache_dir=/tmp/openscrub-python39-20261117/pytest-cache'
export OPENSCRUB_NO_AUTOFETCH=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export UV_CACHE_DIR=/tmp/openscrub-python39-20261117/uv-cache
export UV_PYTHON_INSTALL_DIR=/tmp/openscrub-python39-20261117/python
export TMPDIR=/tmp/openscrub-python39-20261117/tmp
export XDG_CACHE_HOME=/tmp/openscrub-python39-20261117/cache
export XDG_CONFIG_HOME=/tmp/openscrub-python39-20261117/config
