"""Confidence decisions and pixel-bound lettering must compose."""

import json

import cv2
import numpy as np
import pytest

import openscrub as core


class Quiet(core.Callbacks):
    def log(self, message):
        pass


def samples(path):
    cap = cv2.VideoCapture(str(path))
    found = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # The first point lies within the plate but outside the lettering.
        found.append((int(frame[15, 15].mean()), int(frame[30, 45].mean())))
    cap.release()
    return found


@pytest.mark.parametrize("policy,enabled", [
    # Frames 1-2 support an automatic mask, which covers the whole track.
    ("manual_review", [True, True, True, True]),
    ("blur_candidates", [True, True, True, True]),
])
def test_confidence_and_lettering_scan_render_and_reopen(tmp_path, monkeypatch, policy, enabled):
    path = tmp_path / "input.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 4, (96, 64))
    assert writer.isOpened()
    for _ in range(4):
        writer.write(np.full((64, 96, 3), 220, np.uint8))
    writer.release()

    class Plate:
        INPUT = 640
        def __init__(self, *args, **kwargs):
            self.scores = iter((.3, .9, .9, .3))
        def available(self):
            return True
        def find(self, frame, scale):
            return [(10, 10, 80, 50, next(self.scores))]

    class Text:
        def __init__(self, *args, **kwargs):
            pass
        def available(self):
            return True
        def find_plate(self, frame, box):
            return [np.array([[30, 20], [60, 20], [60, 40], [30, 40]], np.float32)], ""

    monkeypatch.setattr(core, "PlateDetector", Plate)
    monkeypatch.setattr(core, "TextRegionDetector", Text)
    parser = core.build_parser()
    args = core._prep_args(parser.parse_args([
        str(path), "--categories", "plate", "--tile", "off", "--no-backtrack",
        "--plate-threshold", ".1", "--uncertain-policy", policy,
        "--plate-auto-cutoff", ".8", "--plate-coverage", "narrow",
        "--encoder", "x264", "--mode", "box", "--pad", "0",
        "--output", str(tmp_path / "initial.mp4"), "--report", str(tmp_path / "report.json"),
    ]), parser)
    state = core.run_scan(args, Quiet())
    core.run_render(args, state, Quiet())
    doc = json.loads((tmp_path / "report.json").read_text())
    direct = sorted((r for r in doc["detections"]
                     if r.get("policy_evidence", {}).get("origin") == "detection"),
                    key=lambda row: row["policy_evidence"]["frame"])
    assert [r["policy_evidence"]["frame"] for r in direct] == list(range(4))
    assert [r["enabled"] for r in direct] == enabled
    assert all(r["narrow_plate"]["frame_index"] == i for i, r in enumerate(direct))
    initial = samples(args.output)
    assert len(initial) == 4
    assert [inside < 50 for _, inside in initial] == enabled
    assert all(outside > 150 for outside, _ in initial)

    # A verified manual quad and the automatic lettering polygon remain
    # independent. At the inspected frame the explicit quad wins.
    facts = core.exact.probe_source(str(path))
    fps, cum, timeline = core.exact.timeline(doc, facts)
    direct[2]["output_choice"] = "blur"
    direct[2]["manual_plate_quad"] = core.plate_quad.make_record(
        [[65, 20], [75, 20], [75, 35], [65, 35]],
        {"index": 2, "timeline_eq": timeline}, doc["provenance"]["input_sha256"],
        fps, len(cum), facts)
    (tmp_path / "report.json").write_text(json.dumps(doc))
    quad_args = core._prep_args(parser.parse_args([
        str(path), "--from-report", args.report, "--encoder", "x264",
        "--mode", "box", "--pad", "0", "--output", str(tmp_path / "quad.mp4"),
    ]), parser)
    core.run_pipeline(quad_args, Quiet())
    cap = cv2.VideoCapture(quad_args.output)
    quad_frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        quad_frames.append(frame)
    cap.release()
    assert quad_frames[2][25, 70].mean() < 50
    assert quad_frames[2][30, 45].mean() > 150

    # Explicit choices supersede the policy, and a stale lettering proof falls
    # back to the full box. A Keep on one sample inside a masked track does not
    # uncover its frame: the previous sample's span still reaches it (as with
    # standard plates), and off its inspected frame that sample is a full box.
    direct[0]["output_choice"] = "blur"
    direct[2]["output_choice"] = "keep"
    direct[2].pop("manual_plate_quad")
    direct[0]["narrow_plate"]["frame_sha256"] = "0" * 64
    (tmp_path / "report.json").write_text(json.dumps(doc))
    reopened = core._prep_args(parser.parse_args([
        str(path), "--from-report", args.report, "--encoder", "x264",
        "--mode", "box", "--pad", "0", "--output", str(tmp_path / "reopened.mp4"),
    ]), parser)
    core.run_pipeline(reopened, Quiet())
    actual = samples(reopened.output)
    assert [inside < 50 for _, inside in actual] == [True, True, True, True]
    assert actual[0][0] < 50
    assert actual[2][0] < 50
