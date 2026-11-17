# Recorded acceptance commands. Do not rerun completed gates automatically.
# All commands used login:false. Source was frozen/clean throughout.
# Controller/helper:
TOOL=/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py
EVIDENCE=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task16330-evidence
# For actual3.12: source /tmp/openscrub-baseline-20261116/env-opencv4.sh
# collection
python3 "$TOOL" --config "$EVIDENCE/frozen312.json" --run-id collect312 run -- -m pytest $(cat "$EVIDENCE/selected-tests.txt") --collect-only -q
# Original3.12 owning run; authorized escalation selected for listening sockets.
python3 "$TOOL" --config "$EVIDENCE/frozen312.json" --run-id owners312 run -- -m pytest $(cat "$EVIDENCE/selected-tests.txt") -q -ra
# Supervisor-approved targeted3.12 setup recovery; original run remains retained.
python3 "$TOOL" --config "$EVIDENCE/adapted312.json" --run-id roundtrip312 run -- -m pytest /home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_report_roundtrip.py::test_real_render_and_fresh_route_reopen_keep_all_ten_rows -o pythonpath="$EVIDENCE/adapters" -p roundtrip_stdout -q -ra
python3 "$TOOL" --config "$EVIDENCE/frozen312.json" --run-id environment312 run -- "$EVIDENCE/adapters/environment.py"
# Offline package: cached tools installed task-locally with --no-index --no-deps --no-cache-dir.
# Authorized escalation selected originally because the installed adapter listens.
python3 "$TOOL" --config "$EVIDENCE/package.json" --run-id package312 package
# For actual3.9: source /tmp/openscrub-python39-20261117/env.sh
# First owners39 launch mistakenly used python3, resolving legacy3.9 controller
# sitecustomize through inherited PYTHONPATH. No run/workload allocated. Traceback retained.
# Corrected controller; actual workload remains config-pinned3.9.25.
env -u PYTHONPATH /usr/bin/python3 "$TOOL" --config "$EVIDENCE/adapted39.json" --run-id owners39a run -- -m pytest $(cat "$EVIDENCE/selected-tests.txt") -o pythonpath="$EVIDENCE/adapters" -p roundtrip_stdout_selected -q -ra
env -u PYTHONPATH /usr/bin/python3 "$TOOL" --config "$EVIDENCE/frozen39.json" --run-id environment39 run -- "$EVIDENCE/adapters/environment.py"
# Read-only post-package/static audit, no product import.
/usr/bin/python3 "$EVIDENCE/adapters/audit.py"
