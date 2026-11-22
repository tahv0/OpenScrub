"""Mode switch for the assisted plate-letters cover."""

import cv2
import numpy as np
import pytest

import openscrub


def test_assisted_needs_explicit_permission():
    parser = openscrub.build_parser()
    with pytest.raises(SystemExit):
        openscrub._prep_args(parser.parse_args(["x.mp4", "--plate-coverage", "assisted"]), parser)
    args = openscrub._prep_args(parser.parse_args(
        ["x.mp4", "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    assert args.plate_coverage == "assisted"
    settings = openscrub._settings_dict(args)
    assert settings["plate_coverage"] == "assisted"
    assert "no_box_fallback" not in settings and "plate_narrow_margin" not in settings


def test_full_and_narrow_settings_unchanged():
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(["x.mp4"]), parser)
    assert "plate_coverage" not in openscrub._settings_dict(args)
    narrow = openscrub._prep_args(parser.parse_args(
        ["x.mp4", "--plate-coverage", "narrow", "--plate-narrow-margin", "2"]), parser)
    settings = openscrub._settings_dict(narrow)
    assert settings["plate_coverage"] == "narrow" and settings["plate_narrow_margin"] == 2


def test_saved_assisted_survives_from_report_restore(tmp_path, monkeypatch):
    source = str(tmp_path / "original.mp4")
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 64))
    assert writer.isOpened()
    writer.write(np.full((64, 96, 3), 220, np.uint8))
    writer.release()
    parser = openscrub.build_parser()
    scan_args = openscrub._prep_args(parser.parse_args(
        [source, "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    row = openscrub.Detection(0, .1, (10, 10, 80, 50), "plate", "plate", 1)
    report = tmp_path / "report.json"
    openscrub.write_report(report, scan_args, {"fps": 10, "cum": [(0, 0)], "bands": [(0, 0)],
                                               "detections": [row]})
    output = str(tmp_path / "out.mp4")
    args = openscrub._prep_args(parser.parse_args(
        [source, "--from-report", str(report), "--mode", "box", "--pad", "0",
         "--encoder", "x264", "-o", output]), parser)
    assert not args.no_box_fallback  # a saved report must not need the flag
    # The coverage restore runs before encoding; stop there so no ffmpeg is needed.
    monkeypatch.setattr(openscrub, "_render_into", lambda *a, **k: None)
    openscrub.run_pipeline(args)
    assert args.plate_coverage == "assisted"
