#!/usr/bin/env python3
"""Exercise pinned upstream load/write report projection with synthetic rows.

No renderer/runtime imports. This isolates the lossy projection used by the
render call chain; it is not an HTTP or actual video-render reproduction.
"""
import ast
from dataclasses import asdict, dataclass
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile

BASE = "5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f"


def main():
    source = subprocess.check_output(["git", "show", BASE + ":openscrub.py"], text=True)
    wanted = {"Detection", "load_report", "write_report"}
    nodes = [node for node in ast.parse(source).body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted]
    namespace = dict(dataclass=dataclass, asdict=asdict, datetime=datetime, json=json,
                     os=os, VERSION="audit-probe", _settings_dict=lambda _: {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), BASE, "exec"), namespace)
    rows = [dict(t_start=0, t_end=1, cbox=[i, 0, i+1, 1], category="manual",
                 text=f"synthetic-row-{i}", enabled=i != 1) for i in range(3)]
    doc = dict(provenance={"input_sha256": "synthetic-identity"},
               render_state=dict(fps=30, cum=[[0, 0]], bands=[[0, 0]]), detections=rows)
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory(prefix="openscrub-audit-report-") as directory:
        before = Path(directory) / "before.json"
        after = Path(directory) / "after.json"
        before.write_text(json.dumps(doc))
        detections, render_state, _ = namespace["load_report"](str(before))
        args = SimpleNamespace(video="synthetic-source.mp4")
        namespace["write_report"](str(after), args, dict(render_state, detections=detections))
        projected = json.loads(after.read_text())
    result = dict(base=BASE, evidence="source-isolated load_report/write_report projection; no video or HTTP",
                  original_rows=[dict(index=i, text=row["text"], enabled=row["enabled"]) for i, row in enumerate(rows)],
                  projected_rows=[dict(index=i, text=row["text"], enabled=row["enabled"]) for i, row in enumerate(projected["detections"])],
                  settings_shim="_settings_dict returns {}; irrelevant to row projection")
    assert len(projected["detections"]) == 2
    assert projected["detections"][1]["text"] == "synthetic-row-2"
    assert all(row["enabled"] for row in projected["detections"])
    Path(__file__).with_name("render-review-projection-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
