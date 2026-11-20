"""Safety and localization coverage for optional lettering-only plates."""

import cv2
import numpy as np

import openscrub


def test_guard_preserves_disconnected_letter_regions():
    crop = np.full((80, 220, 3), 240, np.uint8)
    for x in (35, 145):
        cv2.rectangle(crop, (x, 25), (x + 20, 55), (20, 20, 20), -1)
    probability = np.zeros((80, 220), np.float32)
    probability[27:54, 37:54] = .9
    probability[27:54, 147:164] = .9

    polygons, reason = openscrub._narrow_from_probability(crop, probability)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.rint(p).astype(np.int32) for p in polygons], 1)
    assert reason == ""
    assert len(polygons) == 2
    assert mask[40, 45] and mask[40, 155]
    assert not mask[40, 105]


def test_guard_rejects_low_contrast_and_uncovered_letters():
    crop = np.full((80, 220, 3), 240, np.uint8)
    probability = np.zeros((80, 220), np.float32)
    probability[27:54, 37:54] = .9
    assert openscrub._narrow_from_probability(crop, probability)[1] == 'unverifiable_contrast'
    for x in (35, 145):
        cv2.rectangle(crop, (x, 25), (x + 20, 55), (20, 20, 20), -1)
    assert openscrub._narrow_from_probability(crop, probability)[1] == 'residual_text_evidence'


def test_guard_keeps_distinct_rows_and_hyphen():
    crop = np.full((100, 240, 3), 240, np.uint8)
    prob = np.zeros((100, 240), np.float32)
    for x1, y1, x2, y2 in ((40, 20, 60, 45), (80, 29, 91, 33),
                            (110, 20, 130, 45), (55, 65, 68, 80)):
        cv2.rectangle(crop, (x1, y1), (x2, y2), (20, 20, 20), -1)
        prob[y1+1:y2, x1+1:x2] = .9
    polygons, reason = openscrub._narrow_from_probability(crop, prob)
    assert reason == '' and len(polygons) == 4


def test_plate_localization_missing_model_and_clipped_crop():
    detector = openscrub.TextRegionDetector.__new__(openscrub.TextRegionDetector)
    detector.sess = None
    frame = np.full((80, 220, 3), 240, np.uint8)
    assert detector.find_plate(frame, (10, 10, 180, 70))[1] == 'model_unavailable'
    assert detector.find_plate(frame, (-1, 10, 180, 70))[1] == 'invalid_crop'
    assert detector.find_plate(frame, (float('nan'), 10, 180, 70))[1] == 'invalid_crop'


def test_corrupt_cached_text_model_disables_narrow_localization(tmp_path, monkeypatch):
    (tmp_path / 'text_detection_ppocrv5_mobile.onnx').write_bytes(b'x' * 10001)
    monkeypatch.setattr(openscrub, '_model_dir', lambda: str(tmp_path))
    detector = openscrub.TextRegionDetector(verify_hash=True)
    frame = np.full((60, 120, 3), 240, np.uint8)
    assert not detector.available()
    assert detector.find_plate(frame, (10, 10, 100, 50))[1] == 'model_unavailable'


def test_narrow_geometry_requires_same_frame_and_unmodified_geometry():
    frame = np.full((50, 100, 3), 230, np.uint8)
    frame[20:30, 35:45] = 20
    polygon = (((.25, .25), (.75, .25), (.75, .75), (.25, .75)),)
    base = openscrub.Detection(0, .04, (20, 10, 60, 40), 'plate', 'plate', 1, dense=True, track=2)
    row = openscrub._record_narrow_plate(base, 0, openscrub._frame_sha256(frame), polygon, 1.5, '')
    assert openscrub._narrow_plate_eligible(row, 0, frame)
    assert not openscrub._narrow_plate_eligible(row, 1, frame)
    changed = frame.copy()
    changed[0, 0] = 1
    assert not openscrub._narrow_plate_eligible(row, 0, changed)
    row.cbox = (21, 10, 61, 40)
    assert not openscrub._narrow_plate_eligible(row, 0, frame)


