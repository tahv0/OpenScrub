#!/usr/bin/env python3
"""Sequential no-retrieval prefix alternative; no seek or inference."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess

import cv2

from probe import BASE, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = subprocess.check_output(["git", "show", BASE + ":openscrub.py"], text=True)
    cv2.setNumThreads(1)
    output = dict(base=BASE, started_utc=datetime.now(timezone.utc).isoformat(), clips={})
    for clip in ("gop30", "single-keyframe"):
        path = args.work / (clip + ".mp4")
        print("measuring", clip, flush=True)
        warmups = [[run(source, path, mode) for mode in ("base", "grab")] for _ in range(3)]
        runs = [run(source, path, mode) for i in range(5)
                for mode in (("base", "grab") if i % 2 == 0 else ("grab", "base"))]
        reference = warmups[0][0]
        for result in [r for pair in warmups for r in pair] + runs:
            assert result["exception"] is None
            assert result["row_sha256"] == reference["row_sha256"]
            assert result["useful_markers"] == list(range(17872, 18001))
            assert result["releases"] == result["capture_count"]
            assert not result["seeks"] and not result["native_set_calls"]
            assert result["remaining_grab_state"] == 0
            if result["mode"] == "grab":
                assert result["reads"] == 129 and result["grabs"] == 17872
            result.pop("rows")
            result.pop("useful_markers")
            result["matches_reference_rows_and_markers"] = True
        cancellation = {mode + "/" + kind: run(source, path, mode, cancel=kind)
                        for mode in ("base", "grab") for kind in ("before", "timed")}
        for key, result in cancellation.items():
            assert result["exception"] == "PipelineCancelled"
            if key.startswith("grab/"):
                assert result["remaining_grab_state"] == 0
                assert result["releases"] == result["capture_count"]
            result.pop("rows")
            result.pop("useful_markers")
        output["clips"][clip] = dict(warmups=warmups, runs=runs, cancellation=cancellation,
                                     reference_row_sha256=reference["row_sha256"],
                                     median_seconds={mode: statistics.median(r["seconds"] for r in runs if r["mode"] == mode)
                                                     for mode in ("base", "grab")})
        args.output.write_text(json.dumps(output, indent=2) + "\n")
    output["finished_utc"] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({name: clip["median_seconds"] for name, clip in output["clips"].items()}, indent=2))


if __name__ == "__main__":
    main()
