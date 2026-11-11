"""Actual decoded frame counts for partial SDR/HDR rendering and refinement."""
from pathlib import Path
import json
import subprocess
import wave
import cv2
import numpy as np
import pytest
import openscrub
import video_learning


@pytest.fixture
def source(tmp_path):
    video=tmp_path/'source.mp4'
    w=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(96,64))
    for n in range(40):w.write(np.full((64,96,3),30+(47*n)%190,np.uint8))
    w.release()
    return video


def frame_count(path):
    cap=cv2.VideoCapture(str(path)); count=0
    while cap.read()[0]:count+=1
    cap.release();return count


def decoded_frames(path):
    cap=cv2.VideoCapture(str(path));frames=[]
    try:
        while True:
            ok,frame=cap.read()
            if not ok:return frames
            frames.append(frame)
    finally:cap.release()


def test_sdr_section_export_encodes_exactly_owned_frames(source,tmp_path):
    parser=openscrub.build_parser()
    args=openscrub._prep_args(parser.parse_args([str(source),'-o',str(tmp_path/'part.mp4'),
         '--encoder','x264','--categories','plate']),parser)
    args.section_range=(10,20)
    state=dict(fps=10.,cum=[(0,0)]*40,bands=[(0,0)]*40,detections=[],stats={})
    openscrub.run_render(args,state)
    assert frame_count(tmp_path/'part.mp4')==10


def test_hdr_section_export_encodes_exactly_owned_frames(source,tmp_path):
    out=tmp_path/'part-hdr.mp4'
    openscrub.render_hdr(str(source),str(out),[],[(0,0)]*40,[(0,0)]*40,10.,0,'box',
                        'libx265',{},frame_range=(10,20))
    assert frame_count(out)==10


@pytest.mark.parametrize('hdr',[False,True])
def test_section_masks_use_absolute_frame_indices_and_output_starts_at_requested_frame(source,tmp_path,hdr):
    out=tmp_path/('indexed-hdr.mp4' if hdr else 'indexed-sdr.mp4')
    detection=openscrub.Detection(1.5,1.5,(10,10,30,25),'plate','plate',1.,(0,0),frame_index=15)
    if hdr:
        openscrub.render_hdr(str(source),str(out),[detection],[(0,0)]*40,[(0,0)]*40,
                             10.,0,'box','libx265',{},frame_range=(10,20))
    else:
        openscrub.render(str(source),str(out),[detection],[(0,0)]*40,[(0,0)]*40,
                         10.,0,'box',False,encoder='x264',frame_range=(10,20))
    frames=decoded_frames(out);expected=decoded_frames(source)[10:20]
    assert len(frames)==10
    for frame,original in zip(frames,expected):
        # Colors are separated by at least 47 levels between neighboring
        # source frames; allow only the small BGR/YUV re-encode round trip.
        assert abs(frame[40:,50:].mean()-original[40:,50:].mean())<4
    assert frames[5][13:22,13:27].max()<5
    assert all(frames[i][13:22,13:27].min()>30 for i in range(10) if i!=5)


def test_hdr_section_refuses_render_source_with_a_different_timeline(source,tmp_path):
    hdr=tmp_path/'unaligned.mp4'
    writer=cv2.VideoWriter(str(hdr),cv2.VideoWriter_fourcc(*'mp4v'),10,(96,64))
    for _ in range(41):writer.write(np.full((64,96,3),80,np.uint8))
    writer.release()
    parser=openscrub.build_parser()
    args=openscrub._prep_args(parser.parse_args([str(source),'--encoder','x264',
        '-o',str(tmp_path/'unsafe-hdr.mp4')]),parser)
    args.section_range=(10,20);args.hdr_source=str(hdr);args.hdr_encoder='libx265';args.hdr_tags={}
    state=dict(fps=10.,cum=[(0,0)]*40,bands=[(0,0)]*40,detections=[],stats={},
               input_sha256=openscrub.sha256_file(source),total_frames=40)
    with pytest.raises(ValueError,match='(?i)HDR.*timeline|timeline.*HDR'):
        openscrub.run_render(args,state)
    assert not Path(args.output).exists()


