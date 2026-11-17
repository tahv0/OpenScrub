from pathlib import Path
p=Path('tests/test_polygon_fallback.py');s=p.read_text().replace('def test_usable_contours_keep_baseline_pixels(', 'def test_usable_contours_keep_exact_combined_pixels(')
s=s.replace('            m = cv2.resize(mask, (6, 6), interpolation=cv2.INTER_NEAREST)', '''            # Enumerate global touched-luma cells independently of the
            # production aligned reduction; combined P16A owns HDR mapping.
            m = np.zeros((6, 6), np.uint8)
            for row, col in np.argwhere(mask):
                m[(4 + int(row)) // 2 - 2, (4 + int(col)) // 2 - 2] = 255''')
p.write_text(s)
p=Path('tests/test_batch_integration.py');s=p.read_text();s+='''

@pytest.mark.parametrize("path", ["sdr", "hdr"])
def test_combined_report_run_render_default_coverage_exact_input(path, tiny_media, tmp_path, monkeypatch):
    """Default tight orchestration must preserve A coverage and B fallback."""
    from test_polygon_fallback import observe_render, ffmpeg, BAD
    from test_hdr_chroma_coverage import _metadata, TAGS
    source = tiny_media[path]
    rows = []
    for box, category, poly, enabled in [
        ([4, 4, 16, 16], "person", [[(1/12, 1/12), (2/12, 1/12), (1/12, 2/12)]], True),
        ([24, 4, 36, 16], "person", BAD["missing_coordinate"], True),
        ([44, 4, 56, 16], "email", None, True),
        ([4, 32, 16, 44], "person", BAD["collinear"], False),
    ]:
        rows.append(dict(t_start=0, t_end=1, cbox=box, category=category,
                         text="", confidence=1, enabled=enabled, poly=poly))
    report = tmp_path / "combined.json"
    report.write_text(json.dumps(dict(detections=rows, render_state=dict(
        fps=2, cum=[[0, 0]] * 2, bands=[[0, 0]] * 2))))
    detections, state, _ = openscrub.load_report(str(report))
    assert len(detections) == 3
    state.update(detections=detections, stats={})
    output = tmp_path / "combined.mp4"
    # Parse ordinary CLI defaults: coverage remains tight, quality archival.
    args = openscrub.build_parser().parse_args([str(source), "--mode", "box", "--pad", "1"])
    assert args.coverage == "tight" and args.out_quality == "archival"
    args.output = str(output)
    args.report = None
    args.encoder = "x264"  # deterministic CPU environment, no platform probe claim
    if path == "hdr":
        args.hdr_source, args.hdr_encoder, args.hdr_tags = str(source), "libx265", TAGS
        raw = ffmpeg("-i", str(source), "-f", "rawvideo", "-pix_fmt", "yuv420p10le", "pipe:1")
        frames = np.frombuffer(raw, np.uint16).reshape(2, 6144).copy()
    else:
        cap = cv2.VideoCapture(str(source))
        try:
            frames = np.stack([cap.read()[1] for _ in range(2)])
        finally:
            cap.release()
    selected = {(y + dy, x + dx) for y, x in [(5, 5), (5, 6), (6, 5)]
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    selected |= {(y, x) for y in range(3, 17) for x in range(23, 37)}
    selected |= {(y, x) for y in range(3, 17) for x in range(43, 57)}
    for frame in frames:
        if path == "hdr":
            y, u, v = frame[:4096].reshape(64,64), frame[4096:5120].reshape(32,32), frame[5120:].reshape(32,32)
            for row, col in selected:
                y[row, col] = 64
                u[row//2, col//2] = v[row//2, col//2] = 512
        else:
            for row, col in selected:
                frame[row, col] = 0
    with observe_render(monkeypatch, path) as captured:
        openscrub.run_render(args, state)
        assert len(captured) == 2
        assert b"".join(captured) == frames.tobytes()  # exact unrelated/kept cells too
    meta = _metadata(output)
    assert (meta["width"], meta["height"], meta["nb_read_frames"]) == (64, 64, "2")
    assert meta["pix_fmt"] == ("yuv420p10le" if path == "hdr" else "yuv420p")
    if path == "hdr":
        assert {key: meta[key] for key in ("color_space", "color_transfer", "color_primaries")} == dict(
            color_space="bt2020nc", color_transfer="smpte2084", color_primaries="bt2020")
    assert output.stat().st_size > 0
    assert report.read_text()  # orchestration does not replace the raw input report
'''
s=s.replace('import numpy as np\n','import numpy as np\nimport pytest\nfrom test_polygon_fallback import tiny_media\n');p.write_text(s)
