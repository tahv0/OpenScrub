# Source editing only.
from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub.py');s=p.read_text()
start=s.index('    try:\n',s.index('def _geometry_box('));end=s.index('    except (OverflowError, FloatingPointError):',start)
s=s[:start]+'    try:\n        with np.errstate(over="raise", invalid="raise"):\n'+''.join('    '+line if line.strip() else line for line in s[start+len('    try:\n'):end].splitlines(True))+s[end:]
helper='''def _geometry_bands(bx, by, w, h, margin, stage):
    try:
        with np.errstate(over="raise", invalid="raise"):
            boxes = []
            if by < -2:
                boxes.append((0, h - (abs(by) + margin), w, h))
            elif by > 2:
                boxes.append((0, 0, w, by + margin))
            if bx < -2:
                boxes.append((w - (abs(bx) + margin), 0, w, h))
            elif bx > 2:
                boxes.append((0, 0, bx + margin, h))
            for box in boxes:
                _geometry_finite(box, 4, stage, "band box")
    except (OverflowError, FloatingPointError):
        raise ValueError(f"render geometry {stage}: invalid band arithmetic") from None
    return boxes


'''
s=s.replace('def _geometry_metadata(',helper+'def _geometry_metadata(',1)
start=s.index('            px, py = 0.12 *');end=s.index('            new.append(',start)
s=s[:start]+'''            where = f"coverage detection {ordinals[id(ds[i])]}"
            try:
                with np.errstate(over="raise", invalid="raise"):
                    px, py = 0.12 * (x2 - x1), 0.12 * (y2 - y1)
                    expanded = (x1 - px, y1 - py, x2 + px, y2 + py)
                    _geometry_finite(expanded, 4, where, "expanded cbox")
            except (OverflowError, FloatingPointError):
                raise ValueError(f"render geometry {where}: invalid expanded cbox arithmetic") from None
''' + s[end:]
# Keep each path's existing band painter; share only the numeric boxes.
start=s.index('        if by < -2:',s.index('def render_hdr('));end=s.index('\n        try:\n            enc.stdin.write',start)
s=s[:start]+'''        for box in _geometry_bands(bx, by, w, h, band_margin, f"HDR frame {idx}"):
            band(*box)
''' + s[end:]
start=s.index('        if by < -2:',s.index('def render('));end=s.index('\n        if proc is not None:',start)
s=s[:start]+'''        for box in _geometry_bands(bx, by, w, h, band_margin, f"SDR frame {idx}"):
            band(*box)
''' + s[end:]
s=s.replace('            _geometry_finite((x1, y1_, x2, y2_), 4, f"HDR frame {idx}", "band box")\n','',1).replace('            _geometry_finite((x1, y1, x2, y2), 4, f"SDR frame {idx}", "band box")\n','',1)
p.write_text(s)
