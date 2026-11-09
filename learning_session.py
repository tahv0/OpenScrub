"""Transactional, local video-learning sessions; no training on the web thread."""
from copy import deepcopy
from collections import deque
from contextlib import closing
from fractions import Fraction
import queue
import re
import tempfile
import threading
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

import cv2
import numpy as np

import video_learning as vl
import stop_review


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def private_dir(path):
    path=Path(path);path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name!='nt':path.chmod(0o700)
    return path


def atomic_json(path,data):
    path=Path(path);private_dir(path.parent)
    stop_review.atomic_report(str(path),data)


def verify_source(job,doc):
    expected=doc.get('provenance',{}).get('input_sha256')
    actual=sha256(job['video'])
    if expected and expected!=actual:
        raise ValueError('Learning source changed; the saved annotations belong to a different video')
    return actual


def feedback_fingerprint(samples):
    fields=('image_sha256','label','points','group')
    items=[{k:record.get(k) for k in fields} for _,record in sorted(samples.items())]
    return hashlib.sha256(json.dumps(items,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _load(path,default=None):
    path=Path(path)
    if not path.exists():return deepcopy(default)
    return json.loads(path.read_text(encoding='utf-8'))


# Training collection owns its decoder. Never borrow the interactive preview
# lock, Flask abort(), or its ten-second request deadline for batch work.
def _collection_cancel(cancel):
    if cancel():
        raise InterruptedError('Learning collection cancelled; saved review retained')


def _stop_collection_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _collection_probe(path, fps, cancel, progress, timeout):
    command=['ffprobe','-v','error','-select_streams','v:0',
             '-show_entries','stream=avg_frame_rate,r_frame_rate',
             '-of','json',str(path)]
    started=time.monotonic()
    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        while True:
            _collection_cancel(cancel)
            if time.monotonic()-started>timeout:
                raise TimeoutError('Training source probing stalled; saved review retained')
            if progress:progress(-1,None)
            try:
                stdout,stderr=process.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                pass
        if process.returncode:
            raise ValueError('Cannot probe training source: '+stderr.decode(errors='replace')[-500:])
        stream=json.loads(stdout)['streams'][0]
        avg=float(Fraction(stream['avg_frame_rate']))
        nominal=float(Fraction(stream['r_frame_rate']))
        if (not math.isfinite(avg) or avg<=0 or
                abs(avg-nominal)>max(.001,avg*.0001) or
                not math.isclose(avg,fps,rel_tol=1e-6,abs_tol=1e-6)):
            raise ValueError('Training source frame rate does not match the reviewed CFR timeline')
    finally:
        _stop_collection_process(process)
        process.stdout.close();process.stderr.close()


def _frame_selection(indices):
    """Balanced selection avoids a linear expression scan per video frame."""
    if len(indices)==1:return 'eq(n,%d)'%indices[0]
    mid=len(indices)//2
    return 'if(lt(n,%d),%s,%s)'%(indices[mid],
        _frame_selection(indices[:mid]),_frame_selection(indices[mid:]))


def iter_training_frames(path, indices, fps, cancel, progress=None, stall_timeout=120):
    """Decode selected exact CFR frames once, in order, with bounded memory.

    No transcode or frame dump is written. FFmpeg traverses from frame zero to
    the last required frame, emitting only selected PPMs. Integer PTS is checked
    against the reviewed timeline. The stall guard measures *lack of decoder
    progress*, not total traversal time; cancellation kills and reaps the child.
    """
    wanted=sorted(set(indices))
    if not wanted:return
    if any(not isinstance(i,int) or isinstance(i,bool) or i<0 for i in wanted):
        raise ValueError('Training source frames must be nonnegative integers')
    if not math.isfinite(fps) or fps<=0 or stall_timeout<=0:
        raise ValueError('Invalid training frame rate or decoder timeout')
    _collection_cancel(cancel)
    _collection_probe(path,fps,cancel,progress,stall_timeout)
    # Only a filter expression is staged, never video/pixels. A script avoids
    # operating-system argv limits for large reviewed sets.
    with tempfile.TemporaryDirectory(prefix='openscrub-collect-') as temporary:
        script=Path(temporary)/'select.txt'
        script.write_text("showinfo=checksum=0,select='"+_frame_selection(wanted)+"'",encoding='utf-8')
        command=['ffmpeg','-hide_banner','-loglevel','info','-nostats','-nostdin',
                 '-threads','2','-filter_threads','1','-copyts','-i',str(path),
                 '-map','0:v:0','-an','-sn','-filter_script:v',str(script),
                 '-frames:v',str(len(wanted)),'-vsync','0','-threads','1',
                 '-f','image2pipe','-vcodec','ppm','pipe:1']
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        stopped=threading.Event();frames=queue.Queue(maxsize=1)
        metadata={};targets=set(wanted);tail=deque(maxlen=8)
        state={'frame':-1,'updated':time.monotonic(),'origin':None,'timebase':None}
        def put(value):
            while not stopped.is_set():
                try:frames.put(value,timeout=.1);return
                except queue.Full:pass
        def pixels():
            try:
                while not stopped.is_set():
                    magic=process.stdout.readline(64)
                    if not magic:break
                    if magic.strip()!=b'P6':raise ValueError('Invalid training decoder image header')
                    size=process.stdout.readline(128);maximum=process.stdout.readline(64)
                    width,height=map(int,size.split())
                    if (maximum.strip()!=b'255' or width<=0 or height<=0 or width*height>64000000):
                        raise ValueError('Invalid training decoder image dimensions')
                    remaining=width*height*3;data=bytearray()
                    while remaining:
                        chunk=process.stdout.read(min(1048576,remaining))
                        if not chunk:raise ValueError('Incomplete training source frame')
                        data.extend(chunk);remaining-=len(chunk);state['updated']=time.monotonic()
                    rgb=np.frombuffer(data,np.uint8).reshape(height,width,3)
                    put(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            except Exception as error:put(error)
            finally:put(None)
        def messages():
            try:
                for raw in iter(process.stderr.readline,b''):
                    text=raw.decode('utf-8',errors='replace');tail.append(text[-600:])
                    tb=re.search(r'config in time_base:\s*(\d+/\d+)',text)
                    if tb:state['timebase']=Fraction(tb.group(1))
                    match=re.search(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:',text)
                    if match:
                        n,pts=map(int,match.groups())
                        if n==0:state['origin']=pts
                        if n in targets:metadata[n]=pts
                        state['frame']=n;state['updated']=time.monotonic()
            except (OSError,ValueError):
                pass # The main thread checks missing timeline information.
        readers=[threading.Thread(target=pixels,daemon=True),threading.Thread(target=messages,daemon=True)]
        for reader in readers:reader.start()
        started=time.monotonic()
        def check(index):
            _collection_cancel(cancel)
            if progress:progress(state['frame'],index)
            if time.monotonic()-state['updated']>stall_timeout:
                raise TimeoutError('Training decoder made no progress for %g seconds while preparing source frame %d; saved review retained'%(stall_timeout,index))
            if time.monotonic()-started>43200:
                raise TimeoutError('Learning collection exceeded its 12-hour safety limit; saved review retained')
        try:
            for index in wanted:
                # Consumer work (crop persistence) is not a decoder stall.
                state['updated']=time.monotonic()
                while True:
                    check(index)
                    try:image=frames.get(timeout=.1);break
                    except queue.Empty:pass
                if isinstance(image,Exception):raise image
                if image is None:
                    raise ValueError('Cannot decode training source frame %d; source ended or decoder failed. %s'%(index,''.join(tail)[-600:]))
                while index not in metadata or state['origin'] is None or state['timebase'] is None:
                    check(index)
                    if not readers[1].is_alive():
                        raise ValueError('Cannot verify training source frame %d timeline'%index)
                    time.sleep(.01)
                got=float((metadata.pop(index)-state['origin'])*state['timebase'])*fps
                if abs(got-index)>.15:
                    raise ValueError('Training source frame %d does not match the reviewed timeline'%index)
                yield index,image
            # Errors after the last delivered image must not be hidden.
            while process.poll() is None:
                check(wanted[-1]);time.sleep(.05)
            if process.returncode:
                raise ValueError('Training decoder failed: '+''.join(tail)[-600:])
        finally:
            stopped.set();_stop_collection_process(process)
            for reader in readers:reader.join(timeout=2)
            process.stdout.close();process.stderr.close()


def collect_feedback(job,doc,read_frame=None,log=None):
    """Migrate existing successful annotations, then accumulate source-bound data.

    Imported images are remembered by immutable filename, so old manifests are
    never reinterpreted against a later pass's changed detection indices.
    Current report labels can revoke previously imported examples.
    """
    cancel=job.get('cancel')
    cancelled=cancel.is_set if cancel is not None else lambda:False
    _collection_cancel(cancelled)
    log=log or (lambda message:None)
    root=private_dir(Path(job['dir'])/'learning')
    private_dir(root/'samples')
    source=doc['provenance'].get('input_sha256')
    if not source:raise ValueError('Verify the source before harvesting feedback')
    store=_load(root/'feedback.json',{'schema':1,'source_sha256':source,'samples':{},'imported_images':[],
                                    'constraints':None})
    if store['source_sha256']!=source:raise ValueError('Feedback source changed')
    job['learning']={'stage':'collecting','message':'Indexing saved human decisions before collecting training images'}
    log(job['learning']['message'])
    current=vl.capture_constraints(doc)
    prior=(store.get('constraints') or {}).get('anchors',[])
    merged={a['id']:a for a in prior}
    by_frame={}
    for k,a in merged.items():by_frame.setdefault(a['frame'],{})[k]=a
    for a in current['anchors']:
        _collection_cancel(cancelled)
        # A new generation can have new IDs. Match same source frame/region,
        # using spatial agreement rather than pretending track numbers persist.
        related=[k for k,v in by_frame.get(a['frame'],{}).items() if vl._iou(v['box'],a['box'])>=.5]
        if len(related)==1:
            a['id']=related[0];a['group']=merged[related[0]].get('group',a.get('group'))
        old=merged.get(a['id'])
        if old and old['frame']!=a['frame']:
            by_frame.get(old['frame'],{}).pop(a['id'],None)
        merged[a['id']]=a
        by_frame.setdefault(a['frame'],{})[a['id']]=a
    paths={p['group']:p for p in (store.get('constraints') or {}).get('negative_paths',[])}
    paths.update({p['group']:p for p in current.get('negative_paths',[])})
    current['negative_paths']=list(paths.values())
    current['anchors']=list(merged.values());store['constraints']=current
    rows,rs=doc['detections'],doc['render_state']
    generation=(doc.get('learning') or {}).get('pass_id','initial')
    groups={}
    for i,r in enumerate(rows):
        if r.get('learning_group'):
            groups[r.get('track',-1)]=r['learning_group']
    def group_for(i,r):
        track=r.get('track',-1)
        return groups.get(track) or '%s:%s:%s'%(source,generation,('track-'+str(track) if track>=0 else 'row-'+str(i)))
    manifest=Path(job['dir'])/'plate_annotations'/'annotations.jsonl'
    seen=set(store['imported_images']);entries=[]
    if manifest.exists():
        for line in manifest.read_text(encoding='utf-8').splitlines():
            item=json.loads(line)
            if item.get('verified_by_user') is True and item.get('image') not in seen:
                entries.append(item)
    requested=[]
    for item in entries:
        i=int(item.get('detection_index',-1))
        if not 0<=i<len(rows):continue
        r=rows[i]
        if r.get('category')!='plate' or r.get('verified_label')!='plate' or not r.get('plate_quad'):continue
        frame=vl._frame(r,rs)
        if abs(float(item.get('frame_time',0))*rs['fps']-frame)>.51:continue
        requested.append((i,r,'positive',item['image']))
    # Explicit negative seed(s), not normal Keep/Blur output choices.
    negatives={}
    for i,r in enumerate(rows):
        if r.get('category')=='plate' and r.get('verified_label')=='not_plate':
            negatives.setdefault(group_for(i,r),(i,r))
    requested.extend((i,r,'negative',None) for i,r in negatives.values())
    # Explicit rejection wins over contradictory positive rows from the same
    # group, as in the previous positive-then-negative collector.
    requested=[item for item in requested if item[2]=='negative' or group_for(item[0],item[1]) not in negatives]
    requested.sort(key=lambda item:vl._frame(item[1],rs))
    # Do not decode already committed negatives when retrying a collection.
    committed={}
    for sample in store['samples'].values():committed.setdefault(sample['frame'],[]).append(sample)
    def already_saved(item):
        i,r,label,_=item
        if label!='negative':return False
        frame=vl._frame(r,rs);box=vl._screen_box(r,rs,frame)
        matches=[v for v in committed.get(frame,[]) if vl._iou(v['box'],box)>=.5]
        return len(matches)==1 and matches[0]['label']=='negative'
    requested=[item for item in requested if not already_saved(item)]
    completed=0;total=len(requested);last_notice=[0.]
    positive=sum(item[2]=='positive' for item in requested)
    def progress(decoded=-1,target=None,force=False):
        now=time.monotonic()
        if not force and now-last_notice[0]<2:return
        last_notice[0]=now
        message='Collecting reviewed examples: %d/%d (%d positive, %d negative)'%(completed,total,positive,total-positive)
        if target is not None:message+='; decoding source frame %d toward %d'%(max(0,decoded),target)
        message+='; training has not started'
        job['learning']={'stage':'collecting','message':message,'completed_examples':completed,
                         'total_examples':total,'source_frame':decoded,'target_frame':target}
        log(message)
    progress(force=True)
    wanted=sorted({vl._frame(r,rs) for _,r,_,_ in requested})
    iterator=(iter_training_frames(job['video'],wanted,float(rs['fps']),cancelled,progress)
              if read_frame is None else ((f,read_frame(f)) for f in wanted))
    created=[];committed_ok=False;last_frame=None;image=None
    try:
        with closing(iterator):
            for i,r,label,imported in requested:
                _collection_cancel(cancelled)
                frame=vl._frame(r,rs);box=vl._screen_box(r,rs,frame);group=group_for(i,r)
                related=[(k,s) for k,s in store['samples'].items()
                         if s['frame']==frame and vl._iou(s['box'],box)>=.5]
                if len(related)==1:
                    sid,previous=related[0];group=previous['group']
                    if label=='negative' and previous['label']=='negative':
                        completed+=1;progress(force=completed==total);continue
                else:sid=uuid.uuid4().hex
                if label=='positive':
                    # A newly drawn positive reverses an older rejection of that object.
                    store['samples']={k:s for k,s in store['samples'].items()
                                      if s['group']!=group or s['label']!='negative'}
                    current['negative_paths']=[p for p in current['negative_paths'] if p['group']!=group]
                    current['anchors']=[a for a in current['anchors'] if a.get('group')!=group or a.get('label')!='not_plate']
                if label=='negative':
                    store['samples']={k:s for k,s in store['samples'].items()
                                      if s['group']!=group or s['label']!='positive'}
                if frame!=last_frame:
                    decoded,image=next(iterator)
                    if decoded!=frame:raise ValueError('Training source frame order mismatch')
                    last_frame=frame
                if image is None:raise ValueError('Cannot decode reviewed frame %d for training'%frame)
                bounds=list(box);screen_points=None
                if label=='positive':
                    # Review coordinates are relative to the ORIGINAL detector box,
                    # not its training crop. Values outside [0, 1] are valid when the
                    # reviewer corrects an undersized or misplaced detector proposal.
                    context='Reviewed finding %d, frame %d: '%(i,frame)
                    recovery='. Check this finding in review and retry; saved annotations were kept.'
                    q=np.asarray(r['plate_quad'],dtype=np.float64)
                    if q.shape!=(4,2) or not np.isfinite(q).all():
                        raise ValueError(context+'expected four finite corner points'+recovery)
                    scale=np.asarray([box[2]-box[0],box[3]-box[1]],dtype=np.float64)
                    screen_points=q*scale+box[:2]
                    # The autosave API rounds box-relative coordinates to 6 decimals.
                    # Permit only that subpixel error at the source frame boundary;
                    # never clamp a genuine off-frame polygon or truncate it to a box.
                    limit=np.asarray([image.shape[1],image.shape[0]],dtype=np.float64)
                    tolerance=np.abs(scale)*0.5e-6+1e-9
                    if (not np.isfinite(screen_points).all() or np.any(screen_points < -tolerance)
                            or np.any(screen_points > limit+tolerance)):
                        raise ValueError(context+'verified corners are outside the source frame'+recovery)
                    screen_points=np.clip(screen_points,0,limit)
                    if not cv2.isContourConvex(screen_points.astype(np.float32).reshape(-1,1,2)):
                        raise ValueError(context+'corners must form a convex quadrilateral'+recovery)
                    # Include all corrected vertices before adding context and clipping
                    # the crop to the source image. Keep `box` unchanged for identity
                    # matching and comparison with the original detector's coverage.
                    bounds=[min(box[0],screen_points[:,0].min()),
                            min(box[1],screen_points[:,1].min()),
                            max(box[2],screen_points[:,0].max()),
                            max(box[3],screen_points[:,1].max())]
                x1,y1,x2,y2=vl.crop_bounds(bounds,image.shape)
                crop=image[y1:y2,x1:x2]
                if not crop.size:raise ValueError('Empty training crop for finding %d, frame %d'%(i,frame))
                points=None if screen_points is None else (
                    (screen_points-[x1,y1])/[x2-x1,y2-y1]).tolist()
                filename='samples/'+uuid.uuid4().hex+'.png'
                created.append(root/filename)
                if not cv2.imwrite(str(root/filename),crop):raise OSError('Could not persist training crop')
                if os.name!='nt':(root/filename).chmod(0o600)
                store['samples'][sid]={'image':filename,'image_sha256':sha256(root/filename),
                    'label':label,'quality':'human_quad' if label=='positive' else 'human_hard_negative',
                    'points':points,'frame':frame,'box':box,'group':group,
                    'baseline_box':[(box[0]-x1)/(x2-x1),(box[1]-y1)/(y2-y1),
                                    (box[2]-x1)/(x2-x1),(box[3]-y1)/(y2-y1)]}
                if imported:seen.add(imported)
                completed+=1;progress(force=completed==total)
            # Drive the reader to normal EOF so late decoding errors are checked.
            try:next(iterator)
            except StopIteration:pass
            else:raise ValueError('Unexpected extra training source frame')
        _collection_cancel(cancelled)
        store['imported_images']=sorted(seen)
        store['fingerprint']=feedback_fingerprint(store['samples'])
        atomic_json(root/'feedback.json',store)
        committed_ok=True
        return store
    finally:
        if not committed_ok:
            for path in created:
                try:path.unlink()
                except FileNotFoundError:pass


def export_dataset(root,feedback,destination):
    """Export snapshots only; never revisit detection IDs or approximate seeks."""
    destination=private_dir(destination);root=Path(root)
    records=[];hashes=set()
    for sid,s in sorted(feedback['samples'].items()):
        source=root/s['image']
        if sha256(source)!=s['image_sha256']:raise ValueError('Saved training image changed')
        key=(s['image_sha256'],s['label'])
        if key in hashes:continue
        hashes.add(key)
        # Group stable object examples together; do not split adjacent frames.
        split='val' if int(hashlib.sha256(s['group'].encode()).hexdigest()[:8],16)/0xffffffff<.2 else 'train'
        image_dir=private_dir(destination/'images'/split)
        label_dir=private_dir(destination/'labels'/split)
        shutil.copyfile(source,image_dir/(sid+'.png'))
        line='' if s['label']=='negative' else '0 '+' '.join('%.7f'%v for p in s['points'] for v in p)+'\n'
        (label_dir/(sid+'.txt')).write_text(line,encoding='utf-8')
        record={'image':'images/%s/%s.png'%(split,sid),'label':s['label'],'quality':s['quality'],
                'split':split,'job':s['group'],'track':0,'detection_index':s['frame'],
                'baseline_box':s['baseline_box']}
        records.append(record)
    (destination/'manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf-8')
    (destination/'data.yaml').write_text('path: '+json.dumps(str(destination.resolve()))+
        '\ntrain: images/train\nval: images/val\nnames:\n  0: plate\n',encoding='utf-8')
    return records


def trainer_script():
    root=Path(__file__).resolve().parent
    for path in (root/'scripts'/'train_plate_seg.py',root/'openscrub_train_plate_seg.py'):
        if path.is_file():return path
    raise ValueError('Training script was not packaged in this installation')


def preflight():
    python=os.environ.get('OPENSCRUB_TRAIN_PYTHON',sys.executable)
    weights=os.environ.get('OPENSCRUB_TRAIN_WEIGHTS','')
    problems=[]
    if not weights or not Path(weights).is_file():
        problems.append('Set OPENSCRUB_TRAIN_WEIGHTS to a trusted local single-class-compatible segmentation .pt checkpoint.')
    script=trainer_script()
    try:
        check=subprocess.run([python,'-c',
            'import torch,ultralytics,onnx,onnxruntime; assert torch.cuda.is_available(), "CUDA unavailable"; print(torch.cuda.get_device_name(0))'],
            capture_output=True,text=True,timeout=30)
        if check.returncode:problems.append('Training environment is not ready: '+(check.stderr.strip().splitlines() or ['unknown import failure'])[-1])
    except (OSError,subprocess.TimeoutExpired) as e:problems.append('Training Python cannot run: '+str(e))
    return {'ready':not problems,'problems':problems,'python':python,'weights':weights,'script':str(script)}


def run_training(dataset,versions,weights,job,settings):
    command=[os.environ.get('OPENSCRUB_TRAIN_PYTHON',sys.executable),str(trainer_script()),
        'train','--dataset',str(dataset),'--weights',str(weights),'--versions-dir',str(versions),
        '--device','0','--epochs',str(settings.get('epochs',40)),'--batch',str(settings.get('batch',8)),
        '--workers','0','--accept-ultralytics-license']
    private_dir(versions)
    logfile=Path(versions).parent/'training.log'
    with open(logfile,'w',encoding='utf-8') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
                                 start_new_session=os.name!='nt')
        position=0
        try:
            started=time.monotonic()
            while process.poll() is None:
                with open(logfile,encoding='utf-8',errors='replace') as output:
                    output.seek(position);text=output.read(32768);position=output.tell()
                if text:job.setdefault('log',[]).extend(text.replace(chr(13),chr(10)).splitlines()[-12:])
                if time.monotonic()-started>43200:raise TimeoutError('Training exceeded the 12-hour process limit')
                if job['cancel'].wait(.5):raise InterruptedError('Training cancelled; prior review retained')
            if process.returncode:
                tail=logfile.read_text(encoding='utf-8',errors='replace').splitlines()[-12:]
                raise ValueError('Training failed: '+'\n'.join(tail))
        finally:
            if process.poll() is None:
                if os.name!='nt':os.killpg(process.pid,signal.SIGTERM)
                else:process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name!='nt':os.killpg(process.pid,signal.SIGKILL)
                    else:process.kill()
                    process.wait()
    index=_load(Path(versions)/'index.json',{'versions':[]})
    if not index['versions']:raise ValueError('Training produced no candidate')
    version=index['versions'][-1]['version']
    folder=Path(versions)/version
    meta=_load(folder/'manifest.json')
    for name in ('model.onnx','weights.pt'):
        if sha256(folder/name)!=(meta.get('artifacts') or {}).get(name):
            raise ValueError('Training artifact integrity check failed')
    return folder,meta


def calibrate(model,dataset):
    """Require an actually tighter held-out mask without known undercoverage.

    Empty predictions keep the original proposal. This is not a statistical
    guarantee for unseen frames, nor permission to reject new detections.
    """
    dataset=Path(dataset);examples=[]
    for line in (dataset/'manifest.jsonl').read_text(encoding='utf-8').splitlines():
        r=json.loads(line)
        if r['split']!='val' or r['label']!='positive':continue
        image=cv2.imread(str(dataset/r['image']))
        if image is None:raise ValueError('Unreadable validation crop')
        h,w=image.shape[:2];label=dataset/'labels'/'val'/(Path(r['image']).stem+'.txt')
        values=[float(v) for v in label.read_text().split()[1:]]
        pts=np.asarray(values,np.float32).reshape(-1,2)*[w,h]
        gt=np.zeros((h,w),np.uint8);cv2.fillPoly(gt,[np.rint(pts).astype(np.int32)],1)
        mask,score=model.predict(image)
        if mask is not None:_,mask=vl.conservative_quad(mask)
        b=r['baseline_box'];base=np.zeros((h,w),np.uint8)
        cv2.rectangle(base,(int(b[0]*w),int(b[1]*h)),(int(b[2]*w),int(b[3]*h)),1,-1)
        examples.append((gt,base,mask,score))
    if len(examples)<4:raise ValueError('At least four held-out positive examples are required for activation')
    for threshold in sorted({.25,.5,.75,.9,.95}|{min(.999,s+.001) for _,_,_,s in examples}):
        gain=0.;accepted=0;valid=True
        for gt,base,mask,score in examples:
            if mask is None or score<threshold:continue
            coverage=float(np.logical_and(mask,gt).sum())/max(1,int(gt.sum()))
            if coverage<.995:valid=False;break
            accepted+=1
            gain+=int(np.logical_and(base,~gt.astype(bool)).sum())-int(np.logical_and(mask,~gt.astype(bool)).sum())
        if valid and accepted and gain>0:
            return {'threshold':threshold,'held_out_positive':len(examples),'accepted':accepted,
                    'excess_pixels_removed':int(gain),'minimum_known_coverage':.995,
                    'warning':'Held-out checks on this video do not prove complete redaction.'}
    raise ValueError('The trained model did not demonstrate tighter coverage without known plate-pixel loss. Previous review kept; add different corrected examples instead of repeating an unchanged scan.')


def run_session(job,read_frame,full_scan,publish,log=None,train=None,refiner=None,calibration=None):
    """Stage everything; publish only after training, full rescan and constraints.

    Injected callables allow integration tests to isolate hardware. Production
    uses run_training, actual ONNX inference, and the original scan engine.
    """
    log=log or (lambda message:None)
    root=private_dir(Path(job['dir'])/'learning')
    doc=_load(Path(job['dir'])/'report.json')
    job['learning']={'stage':'verifying','message':'Verifying the source fingerprint before using saved annotations'}
    atomic_json(root/'status.json',job['learning'])
    source=verify_source(job,doc);doc.setdefault('provenance',{})['input_sha256']=source
    settings=job.get('learning_request',{})
    if settings.get('license_accepted') is not True:
        raise ValueError('Local training license acknowledgment is required')
    def phase(name,message):
        job['learning']={'stage':name,'message':message}
        atomic_json(root/'status.json',job['learning']);log(message)
    phase('collecting','Collecting your saved positive and negative examples')
    feedback=collect_feedback(job,doc,read_frame,log=log)
    prior=(doc.get('learning') or {}).get('active', _load(root/'active.json',{}))
    if prior.get('feedback_fingerprint')==feedback['fingerprint']:
        raise ValueError('No new or changed training examples since the last accepted pass. Repeating that training is disabled; review unresolved cases first.')
    pass_id='pass-'+uuid.uuid4().hex[:12];stage=private_dir(root/'passes'/pass_id)
    atomic_json(stage/'before-report.json',doc)
    records=export_dataset(root,feedback,stage/'dataset')
    if not records:raise ValueError('There are no explicit reviewed training examples yet')
    phase('training','Training on reviewed examples; original models and previous result are unchanged')
    weights=prior.get('weights') or os.environ.get('OPENSCRUB_TRAIN_WEIGHTS','')
    folder,meta=(train or run_training)(stage/'dataset',stage/'versions',weights,job,settings)
    model=(refiner or vl.CropRefiner)(Path(folder)/'model.onnx')
    phase('validating','Checking learned mask coverage on held-out examples')
    gate=(calibration or calibrate)(model,stage/'dataset')
    phase('rescanning','Rescanning from the beginning with the original detectors')
    fresh=full_scan(stage/'raw-report.json')
    if job['cancel'].is_set():raise InterruptedError('Learning cancelled; prior result retained')
    if fresh.get('stop_review'):
        raise ValueError('A learning rescan must cover the full configured timeline')
    if fresh['provenance'].get('input_sha256')!=source:
        raise ValueError('Rescan source changed; previous result retained')
    # Keep intake provenance so re-rendering cannot silently change HDR/normalization.
    for key in ('original_input','vfr_normalized','hdr_tonemapped','hdr_output'):
        if key in doc['provenance']:
            fresh['provenance'][key]=doc['provenance'][key]
    phase('refining','Applying the learned segmentation model to original-detector proposals')
    refined,stats=vl.refine_report(job['video'],fresh,model,gate['threshold'],job['cancel'].is_set)
    refined=vl.apply_constraints(refined,feedback['constraints'])
    refined['learning']={'pass_id':pass_id,'needs_render':True,'model_sha256':meta['artifacts']['model.onnx'],
        'version':meta['version'],'feedback_fingerprint':feedback['fingerprint'],
        'inference':stats,'validation':gate,'previous_report':str(stage/'before-report.json')}
    if not stats['refined']:
        raise ValueError('The learned model made no usable refinements on the rescan. Previous review retained; add different corrected examples rather than repeat this pass.')
    if not stats['model_calls']:
        raise ValueError('The rescan produced no proposals for the learned model; previous result retained')
    if sha256(job['video'])!=source:raise ValueError('Source changed during training; previous result retained')
    active={'pass_id':pass_id,'weights':str(Path(folder)/'weights.pt'),
            'model':str(Path(folder)/'model.onnx'),'feedback_fingerprint':feedback['fingerprint']}
    refined['learning']['active']=active
    # The report is the transaction's commit record. Side indexes are recoverable.
    publish(refined)
    try:
        atomic_json(root/'active.json',active)
    except OSError as error:
        log('Active-version index could not be updated; the committed report retains it: '+str(error))
    message='Learning pass complete. Inspect remaining disagreements and rendered coverage before sharing.'
    job['learning']={'stage':'review','message':message}
    try:atomic_json(root/'status.json',job['learning'])
    except OSError:log(message)
    return refined


def preserve_render_review(before, rendered):
    """Keep row identities and rejected examples after the render-only rewrite.

    The engine serializes enabled Detection objects for its output audit. That
    projection must not replace the richer, indexed annotation store in web jobs.
    """
    expected = before.get('provenance', {}).get('input_sha256')
    if expected and expected != rendered.get('provenance', {}).get('input_sha256'):
        raise ValueError('Rendered source differs from the reviewed source; review retained')
    if before.get('render_state') != rendered.get('render_state'):
        raise ValueError('Rendered timeline differs from the review; review retained')
    result = deepcopy(rendered)
    result['detections'] = deepcopy(before['detections'])
    if before.get('learning'):
        result['learning'] = deepcopy(before['learning'])
        result['learning']['needs_render'] = False
    return result