def test_hdr_section_fails_closed_on_short_decode(source,tmp_path,monkeypatch):
    real_capture=cv2.VideoCapture
    class OverreportedMetadata:
        def __init__(self,path):self.cap=real_capture(path)
        def get(self,prop):
            return 50 if prop==cv2.CAP_PROP_FRAME_COUNT else self.cap.get(prop)
        def isOpened(self):return self.cap.isOpened()
        def release(self):return self.cap.release()
    monkeypatch.setattr(openscrub.cv2,'VideoCapture',OverreportedMetadata)
    out=tmp_path/'short-hdr.mp4'
    with pytest.raises(RuntimeError,match='(?i)decoder.*frame'):
        openscrub.render_hdr(str(source),str(out),[],[(0,0)]*50,[(0,0)]*50,
                             10.,0,'box','libx265',{},frame_range=(35,45))
    assert not out.exists()


def test_refinement_decodes_only_requested_frames(source):
    doc={'provenance':{},'render_state':{'fps':10.,'cum':[[0,0]]*40,'bands':[[0,0]]*40},
         'detections':[dict(category='plate',frame_index=15,t_start=1.5,t_end=1.5,
                            cbox=[10,10,30,25]) ]}
    class Uncertain:
        def predict(self,crop):return None,0.
    seen=[]
    result,stats=video_learning.refine_report(str(source),doc,Uncertain(),
        progress=lambda a,b:seen.append((a,b)),frame_range=(10,20))
    assert stats['decoded_frames']==10
    assert stats['model_calls']==1
    assert seen[-1]==(10,10)
    assert result['detections'][0]['frame_index']==15


def test_section_report_keeps_full_source_identity_for_partial_scan(source,tmp_path):
    path=tmp_path/'report.json'
    args=openscrub.build_parser().parse_args([str(source)])
    fingerprint=openscrub.sha256_file(source)
    state=dict(fps=10.,cum=[(0,0)]*20,bands=[(0,0)]*20,detections=[],
               input_sha256=fingerprint,total_frames=40)
    openscrub.write_report(path,args,state)
    doc=json.loads(path.read_text())
    assert doc['source_identity']==dict(input_sha256=fingerprint,fps=10.,total_frames=40)
    assert len(doc['render_state']['cum'])==20


def test_section_from_report_refuses_changed_source(source,tmp_path):
    report=tmp_path/'report.json';out=tmp_path/'unsafe.mp4'
    report.write_text(json.dumps(dict(
        provenance=dict(input_sha256='0'*64),detections=[],
        source_identity=dict(input_sha256='0'*64,fps=10.,total_frames=40),
        render_state=dict(fps=10.,cum=[[0,0]]*40,bands=[[0,0]]*40))))
    parser=openscrub.build_parser()
    args=openscrub._prep_args(parser.parse_args([str(source),'--from-report',str(report),
        '--encoder','x264','-o',str(out)]),parser)
    args.section_range=(10,20)
    with pytest.raises(ValueError,match='(?i)source.*changed|sha256 mismatch'):
        openscrub.run_pipeline(args)
    assert not out.exists()


def test_section_from_report_refuses_changed_original_before_normalization(source,tmp_path):
    report=tmp_path/'original-report.json';out=tmp_path/'unsafe-original.mp4'
    fingerprint=openscrub.sha256_file(source)
    report.write_text(json.dumps(dict(
        provenance=dict(input_sha256=fingerprint,original_input=str(source),original_input_sha256='0'*64),
        source_identity=dict(input_sha256=fingerprint,fps=10.,total_frames=40),
        detections=[],render_state=dict(fps=10.,cum=[[0,0]]*40,bands=[[0,0]]*40))))
    parser=openscrub.build_parser()
    args=openscrub._prep_args(parser.parse_args([str(source),'--from-report',str(report),
        '--encoder','x264','-o',str(out)]),parser)
    args.section_range=(10,20)
    with pytest.raises(ValueError,match='(?i)original.*changed'):
        openscrub.run_pipeline(args)
    assert not out.exists()


