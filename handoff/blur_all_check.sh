#!/usr/bin/env bash
# Browser check: 3000 synthetic cards -> Blur all -> save -> render.
# Usage: bash handoff/blur_all_check.sh [engine dir]   (needs Playwright, ffmpeg, the app's deps)
# Runs on a throwaway copy, so it never touches a real job store.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(cd "${1:-$HERE/..}" && pwd)
T=$(mktemp -d)
W=
trap '[ -z "$W" ] || { kill "$W"; wait "$W" || true; } 2>/dev/null; rm -rf "$T"' EXIT
mkdir "$T/app" "$T/home"
tar -C "$SRC" --exclude=./openscrub_jobs --exclude=./tmp --exclude=./.git --exclude=./certs -cf - . | tar -C "$T/app" -xf -
python "$HERE/make_job.py" "$T/app"
HOME="$T/home" python "$T/app/openscrub_web.py" --http --host 127.0.0.1 --port 18391 > "$T/web.log" 2>&1 &
W=$!
for _ in $(seq 1 90); do curl -s -o /dev/null http://127.0.0.1:18391/ && break; sleep 1; done
timeout 440 node "$HERE/click.cjs"
python - "$T/app/openscrub_jobs/aaaaaaaaaaaa" <<'P'
import sys, json, cv2
j = sys.argv[1]
rows = json.load(open(j + "/report.json"))["detections"]
off = sum(not r["enabled"] for r in rows)
cap = cv2.VideoCapture(j + "/output.mp4")
n = masked = 0
while True:
    ok, im = cap.read()
    if not ok:
        break
    n += 1
    masked += float(im[30:50, 45:85].mean()) < 30
print(f"rows still visible={off} masked={masked}/{n}")
# the last 3 frames of the synthetic clip carry no detection
sys.exit(0 if off == 0 and n == 1800 and masked >= 1797 else 1)
P
