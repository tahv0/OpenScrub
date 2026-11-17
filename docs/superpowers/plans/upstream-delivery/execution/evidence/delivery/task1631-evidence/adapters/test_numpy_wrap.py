"""External owning baseline/candidate control, no dependence on new helpers."""
import warnings
import cv2
import numpy as np
import pytest
import openscrub as o


def test_numpy_wrap_actual_frame(tmp_path, monkeypatch):
    source = str(tmp_path / 'source.avi')
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'MJPG'), 1, (16, 16))
    assert writer.isOpened()
    writer.write(np.full((16, 16, 3), 200, np.uint8)); writer.release()
    monkeypatch.setattr(o, 'nvenc_available', lambda *a: None)
    captures, writers = [], []
    capture, writer_type = o.cv2.VideoCapture, o.cv2.VideoWriter
    def cap(*a):
        result = capture(*a); captures.append(result); return result
    def sink(*a):
        result = writer_type(*a); writers.append(result); return result
    monkeypatch.setattr(o.cv2, 'VideoCapture', cap)
    monkeypatch.setattr(o.cv2, 'VideoWriter', sink)
    d = o.Detection(0, 0, (2, 2, 10, 10), 'person', '', 1,
                    aoff=(np.int64(-1), np.int64(0)))
    previous = np.geterr()
    try:
        with warnings.catch_warnings(record=True), np.errstate(over='warn', invalid='warn'):
            with pytest.raises(ValueError, match=r'geometry.*detection 1.*frame 0.*arithmetic'):
                o.render(source, str(tmp_path / 'out.avi'), [d],
                         [(np.int64(2**63-1), np.int64(0))], [(0, 0)],
                         1, 0, 'box', False)
        assert np.geterr() == previous
    finally:
        for resource in captures + writers:
            resource.release()
