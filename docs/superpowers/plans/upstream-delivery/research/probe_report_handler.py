"""Source-isolated research probe; not an application or HTTP integration test.

Run from the repository root. Extracts two functions from a pinned Git revision,
uses synthetic reports in a temporary directory, and prints JSON evidence.
No application imports, model downloads, dependency installs or live job access.
"""

import argparse
import ast
import copy
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace


def report(rows):
    return {
        "detections": [
            {
                "t_start": float(i), "t_end": float(i + 1),
                "cbox": [10, 10, 70, 30], "category": "plate",
                "text": "synthetic", "confidence": 0.8,
                "aoff": [0, 0], "last_seen": float(i), "enabled": True,
            }
            for i in range(rows)
        ],
        "render_state": {"fps": 30, "cum": [[0, 0]]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f")
    args = parser.parse_args()
    sha = subprocess.check_output(["git", "rev-parse", args.ref], text=True).strip()
    source = subprocess.check_output(["git", "show", sha + ":openscrub_web.py"], text=True)
    wanted = {"_load_job_report", "job_save_edits"}
    nodes = [copy.deepcopy(n) for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef) and n.name in wanted]
    if {n.name for n in nodes} != wanted:
        raise RuntimeError("Expected source functions not found")
    for node in nodes:
        node.decorator_list = []
    code = compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                   sha + ":openscrub_web.py", "exec")
    evidence = {"upstream_sha": sha, "python": platform.python_version(),
                "platform": platform.system(), "scope": "source-isolated handler; no HTTP, browser or video decoding"}

    with tempfile.TemporaryDirectory(prefix="openscrub-report-probe-") as directory:
        path = Path(directory) / "report.json"

        def write(doc):
            path.write_text(json.dumps(doc, indent=1), encoding="utf-8")

        def read():
            return json.loads(path.read_text(encoding="utf-8"))

        def namespace(payload, json_module=json):
            ns = {"os": os, "json": json_module,
                  "JOBS": {"probe": {"dir": directory}},
                  "request": SimpleNamespace(get_json=lambda **_: payload),
                  "jsonify": lambda value: value,
                  "abort": lambda status: (_ for _ in ()).throw(RuntimeError(status))}
            exec(code, ns)
            return ns

        timings = []
        for rows in (1000, 10000, 100000):
            doc = report(rows)
            samples = []
            for _ in range(3):
                write(doc)
                ns = namespace({"enabled": {"0": False}})
                start = time.perf_counter()
                ns["job_save_edits"]("probe")
                samples.append(time.perf_counter() - start)
            timings.append({"rows": rows, "report_bytes": path.stat().st_size,
                            "save_seconds": samples, "median_seconds": statistics.median(samples)})
        evidence["minimal_report_baseline"] = timings

        write(report(2))
        original = path.read_bytes()

        def fail_dump(document, stream, **kwargs):
            stream.write('{"detections": [')
            raise OSError("injected interrupted write")

        ns = namespace({"enabled": {"0": False}}, SimpleNamespace(load=json.load, dump=fail_dump))
        try:
            ns["job_save_edits"]("probe")
        except OSError:
            pass
        else:
            raise AssertionError("Write injection did not run")
        try:
            read()
            valid = True
        except json.JSONDecodeError:
            valid = False
        evidence["interrupted_write"] = {
            "previous_bytes_preserved": path.read_bytes() == original,
            "report_is_valid_json_after_failure": valid,
        }

        write(report(2))
        payload = {"manual": [{"t_start": 0, "t_end": 1, "t_ref": 0,
                              "screen_box": [10, 10, 70, 30]}]}
        ns = namespace(payload)
        ns["job_save_edits"]("probe")
        first_count = len(read()["detections"])
        ns["job_save_edits"]("probe")
        evidence["replayed_manual_save"] = {
            "initial_rows": 2, "rows_after_first": first_count,
            "rows_after_identical_retry": len(read()["detections"]),
        }

        write(report(2))
        barrier = threading.Barrier(2, timeout=5)
        first_finished = threading.Event()
        failures = []

        def save_worker(index):
            ns = namespace({"enabled": {str(index): False}})
            original_load = ns["_load_job_report"]

            def read_snapshot(job):
                snapshot = original_load(job)
                barrier.wait()
                if index == 1 and not first_finished.wait(5):
                    raise RuntimeError("First save did not complete")
                return snapshot

            ns["_load_job_report"] = read_snapshot
            try:
                ns["job_save_edits"]("probe")
            except Exception as error:
                failures.append(type(error).__name__ + ": " + str(error))
            finally:
                if index == 0:
                    first_finished.set()

        threads = [threading.Thread(target=save_worker, args=(i,)) for i in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        if failures or any(thread.is_alive() for thread in threads):
            raise RuntimeError(str(failures or "Thread did not complete"))
        evidence["overlapping_sparse_saves"] = {
            "expected_enabled": [False, False],
            "actual_enabled": [d["enabled"] for d in read()["detections"]],
            "schedule": "both read old report; save 0 completes; save 1 writes its snapshot",
        }
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
