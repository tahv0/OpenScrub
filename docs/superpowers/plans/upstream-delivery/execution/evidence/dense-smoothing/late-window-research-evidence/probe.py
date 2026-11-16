#!/usr/bin/env python3
"""Pinned-source real decoder experiment. All media go to --work under /tmp.

No product import, model, user footage, Git write, or product source edit.
"""
import argparse
import ast
import copy
import dataclasses
import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

BASE = "e21ebdf6e3ee46e6c65050dc956a9a3459152269"
FPS, WIDTH, HEIGHT, FRAMES = 30, 256, 144, 18300
FIRST = 17872


def generate(work):
    rng = np.random.default_rng(20261116)
    background = rng.integers(30, 85, (HEIGHT, WIDTH, 3), dtype=np.uint8)
    texture = rng.integers(0, 256, (48, 64, 3), dtype=np.uint8)
    commands, processes = [], []
    for name, gop in (("gop30", 30), ("single-keyframe", FRAMES + 1)):
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{WIDTH}x{HEIGHT}",
                   "-r", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264",
                   "-preset", "fast", "-crf", "18", "-threads", "1", "-pix_fmt", "yuv420p",
                   "-x264-params", f"keyint={gop}:min-keyint={gop}:scenecut=0:open-gop=0:bframes=2",
                   str(work / (name + ".mp4"))]
        commands.append(command)
        processes.append(subprocess.Popen(command, stdin=subprocess.PIPE))
    for index in range(FRAMES):
        frame = background.copy()
        # 16 high-contrast little-endian cells survive YUV420/H.264.
        for bit in range(16):
            frame[0:16, bit * 14:(bit + 1) * 14] = 240 if index & (1 << bit) else 12
        cv2.putText(frame, f"frame {index:05d}", (2, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.48, (240, 240, 240), 1, cv2.LINE_8)
        # Fixed texture, slow deterministic motion, starts two seconds before detection.
        if 17940 <= index <= 18060:
            x = 100 + (index - 18000) // 6
            frame[70:118, x:x + 64] = texture
        raw = frame.tobytes()
        for process in processes:
            process.stdin.write(raw)
    for process in processes:
        process.stdin.close()
        assert process.wait() == 0
    (work / "generation-commands.json").write_text(json.dumps(commands, indent=2) + "\n")


def marker(frame):
    return sum((int(frame[4:12, bit * 14 + 4:bit * 14 + 10].mean()) > 128) << bit
               for bit in range(16))


def metadata(path):
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
        "-show_format", "-of", "json", str(path)], text=True))
    frames = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
        "-show_entries", "frame=key_frame,best_effort_timestamp_time,pict_type",
        "-of", "json", str(path)], text=True))["frames"]
    return dict(stream=data["streams"][0], format=data["format"],
                frame_count=len(frames), keyframes=[i for i, f in enumerate(frames) if f["key_frame"]],
                first_pts=frames[0]["best_effort_timestamp_time"],
                last_pts=frames[-1]["best_effort_timestamp_time"],
                pts_step_min=min(float(b["best_effort_timestamp_time"]) - float(a["best_effort_timestamp_time"])
                                 for a, b in zip(frames, frames[1:])),
                pts_step_max=max(float(b["best_effort_timestamp_time"]) - float(a["best_effort_timestamp_time"])
                                 for a, b in zip(frames, frames[1:])))


