#!/usr/bin/env python3
"""Compare complete modules' merge finalization, with inference excluded.

Run with --base-source DIR --head-source DIR --output FILE. Both directories
must contain complete source exports. Run alone, with no other owned runtime
work. Inputs are prepared outside timing. Work tracing and tracemalloc runs are
separate from timing. Five samples describe these fixtures, not a population.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import random
import resource
import statistics
import sys
import time
import tracemalloc

from rapidfuzz import fuzz
import cv2

CASES = [(100, 100, "unique"), (300, 300, "unique"),
         (10000, 30, "unique"), (1000, 1000, "repeated")]


def load(root, name):
    path = root.resolve() / "openscrub.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve() == path
    return module


def fixture(module, n, k, mode):
    scans, detections = [], []
    for i in range(n):
        rng = random.Random(83011 + (i if mode == "unique" else 0))
        text = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(24)) + "@sample.invalid"
        scans.append((i / 3, (0., 0.), [(text, (8, 8, 150, 28), .99)]))
        if i >= n - k:
            detections.append(module.Detection(i / 3, 0., (8, 8, 150, 28), "email", text, .99))
    return detections, scans


def execute(module, inputs):
    return module.merge_detections(inputs[0], .5, scans=inputs[1], fuzz=fuzz)


def records(result):
    return [asdict(d) for d in result]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def work(module, case):
    lines = Path(module.__file__).read_text().splitlines()
    markers = {
        "tail_timestamp_visits": "if st <= m.last_seen + 0.01:",
        "merge_candidate_visits": "if m.category != d.category or not boxes_overlap(m.cbox, d.cbox):",
        "index_entries": "tail_times.append(st)",
        "index_queries": "start = bisect_right(tail_times, m.last_seen + 0.01)",
    }
    by_line = {i + 1: key for key, text in markers.items()
               for i, line in enumerate(lines) if line.strip() == text}
    counts, index_bytes = Counter(), [0]
    inputs = fixture(module, *case)

    def trace(frame, event, arg):
        if frame.f_code is module.merge_detections.__code__ and event == "line":
            key = by_line.get(frame.f_lineno)
            if key:
                counts[key] += 1
            # List owns references to existing timestamp objects, no copies.
            if key == "index_queries":
                index_bytes[0] = max(index_bytes[0], sys.getsizeof(frame.f_locals["tail_times"]))
        return trace

    sys.settrace(trace)
    try:
        result = execute(module, inputs)
    finally:
        sys.settrace(None)
    inputs = fixture(module, *case)
    gc.collect()
    tracemalloc.start()
    execute(module, inputs)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(counts=counts, index_list_bytes=index_bytes[0],
                merge_traced_current_bytes=current, merge_traced_peak_bytes=peak,
                output_sha256=digest(records(result)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-source", type=Path, required=True)
    parser.add_argument("--head-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    modules = {"base": load(args.base_source, "tail_base"),
               "head": load(args.head_source, "tail_head")}
    cv2.setNumThreads(1)
    report = dict(environment=dict(python=sys.version, executable=sys.executable,
                                  platform=platform.platform(), opencv=cv2.__version__,
                                  cwd=str(Path.cwd()), opencv_threads=cv2.getNumThreads()),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  sources={name: dict(path=module.__file__, sha256=hashlib.sha256(
                      Path(module.__file__).read_bytes()).hexdigest()) for name, module in modules.items()},
                  warmups=3, samples=5, gc_enabled_during_timing=True, cases=[])
    for case in CASES:
        row = dict(scans=case[0], detections=case[1], mode=case[2], warmup_samples=[], samples=[], outputs={})
        expected = None
        for repetition in range(8):
            order = ["base", "head"] if repetition % 2 == 0 else ["head", "base"]
            sample = dict(repetition=repetition - 3, order=order, ns={}, output_sha256={})
            for name in order:
                inputs = fixture(modules[name], *case)
                assert gc.isenabled(), "Compare ordinary runtime with GC enabled"
                start = time.perf_counter_ns()
                result = execute(modules[name], inputs)
                elapsed = time.perf_counter_ns() - start
                output = records(result)
                if expected is None:
                    expected = output
                assert output == expected, (case, repetition, name)
                sample["ns"][name] = elapsed
                sample["output_sha256"][name] = digest(output)
                row["outputs"][name] = output
            if repetition >= 3:
                row["samples"].append(sample)
            else:
                row["warmup_samples"].append(sample)
        row["median_ns"] = {name: statistics.median(s["ns"][name] for s in row["samples"]) for name in modules}
        row["head_change_percent"] = 100 * (row["median_ns"]["head"] / row["median_ns"]["base"] - 1)
        report["cases"].append(row)
    # Finish ALL timed cases before any tracing or allocation instrumentation.
    for row, case in zip(report["cases"], CASES):
        row["work_and_memory"] = {name: work(module, case) for name, module in modules.items()}
    report["process_maxrss_kib_after_all_cases"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["memory_limit"] = "tracemalloc excludes native heaps; maxrss is whole-process cumulative high-water, not index attribution"
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for row in report["cases"]:
        print({k: v for k, v in row.items() if k not in ("outputs", "warmup_samples", "samples")})


if __name__ == "__main__":
    main()