def test_report_binds_original_input_fingerprint_once(source,tmp_path):
    path=tmp_path/'report.json'
    args=openscrub.build_parser().parse_args([str(source)])
    args.original_video=str(source)
    fingerprint=openscrub.sha256_file(source)
    state=dict(fps=10.,cum=[(0,0)]*40,bands=[(0,0)]*40,detections=[],
               input_sha256=fingerprint,total_frames=40)
    openscrub.write_report(path,args,state)
    assert json.loads(path.read_text())['provenance']['original_input_sha256']==fingerprint
    with source.open('ab') as changed:changed.write(b'changed after first report')
    openscrub.write_report(path,args,state)
    assert json.loads(path.read_text())['provenance']['original_input_sha256']==fingerprint


def test_section_report_render_preserves_original_fingerprint_and_source_timeline(source,tmp_path):
    report=tmp_path/'before.json';after=tmp_path/'after.json';fingerprint=openscrub.sha256_file(source)
    report.write_text(json.dumps(dict(
        provenance=dict(input_sha256=fingerprint,original_input=str(source),original_input_sha256=fingerprint),
        source_identity=dict(input_sha256=fingerprint,fps=10.,total_frames=40),
        detections=[],render_state=dict(fps=10.,cum=[[0,0]]*20,bands=[[0,0]]*20))))
    parser=openscrub.build_parser()
    args=openscrub._prep_args(parser.parse_args([str(source),'--from-report',str(report),
        '--encoder','x264','-o',str(tmp_path/'valid-part.mp4'),'--report',str(after)]),parser)
    args.section_range=(10,20)
    openscrub.run_pipeline(args)
    result=json.loads(after.read_text())
    assert result['provenance']['original_input']==str(source)
    assert result['provenance']['original_input_sha256']==fingerprint
    assert result['source_identity']==dict(input_sha256=fingerprint,fps=10.,total_frames=40)


@pytest.mark.parametrize('hdr,vfr',[(False,True),(True,False),(True,True)])
def test_section_export_reuses_normalized_parent_source_and_hdr_context(source,tmp_path,hdr,vfr):
    parent=tmp_path/'parent';parent.mkdir()
    child=tmp_path/'export';child.mkdir()
    original=parent/'input.mp4'
    filters=(['-vf',"setpts='if(lt(N,20),N/(10*TB),(2+(N-20)/20)/TB)'",
              '-fps_mode','vfr','-enc_time_base','1:20'] if vfr else [])
    codec=(['-c:v','libx265','-x265-params',
            'pools=1:log-level=error:colorprim=9:transfer=16:colormatrix=9',
            '-pix_fmt','yuv420p10le','-color_primaries','bt2020',
            '-color_trc','smpte2084','-colorspace','bt2020nc']
           if hdr else ['-c:v','libx264'])
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(source),
                    *filters,*codec,str(original)],check=True,capture_output=True)
    assert openscrub.probe_vfr(str(original))[0] is vfr
    assert openscrub.probe_hdr(str(original))[0] is hdr
    parser=openscrub.build_parser()
    intake=openscrub._prep_args(parser.parse_args([str(original),'--encoder','x264',
        '-o',str(parent/'output.mp4')]),parser)
    openscrub.normalize_vfr(intake,openscrub.Callbacks())
    reviewed_source=Path(intake.video)
    assert reviewed_source!=original
    cap=cv2.VideoCapture(str(reviewed_source))
    fps=cap.get(cv2.CAP_PROP_FPS);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));cap.release()
    fingerprint=openscrub.sha256_file(reviewed_source)
    render_source=getattr(intake,'hdr_source',None)
    state=dict(fps=fps,cum=[(0,0)]*total,bands=[(0,0)]*total,detections=[],
               input_sha256=fingerprint,total_frames=total)
    report=parent/'report.json';openscrub.write_report(report,intake,state)
    after=child/'report.json';out=child/'output.mp4'
    args=openscrub._prep_args(parser.parse_args([str(reviewed_source),'--from-report',str(report),
        '--encoder','x264','-o',str(out),'--report',str(after)]),parser)
    args.section_range=(10,20)
    openscrub.run_pipeline(args)
    assert Path(args.video)==reviewed_source
    assert openscrub.sha256_file(reviewed_source)==fingerprint
    assert getattr(args,'hdr_source',None)==render_source
    assert sorted(p.name for p in child.iterdir())==['output.mp4','report.json']
    assert frame_count(out)==10
    assert openscrub.probe_hdr(str(out))[0] is hdr
    saved=json.loads(after.read_text())
    assert saved['provenance']['input']==str(reviewed_source)
    assert saved['provenance']['original_input']==str(original)
    assert saved['source_identity']==dict(input_sha256=fingerprint,fps=fps,total_frames=total)