def load_source(source, mode, audit):
    tree = ast.parse(source)
    names = {"Detection", "smooth_dense_tracks", "_grab_frame", "_seek_cap", "PipelineCancelled"}
    nodes = [copy.deepcopy(n) for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    function = next(n for n in nodes if n.name == "smooth_dense_tracks")
    if mode in ("donor", "safe", "safe-cleanup"):
        location = next(i for i, n in enumerate(function.body) if isinstance(n, ast.FunctionDef) and n.name == "_fill_to")
        code = '''
if cap is not None and _span_lo:
    first_needed = min(_span_lo)
    if first_needed > int(2 * _fps_g):
        if _seek_cap(cap, first_needed, _fps_g):
            _seq["pos"] = first_needed
        elif SAFE:
            _grab_state.pop(id(cap), None)
            cap.release()
            cap = cv2.VideoCapture(video)
            if not cap.isOpened():
                raise RuntimeError("cannot reopen smoothing source")
            _grab_state.pop(id(cap), None)
'''.replace("SAFE", str(mode != "donor"))
        if mode == "safe-cleanup":
            checkpoint = "if cb is not None and cb.cancelled():\n    raise PipelineCancelled()\n"
            code = checkpoint + code + "\n" + checkpoint
        function.body[location:location] = ast.parse(code).body
    if mode == "grab":
        fill = next(n for n in function.body if isinstance(n, ast.FunctionDef) and n.name == "_fill_to")
        loop = next(n for n in fill.body if isinstance(n, ast.While))
        read_index = next(i for i, n in enumerate(loop.body) if isinstance(n, ast.Assign)
                          and ast.unparse(n) == "ok, fr = cap.read()")
        loop.body[read_index:read_index + 1] = ast.parse('''
if _seq["pos"] in _span_lo:
    ok, fr = cap.read()
else:
    ok, fr = cap.grab(), None
''').body
    if mode in ("safe-cleanup", "grab"):
        # Lifecycle experiment only: put the decoder lifetime under finally.
        # Drop the old normal-only release to keep ownership singular.
        function.body = [n for n in function.body if not (
            isinstance(n, ast.If) and len(n.body) == 1
            and isinstance(n.body[0], ast.Expr)
            and ast.unparse(n.body[0]) == "cap.release()")]
        cap_index = next(i for i, n in enumerate(function.body) if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == "cap" for t in n.targets))
        tail = function.body[cap_index + 1:]
        final = ast.parse('''
if cap is not None:
    _grab_state.pop(id(cap), None)
    cap.release()
''').body
        function.body[cap_index + 1:] = [ast.Try(body=tail, handlers=[], orelse=[], finalbody=final)]
    namespace = dict(cv2=audit, np=np, time=time, dataclass=dataclasses.dataclass, _grab_state={})
    exec(compile(ast.fix_missing_locations(ast.Module(nodes, type_ignores=[])), "pinned-source-experiment", "exec"), namespace)
    return namespace


class Audit:
    def __init__(self):
        self.captures, self.useful = [], []
        self.in_seek = False

    def __getattr__(self, key):
        return getattr(cv2, key)

    def VideoCapture(self, path):
        capture = Capture(path, self)
        self.captures.append(capture)
        return capture

    def cvtColor(self, frame, *args, **kwargs):
        self.useful.append(marker(frame))
        return cv2.cvtColor(frame, *args, **kwargs)


class Capture:
    def __init__(self, path, audit):
        self.native = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
        self.audit = audit
        self.reads = self.seek_reads = self.releases = 0
        self.grabs = 0
        self.seeks = []

    def read(self):
        self.reads += 1
        self.seek_reads += int(self.audit.in_seek)
        return self.native.read()

    def grab(self):
        self.grabs += 1
        return self.native.grab()

    def set(self, prop, value):
        start = time.perf_counter()
        ok = self.native.set(prop, value)
        self.seeks.append(dict(property=prop, value=value, ok=ok, seconds=time.perf_counter() - start))
        return ok

    def get(self, prop):
        return self.native.get(prop)

    def isOpened(self):
        return self.native.isOpened()

    def release(self):
        self.releases += 1
        self.native.release()


