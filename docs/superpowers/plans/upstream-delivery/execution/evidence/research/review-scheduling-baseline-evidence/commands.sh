#!/usr/bin/env bash
# Recorded reproduction pattern; no install, product mutation, inference or build.
# Run from the repository object store. Use separate terminals for the servers.
mkdir -p /tmp/openscrub-review-scheduling-20261117/baseline /tmp/openscrub-review-scheduling-20261117/p07a
git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 | tar -xf - -C /tmp/openscrub-review-scheduling-20261117/baseline
git archive 92124753736e287ac800af91f0ac96f3e96c01be | tar -xf - -C /tmp/openscrub-review-scheduling-20261117/p07a
# Copy the supplied serve.py/browser.cjs from this evidence directory into the temporary root.
# Loopback binding and Chromium required approved sandbox escalation in this environment.
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python /tmp/openscrub-review-scheduling-20261117/serve.py
# Separate terminal, same Python environment:
# python /tmp/openscrub-review-scheduling-20261117/serve.py --source p07a --port 18519
# Separate terminal:
# PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu node /tmp/openscrub-review-scheduling-20261117/browser.cjs
# QA_SOURCE=p07a QA_PORT=18519 PLAYWRIGHT_BROWSERS_PATH=/tmp/openscrub-save-as-20261116/browsers LD_LIBRARY_PATH=/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu node /tmp/openscrub-review-scheduling-20261117/browser.cjs
# Browser probes release their gates and close contexts in finally blocks.
# Actual final server cleanup: kill -TERM 599369 600035
# Both listeners were then verified closed using socket.connect_ex; see cleanup JSON.