def test_section_refinement_leaves_outside_proposals_untouched(source):
    rows=[dict(category='plate',frame_index=n,t_start=n/10,t_end=n/10,
               cbox=[10,10,30,25]) for n in (5,15,25)]
    doc=dict(provenance={},render_state=dict(fps=10.,cum=[[0,0]]*40),detections=rows)
    class Uncertain:
        def predict(self,crop):return None,0.
    result,stats=video_learning.refine_report(str(source),doc,Uncertain(),frame_range=(10,20))
    assert stats['model_calls']==1 and stats['decoded_frames']==10
    assert result['detections'][0]==rows[0]
    assert result['detections'][2]==rows[2]


@pytest.mark.parametrize('fps,limit',[(12.,40),(10.,15)])
def test_section_render_rejects_misaligned_or_unscanned_timeline(source,tmp_path,fps,limit):
    out=tmp_path/'invalid.mp4'
    with pytest.raises(ValueError,match='(?i)timeline|frame rate|scanned'):
        openscrub.render(str(source),str(out),[],[(0,0)]*limit,[(0,0)]*limit,
                         fps,0,'box',False,encoder='x264',frame_range=(10,20))
    assert not out.exists()


def test_section_render_fails_closed_when_decoder_ends_early(source,tmp_path,monkeypatch):
    real_capture=cv2.VideoCapture
    class ShortCapture:
        def __init__(self,path):self.cap=real_capture(path)
        def get(self,*args):return self.cap.get(*args)
        def set(self,*args):return self.cap.set(*args)
        def isOpened(self):return self.cap.isOpened()
        def release(self):return self.cap.release()
        def read(self):
            if self.cap.get(cv2.CAP_PROP_POS_FRAMES)>=15:return False,None
            return self.cap.read()
    monkeypatch.setattr(openscrub.cv2,'VideoCapture',ShortCapture)
    out=tmp_path/'partial.mp4'
    with pytest.raises((ValueError,RuntimeError),match='(?i)decoder|section.*frame'):
        openscrub.render(str(source),str(out),[],[(0,0)]*40,[(0,0)]*40,
                         10.,0,'box',False,encoder='x264',frame_range=(10,20))
    assert not out.exists()


