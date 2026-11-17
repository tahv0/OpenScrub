#!/usr/bin/env python3
"""Source-isolated prefix-read probe; fake decoder, no media or runtime imports.

Runs original function AST until first useful grayscale conversion. The seek
adapter simulates success/failure; this does NOT validate OpenCV seek accuracy,
render correctness, real-video throughput or application integration.
"""
import ast
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

BASE = "5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f"
DONOR = "b4d0c75f25d91510fe1692f901d11853dc7db005"


class UsefulFrameReached(Exception):
    pass


class Capture:
    def __init__(self):
        self.pos = 0
        self.read_count = 0
        self.seeks = []

    def isOpened(self):
        return True

    def get(self, _):
        return 30.0

    def read(self):
        self.read_count += 1
        self.pos += 1
        return True, None

    def release(self):
        pass


def run(sha, seek_success):
    source = subprocess.check_output(["git", "show", sha + ":openscrub.py"], text=True)
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "smooth_dense_tracks")
    cap = Capture()

    def convert(*_):
        raise UsefulFrameReached()

    def seek(cap, index, fps):
        cap.seeks.append(index)
        if seek_success:
            cap.pos = index
        return seek_success

    cv = SimpleNamespace(VideoCapture=lambda _: cap, CAP_PROP_FPS=1,
                         COLOR_BGR2GRAY=2, cvtColor=convert, resize=lambda *_args, **_kwargs: None)
    ns = dict(cv2=cv, time=time, _seek_cap=seek)
    exec(compile(ast.Module(body=[node], type_ignores=[]), sha, "exec"), ns)
    row = SimpleNamespace(t_start=600.0, t_end=600.0, cbox=(20, 20, 80, 80),
                          aoff=(0, 0), dense=True, track=1, category="face", frame_index=-1)
    cb = SimpleNamespace(cancelled=lambda: False, progress=lambda *_: None, log=lambda *_: None)
    try:
        ns["smooth_dense_tracks"]([row], 30.0, "synthetic-decoder", win_start=590.0, cb=cb)
    except UsefulFrameReached:
        pass
    else:
        raise AssertionError("Probe did not reach useful frame")
    return dict(sha=sha, seek_success=seek_success, decoder_reads_until_first_useful_gray=cap.read_count,
                simulated_seek_targets=cap.seeks, decoder_next_frame=cap.pos)


if __name__ == "__main__":
    result = dict(evidence="source-isolated synthetic decoder; not real video", fps=30,
                  first_detection_seconds=600, window_start_seconds=590,
                  results=[run(sha, success) for sha in (BASE, DONOR) for success in (True, False)])
    Path(__file__).with_name("dense-smoothing-prefix-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
