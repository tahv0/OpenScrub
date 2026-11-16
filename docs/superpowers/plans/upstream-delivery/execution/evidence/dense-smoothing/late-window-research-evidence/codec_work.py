#!/usr/bin/env python3
"""Run after probe.py, with no competing experiment from this harness.

FFmpeg CLI diagnostics expose codec work that VideoCapture.read counts hide.
These single runs support work counts; they are not repeated latency samples.
"""
import argparse
import json
from pathlib import Path
import subprocess

from probe import Audit, BASE, load_source, marker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = subprocess.check_output(["git", "show", BASE + ":openscrub.py"], text=True)
    output = {}
    for name in ("gop30", "single-keyframe"):
        path = args.work / (name + ".mp4")
        command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "debug", "-benchmark",
                   "-threads", "1", "-ss", "595.733333333", "-i", str(path), "-an",
                   "-threads", "1", "-frames:v", "129", "-f", "null", "-"]
        done = subprocess.run(command, capture_output=True, text=True, check=True)
        (args.work / (name + "-ffmpeg-seek-debug.log")).write_text(done.stderr)
        excerpts = [line for line in done.stderr.splitlines()
                    if any(text in line for text in ("frames decoded", "successfully decoded", "packets read", "bench:"))]
        seeks = []
        for frame_index in (30, 9000, 17872):
            audit = Audit()
            namespace = load_source(source, "base", audit)
            cap = audit.VideoCapture(path)
            backend = cap.native.getBackendName()
            decoder_threads = cap.native.get(audit.CAP_PROP_N_THREADS)
            ok = namespace["_seek_cap"](cap, frame_index, 30.)
            read_ok, frame = cap.read()
            actual = marker(frame) if read_ok else None
            assert ok and actual == frame_index
            seeks.append(dict(requested_frame=frame_index, actual_marker=actual, helper_success=ok,
                              backend=backend, decoder_threads=decoder_threads,
                              native_set_calls=cap.seeks, python_reads=cap.reads))
            namespace["_grab_state"].pop(id(cap), None)
            cap.release()
        output[name] = dict(command=command, excerpts=excerpts, marker_seek_checks=seeks)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
