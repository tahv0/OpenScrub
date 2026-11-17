set -eu
. /tmp/openscrub-task110/env.sh
PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m build --outdir /tmp/openscrub-task110/dist
