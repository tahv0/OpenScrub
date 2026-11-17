from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
p=root/'openscrub.py'
s=p.read_text()
a=s.index('def _blur_silhouette_yuv10(')
b=s.index('\n\ndef apply_coverage',a)
owner=s[a:b]
owner=owner.replace('    def _fill_masked(plane, px1, py1, px2, py2, black, kmin):', '''    # Align the existing luma mask to the frame's global 2x2 chroma grid.
    # A chroma cell is selected if any of its luma pixels are selected,
    # including odd ROI origins and the final partial row/column.
    cx1, cy1 = x1i // 2, y1i // 2
    cw, ch = (x2i + 1) // 2 - cx1, (y2i + 1) // 2 - cy1
    aligned = np.zeros((ch * 2, cw * 2), np.uint8)
    ox, oy = x1i % 2, y1i % 2
    aligned[oy:oy + rh, ox:ox + rw] = mask
    chroma_mask = aligned.reshape(ch, 2, cw, 2).max(axis=(1, 3))

    def _fill_masked(plane, px1, py1, px2, py2, black, kmin, m):''')
owner=owner.replace('''        m = mask
        if m.shape != roi.shape:            # chroma planes are half-res
            m = cv2.resize(mask, (roi.shape[1], roi.shape[0]),
                           interpolation=cv2.INTER_NEAREST)
        cv2.copyTo(filled, m, roi)''','''        cv2.copyTo(filled, m[:roi.shape[0], :roi.shape[1]], roi)''')
owner=owner.replace('x2i, y2i, 64, 31)', 'x2i, y2i, 64, 31, mask)')
owner=owner.replace('(y2i + 1) // 2), 512, 15)', '(y2i + 1) // 2), 512, 15, chroma_mask)')
assert 'INTER_NEAREST)\n        cv2.copyTo' not in owner
p.write_text(s[:a]+owner+s[b:])
p=root/'pyproject.toml'
s=p.read_text().replace('    "test_openscrub.py",\n]', '    "test_openscrub.py",\n    "tests/",\n    "CONTRIBUTING.md",\n]')
p.write_text(s)
p=root/'CONTRIBUTING.md'
s=p.read_text().replace('python -m pytest test_openscrub.py -q', 'python -m pytest -q')
s=s.replace('For web UI changes,', 'Full discovery includes `tests/`. The synthetic HDR encoder-input regressions\nrequire FFmpeg/ffprobe with libx265; they skip when these tools are unavailable.\n\nFor web UI changes,')
p.write_text(s)
p=root/'README.md'
s=p.read_text().replace('(`pytest test_openscrub.py`)', '(`python -m pytest -q`)')
p.write_text(s)
