#!/usr/bin/env python3
"""Native seek cancellation boundary; run separately from timing comparisons."""
import argparse
import json
from pathlib import Path
import subprocess

from probe import BASE, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = subprocess.check_output(["git", "show", BASE + ":openscrub.py"], text=True)
    results = {}
    for clip in ("gop30", "single-keyframe"):
        for mode in ("base", "safe", "safe-cleanup"):
            for cancellation in ("before", "timed"):
                result = run(source, args.work / (clip + ".mp4"), mode, cancel=cancellation)
                assert result["exception"] == "PipelineCancelled"
                if mode == "safe-cleanup":
                    assert result["releases"] == result["capture_count"]
                    assert result["remaining_grab_state"] == 0
                    if cancellation == "before":
                        assert not result["seeks"] and result["reads"] == 0
                results[f"{clip}/{mode}/{cancellation}"] = result
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({k: {field: value[field] for field in (
        "seconds", "reads", "releases", "remaining_grab_state")} for k, value in results.items()}, indent=2))


if __name__ == "__main__":
    main()