def test_report_roundtrip_preserves_narrow_frame_evidence_without_changing_full_rows():
    from dataclasses import asdict
    frame = np.full((50, 100, 3), 230, np.uint8)
    poly = (((.2, .2), (.8, .2), (.8, .8), (.2, .8)),)
    plain = openscrub.Detection(0, .1, (20, 10, 60, 40), 'plate', 'plate', 1)
    row = openscrub._record_narrow_plate(plain, 0, openscrub._frame_sha256(frame), poly, 0, '')
    loaded, _, _ = openscrub._decode_report([asdict(row), asdict(plain)])
    assert openscrub._narrow_plate_eligible(loaded[0], 0, frame)
    assert 'narrow_plate' not in asdict(loaded[1])


def test_interpolated_plate_samples_do_not_inherit_text_polygon():
    frame = np.full((50, 100, 3), 230, np.uint8)
    poly = (((.2, .2), (.8, .2), (.8, .8), (.2, .8)),)
    rows = []
    for i in (0, 3):
        base = openscrub.Detection(i/30, i/30, (10+i, 10, 50+i, 40), 'plate', 'plate', 1, dense=True, track=2)
        rows.append(openscrub._record_narrow_plate(base, i, openscrub._frame_sha256(frame), poly, 0, ''))
    openscrub.smooth_dense_tracks(rows, 30, None)
    assert len(rows) > 2
    assert all(not row.poly for row in rows[2:])


def test_encoded_render_uses_full_plate_when_frame_evidence_is_stale(tmp_path):
    source = str(tmp_path / 'source.mp4')
    output = str(tmp_path / 'output.mp4')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'mp4v'), 10, (96, 64))
    assert writer.isOpened()
    for level in (220, 210):
        image = np.full((64, 96, 3), level, np.uint8)
        cv2.rectangle(image, (34, 25), (54, 35), (20, 20, 20), -1)
        writer.write(image)
    writer.release()
    cap = cv2.VideoCapture(source)
    ok, inspected = cap.read()
    assert ok
    cap.release()
    poly = (((.25, .25), (.75, .25), (.75, .75), (.25, .75)),)
    base = openscrub.Detection(0, .1, (10, 10, 80, 50), 'plate', 'plate', 1)
    row = openscrub._record_narrow_plate(base, 0, openscrub._frame_sha256(inspected), poly, 0, '')
    openscrub.render(source, output, [row], [(0, 0)] * 2, [(0, 0)] * 2,
                     10, 0, 'box', False, encoder='x264')
    cap = cv2.VideoCapture(output)
    ok0, first = cap.read()
    ok1, second = cap.read()
    cap.release()
    assert ok0 and ok1
    assert first[20, 20].mean() > 150  # inside full box, outside lettering
    assert first[30, 45].mean() < 50
    assert second[20, 20].mean() < 50  # stale polygon must become full box


def test_cli_defaults_preserve_ordinary_report_settings_and_validate_margin():
    import pytest
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(['input.mp4']), parser)
    assert args.plate_coverage == 'full'
    settings = openscrub._settings_dict(args)
    assert 'plate_coverage' not in settings and 'plate_narrow_margin' not in settings
    narrow = openscrub._prep_args(parser.parse_args(['input.mp4', '--plate-coverage', 'narrow', '--plate-narrow-margin', '1.5']), parser)
    assert (narrow.plate_coverage, narrow.plate_narrow_margin) == ('narrow', 1.5)
    for value in ('-1', 'nan', 'inf'):
        with pytest.raises(SystemExit):
            openscrub._prep_args(parser.parse_args(['input.mp4', '--plate-narrow-margin', value]), parser)


