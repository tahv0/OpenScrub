"""Real local Tesseract and video decoding on generated detached plates."""
import shutil
import subprocess

import cv2
import numpy as np
import pytest

from openscrub_internal.plate_search.matching import PlateQuery
from openscrub_internal.plate_search.samples import search_capture

pytestmark = pytest.mark.skipif(not shutil.which('tesseract'), reason='local Tesseract unavailable')


def _clip(path):
    width, height = 960, 540
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 4, (width,height))
    if not writer.isOpened():
        pytest.skip('OpenCV MPEG4 video writer unavailable')
    plate = np.full((100,360,3), 240, np.uint8)
    cv2.rectangle(plate,(0,0),(359,99),(20,20,20),3)
    cv2.putText(plate,'KJF572',(23,72),cv2.FONT_HERSHEY_SIMPLEX,2.1,(5,5,5),5,cv2.LINE_AA)
    for index in range(4):
        frame = np.full((height,width,3),(95,110,120),np.uint8)
        if index == 0:
            frame[90:190,300:660] = plate  # flat plate on a wall
        if index == 2:
            source = np.float32([[0,0],[359,0],[359,99],[0,99]])
            target = np.float32([[280,350],[660,335],[640,450],[295,455]])
            matrix = cv2.getPerspectiveTransform(source,target)
            patch = cv2.warpPerspective(plate,matrix,(width,height))
            mask = cv2.warpPerspective(np.full((100,360),255,np.uint8),matrix,(width,height))
            frame[mask > 0] = patch[mask > 0]  # skewed plate on the ground
        writer.write(frame)
    writer.release()


def test_real_tesseract_finds_wall_and_ground_in_sampled_video(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'detached.mp4'
    _clip(path)
    invocations = []
    original = subprocess.Popen
    def spawn(args, *a, **kw):
        invocations.append(args)
        return original(args, *a, **kw)
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    try:
        result = search_capture(cap, (PlateQuery('KJF572'),PlateQuery('JF5','fragment')),
            [0,1,2,3], fps=4., count=4, width=960, height=540, tolerance_s=.01)
    finally:
        cap.release()
    assert result.requested_indices == result.completed_indices == (0,1,2,3)
    assert not result.cancelled
    assert not result.frames[1].hits and not result.frames[3].hits
    for index, expected in ((0,(300,90,660,190)), (2,(280,335,660,455))):
        hits = result.frames[index].hits
        assert hits
        hit = next(h for h in hits if {m.match_kind for m in h.matches} == {'full_equal','fragment'})
        x1,y1,x2,y2 = hit.observation.box
        assert expected[0] <= x1 < x2 <= expected[2]
        assert expected[1] <= y1 < y2 <= expected[3]
        assert hit.suggested_box[0] <= x1 and hit.suggested_box[2] >= x2
        assert hit.suggested_box[1] <= y1 and hit.suggested_box[3] >= y2
        assert hit.boundary == 'unknown'
    assert invocations and all('KJF572' not in str(args) and 'JF5' not in str(args)
                               for args in invocations)
    captured = capsys.readouterr()
    assert 'KJF572' not in captured.out + captured.err
    assert 'JF5' not in captured.out + captured.err


def test_small_4k_plate_is_searched_at_native_resolution(tmp_path):
    width, height = 3840, 2160
    frame = np.full((height,width,3),(90,105,120),np.uint8)
    plate = np.full((52,210,3),240,np.uint8)
    cv2.rectangle(plate,(0,0),(209,51),(10,10,10),2)
    cv2.putText(plate,'MVB849',(10,37),cv2.FONT_HERSHEY_SIMPLEX,.93,(0,0,0),2,cv2.LINE_AA)
    frame[1570:1622,2800:3010] = plate
    path = tmp_path / 'small-4k.mp4'
    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),2,(width,height))
    if not writer.isOpened():
        pytest.skip('OpenCV 4K MPEG4 video writer unavailable')
    writer.write(frame)
    writer.release()
    del frame
    cap = cv2.VideoCapture(str(path),cv2.CAP_FFMPEG)
    try:
        result = search_capture(cap,(PlateQuery('MVB849'),PlateQuery('VB8','fragment')),
            [0],fps=2.,count=1,width=width,height=height,tolerance_s=.01)
    finally:
        cap.release()
    assert result.completed_indices == (0,) and not result.cancelled
    assert not result.frames[0].truncated
    hit = next(h for h in result.frames[0].hits
               if {m.match_kind for m in h.matches} == {'full_equal','fragment'})
    x1,y1,x2,y2 = hit.observation.box
    assert 2795 <= x1 < x2 <= 3015 and 1565 <= y1 < y2 <= 1627
    assert hit.boundary == 'unknown'


@pytest.mark.skipif(__import__('os').name == 'nt', reason='executable timeout fixture is POSIX')
def test_tesseract_timeout_is_sanitized_and_cleans_temporary_files(tmp_path, monkeypatch):
    import sys
    import tempfile
    import pytesseract
    from openscrub_internal.plate_search import search

    binary = tmp_path / 'slow-ocr'
    binary.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(10)\n')
    binary.chmod(0o700)
    tempdir = tmp_path / 'temp'
    tempdir.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(tempdir))
    monkeypatch.setattr(pytesseract.pytesseract, 'tesseract_cmd', str(binary))
    monkeypatch.setattr(search, 'OCR_TIMEOUT_SECONDS', .1)
    with pytest.raises(search.SearchError, match='^OCR reader failed or timed out$'):
        search.search_frame(np.full((100,300,3),255,np.uint8),(PlateQuery('KJF572'),))
    assert list(tempdir.iterdir()) == []


def test_successful_tesseract_call_cleans_temporary_files(tmp_path, monkeypatch):
    import tempfile
    from openscrub_internal.plate_search.search import search_frame
    tempdir = tmp_path / 'temp'
    tempdir.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(tempdir))
    frame = np.full((120,360,3),255,np.uint8)
    cv2.putText(frame,'KJF572',(25,80),cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),4,cv2.LINE_AA)
    result = search_frame(frame, (PlateQuery('KJF572'),))
    assert result.complete and result.hits
    assert list(tempdir.iterdir()) == []
