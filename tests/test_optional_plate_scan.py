"""Opt-in plate decisions must survive the real scan/smoothing/render path."""

import json

import cv2
import numpy as np
import pytest

import openscrub as core


class Quiet(core.Callbacks):
    def log(self, message):
        pass


def clip(tmp_path):
    path = tmp_path / "frames.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"),
                             4., (160, 96))
    assert writer.isOpened()
    frame = np.full((96, 160, 3), 215, np.uint8)
    for _ in range(10):
        writer.write(frame)
    writer.release()
    return path


def scan(tmp_path, monkeypatch, policy):
    class Detector:
        INPUT = 640

        def __init__(self, *args, **kwargs):
            self.scores = iter([None, None, .9, None, .9, .3, .9, .9, None, None])

        def available(self):
            return True

        def find(self, frame, scale):
            score = next(self.scores)
            return [(30, 20, 100, 60, score)] if score is not None else []

    monkeypatch.setattr(core, "PlateDetector", Detector)
    path = clip(tmp_path)
    parser = core.build_parser()
    assert "--uncertain-policy" in parser._option_string_actions, "opt-in policy is not wired into scanning"
    optional = (["--uncertain-policy", policy, "--plate-auto-cutoff", ".8"]
                if policy not in (None, "off") else [])
    args = core._prep_args(parser.parse_args([
        str(path), "--categories", "plate", "--no-vfr-fix", "--tile", "off",
        "--plate-threshold", ".1", *optional, "--encoder", "x264", "--mode", "box",
        "--pad", "0", "--output", str(tmp_path / "initial.mp4"),
        "--report", str(tmp_path / "report.json")]), parser)
    if policy == "off":
        args.uncertain_policy = "off"
    state = core.run_scan(args, Quiet())
    return args, state


def masked_frames(path):
    cap = cv2.VideoCapture(str(path))
    result = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        result.append(float(frame[30:50, 45:85].mean()) < 20)
    cap.release()
    return result


@pytest.mark.parametrize("policy,expected", [
    ("manual_review", [False, False, False, False, True, False, False, True, False, False]),
    ("blur_candidates", [False, False, True, False, True, True, True, True, False, False]),
])
def test_source_frames_survive_smoothing_and_render_roundtrip(tmp_path, monkeypatch, policy, expected):
    args, state = scan(tmp_path, monkeypatch, policy)
    core.run_render(args, state, Quiet())
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["plate_policy_evidence_version"] == 1
    direct = [r for r in report["detections"]
              if r.get("policy_evidence", {}).get("origin") == "detection"]
    assert [r["policy_evidence"]["frame"] for r in direct] == [2, 4, 5, 6, 7]
    assert direct[0]["t_start"] < 2 / 4  # smoothing moved its start after evidence capture
    synthetic = [r for r in report["detections"]
                 if r.get("policy_evidence", {}).get("origin") != "detection"]
    assert synthetic and all(not r["enabled"] for r in synthetic)
    assert masked_frames(args.output) == expected

    parser = core.build_parser()
    reopened = core._prep_args(parser.parse_args([
        str(tmp_path / "frames.avi"), "--from-report", str(tmp_path / "report.json"),
        "--no-vfr-fix", "--encoder", "x264", "--mode", "box", "--pad", "0",
        "--output", str(tmp_path / "reopened.mp4")]), parser)
    core.run_pipeline(reopened, Quiet())
    assert masked_frames(reopened.output) == expected


def test_off_and_absent_produce_identical_stock_report_bytes(tmp_path, monkeypatch):
    base_args, base_state = scan(tmp_path, monkeypatch, None)
    base = core._report_document(base_args, base_state)
    off_args, off_state = scan(tmp_path, monkeypatch, "off")
    off = core._report_document(off_args, off_state)
    base["provenance"]["timestamp"] = off["provenance"]["timestamp"] = "fixed"
    assert json.dumps(base, indent=1).encode() == json.dumps(off, indent=1).encode()


