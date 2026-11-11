"""Actual work counters and preview freshness, independent of GPU speed."""
import threading
import numpy as np
import openscrub_web as web


def job(tmp_path):
    return dict(id='progress',name='Synthetic',dir=str(tmp_path),options={},
        phase='learning',progress=.5,error=None,stats={},log=[],output=None,
        cancel=threading.Event(),stop=threading.Event(),
        learning={'stage':'rescanning','message':'Rescanning'})


def test_rescan_progress_reports_actual_frames_and_age(tmp_path,monkeypatch):
    j=job(tmp_path)
    clock=[100.]
    monkeypatch.setattr(web.time,'time',lambda:clock[0])
    cb=web.WebCallbacks(j)
    cb.progress('scan',10,100)
    status=web.job_public(j)
    assert status['activity']['done']==10
    assert status['activity']['total']==100
    assert status['activity']['last_progress_at']==100.
    assert status['learning']['done']==10
    clock[0]=102.
    cb.progress('scan',10,100)
    assert j['activity']['last_progress_at']==100.
    clock[0]=103.
    cb.progress('scan',11,100)
    assert j['activity']['last_progress_at']==103.


def test_preview_is_current_pass_only_and_throttled(tmp_path,monkeypatch):
    j=job(tmp_path)
    clock=[100.]
    monkeypatch.setattr(web.time,'time',lambda:clock[0])
    frame=np.zeros((20,30,3),np.uint8)
    cb=web.WebCallbacks(j)
    cb.scan_frame(frame,1.2,2)
    first=web.job_public(j)['preview']
    assert first['source_time']==1.2 and first['updated_at']==100.
    cb.scan_frame(frame,1.3,3)
    assert web.job_public(j)['preview']==first
    clock[0]=102.
    cb.scan_frame(frame,1.4,3)
    assert web.job_public(j)['preview']['revision']!=first['revision']


def test_track_finalization_reports_tracks_not_frames(tmp_path):
    j=job(tmp_path)
    web.WebCallbacks(j).progress('post',2,5)
    assert j['activity']['unit']=='tracks'
    assert j['learning']['unit']=='tracks'