def test_narrow_scan_localizes_each_detected_native_frame(tmp_path, monkeypatch):
    source = str(tmp_path / 'scan.mp4')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'mp4v'), 10, (96, 64))
    assert writer.isOpened()
    for i in range(4):
        image = np.full((64, 96, 3), 220 - i * 10, np.uint8)
        cv2.rectangle(image, (34, 25), (54, 35), (20, 20, 20), -1)
        writer.write(image)
    writer.release()
    class Plate:
        INPUT = 640
        def __init__(self, *a, **kw): pass
        def available(self): return True
        def find(self, frame, scale):
            assert frame.shape == (64, 96, 3) and scale == 1.0
            return [(10, 10, 80, 50, .9)]
    class Text:
        def __init__(self, *a, **kw): pass
        def available(self): return True
        def find_plate(self, frame, box):
            return [np.array([[30, 20], [60, 20], [60, 40], [30, 40]], np.float32)], ''
    monkeypatch.setattr(openscrub, 'PlateDetector', Plate)
    monkeypatch.setattr(openscrub, 'TextRegionDetector', Text)
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args([source, '--categories', 'plate', '--plate-coverage', 'narrow', '--scan-speed', 'fastest', '--tile', 'off', '--no-backtrack']), parser)
    state = openscrub.run_scan(args)
    detected = [d for d in state['detections'] if isinstance(d, openscrub.NarrowPlateDetection) and d.poly]
    assert [d.narrow_plate['frame_index'] for d in detected] == [0, 1, 2, 3]
    cap = cv2.VideoCapture(source)
    for index, row in enumerate(detected):
        ok, frame = cap.read()
        assert ok and openscrub._narrow_plate_eligible(row, index, frame)
    cap.release()


def test_narrow_report_records_model_fallback(tmp_path):
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(['input.mp4', '--plate-coverage', 'narrow']), parser)
    frame = np.zeros((50, 100, 3), np.uint8)
    base = openscrub.Detection(0, 0, (10, 10, 70, 40), 'plate', 'plate', 1)
    row = openscrub._record_narrow_plate(base, 0, openscrub._frame_sha256(frame), (), 0, 'model_unavailable')
    doc = openscrub._report_document(args, {'fps': 30, 'cum': [(0, 0)], 'bands': [(0, 0)], 'detections': [row]})
    assert doc['plate_fallbacks'] == {'model_unavailable': 1}
    assert doc['provenance']['settings']['plate_coverage'] == 'narrow'
    assert doc['detections'][0]['narrow_plate']['fallback'] == 'model_unavailable'


def test_explicit_full_coverage_overrides_a_narrow_report(tmp_path):
    import json
    source = str(tmp_path / 'original.mp4')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'mp4v'), 10, (96, 64))
    assert writer.isOpened()
    writer.write(np.full((64, 96, 3), 220, np.uint8))
    writer.release()
    cap = cv2.VideoCapture(source)
    ok, frame = cap.read()
    cap.release()
    assert ok
    poly = (((.25, .25), (.75, .25), (.75, .75), (.25, .75)),)
    base = openscrub.Detection(0, .1, (10, 10, 80, 50), 'plate', 'plate', 1)
    row = openscrub._record_narrow_plate(base, 0, openscrub._frame_sha256(frame), poly, 0, '')
    parser = openscrub.build_parser()
    scan_args = openscrub._prep_args(parser.parse_args([source, '--plate-coverage', 'narrow']), parser)
    report = tmp_path / 'report.json'
    openscrub.write_report(report, scan_args, {'fps': 10, 'cum': [(0, 0)], 'bands': [(0, 0)], 'detections': [row]})
    output = str(tmp_path / 'full.mp4')
    args = openscrub._prep_args(parser.parse_args([source, '--from-report', str(report), '--plate-coverage', 'full', '--mode', 'box', '--pad', '0', '--encoder', 'x264', '-o', output]), parser)
    openscrub.run_pipeline(args)
    cap = cv2.VideoCapture(output)
    ok, result = cap.read()
    cap.release()
    assert ok and result[20, 20].mean() < 50


def test_frame_boundary_plate_is_treated_as_potentially_clipped():
    detector = openscrub.TextRegionDetector.__new__(openscrub.TextRegionDetector)
    detector.sess = None
    frame = np.full((80, 220, 3), 240, np.uint8)
    for box in ((0, 10, 100, 70), (10, 0, 100, 70), (10, 10, 220, 70), (10, 10, 100, 80)):
        assert detector.find_plate(frame, box)[1] == 'invalid_crop'


