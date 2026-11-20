"""Checkpoint frame bounds also constrain optional plate evidence."""

from dataclasses import asdict
import json

import numpy as np

import openscrub as core
from test_scan_frame_authority import Quiet, completed_report, decode_bgr, make_video


def test_bounded_lettering_row_retains_both_authorities_and_choices():
    frame = np.full((32, 64, 3), 200, np.uint8)
    base = core.Detection(0, 1, (4, 4, 60, 28), "plate", "plate", .9,
                          dense=True, track=1)
    polygon = (((.2, .2), (.8, .2), (.8, .8), (.2, .8)),)
    narrow = core._record_narrow_plate(base, 1, core._frame_sha256(frame), polygon, 0, "")
    row = asdict(narrow)
    row.update(enabled=False, output_choice="blur", scan_frame_start=1, scan_frame_end=2,
               policy_evidence={"origin": "detection", "frame": 1, "geometry_valid": True})
    doc = {"plate_policy_evidence_version": 1,
           "provenance": {"settings": {"uncertain_policy": "manual_review",
                                        "plate_threshold": .1, "plate_auto_cutoff": .8}},
           "render_state": {"fps": 2., "cum": [[0, 0]] * 3, "bands": [[0, 0]] * 3},
           "detections": [row]}
    loaded, _, _ = core._decode_report(doc)
    assert len(loaded) == 1  # explicit Blur remains authoritative
    item = loaded[0]
    assert core._narrow_plate_eligible(item, 1, frame)
    assert (item.scan_frame_start, item.scan_frame_end) == (1, 2)
    assert core._active_on_frame(item, .5, 1) and core._frame_authorized(item, 1)
    assert not core._frame_authorized(item, 0) and not core._frame_authorized(item, 2)

    doc["detections"][0]["output_choice"] = "keep"
    assert core._decode_report(doc)[0] == []
    doc["detections"][0]["output_choice"] = "blur"
    doc["detections"][0]["policy_evidence"]["geometry_valid"] = False
    assert core._decode_report(doc)[0] == []


def test_render_intersects_checkpoint_bounds_with_explicit_plate_choice(tmp_path):
    video = make_video(tmp_path)
    doc = completed_report(video)
    frame = decode_bgr(video)[5]
    base = core.Detection(0, 11 / 120, (5, 10, 55, 30), "plate", "plate", .9,
                          dense=True, track=1)
    polygon = (((.2, .2), (.8, .2), (.8, .8), (.2, .8)),)
    row = asdict(core._record_narrow_plate(base, 5, core._frame_sha256(frame), polygon, 0, ""))
    row.update(enabled=False, output_choice="blur", scan_frame_start=5, scan_frame_end=6,
               policy_evidence={"origin": "detection", "frame": 5, "geometry_valid": True})
    doc["plate_policy_evidence_version"] = 1
    doc["provenance"]["settings"] = {"uncertain_policy": "manual_review",
                                        "plate_threshold": .1, "plate_auto_cutoff": .8,
                                        "plate_coverage": "narrow"}
    doc["detections"] = [row]
    report = tmp_path / "report.json"

    def render(name):
        report.write_text(json.dumps(doc))
        args = core._prep_args(core.build_parser().parse_args([
            str(video), "--from-report", str(report), "--output", str(tmp_path / name),
            "--no-vfr-fix", "--encoder", "x264", "--mode", "box", "--pad", "0",
        ]), core.build_parser())
        core.run_pipeline(args, Quiet())
        return [frame[20, 20].mean() < 30 for frame in decode_bgr(args.output)]

    assert render("allowed.mp4") == [i == 5 for i in range(12)]
    row["scan_frame_start"], row["scan_frame_end"] = 6, 7
    assert render("outside-bound.mp4") == [False] * 12
    row["scan_frame_start"], row["scan_frame_end"] = 5, 6
    row["output_choice"] = "keep"
    assert render("keep.mp4") == [False] * 12
