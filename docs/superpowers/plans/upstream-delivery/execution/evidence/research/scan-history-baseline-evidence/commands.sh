#!/usr/bin/env bash
# Run export commands from /home/tahv0/src/OpenScrub. This is a reproducer,
# not an installer. The compatible existing environment is reused read-only.
mkdir -p /tmp/openscrub-scan-history-20261117/source
mkdir -p /tmp/openscrub-scan-history-20261117/evidence
git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 | tar -x -C /tmp/openscrub-scan-history-20261117/source
git show a11a3926 -- finding_previews.py > /tmp/openscrub-scan-history-20261117/evidence/donor-a11a3926.patch
# Copy the sibling evidence probe.py to /tmp/openscrub-scan-history-20261117/probe.py.
cd /tmp/openscrub-scan-history-20261117/source
env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 OPENSCRUB_NO_AUTOFETCH=1 LD_LIBRARY_PATH=/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu/pulseaudio /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python /tmp/openscrub-scan-history-20261117/probe.py > /tmp/openscrub-scan-history-20261117/evidence/run.log 2>&1
# No timing runs. Cleanup performed separately and recorded in cleanup.json.