def test_edited_span_can_remove_an_observation_from_output(tmp_path, monkeypatch):
    args, state = scan(tmp_path, monkeypatch, 'manual_review')
    for detection in state['detections']:
        evidence = getattr(detection, '_plate_policy_evidence', {})
        if evidence.get('frame') == 4:
            detection.t_start, detection.t_end = 1.6, 1.7
    core.run_render(args, state, Quiet())
    assert masked_frames(args.output) == [False, False, False, False, False,
                                          False, False, True, False, False]


def test_load_report_returns_only_effective_enabled_detections(tmp_path, monkeypatch):
    args, state = scan(tmp_path, monkeypatch, 'manual_review')
    core.run_render(args, state, Quiet())
    detections, _, _ = core.load_report(args.report)
    assert [d._plate_policy_evidence['frame'] for d in detections] == [4, 7]


def test_invalid_report_confidence_does_not_block_or_create_a_mask(tmp_path, monkeypatch):
    args, state = scan(tmp_path, monkeypatch, 'blur_candidates')
    core.run_render(args, state, Quiet())
    report = json.loads((tmp_path / 'report.json').read_text())
    row = next(r for r in report['detections']
               if r.get('policy_evidence', {}).get('frame') == 2)
    row['confidence'] = 10 ** 1000
    (tmp_path / 'report.json').write_text(json.dumps(report))
    parser = core.build_parser()
    reopened = core._prep_args(parser.parse_args([
        str(tmp_path / 'frames.avi'), '--from-report', args.report,
        '--no-vfr-fix', '--encoder', 'x264', '--mode', 'box', '--pad', '0',
        '--output', str(tmp_path / 'invalid.mp4')]), parser)
    core.run_pipeline(reopened, Quiet())
    assert masked_frames(reopened.output) == [False, False, False, False, True,
                                               True, True, True, False, False]


def test_off_capable_report_cannot_render_an_unsupported_gap(tmp_path, monkeypatch):
    args, state = scan(tmp_path, monkeypatch, 'manual_review')
    core.run_render(args, state, Quiet())
    report = json.loads((tmp_path / 'report.json').read_text())
    report['provenance']['settings']['uncertain_policy'] = 'off'
    row = next(r for r in report['detections']
               if r.get('policy_evidence', {}).get('frame') == 4)
    row.update(cbox=[0, 0, 0, 0], enabled=True, output_choice='blur')
    row['policy_evidence']['geometry_valid'] = False
    (tmp_path / 'report.json').write_text(json.dumps(report))
    parser = core.build_parser()
    reopened = core._prep_args(parser.parse_args([
        str(tmp_path / 'frames.avi'), '--from-report', args.report,
        '--no-vfr-fix', '--encoder', 'x264', '--mode', 'box', '--pad', '0',
        '--output', str(tmp_path / 'off-gap.mp4')]), parser)
    core.run_pipeline(reopened, Quiet())
    assert masked_frames(reopened.output) == [False, False, False, False, False,
                                               False, False, True, False, False]


def test_changed_source_turns_optional_plate_locations_into_gaps(tmp_path, monkeypatch):
    args, state = scan(tmp_path, monkeypatch, 'blur_candidates')
    core.run_render(args, state, Quiet())
    other = tmp_path / 'other.avi'
    writer = cv2.VideoWriter(str(other), cv2.VideoWriter_fourcc(*'FFV1'), 4., (160, 96))
    assert writer.isOpened()
    for _ in range(10):
        writer.write(np.full((96, 160, 3), 180, np.uint8))
    writer.release()
    parser = core.build_parser()
    reopened = core._prep_args(parser.parse_args([
        str(other), '--from-report', args.report, '--no-vfr-fix', '--encoder', 'x264',
        '--mode', 'box', '--pad', '0', '--output', str(tmp_path / 'other-out.mp4')]), parser)
    core.run_pipeline(reopened, Quiet())
    assert masked_frames(reopened.output) == [False] * 10