def test_narrow_report_with_vfr_bypass_uses_full_boxes(tmp_path):
    source = str(tmp_path / 'original.mp4')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'mp4v'), 10, (96, 64))
    assert writer.isOpened()
    writer.write(np.full((64, 96, 3), 220, np.uint8))
    writer.release()
    cap = cv2.VideoCapture(source)
    ok, frame = cap.read()
    cap.release()
    assert ok
    poly = (((.25, .25), (.75, .25), (.75, .75), (.25, .75)),)
    base = openscrub.Detection(0, .1, (10, 10, 80, 50), 'plate', 'plate', 1)
    row = openscrub._record_narrow_plate(base, 0, openscrub._frame_sha256(frame), poly, 0, '')
    parser = openscrub.build_parser()
    scan_args = openscrub._prep_args(parser.parse_args([source, '--plate-coverage', 'narrow']), parser)
    report = tmp_path / 'report.json'
    openscrub.write_report(report, scan_args, {'fps': 10, 'cum': [(0, 0)], 'bands': [(0, 0)], 'detections': [row]})
    output = str(tmp_path / 'bypassed.mp4')
    args = openscrub._prep_args(parser.parse_args([source, '--from-report', str(report), '--vfr', 'ignore', '--mode', 'box', '--pad', '0', '--encoder', 'x264', '-o', output]), parser)
    openscrub.run_pipeline(args)
    cap = cv2.VideoCapture(output)
    ok, result = cap.read()
    cap.release()
    assert ok and result[20, 20].mean() < 50


def test_scan_hashes_once_only_for_frames_with_accepted_polygons(tmp_path, monkeypatch):
    source = str(tmp_path / 'two-plates.mp4')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'mp4v'), 10, (160, 80))
    assert writer.isOpened()
    for _ in range(2):
        writer.write(np.full((80, 160, 3), 220, np.uint8))
    writer.release()
    class Plate:
        INPUT = 640
        def __init__(self, *a, **kw): pass
        def available(self): return True
        def find(self, frame, scale): return [(10, 10, 70, 70, .9), (90, 10, 150, 70, .9)]
    class Text:
        fallback = False
        def __init__(self, *a, **kw): pass
        def available(self): return True
        def find_plate(self, frame, box):
            if self.fallback:
                return [], 'model_unavailable'
            x, y = box[:2]
            return [np.array([[x+10,y+10], [x+30,y+10], [x+30,y+30], [x+10,y+30]])], ''
    monkeypatch.setattr(openscrub, 'PlateDetector', Plate)
    monkeypatch.setattr(openscrub, 'TextRegionDetector', Text)
    actual_hash = openscrub._frame_sha256
    calls = []
    def counted(frame):
        calls.append(frame.shape)
        return actual_hash(frame)
    monkeypatch.setattr(openscrub, '_frame_sha256', counted)
    parser = openscrub.build_parser()
    def scan(extra):
        args = openscrub._prep_args(parser.parse_args([source, '--categories', 'plate', '--tile', 'off', '--no-backtrack', *extra]), parser)
        return openscrub.run_scan(args)
    scan(['--plate-coverage', 'narrow'])
    assert len(calls) == 2  # one per source frame, not one per plate
    calls.clear()
    Text.fallback = True
    scan(['--plate-coverage', 'narrow'])
    assert not calls
    scan([])
    assert not calls


