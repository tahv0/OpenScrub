"""Tail coverage controls against the complete active engine (no old checkout)."""
from dataclasses import asdict
from decimal import Decimal
import json

import cv2
import numpy as np
import pytest
from rapidfuzz import fuzz

import openscrub as core

BOX = (8, 8, 150, 28)
TEXT = "alice@example.invalid"


def detection(t=0., **fields):
    return core.Detection(t, 99., BOX, "email", TEXT, .91,
                          aoff=(2., 3.), track=7, person=4,
                          poly=((.1, .2),), **fields)


def record(start=0., end=.5, seen=0., **fields):
    return dict(t_start=start, t_end=end, cbox=BOX, category="email",
                text=TEXT, confidence=.91, aoff=(2., 3.), last_seen=seen,
                dense=False, track=7, person=4, poly=((.1, .2),), **fields)


def scan(t, text=TEXT, confidence=.99, box=BOX):
    return (t, (0., 0.), [(text, box, confidence)])


def merge(dets, scans, **kwargs):
    return [asdict(d) for d in core.merge_detections(
        dets, .5, scans=scans, fuzz=fuzz, **kwargs)]


@pytest.mark.parametrize("history,end,seen", [
    ([scan(0), scan(.5), scan(1)], 1.5, 1),
    ([scan(.01, "different"), scan(.5)], 1., .5),
    ([scan(.5), scan(.5, "different"), scan(.51, "different"), scan(1)], 1.5, 1),
    ((scan(.5), scan(1)), 1.5, 1),
    (iter([scan(.5), scan(1)]), 1.5, 1),
    ([scan(.5), scan(1, "different"), ("invalid",)], 1., .5),
    ([scan(.5), scan(1, "different"), scan(1.5)], 1., .5),
    ([scan(.5, confidence=.49), scan(1)], .5, 0.),
    ([scan(.5, confidence=.5), scan(1, box=(500, 500, 550, 520))], 1., .5),
    ([scan(4.), scan(8.), scan(12.01)], 8.5, 8.),
    # Caller order is meaningful: the earlier contradictory row is skipped
    # after support at 2 advances last_seen, so sorting would lose coverage.
    ([scan(2), scan(1, "different"), scan(3)], 3.5, 3),
    ([(np.float64(.5), (0., 0.), [])], .5, 0.),
    ([(float("nan"), (0., 0.), []), scan(.5)], .5, 0.),
])
def test_tail_records_preserve_support_boundaries_and_caller_order(history, end, seen):
    # The second independent region makes this exercise shared history too.
    other = core.Detection(0., 99., (500, 500, 550, 520), "phone", "5551234567", .8)
    assert merge([detection(), other], history) == [
        record(end=end, seen=seen),
        dict(t_start=0., t_end=.5, cbox=(500, 500, 550, 520),
             category="phone", text="5551234567", confidence=.8,
             aoff=(0., 0.), last_seen=0., dense=False, track=-1, person=-1, poly=()),
    ]


def test_repeated_detections_keep_first_record_and_extend_later_support():
    assert merge([detection(), detection(1.)], [scan(0.), scan(1.), scan(1.5)]) == [
        record(end=2., seen=1.5)]


@pytest.mark.parametrize("history,error", [
    ([(None, (0., 0.), [])], TypeError),
    ([(Decimal(".5"), (0., 0.), [])], TypeError),
    ([("later", (0., 0.), [])], TypeError),
    ([(0., (0., 0.))], ValueError),
])
def test_malformed_history_keeps_existing_failure(history, error):
    with pytest.raises(error):
        merge([detection(), core.Detection(1., 99., BOX, "phone", "5551234567", .8)], history)


def test_empty_and_no_tail_paths_do_not_inspect_history():
    assert merge([], [("invalid",)]) == []
    dense = detection(dense=True)
    assert merge([dense], [("invalid",)]) == [dict(record(end=99.), dense=True)]
    assert merge([detection()], []) == [record()]
    assert [asdict(d) for d in core.merge_detections(
        [detection()], .5, scans=[("invalid",)], fuzz=None)] == [record()]


def test_run_scan_finalization_and_report_with_controlled_ocr(tmp_path, monkeypatch):
    """Real decoding, forward/reverse recall, merge, and report; OCR is controlled."""
    clip = tmp_path / "fixed.avi"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"FFV1"), 6., (160, 96))
    assert writer.isOpened()
    frame = np.random.default_rng(1411).integers(0, 256, (96, 160, 3), dtype=np.uint8)
    for _ in range(8):
        writer.write(frame)
    writer.release()

    class OCR:
        calls = 0
        def read(self, image):
            self.calls += 1
            return [(TEXT, BOX, .99), ("bob@example.invalid", (8, 65, 150, 85), .99),
                    ("ready", (85, 40, 150, 60), .99)]

    ocr = OCR()
    monkeypatch.setattr(core, "make_ocr", lambda *args, **kwargs: ocr)
    parser = core.build_parser()
    args = core._prep_args(parser.parse_args([
        str(clip), "--categories", "email", "--engine", "tesseract",
        "--sample-interval", "0.3333333333333333", "--scroll-track", "off",
        "--adaptive", "off", "--ocr-upscale", "off", "--no-vfr-fix", "--no-backtrack",
    ]), parser)
    state = core.run_scan(args, core.Callbacks())
    assert ocr.calls == state["stats"]["scans"] == 4
    expected = dict(t_start=0., t_end=1.6333333333333333, cbox=BOX, category="email", text=TEXT,
                    confidence=.99, aoff=(0., 0.), last_seen=1., dense=False,
                    track=-1, person=-1, poly=())
    expected_records = [expected, dict(expected, text="bob@example.invalid", cbox=(8, 65, 150, 85))]
    assert [asdict(d) for d in state["detections"]] == expected_records
    report = tmp_path / "report.json"
    core.write_report(str(report), args, state)
    doc = json.loads(report.read_text())
    assert doc["detections"] == json.loads(json.dumps([dict(d, enabled=True) for d in expected_records]))
    assert doc["render_state"]["cum"] == [[round(x, 1), round(y, 1)] for x, y in state["cum"]]
