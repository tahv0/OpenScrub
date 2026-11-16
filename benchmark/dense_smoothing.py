#!/usr/bin/env python3
"""Compare complete imported modules on the marked late-window research media.

Generate media with the recipe in the Task111 evidence; keep it outside Git.
Example (run from repository root):
  python benchmark/dense_smoothing.py --before /tmp/before/openscrub.py \
    --before-revision <sha> --after openscrub.py --after-revision <sha> \
    --media-dir /tmp/openscrub-late-window-20261116 --output /tmp/result.json

Only smooth_dense_tracks is timed. No inference, download, seek, or cache reset.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import resource
import statistics
import sys
import time
from types import SimpleNamespace

import cv2
import numpy as np


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Audit:
    def __init__(self):
        self.captures, self.markers = [], []
        self.reads = self.grabs = self.sets = self.releases = 0

    def __getattr__(self, name):
        return getattr(cv2, name)

    def VideoCapture(self, path):
        native = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
        audit = self

        class Counted:
            def __getattr__(self, name):
                return getattr(native, name)

            def read(self):
                audit.reads += 1
                return native.read()

            def grab(self):
                audit.grabs += 1
                return native.grab()

            def set(self, *args):
                audit.sets += 1
                return native.set(*args)

            def release(self):
                audit.releases += 1
                native.release()

        self.captures.append(native)
        return Counted()

    def cvtColor(self, frame, *args, **kwargs):
        self.markers.append(sum((int(frame[4:12, bit * 14 + 4:bit * 14 + 10].mean()) > 128) << bit
                                for bit in range(16)))
        return cv2.cvtColor(frame, *args, **kwargs)


def run(module, path, cancel=None):
    audit = Audit()
    original_cv2 = module.cv2
    module.cv2 = audit
    dets = [module.Detection(600 + dt, 600 + dt, (x, 70, x + 64, 118),
                             "face", "synthetic", .95, dense=True, track=1, poly=())
            for dt, x in ((0, 100), (.2, 101), (.3, 101))]
    start = time.perf_counter()
    cb = SimpleNamespace(cancelled=lambda: cancel == "before" or (
        cancel == "timed" and time.perf_counter() - start >= .020),
        progress=lambda *_: None, log=lambda *_: None)
    exception, returned = None, None
    try:
        returned = module.smooth_dense_tracks(dets, 30., str(path), win_start=590., cb=cb)
    except module.PipelineCancelled:
        exception = "PipelineCancelled"
    finally:
        seconds = time.perf_counter() - start
        module.cv2 = original_cv2
        # Record function-owned cleanup first; harness cleanup also prevents
        # the pre-change cancellation leak from contaminating later samples.
        releases = audit.releases
        for native in audit.captures:
            native.release()
    rows = [asdict(d) for d in dets]
    return dict(seconds=seconds, returned=returned, exception=exception,
                reads=audit.reads, grabs=audit.grabs, sets=audit.sets,
                captures=len(audit.captures), releases=releases,
                remaining_grab_state=len(module._grab_state),
                rows=rows, markers=audit.markers, rows_sha256=digest(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "media-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("before", "after"):
        parser.add_argument("--" + name + "-revision", required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    modules = {name: load(getattr(args, name), "dense_benchmark_" + name) for name in ("before", "after")}
    result = dict(started_utc=datetime.now(timezone.utc).isoformat(),
                  sources={name: dict(revision=getattr(args, name + "_revision"),
                                      path=str(getattr(args, name).resolve()),
                                      sha256=hashlib.sha256(getattr(args, name).read_bytes()).hexdigest())
                           for name in modules},
                  environment=dict(python=platform.python_version(), platform=platform.platform(),
                                   opencv=cv2.__version__, numpy=np.__version__, cv_threads=cv2.getNumThreads()),
                  clips={})
    for clip in ("gop30", "single-keyframe"):
        path = args.media_dir / (clip + ".mp4")
        records, reference = [], None
        for phase, pairs in (("warmup", 3), ("sample", 5)):
            for pair in range(pairs):
                for name in (("before", "after") if pair % 2 == 0 else ("after", "before")):
                    record = run(modules[name], path)
                    if reference is None:
                        reference = dict(rows=record["rows"], markers=record["markers"])
                    assert record["exception"] is None
                    assert record["rows"] == reference["rows"]
                    assert record["markers"] == reference["markers"] == list(range(17872, 18001))
                    assert record["returned"] == (2, 30, 2.25)
                    assert record["sets"] == record["remaining_grab_state"] == 0
                    assert record["captures"] == record["releases"] == 1
                    assert (record["reads"], record["grabs"]) == ((18001, 0) if name == "before" else (129, 17872))
                    del record["rows"], record["markers"]
                    record.update(source=name, phase=phase, pair=pair,
                                  matches_reference_rows_and_markers=True)
                    records.append(record)
                    print(clip, phase, pair, name, f'{record["seconds"]:.6f}', flush=True)
        cancellations = {}
        for name, module in modules.items():
            for kind in ("before", "timed"):
                record = run(module, path, cancel=kind)
                assert record["exception"] == "PipelineCancelled"
                assert record["sets"] == record["remaining_grab_state"] == 0
                if name == "after":
                    assert record["captures"] == record["releases"] == 1
                del record["rows"], record["markers"]
                cancellations[name + "/" + kind] = record
        result["clips"][clip] = dict(
            media_path=str(path), media_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            reference=reference, runs=records, cancellation=cancellations,
            median_seconds={name: statistics.median(r["seconds"] for r in records
                                                    if r["source"] == name and r["phase"] == "sample")
                            for name in modules})
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    result.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                  process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