def test_real_stock_detector_and_encoded_video(tmp_path, monkeypatch):
    """Optional local integration: real PP-OCR detector, native scan and encode."""
    import os
    import time
    import pytest
    model_dir = os.environ.get('OPENSCRUB_TEST_PPDET_DIR')
    if not model_dir:
        pytest.skip('set OPENSCRUB_TEST_PPDET_DIR to the stock PP-OCRv5 model directory')
    ort = pytest.importorskip('onnxruntime')
    monkeypatch.setattr(openscrub, '_model_dir', lambda: model_dir)
    def real_session(path):
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        return ort.InferenceSession(path, sess_options=options, providers=['CPUExecutionProvider'])
    monkeypatch.setattr(openscrub, '_ort_session', real_session)
    class Plate:
        INPUT = 640
        def __init__(self, *a, **kw): pass
        def available(self): return True
        def find(self, frame, scale): return [(32, 24, 288, 120, .95)]
    monkeypatch.setattr(openscrub, 'PlateDetector', Plate)
    source = str(tmp_path / 'stock-input.mp4')
    output = str(tmp_path / 'stock-output.mp4')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 144))
    assert writer.isOpened()
    for _ in range(3):
        frame = np.full((144, 320, 3), 90, np.uint8)
        frame[24:120, 32:288] = 236
        text = 'QZ 27 KTX'
        (width, height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.3, 2)
        cv2.putText(frame, text, (32+(256-width)//2, 24+(96+height)//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, (18, 18, 18), 2, cv2.LINE_AA)
        writer.write(frame)
    writer.release()
    parser = openscrub.build_parser()
    def args_for(coverage):
        return openscrub._prep_args(parser.parse_args([source, '--categories', 'plate',
            '--plate-coverage', coverage, '--tile', 'off', '--no-backtrack',
            '--mode', 'box', '--pad', '0', '--encoder', 'x264', '-o', output]), parser)
    full_args = args_for('full')
    start = time.perf_counter()
    openscrub.run_scan(full_args)
    full_seconds = time.perf_counter() - start
    args = args_for('narrow')
    start = time.perf_counter()
    state = openscrub.run_scan(args)
    narrow_seconds = time.perf_counter() - start
    rows = [d for d in state['detections'] if isinstance(d, openscrub.NarrowPlateDetection)]
    assert len(rows) == 3 and any(d.poly for d in rows)
    fallback_count = sum(not d.poly for d in rows)
    cap = cv2.VideoCapture(source)
    inspected = []
    for index, row in enumerate(rows):
        ok, frame = cap.read()
        assert ok
        mask = np.zeros(frame.shape[:2], np.uint8)
        if row.poly:
            assert openscrub._narrow_plate_eligible(row, index, frame)
            pts = [np.rint(np.array(p) * [256, 96] + [32, 24]).astype(np.int32) for p in row.poly]
            cv2.fillPoly(mask, pts, 1)
        else:
            assert row.narrow_plate['fallback']
            mask[24:120, 32:288] = 1
        strong = cv2.cvtColor(frame[24:120, 32:288], cv2.COLOR_BGR2GRAY) < 80
        assert strong.sum() > 100
        assert not np.any(strong & (mask[24:120, 32:288] == 0))
        inspected.append((frame, mask))
    cap.release()
    start = time.perf_counter()
    openscrub.run_render(args, state)
    render_seconds = time.perf_counter() - start
    cap = cv2.VideoCapture(output)
    for original, mask in inspected:
        ok, rendered = cap.read()
        assert ok
        original_gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        rendered_gray = cv2.cvtColor(rendered, cv2.COLOR_BGR2GRAY)
        inside = (mask == 1) & (original_gray > 180)
        outside = np.zeros(mask.shape, bool)
        outside[30:114, 38:282] = True
        outside &= (mask == 0) & (original_gray > 180)
        assert inside.sum() > 100
        assert np.median(rendered_gray[inside]) < 50
        if outside.any():
            assert np.median(rendered_gray[outside]) > 150
    cap.release()
    print('synthetic 3-frame wall time: full scan %.3fs; narrow scan %.3fs; narrow encode %.3fs; fallbacks %d/3' %
          (full_seconds, narrow_seconds, render_seconds, fallback_count))


def test_default_render_preserves_existing_plate_polygon(tmp_path, monkeypatch):
    source = str(tmp_path / "original.mp4")
    output = str(tmp_path / "rendered.mp4")
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 64))
    assert writer.isOpened()
    writer.write(np.full((64, 96, 3), 220, np.uint8))
    writer.release()

    def unexpected_hash(frame):
        raise AssertionError("an existing plate polygon does not require a pixel hash")

    monkeypatch.setattr(openscrub, "_frame_sha256", unexpected_hash)
    row = openscrub.Detection(
        0, .1, (10, 10, 80, 50), "plate", "plate", 1,
        poly=(((.25, .25), (.75, .25), (.75, .75), (.25, .75)),),
    )
    parser = openscrub.build_parser()
    args = openscrub._prep_args(
        parser.parse_args([source, "--mode", "box", "--pad", "0",
                           "--encoder", "x264", "-o", output]),
        parser,
    )
    state = {"fps": 10, "cum": [(0, 0)], "bands": [(0, 0)],
             "detections": [row], "stats": {}}
    openscrub.run_render(args, state)
    reader = cv2.VideoCapture(output)
    try:
        ok, rendered = reader.read()
        assert ok
        assert rendered[20, 20].mean() > 150
        assert rendered[30, 45].mean() < 50
    finally:
        reader.release()
