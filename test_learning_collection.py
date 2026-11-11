"""Training collection must not inherit a thumbnail's deadline or retry policy."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import threading
import time

import cv2
import numpy as np
import pytest
import learning_session as ls
import openscrub_web as web
from test_plate_quad_editor import plate_job
from test_learning_session import _seed


def negative_job(tmp_path, frames=(8, 2, 8, 5)):
    folder=tmp_path/'job';folder.mkdir()
    job={'dir':str(folder),'video':str(folder/'input.mp4'),
         'cancel':threading.Event(),'learning':{'stage':'collecting'},'log':[]}
    doc={'provenance':{'input_sha256':'f'*64},
         'render_state':{'fps':10,'cum':[[0,0]]*20},
         'detections':[{'category':'plate','enabled':False,'verified_label':'not_plate',
                        'frame_index':f,'t_start':f/10,'t_end':f/10+.1,
                        'track':i,'cbox':[5+i*20,5,15+i*20,15]} for i,f in enumerate(frames)]}
    return job,doc


def test_worker_collection_is_independent_of_interactive_preview_timeout(plate_job,monkeypatch):
    job,doc,path,folder=_seed(plate_job)
    before=path.read_bytes()
    monkeypatch.setattr(ls,'preflight',lambda:{'ready':True,'problems':[]})
    def no_preview(*a):raise RuntimeError('interactive preview decoder was used')
    monkeypatch.setattr(web,'_read_exact_frame',no_preview)
    def reached(*a):raise ValueError('TRAINER_REACHED')
    monkeypatch.setattr(ls,'run_training',reached)
    job.update(learning_previous_phase='paused',phase='learning')
    web.perform_learning(job)
    assert job['error']=='TRAINER_REACHED',job['error']
    assert job['phase']=='paused' and path.read_bytes()==before
    assert len(json.loads((folder/'learning/feedback.json').read_text())['samples'])==1


def test_collection_reads_unique_frames_in_order(tmp_path):
    job,doc=negative_job(tmp_path);calls=[]
    def read(index):
        calls.append(index);return np.full((40,100,3),index,dtype=np.uint8)
    result=ls.collect_feedback(job,doc,read)
    assert calls==[2,5,8]
    assert len(result['samples'])==4
    assert {s['frame'] for s in result['samples'].values()}=={2,5,8}


def test_collection_reports_completed_examples_not_epochs(tmp_path):
    job,doc=negative_job(tmp_path)
    ls.collect_feedback(job,doc,lambda i:np.zeros((40,100,3),np.uint8))
    assert job['learning'].get('completed_examples')==4
    assert job['learning']['total_examples']==4
    assert job['learning']['stage']=='collecting'
    assert '4/4' in job['learning']['message']
    assert job['learning']['done']==job['learning']['total']==4
    assert job['learning']['unit']=='examples'
    assert job['learning']['updated_at']>=job['learning']['started_at']


def test_cancelled_collection_does_not_read_or_publish(tmp_path):
    job,doc=negative_job(tmp_path);job['cancel'].set();calls=[]
    def read(i):calls.append(i);return np.zeros((40,100,3),np.uint8)
    with pytest.raises(InterruptedError,match='cancel'):
        ls.collect_feedback(job,doc,read)
    assert not calls
    assert not (Path(job['dir'])/'learning/feedback.json').exists()


def test_failure_cleans_new_crops_without_touching_saved_feedback(tmp_path):
    job,doc=negative_job(tmp_path,frames=(1,2))
    def read(i):
        if i==2:raise TimeoutError('deliberate decoder stall')
        return np.zeros((40,100,3),np.uint8)
    with pytest.raises(TimeoutError):ls.collect_feedback(job,doc,read)
    assert not list((Path(job['dir'])/'learning/samples').glob('*.png'))
    assert not (Path(job['dir'])/'learning/feedback.json').exists()


def test_unreviewed_blur_is_not_training_data(tmp_path):
    job,doc=negative_job(tmp_path)
    for row in doc['detections']:row.update(enabled=True,verified_label='')
    def no_read(i):pytest.fail('untouched finding was decoded')
    assert ls.collect_feedback(job,doc,no_read)['samples']=={}


@pytest.fixture
def gop_video(tmp_path):
    path=tmp_path/'long-gop.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
        'testsrc2=size=160x96:rate=10:duration=12','-c:v','libx264','-crf','12',
        '-g','120','-keyint_min','120','-sc_threshold','0','-threads','1',str(path)],check=True)
    return path


def test_stream_decodes_exact_frames_from_single_long_gop(gop_video):
    wanted=[0,3,55,99,119]
    iterator=getattr(ls,'iter_training_frames',None)
    assert callable(iterator),'A training-specific streaming decoder is required'
    got=dict(iterator(str(gop_video),wanted,10,lambda:False))
    cap=cv2.VideoCapture(str(gop_video));references={}
    for i in range(120):
        ok,frame=cap.read();assert ok
        if i in wanted:references[i]=frame
    cap.release()
    assert sorted(got)==wanted
    for i in wanted:assert np.array_equal(got[i],references[i]),i


def test_stream_refuses_mismatched_timeline(gop_video):
    iterator=getattr(ls,'iter_training_frames',None)
    assert callable(iterator),'A training-specific streaming decoder is required'
    with pytest.raises(ValueError,match='frame rate|timeline'):
        list(iterator(str(gop_video),[20],30,lambda:False))


def test_stream_reports_missing_source_frame(gop_video):
    iterator=getattr(ls,'iter_training_frames',None)
    assert callable(iterator),'A training-specific streaming decoder is required'
    with pytest.raises(ValueError,match='frame 130'):
        list(iterator(str(gop_video),[130],10,lambda:False))


def test_decoder_accepts_nonzero_stream_start(gop_video,tmp_path):
    shifted=tmp_path/'offset.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(gop_video),
                    '-c','copy','-output_ts_offset','7',str(shifted)],check=True)
    a=dict(ls.iter_training_frames(str(gop_video),[0,55,119],10,lambda:False))
    b=dict(ls.iter_training_frames(str(shifted),[0,55,119],10,lambda:False))
    assert all(np.array_equal(a[i],b[i]) for i in a)


def intercept_decoder(monkeypatch,script):
    import sys
    original=subprocess.Popen;children=[];commands=[]
    def launch(command,*args,**kwargs):
        if command[0]=='ffmpeg':
            commands.append(list(command))
            command=[sys.executable,'-c',script]+command
            child=original(command,*args,**kwargs);children.append(child);return child
        return original(command,*args,**kwargs)
    monkeypatch.setattr(ls.subprocess,'Popen',launch)
    return children,commands


def test_training_decode_can_take_more_than_preview_deadline(gop_video,monkeypatch):
    children,commands=intercept_decoder(monkeypatch,
        'import os,sys,time;time.sleep(10.5);os.execvp(sys.argv[1],sys.argv[1:])')
    began=time.monotonic();pulses=[]
    got=list(ls.iter_training_frames(str(gop_video),[0,99,119],10,lambda:False,
                                    lambda n,target:pulses.append((n,target))))
    assert time.monotonic()-began>=10
    assert [i for i,_ in got]==[0,99,119]
    assert len(commands)==1 and '-ss' not in commands[0]
    assert children[0].poll() is not None and pulses


@pytest.mark.parametrize('reason',['cancel','stall'])
def test_blocked_decoder_is_terminated_and_reaped(gop_video,monkeypatch,reason):
    children,_=intercept_decoder(monkeypatch,'import time;time.sleep(30)')
    monkeypatch.setattr(ls,'_collection_probe',lambda *a:None)
    cancel=threading.Event();timer=threading.Timer(.3,cancel.set) if reason=='cancel' else None
    if timer:timer.start()
    began=time.monotonic()
    try:
        with pytest.raises(InterruptedError if reason=='cancel' else TimeoutError):
            list(ls.iter_training_frames(str(gop_video),[119],10,cancel.is_set,
                                         stall_timeout=2 if reason=='cancel' else .3))
    finally:
        if timer:timer.cancel()
    assert time.monotonic()-began<4
    assert children and all(p.poll() is not None for p in children)


def test_failed_retry_preserves_committed_samples_and_manifest(tmp_path):
    job,doc=negative_job(tmp_path,frames=(1,))
    first=ls.collect_feedback(job,doc,lambda i:np.zeros((40,100,3),np.uint8))
    root=Path(job['dir'])/'learning';before=(root/'feedback.json').read_bytes()
    files={p:p.read_bytes() for p in (root/'samples').glob('*.png')}
    extra=deepcopy(doc['detections'][0]);extra.update(track=2,frame_index=2,cbox=[60,5,70,15])
    doc['detections'].append(extra)
    def fail(i):
        assert i==2,'Committed negative must not be decoded again'
        raise TimeoutError('stalled')
    with pytest.raises(TimeoutError):ls.collect_feedback(job,doc,fail)
    assert (root/'feedback.json').read_bytes()==before
    assert {p:p.read_bytes() for p in (root/'samples').glob('*.png')}==files


def test_close_generator_reaps_decoder_with_pending_frames(gop_video,monkeypatch):
    children,_=intercept_decoder(monkeypatch,'import os,sys;os.execvp(sys.argv[1],sys.argv[1:])')
    frames=ls.iter_training_frames(str(gop_video),list(range(120)),10,lambda:False)
    assert next(frames)[0]==0
    frames.close()
    assert children[0].poll() is not None


def test_training_collection_handles_real_4k_frame(tmp_path):
    path=tmp_path/'4k.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
        'testsrc2=size=3840x2160:rate=4:duration=2','-c:v','libx264',
        '-preset','ultrafast','-g','8','-threads','2',str(path)],check=True)
    result=dict(ls.iter_training_frames(str(path),[0,4,7],4,lambda:False))
    assert all(frame.shape==(2160,3840,3) for frame in result.values())
    cap=cv2.VideoCapture(str(path))
    for i in range(8):
        ok,frame=cap.read();assert ok
        if i in result:assert np.array_equal(result[i],frame)
    cap.release()


def test_status_reports_forward_decode_progress_before_first_sample(gop_video):
    seen=[]
    list(ls.iter_training_frames(str(gop_video),[119],10,lambda:False,
                                 lambda n,target:seen.append((n,target))))
    assert any(target==119 for n,target in seen)


def test_none_reader_does_not_decode_unreviewed_rows(tmp_path,monkeypatch):
    job,doc=negative_job(tmp_path)
    for row in doc['detections']:row.update(enabled=True,verified_label='')
    def no_process(*a,**k):pytest.fail('Untouched defaults must not launch decoder')
    monkeypatch.setattr(ls.subprocess,'Popen',no_process)
    assert not ls.collect_feedback(job,doc,None)['samples']


def test_collection_progress_is_exposed_by_job_status(plate_job):
    job,doc,path,folder=_seed(plate_job)
    client,jid,*_=plate_job
    job.update(progress=.5,error=None,output=None)
    def read(i):
        status=client.get('/api/jobs/'+jid).get_json()['learning']
        assert status['stage']=='collecting'
        assert status['completed_examples']==0 and status['total_examples']==1
        return web._read_exact_frame(job['video'],i)
    ls.collect_feedback(job,doc,read)
    status=client.get('/api/jobs/'+jid).get_json()['learning']
    assert status['completed_examples']==1 and '1/1' in status['message']


def test_collection_cancel_midway_preserves_prior_report(plate_job):
    job,doc,path,folder=_seed(plate_job);before=path.read_bytes()
    def read(i):
        job['cancel'].set()
        return np.zeros((160,240,3),np.uint8)
    with pytest.raises(InterruptedError):ls.collect_feedback(job,doc,read)
    assert path.read_bytes()==before
    assert not (folder/'learning/feedback.json').exists()
    assert not list((folder/'learning/samples').glob('*.png'))
