# Read-only pinned export; run from /home/tahv0/src/OpenScrub.
# First run only: mkdir -p /tmp/openscrub-polling-baseline-20261117/pinned
# git archive 92124753736e287ac800af91f0ac96f3e96c01be | tar -x -C /tmp/openscrub-polling-baseline-20261117/pinned
# Fixture and browser are synthetic controls; product PAGE/APP_JS are unchanged.
# Existing environment; no installation needed.
/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python /tmp/openscrub-polling-baseline-20261117/serve.py
# In a separate terminal:
PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu node /tmp/openscrub-polling-baseline-20261117/browser.cjs
python3 /tmp/openscrub-polling-baseline-20261117/verify.py
# Stop only this task's synthetic server:
pkill -TERM -f '^/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python /tmp/openscrub-polling-baseline-20261117/serve.py$'
# Expected no match / exit 1:
pgrep -f '^/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python /tmp/openscrub-polling-baseline-20261117/serve.py$'
