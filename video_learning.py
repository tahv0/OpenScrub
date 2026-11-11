"""Video-local correction constraints and single-class ONNX mask refinement.

Human decisions are bound to a source hash, frame and region, never a new
scanner's transient row/track IDs. The original detector remains the proposal
source. Absence of a segmentation prediction is NOT a negative classification.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np


def _frame(row, rs):
    index = row.get('frame_index', -1)
    return int(index if index >= 0 else round(float(row.get('last_seen', row['t_start'])) * rs['fps']))


def _screen_box(row, rs, frame):
    if not 0 <= frame < len(rs['cum']):
        raise ValueError('Correction frame is outside the scanned timeline')
    ox, oy = rs['cum'][frame]
    x1, y1, x2, y2 = row['cbox']
    return [float(x1+ox),float(y1+oy),float(x2+ox),float(y2+oy)]


def _iou(a, b):
    area = max(0., min(a[2],b[2])-max(a[0],b[0])) * max(0., min(a[3],b[3])-max(a[1],b[1]))
    return area / max(1e-9, (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area)


def capture_constraints(doc):
    """Capture explicit decisions. Propagated shapes are not human ground truth."""
    source = doc.get('provenance', {}).get('input_sha256')
    if not isinstance(source, str) or len(source) != 64:
        raise ValueError('A verified source hash is required before a learning pass')
    rs, rows = doc['render_state'], doc['detections']
    denied = {r['track'] for r in rows if r.get('category') == 'plate'
              and r.get('verified_label') == 'not_plate' and r.get('enabled') is False
              and not r.get('learning_anchor') and r.get('track', -1) >= 0}
    anchors = []
    for row_index, row in enumerate(rows):
        if row.get('category') != 'plate':
            continue
        label = row.get('verified_label')
        negative = (label == 'not_plate' and row.get('enabled') is False) or row.get('track', -1) in denied
        keep = row.get('enabled') is False
        if not (negative or keep or label == 'plate'):
            continue
        frame = _frame(row, rs)
        box = _screen_box(row, rs, frame)
        q = row.get('plate_quad') if label == 'plate' and not negative else None
        points = [[box[0]+float(x)*(box[2]-box[0]),box[1]+float(y)*(box[3]-box[1])]
                  for x,y in q] if q else None
        anchor = {'frame':frame,'box':box,'points':points,
                  'enabled':False if negative else not keep,
                  'label':'not_plate' if negative else label or '',
                  'original':deepcopy(row),
                  'group':row.get('learning_group') or '%s:%s:%s'%(source,(doc.get('learning') or {}).get('pass_id','initial'),('track-'+str(row['track']) if row.get('track',-1)>=0 else 'row-'+str(row_index)))}
        anchor['id'] = row.get('learning_anchor') or hashlib.sha256(
            json.dumps([source,frame,box],separators=(',',':')).encode()).hexdigest()[:24]
        anchors.append(anchor)
    paths=[]
    for track in denied:
        members=[r for r in rows if r.get('category')=='plate' and r.get('track',-1)==track]
        samples={_frame(r,rs):_screen_box(r,rs,_frame(r,rs)) for r in members}
        group=next((a['group'] for a in anchors if a['original'].get('track')==track),str(track))
        paths.append({'group':group,'samples':sorted(samples.items())})
    return {'schema':1,'negative_paths':paths,'source_sha256':source,'fps':float(rs['fps']),
            'anchors':anchors,
            'manual':[deepcopy(r) for r in rows if r.get('category')=='manual'],
            'audio_redactions':deepcopy(doc.get('audio_redactions',[]))}


def apply_constraints(doc, constraints):
    if doc.get('provenance',{}).get('input_sha256') != constraints['source_sha256']:
        raise ValueError('Correction source does not match the rescan source')
    rs = doc['render_state']
    if not math.isclose(float(rs['fps']),constraints['fps'],abs_tol=1e-8):
        raise ValueError('Correction timeline changed during the rescan')
    result = deepcopy(doc)
    rows = result['detections']
    indexed = {}
    for row in rows:
        if row.get('category')=='plate':
            indexed.setdefault(_frame(row,rs),[]).append(row)
    # Preserve reviewed negative intervals even when a new pass samples more
    # densely. Interpolate only short observed gaps, never beyond the old track.
    import bisect
    for path in constraints.get('negative_paths',[]):
        samples=path['samples'];times=[v[0] for v in samples]
        for frame,candidates in indexed.items():
            right=bisect.bisect_left(times,frame)
            if right<len(times) and times[right]==frame:
                box=samples[right][1]
            elif right==0 or right==len(times):
                continue
            else:
                a,b=samples[right-1],samples[right]
                if b[0]-a[0]>max(1,rs['fps']*.5):continue
                t=(frame-a[0])/(b[0]-a[0]);box=[x+(y-x)*t for x,y in zip(a[1],b[1])]
            matches=[r for r in candidates if _iou(_screen_box(r,rs,frame),box)>=.5]
            if len(matches)!=1:
                for r in matches:r['learning_conflict']='ambiguous reviewed-negative interval'
                continue
            match=matches[0]
            match.update(enabled=False,verified_label='not_plate',learning_group=path['group'],
                learning_anchor=hashlib.sha256(json.dumps([constraints['source_sha256'],frame,box]).encode()).hexdigest()[:24])
    next_track = max((r.get('track',-1) for r in rows),default=-1)+1
    for anchor in constraints['anchors']:
        frame = anchor['frame']
        if not 0 <= frame < len(rs['cum']):
            raise ValueError('Rescan timeline does not cover a reviewed correction')
        candidates = [(r,_iou(_screen_box(r,rs,frame),anchor['box']))
                      for r in indexed.get(frame,[])]
        matches = [(r,score) for r,score in candidates if score >= .5]
        if len(matches)>1:
            # Do not apply a negative to an ambiguous overlapping object.
            for r,_ in matches: r['learning_conflict']='ambiguous human-correction match'
            if not anchor['enabled']:
                continue
        match = max(matches,key=lambda pair:pair[1])[0] if matches else None
        if match is None:
            if not anchor['enabled']:
                continue  # absent rejected object is the intended outcome
            match = deepcopy(anchor['original'])
            ox,oy=rs['cum'][frame]
            b=anchor['box']
            match.update(cbox=[b[0]-ox,b[1]-oy,b[2]-ox,b[3]-oy],
                         frame_index=frame,t_start=frame/rs['fps'],
                         t_end=(frame+.3)/rs['fps'],track=next_track)
            next_track+=1
            rows.append(match);indexed.setdefault(frame,[]).append(match)
        match['enabled']=anchor['enabled']
        match['verified_label']=anchor['label']
        match['learning_anchor']=anchor['id']
        match['learning_group']=anchor.get('group',anchor['id'])
        if anchor['points']:
            b=_screen_box(match,rs,frame);w,h=b[2]-b[0],b[3]-b[1]
            if w<=0 or h<=0: raise ValueError('Invalid rescan box')
            match['plate_quad']=[[(x-b[0])/w,(y-b[1])/h] for x,y in anchor['points']]
            match.update(poly=[],poly_holes=[],mask_pad=0,fallback_reason='')
    existing={json.dumps(r,sort_keys=True) for r in rows if r.get('category')=='manual'}
    rows.extend(deepcopy(r) for r in constraints.get('manual',[])
                if json.dumps(r,sort_keys=True) not in existing)
    result['audio_redactions']=deepcopy(constraints.get('audio_redactions',[]))
    return result


def review_sample_details(doc, fraction=.1):
    """Budget human review by object groups, not their per-frame sightings.

    Use the same identity-before-track grouping as the review cards. Spread
    the budget over chronological groups, taking the most uncertain group in
    each batch and just one representative from it. Long tracks must not
    consume more of the review budget.
    Unknown tracks remain separate: matching appearance/boxes is not identity.
    This only selects row indices; no rendering detections are removed/merged.
    """
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError('Review fraction must be in (0, 1]')
    groups, starts = {}, {}
    for i, row in enumerate(doc['detections']):
        if (row.get('category') != 'plate' or row.get('verified_label')
                or row.get('zone_dropped')):
            continue
        person, track = row.get('person', -1), row.get('track', -1)
        key = (('person', person) if person >= 0 else
               ('track', track) if track >= 0 else ('row', i))
        start = (float(row.get('t_start', 0)), i)
        starts[key] = min(starts.get(key, start), start)
        confidence = float(row.get('confidence', 0))
        priority = (2 * bool(row.get('learning_conflict') or row.get('fallback_reason'))
                    + (1 - abs(confidence - .5) * 2))
        # Stable tie-break: repeated identical frames don't change which group
        # wins or cause a different picture on every click of the sample button.
        candidate = (priority, -i)
        if key not in groups or candidate > groups[key]:
            groups[key] = candidate
    budget = math.ceil(len(groups) * fraction)
    ordered = sorted(groups, key=starts.__getitem__)
    indices = []
    for slot in range(budget):
        # At 10%, 100 groups become ten consecutive batches of ten groups.
        # Balanced integer boundaries also handle short lists and other ratios.
        batch = ordered[slot * len(ordered) // budget:
                        (slot + 1) * len(ordered) // budget]
        _, index = max(groups[key] for key in batch)
        indices.append(-index)
    return {'indices': indices, 'fraction': fraction, 'unit': 'finding_group',
            'eligible_groups': len(groups), 'selected_groups': len(indices)}


def review_sample(doc, fraction=.1):
    """Compatibility API: one representative per selected finding group."""
    return review_sample_details(doc, fraction)['indices']


def decode_segment(outputs, shape, size, gain, left, top, threshold=.25):
    """Decode one-class raw YOLO-seg or end-to-end mask-coefficient heads.

    Returns an original-crop binary mask and score. Does not classify an empty
    result as negative. Unknown/multi-class layouts fail explicitly.
    """
    protos=[np.asarray(a) for a in outputs if np.asarray(a).ndim==4]
    heads=[np.asarray(a) for a in outputs if np.asarray(a).ndim==3]
    if len(protos)!=1 or len(heads)!=1:
        raise ValueError('Unsupported segmentation output layout')
    proto=protos[0];p=heads[0]
    if proto.shape[0]!=1 or p.shape[0]!=1 or not all(np.isfinite(x).all() for x in (proto,p)):
        raise ValueError('Invalid segmentation output layout or values')
    nm=proto.shape[1];p=p[0]
    if p.shape[0]==5+nm:
        p=p.T;end2end=False
    elif p.shape[1]==5+nm:
        end2end=False
    elif p.shape[1]==6+nm:
        end2end=True
    else:
        raise ValueError('Unsupported single-class segmentation layout')
    if not len(p): return None,0.
    scores=p[:,4];indices=np.flatnonzero(scores>=threshold)
    if not len(indices): return None,float(scores.max(initial=0))
    k=int(indices[np.argmax(scores[indices])]);r=p[k]
    if end2end:
        if int(r[5])!=0: raise ValueError('Expected a single plate class')
        x1,y1,x2,y2=map(float,r[:4]);coef=r[6:]
    else:
        cx,cy,w,h=map(float,r[:4]);x1,y1,x2,y2=cx-w/2,cy-h/2,cx+w/2,cy+h/2;coef=r[5:]
    logits=coef @ proto[0].reshape(nm,-1)
    # sigmoid(logit)>0.5 is exactly logit>0; avoids exp overflow.
    logits=logits.reshape(proto.shape[2:])
    full=cv2.resize(logits,(size,size),interpolation=cv2.INTER_LINEAR)
    yy,xx=np.ogrid[:size,:size]
    full=(full>0)&(xx>=x1)&(xx<x2)&(yy>=y1)&(yy<y2)
    h,w=shape[:2];rh,rw=int(round(h*gain)),int(round(w*gain))
    inner=full[top:top+rh,left:left+rw].astype(np.uint8)
    if not inner.size: raise ValueError('Invalid segmentation letterbox')
    mask=cv2.resize(inner,(w,h),interpolation=cv2.INTER_NEAREST)
    return (mask if mask.any() else None),float(scores[k])


def crop_bounds(box, shape):
    h,w=shape[:2];x1,y1,x2,y2=box
    pad=max(16,int(max(x2-x1,y2-y1)*.4))
    return max(0,int(x1)-pad),max(0,int(y1)-pad),min(w,int(x2)+pad+1),min(h,int(y2)+pad+1)


class CropRefiner:
    """Load the trained ONNX model in the runtime, without training dependencies."""
    def __init__(self, path, providers=None):
        import onnxruntime as ort
        options=ort.SessionOptions();options.intra_op_num_threads=2
        providers=providers or ([p for p in ('CUDAExecutionProvider','CPUExecutionProvider')
                                if p in ort.get_available_providers()])
        source=bytes(path) if isinstance(path,(bytes,bytearray)) else str(path)
        self.session=ort.InferenceSession(source,sess_options=options,providers=providers)
        inputs=self.session.get_inputs()
        if len(inputs)!=1 or len(inputs[0].shape)!=4:
            raise ValueError('Expected one NCHW segmentation input')
        dims=inputs[0].shape
        if dims[0]!=1 or dims[1]!=3 or not isinstance(dims[2],int) or dims[2]!=dims[3]:
            raise ValueError('Only fixed-size, single-image RGB segmentation models are supported')
        self.size=dims[2];self.input=inputs[0].name;self.calls=0

    def predict(self, image):
        h,w=image.shape[:2];gain=self.size/max(h,w)
        rh,rw=int(round(h*gain)),int(round(w*gain))
        left,top=(self.size-rw)//2,(self.size-rh)//2
        canvas=np.full((self.size,self.size,3),114,np.uint8)
        canvas[top:top+rh,left:left+rw]=cv2.resize(image,(rw,rh))
        blob=np.ascontiguousarray(canvas[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255
        outputs=self.session.run(None,{self.input:blob});self.calls+=1
        return decode_segment(outputs,image.shape,self.size,gain,left,top)


def conservative_quad(mask):
    """Use one inspectable four-corner outline, shared by validation and rendering."""
    padded=cv2.dilate(mask.astype(np.uint8),np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(padded,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:return None,None
    allpoints=np.concatenate(contours)
    hull=cv2.convexHull(allpoints)
    proposal=cv2.approxPolyDP(hull,.005*cv2.arcLength(hull,True),True).reshape(-1,2)
    filled=np.zeros_like(padded)
    if len(proposal)==4:
        cv2.fillConvexPoly(filled,proposal.astype(np.int32),1)
    if len(proposal)!=4 or np.logical_and(padded,filled==0).any():
        proposal=cv2.boxPoints(cv2.minAreaRect(allpoints))
    center=proposal.mean(axis=0)
    proposal=proposal[np.argsort(np.arctan2(proposal[:,1]-center[1],proposal[:,0]-center[0]))]
    proposal=np.roll(proposal,-int(np.argmin(proposal.sum(axis=1))),axis=0)
    filled[:]=0;cv2.fillConvexPoly(filled,np.rint(proposal).astype(np.int32),1)
    return proposal,filled


def refine_report(video, doc, model, threshold=.8, cancelled=None, progress=None):
    """One sequential decode, running the learned model on original proposals.

    A separate pass is intentional: crop-trained weights are never substituted
    for the full-frame detector, and post-processing cannot overwrite their
    masks. Unknown cases remain enabled and are explicitly queued for review.
    """
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError('Cannot open video for the learning refinement pass')
    result=deepcopy(doc);rs=result['render_state'];targets={}
    for row in result['detections']:
        if row.get('category')=='plate' and not row.get('zone_dropped'):
            targets.setdefault(_frame(row,rs),[]).append(row)
    stats={'model_calls':0,'refined':0,'disagreements':0,'decoded_frames':0}
    index=0
    try:
        fps=cap.get(cv2.CAP_PROP_FPS)
        if not math.isclose(fps,float(rs['fps']),rel_tol=1e-4,abs_tol=.001):
            raise ValueError('Refinement video frame rate differs from the scan timeline')
        while index < len(rs['cum']):
            if cancelled and cancelled(): raise InterruptedError('Learning pass cancelled; prior review retained')
            ok,image=cap.read()
            if not ok: break
            stats['decoded_frames']+=1
            for row in targets.get(index,[]):
                b=_screen_box(row,rs,index)
                x1,y1,x2,y2=crop_bounds(b,image.shape)
                if x2<=x1 or y2<=y1: raise ValueError('Invalid learning proposal crop')
                mask,score=model.predict(image[y1:y2,x1:x2]);stats['model_calls']+=1
                row['learning_score']=score
                if mask is None or score < threshold:
                    row['learning_conflict']='learned model uncertain; original coverage retained'
                    stats['disagreements']+=1;continue
                points,covered=conservative_quad(mask)
                w,h=b[2]-b[0],b[3]-b[1]
                if points is None or w<=0 or h<=0:
                    row['learning_conflict']='invalid learned mask; original coverage retained'
                    stats['disagreements']+=1;continue
                # A confident adjacent object's mask is not a refinement of
                # this proposal. Keep the original coverage in that case.
                center=points.mean(axis=0)+[x1,y1]
                if not (b[0]<=center[0]<=b[2] and b[1]<=center[1]<=b[3]):
                    row['learning_conflict']='mask belongs outside proposal; original coverage retained'
                    stats['disagreements']+=1;continue
                quad=[[(float(x)+x1-b[0])/w,(float(y)+y1-b[1])/h] for x,y in points]
                row.update(poly=[quad],poly_holes=[],plate_quad=quad,mask_pad=0,
                           frame_index=index,learning_conflict='',fallback_reason='')
                stats['refined']+=1
            index+=1
            if progress and index%30==0:progress(index,len(rs['cum']))
        if targets and max(targets)>=index:
            raise ValueError('Refinement decoder ended before the last detected frame')
        if index < len(rs['cum']):
            raise ValueError('Refinement decoder did not cover the scan timeline')
        if progress:progress(index,index)
        return result,stats
    finally:
        cap.release()
