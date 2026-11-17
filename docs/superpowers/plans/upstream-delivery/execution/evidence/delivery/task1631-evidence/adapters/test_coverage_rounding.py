"""Public-boundary compatibility control for rounded empty coverage results."""
from types import SimpleNamespace
import cv2
import numpy as np
import openscrub as o
import pytest


@pytest.mark.parametrize("pad", [0, 1])
def test_concealed_tiny_positive_source(tmp_path, monkeypatch, pad):
    source = str(tmp_path / 'source.avi')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'MJPG'), 1, (16, 16))
    assert writer.isOpened()
    writer.write(np.full((16, 16, 3), 200, np.uint8)); writer.release()
    monkeypatch.setattr(o, 'nvenc_available', lambda *a: None)
    painted = []
    paint = o.blur_region
    def observe(frame, x1, y1, x2, y2, *a, **kw):
        painted.append((x1, y1, x2, y2))
        return paint(frame, x1, y1, x2, y2, *a, **kw)
    monkeypatch.setattr(o, 'blur_region', observe)
    d = o.Detection(0, 0, (.1, .1, .2, .2), 'person', '', 1, dense=True, track=1)
    assert o.apply_coverage([d], 'concealed')[0].cbox == (0, 0, 0, 0)
    state = dict(detections=[d], cum=[(0, 0)], bands=[(0, 0)], fps=1, stats={})
    args = SimpleNamespace(output=str(tmp_path / 'out.avi'), video=source,
                           preview=False, report=None, pad=pad, mode='box',
                           encoder='cpu', coverage='concealed')
    o.run_render(args, state)
    assert painted == [(-pad, -pad, pad, pad)]