def run(source, path, mode, failure=False, cancel=False):
    audit = Audit()
    ns = load_source(source, mode, audit)
    seek = ns["_seek_cap"]
    seek_records = []

    def wrapped_seek(cap, index, fps):
        start = time.perf_counter()
        audit.in_seek = True
        if failure:
            # Real decoder movement, then report inability to verify. This is
            # fault injection at the helper contract, not a naturally broken file.
            cap.set(cv2.CAP_PROP_POS_FRAMES, 9000)
            cap.read()
            ns["_grab_state"][id(cap)] = {"pos": 9001, "slow": True}
            ok = False
        else:
            ok = seek(cap, index, fps)
        audit.in_seek = False
        seek_records.append(dict(target=index, ok=ok, seconds=time.perf_counter() - start,
                                 next_frame=cap.get(cv2.CAP_PROP_POS_FRAMES)))
        return ok

    ns["_seek_cap"] = wrapped_seek
    detections = [ns["Detection"](600 + dt, 600 + dt, (x, 70, x + 64, 118), "face", "synthetic", .95,
                                   dense=True, track=1, poly=())
                  for dt, x in ((0, 100), (.2, 101), (.3, 101))]
    def cancelled():
        if cancel == "before":
            return True
        if cancel == "timed":
            return time.perf_counter() - start >= .020
        return bool(cancel and any(c.reads + c.grabs for c in audit.captures))

    cb = SimpleNamespace(cancelled=cancelled,
                         progress=lambda *_: None, log=lambda *_: None)
    start = time.perf_counter()
    exception = None
    try:
        returned = ns["smooth_dense_tracks"](detections, 30., str(path), win_start=590., cb=cb)
    except Exception as error:
        exception, returned = type(error).__name__, None
    seconds = time.perf_counter() - start
    rows = [dataclasses.asdict(d) for d in detections]
    result = dict(mode=mode, failure=failure, cancel=cancel, seconds=seconds,
                  returned=returned, exception=exception, rows=rows,
                  row_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                  useful_markers=audit.useful, seeks=seek_records,
                  reads=sum(c.reads for c in audit.captures), seek_reads=sum(c.seek_reads for c in audit.captures),
                  grabs=sum(c.grabs for c in audit.captures),
                  capture_count=len(audit.captures), releases=sum(c.releases for c in audit.captures),
                  remaining_grab_state=len(ns["_grab_state"]),
                  backend=[c.native.getBackendName() for c in audit.captures if c.native.isOpened()],
                  native_set_calls=[s for c in audit.captures for s in c.seeks])
    # Harness cleanup AFTER recording: identify function leaks without leaking our experiment.
    for capture in audit.captures:
        capture.native.release()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(["git", "show", BASE + ":openscrub.py"], text=True)
    if args.generate:
        generate(args.work)
    cv2.setNumThreads(1)
    output = dict(base=BASE, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  environment=dict(python=platform.python_version(), opencv=cv2.__version__, numpy=np.__version__,
                                   platform=platform.platform(), cpu=Path("/proc/cpuinfo").read_text().split("model name\t: ")[1].splitlines()[0],
                                   cv2_threads=cv2.getNumThreads(),
                                   ffmpeg=subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]),
                  configuration=dict(fps=FPS, dimensions=[WIDTH, HEIGHT], frames=FRAMES, window_start=590,
                                     detection_seconds=[600, 600.2, 600.3], seed=20261116,
                                     cache="fresh capture and namespace each invocation; OS file cache uncontrolled/warm; no cache drop"),
                  clips={}, faults={})
    (args.work / "opencv-build.txt").write_text(cv2.getBuildInformation())
    for name in ("gop30", "single-keyframe"):
        path = args.work / (name + ".mp4")
        print("measuring", name, flush=True)
        # Three paired warm-ups, then five alternating measured pairs.
        warmups = [[run(source, path, mode) for mode in ("base", "safe")] for _ in range(3)]
        pairs = [[run(source, path, mode) for mode in (("base", "safe") if i % 2 == 0 else ("safe", "base"))] for i in range(5)]
        reference = warmups[0][0]
        runs = [r for pair in pairs for r in pair]
        for result in [r for pair in warmups + pairs for r in pair]:
            assert result["exception"] is None
            assert result["row_sha256"] == reference["row_sha256"]
            assert result["useful_markers"] == reference["useful_markers"]
            assert result["useful_markers"] == list(range(FIRST, 18001))
            assert result["releases"] == result["capture_count"]
        output["clips"][name] = dict(metadata=metadata(path), warmups=warmups, runs=runs,
                                            median_seconds={mode: statistics.median(r["seconds"] for r in runs if r["mode"] == mode)
                                                            for mode in ("base", "safe")})
        args.output.write_text(json.dumps(output, indent=2) + "\n")
    path = args.work / "gop30.mp4"
    for mode in ("base", "donor", "safe", "safe-cleanup"):
        output["faults"]["failed_seek_" + mode] = run(source, path, mode, failure=True)
        output["faults"]["cancel_" + mode] = run(source, path, mode, cancel=True)
        output["faults"]["already_cancelled_" + mode] = run(source, path, mode, cancel="before")
    output["faults"]["normal_safe-cleanup"] = run(source, path, "safe-cleanup")
    assert output["faults"]["failed_seek_safe"]["row_sha256"] == output["faults"]["failed_seek_base"]["row_sha256"]
    assert output["faults"]["failed_seek_safe"]["useful_markers"] == output["faults"]["failed_seek_base"]["useful_markers"]
    for name, clip in output["clips"].items():
        reference = clip["warmups"][0][0]
        clip["reference_rows"] = reference["rows"]
        clip["reference_useful_markers"] = reference["useful_markers"]
        for result in [r for pair in clip["warmups"] for r in pair] + clip["runs"]:
            result["matches_reference_rows"] = result.pop("rows") == clip["reference_rows"]
            result["matches_reference_useful_markers"] = result.pop("useful_markers") == clip["reference_useful_markers"]
    output["finished_utc"] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({name: value["median_seconds"] for name, value in output["clips"].items()}, indent=2))


if __name__ == "__main__":
    main()