@pytest.fixture
def audio_source(source,tmp_path):
    wav=tmp_path/'tones.wav';rate=48000
    t=np.arange(4*rate)/rate
    frequency=np.where(t<1,220,np.where(t<2,440,880))
    samples=(np.sin(2*np.pi*frequency*t)*14000).astype('<i2')
    with wave.open(str(wav),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(rate)
        output.writeframes(samples.tobytes())
    video=tmp_path/'with-audio.mp4'
    subprocess.run(['ffmpeg','-v','error','-i',str(source),'-i',str(wav),
                    '-c:v','copy','-c:a','aac','-y',str(video)],check=True,capture_output=True)
    return video


@pytest.mark.parametrize('hdr',[False,True])
def test_section_audio_is_trimmed_and_redactions_use_original_timeline(audio_source,tmp_path,hdr):
    out=tmp_path/('audio-hdr.mp4' if hdr else 'audio-sdr.mp4')
    kwargs=dict(audio_spans=[(1.35,1.6,'mute'),(1.75,2.5,'bleep')],frame_range=(10,20))
    if hdr:
        openscrub.render_hdr(str(audio_source),str(out),[],[(0,0)]*40,[(0,0)]*40,
                             10.,0,'box','libx265',{},**kwargs)
    else:
        openscrub.render(str(audio_source),str(out),[],[(0,0)]*40,[(0,0)]*40,
                         10.,0,'box',False,encoder='x264',**kwargs)
    assert frame_count(out)==10
    result=subprocess.run(['ffmpeg','-v','error','-i',str(out),'-map','0:a:0',
                           '-ac','1','-ar','16000','-f','f32le','-'],
                          check=True,capture_output=True)
    samples=np.frombuffer(result.stdout,dtype='<f4')
    # AAC has up to one packet of encoder padding, never source audio after 2s.
    assert .99<=len(samples)/16000<=1.03
    def peak(a,b):
        part=samples[int(a*16000):int(b*16000)]
        return np.fft.rfftfreq(len(part),1/16000)[np.argmax(np.abs(np.fft.rfft(part)))]
    assert abs(peak(.08,.28)-440)<10, 'audio began at the wrong source time'
    assert np.abs(samples[int(.43*16000):int(.54*16000)]).max()<.001
    assert abs(peak(.82,.95)-1000)<15, 'bleep span shifted or leaked beyond the section'


def test_section_with_plain_audio_keeps_only_selected_audio_samples(audio_source,tmp_path):
    out=tmp_path/'plain-audio.mp4'
    openscrub.render(str(audio_source),str(out),[],[(0,0)]*40,[(0,0)]*40,
                     10.,0,'box',False,encoder='x264',frame_range=(10,20))
    raw=subprocess.run(['ffmpeg','-v','error','-i',str(out),'-map','0:a:0',
        '-ac','1','-ar','16000','-f','f32le','-'],check=True,capture_output=True).stdout
    samples=np.frombuffer(raw,dtype='<f4')
    assert .99<=len(samples)/16000<=1.03
    part=samples[1600:4800]
    peak=np.fft.rfftfreq(len(part),1/16000)[np.argmax(np.abs(np.fft.rfft(part)))]
    assert abs(peak-440)<10


def test_section_drops_audio_when_tracks_cannot_be_verified(audio_source,tmp_path,monkeypatch):
    monkeypatch.setattr(openscrub,'probe_audio_tracks',lambda src:[])
    out=tmp_path/'unverified-audio.mp4'
    openscrub.render(str(audio_source),str(out),[],[(0,0)]*40,[(0,0)]*40,
                     10.,0,'box',False,encoder='x264',frame_range=(10,20),
                     audio_spans=[(1.,2.,'mute')])
    streams=json.loads(subprocess.run(['ffprobe','-v','error','-select_streams','a',
        '-show_entries','stream=index','-of','json',str(out)],check=True,capture_output=True,text=True).stdout)
    assert not streams['streams']


def test_section_preserves_audio_that_starts_later_than_video(audio_source,source,tmp_path):
    delayed=tmp_path/'delayed.mp4';out=tmp_path/'delayed-part.mp4'
    subprocess.run(['ffmpeg','-v','error','-i',str(source),'-itsoffset','1.2',
        '-i',str(tmp_path/'tones.wav'),'-c:v','copy','-c:a','aac','-t','4',
        '-y',str(delayed)],check=True,capture_output=True)
    openscrub.render(str(delayed),str(out),[],[(0,0)]*40,[(0,0)]*40,
                     10.,0,'box',False,encoder='x264',frame_range=(10,20))
    raw=subprocess.run(['ffmpeg','-v','error','-i',str(out),'-map','0:a:0',
        '-af','aresample=async=1:first_pts=0','-ac','1','-ar','16000','-f','f32le','-'],
        check=True,capture_output=True).stdout
    samples=np.frombuffer(raw,dtype='<f4')
    assert np.abs(samples[800:2400]).max()<.001, 'late audio was shifted into the initial gap'
    assert np.abs(samples[6400:9600]).max()>.1
