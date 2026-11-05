"""Real localizer evidence with supplied synthetic plate boxes, not locator recall."""
from dataclasses import asdict
from collections import Counter
from pathlib import Path
import json
import os
import subprocess
import time
import cv2
import numpy as np


def make_narrow_job(root, web):
    engine=web.openscrub
    model_dir=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'openscrub-evidence-models'
    model_dir.mkdir(parents=True,exist_ok=True)
    engine._model_dir=lambda:str(model_dir)
    localizer=engine.TextRegionDetector(verify_hash=True)
    if not localizer.available():
        raise RuntimeError('The real pinned text localizer is unavailable')
    jdir=root/'ui-fixtures/jobs/synthetic-lettering'
    jdir.mkdir(parents=True,exist_ok=True)
    src=jdir/'input.webm'
    fps,n=120,48
    frames=[]
    truths=[]
    boxes=[]
    for fi in range(n):
        frame=np.full((360,640,3),(32,27,23),np.uint8)
        cv2.rectangle(frame,(8,8),(28,28),((fi%12)*20,)*3,-1)
        cv2.putText(frame,'SYNTHETIC LETTERING REVIEW',(45,40),cv2.FONT_HERSHEY_SIMPLEX,.65,(230,230,230),1)
        cv2.putText(frame,'Real text detector; supplied plate box',(45,65),cv2.FONT_HERSHEY_SIMPLEX,.45,(190,190,190),1)
        plate=np.full((120,240,3),240,np.uint8)
        truth=np.zeros((120,240),np.uint8)
        lines=[('AB-123',(42,75),1.4,3)] if fi<24 else [('AB123',(50,50),1.2,3),('XY7',(75,90),.65,2)]
        for text,origin,scale,thick in lines:
            cv2.putText(plate,text,origin,cv2.FONT_HERSHEY_SIMPLEX,scale,(20,20,20),thick,cv2.LINE_AA)
            cv2.putText(truth,text,origin,cv2.FONT_HERSHEY_SIMPLEX,scale,255,thick,cv2.LINE_AA)
        x,y=180+fi*3,120
        frame[y:y+120,x:x+240]=plate
        full=np.zeros((360,640),np.uint8);full[y:y+120,x:x+240]=truth
        frames.append(frame);truths.append(full>0);boxes.append((x,y,x+240,y+120))
    cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s','640x360','-r',str(fps),'-i','-','-an','-c:v','libvpx-vp9','-lossless','1','-pix_fmt','yuv444p',str(src)]
    p=subprocess.run(cmd,input=b''.join(f.tobytes() for f in frames),capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace'))
    cap=cv2.VideoCapture(str(src))
    detections=[];rows=[]
    for fi,box in enumerate(boxes):
        ok,frame=cap.read()
        if not ok:raise RuntimeError('Synthetic frame missing')
        t=time.perf_counter();polys,reason=localizer.find_plate(frame,box);ms=(time.perf_counter()-t)*1000
        x,y,x2,y2=box
        normalized=tuple(tuple(((float(a)-x)/(x2-x),(float(b)-y)/(y2-y)) for a,b in poly) for poly in polys)
        d=engine.Detection(fi/fps,(fi+1)/fps,box,'plate','plate',0.0,last_seen=fi/fps,dense=True,track=17,poly=normalized,mask_pad=0 if polys else -1,frame_index=fi,fallback_reason=reason)
        detections.append(dict(asdict(d),enabled=True))
        mask=np.zeros((360,640),np.uint8)
        if polys:cv2.fillPoly(mask,[np.rint(a).astype(np.int32)for a in polys],1)
        else:mask[y:y2,x:x2]=1
        missed=int(np.count_nonzero(truths[fi]&(mask==0)))
        rows.append(dict(frame=fi,groups=len(polys),fallback=reason,missed_glyph_pixels=missed,milliseconds=round(ms,2)))
    cap.release()
    if any(r['missed_glyph_pixels'] for r in rows):raise AssertionError('Accepted localizer UI fixture missed labelled glyph pixels: '+json.dumps(rows))
    if not any(r['groups']>0 and r['frame']<24 for r in rows):raise AssertionError('No accepted clean hyphen example')
    if not any(r['groups']>=2 and r['frame']>=24 for r in rows):raise AssertionError('No accepted clean unequal-row example')
    doc=dict(provenance=dict(input=str(src),original_input='synthetic-lettering.webm',settings=dict(pad=8,mode='box',plate_coverage='narrow',plate_narrow_margin=0,hdr_output='sdr')),render_state=dict(fps=fps,cum=[[0,0]]*n,bands=[[0,0]]*n),detections=detections)
    (jdir/'report.json').write_text(json.dumps(doc))
    summary=dict(scope='Synthetic localizer with supplied plate boxes; not plate locator recall',model_sha256=engine.PPDET_SHA256,frames=n,fps=fps,accepted=sum(r['groups']>0 for r in rows),fallbacks=dict(Counter(r['fallback'] for r in rows if r['fallback'])),cases=rows)
    (root/'narrow-model-ui-evidence.json').write_text(json.dumps(summary,indent=2))
    return summary
