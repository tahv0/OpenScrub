"""Source/frame constraints and actual ONNX mask decoding for rescan learning."""
from copy import deepcopy
import importlib
import importlib.util

import cv2
import numpy as np
import pytest


def learning():
    assert importlib.util.find_spec('video_learning'), 'Learning integration module is missing'
    return importlib.import_module('video_learning')


def report(rows):
    return {'provenance': {'input_sha256':'a'*64},
            'render_state': {'fps':10.,'cum':[[0,0]]*10,'bands':[[0,0]]*10},
            'detections': deepcopy(rows)}


def row(frame, box, **kw):
    return dict(t_start=frame/10,t_end=(frame+.3)/10,last_seen=frame/10,
                frame_index=frame,cbox=box,category='plate',text='plate',
                confidence=.8,enabled=True,dense=True,track=7,**kw)


def test_rejected_track_survives_changed_ids_and_order():
    vl=learning()
    old=report([row(2,[10,10,50,30],verified_label='not_plate'), row(3,[12,10,52,30])])
    old['detections'][0]['enabled']=False
    anchors=vl.capture_constraints(old)
    new=report([row(3,[13,10,53,30]),row(2,[11,10,51,30]),row(2,[80,10,120,30])])
    for i,r in enumerate(new['detections']): r['track']=100+i
    result=vl.apply_constraints(new,anchors)
    assert [r['enabled'] for r in result['detections']]==[False,False,True]
    assert new['detections'][0]['enabled'], 'Do not mutate staged scan input'


def test_manual_shape_wins_in_absolute_pixels_after_box_changes():
    vl=learning()
    q=[[.1,.2],[.85,.1],[.9,.8],[.12,.9]]
    old=report([row(2,[10,10,50,30],plate_quad=q,verified_label='plate')])
    anchors=vl.capture_constraints(old)
    new=report([row(2,[8,8,53,32],plate_quad=[[0,0],[1,0],[1,1],[0,1]])])
    new['detections'][0]['track']=999
    result=vl.apply_constraints(new,anchors)['detections'][0]
    b=result['cbox']; points=np.array(result['plate_quad'])*[b[2]-b[0],b[3]-b[1]]+b[:2]
    assert np.allclose(points,np.array(q)*[40,20]+[10,10])
    assert result['verified_label']=='plate'


def test_missing_manual_plate_is_reinserted_without_promoting_other_frames():
    vl=learning()
    old=report([row(2,[10,10,50,30],plate_quad=[[0,0],[1,0],[1,1],[0,1]],verified_label='plate')])
    result=vl.apply_constraints(report([]),vl.capture_constraints(old))
    assert len(result['detections'])==1
    assert result['detections'][0]['frame_index']==2


def test_constraints_reject_different_source_or_timeline():
    vl=learning(); old=report([row(2,[10,10,50,30],verified_label='not_plate')])
    a=vl.capture_constraints(old)
    new=report([]);new['provenance']['input_sha256']='b'*64
    with pytest.raises(ValueError,match='source'): vl.apply_constraints(new,a)
    new=report([]);new['render_state']['fps']=30
    with pytest.raises(ValueError,match='timeline'): vl.apply_constraints(new,a)


def test_uncertainty_budget_not_adjacent_frame_duplicates():
    vl=learning()
    rows=[row(i%10,[10,10,50,30]) for i in range(100)]
    for i,r in enumerate(rows): r.update(track=i//10,confidence=.5,frame_index=i)
    doc=report(rows)
    picks=vl.review_sample(doc,.1)
    assert len(picks)==1  # 10% of ten tracks, not 10% of 100 frame rows
    assert len({rows[i]['track'] for i in picks})==1
    doc['detections'][picks[0]]['verified_label']='plate'
    assert picks[0] not in vl.review_sample(doc,.1)


def test_segmentation_decoder_restores_letterbox_and_no_prediction_is_not_rejection():
    vl=learning()
    # 100x50 crop letterboxed to 100x100, with a 60x20 rectangle in source.
    pred=np.zeros((1,37,1),np.float32)
    pred[0,:5,0]=[50,50,60,20,.95]
    pred[0,5,0]=1
    proto=np.full((1,32,100,100),-10,np.float32)
    proto[0,0,40:60,20:80]=10
    mask,score=vl.decode_segment([pred,proto],(50,100),100,1.,0,25)
    assert mask.shape==(50,100) and score==pytest.approx(.95)
    assert mask[15:35,20:80].all()
    assert not mask[:10].any()
    pred[0,4,0]=0
    mask,score=vl.decode_segment([pred,proto],(50,100),100,1.,0,25)
    assert mask is None


def test_segmentation_decoder_rejects_unknown_output_layout():
    vl=learning()
    with pytest.raises(ValueError,match='layout'):
        vl.decode_segment([np.zeros((1,6,100)),np.zeros((1,32,20,20))],(40,50),100,2,0,10)


def test_full_refinement_pass_executes_model_and_retains_disagreement(tmp_path):
    vl=learning();path=tmp_path/'video.avi'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(160,80))
    for _ in range(10): writer.write(np.full((80,160,3),130,np.uint8))
    writer.release()
    class Model:
        calls=0
        def predict(self,crop):
            self.calls+=1
            if self.calls==2:return None,0.
            mask=np.zeros(crop.shape[:2],np.uint8)
            h,w=mask.shape;mask[h//3:2*h//3,w//3:2*w//3]=1
            return mask,.95
    model=Model();doc=report([row(2,[20,20,80,50]),row(4,[20,20,80,50])])
    result,stats=vl.refine_report(str(path),doc,model,threshold=.8)
    assert stats['model_calls']==2 and stats['decoded_frames']==10
    assert result['detections'][0]['poly']
    assert result['detections'][1]['enabled'] is True
    assert result['detections'][1]['learning_conflict']
    assert stats['refined']==1


def test_refinement_failure_does_not_change_input(tmp_path):
    vl=learning();doc=report([row(2,[20,20,80,50])]);before=deepcopy(doc)
    with pytest.raises(ValueError): vl.refine_report(str(tmp_path/'missing.mp4'),doc,object(),threshold=.8)
    assert doc==before


def test_actual_onnx_runtime_produces_mask(tmp_path):
    ort=pytest.importorskip('onnxruntime');onnx=pytest.importorskip('onnx')
    from onnx import helper,TensorProto,numpy_helper
    vl=learning()
    p=np.zeros((1,37,1),np.float32);p[0,:5,0]=[32,32,48,24,.9];p[0,5,0]=1
    masks=np.zeros((1,32,16,16),np.float32);masks[0,0,5:11,2:14]=10
    graph=helper.make_graph([
        helper.make_node('Constant',[],['output0'],value=numpy_helper.from_array(p)),
        helper.make_node('Constant',[],['output1'],value=numpy_helper.from_array(masks)),
    ],'mask fixture',[helper.make_tensor_value_info('images',TensorProto.FLOAT,[1,3,64,64])],
       [helper.make_tensor_value_info('output0',TensorProto.FLOAT,[1,37,1]),
        helper.make_tensor_value_info('output1',TensorProto.FLOAT,[1,32,16,16])])
    m=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)],ir_version=9)
    path=tmp_path/'model.onnx';onnx.save(m,path)
    model=vl.CropRefiner(path,providers=['CPUExecutionProvider'])
    mask,score=model.predict(np.full((50,100,3),120,np.uint8))
    assert mask.shape==(50,100) and mask.any() and score>.8 and model.calls==1


def test_learned_preview_quad_and_render_geometry_are_the_same(tmp_path):
    vl=learning();path=tmp_path/'video.avi'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(160,80))
    for _ in range(10):writer.write(np.full((80,160,3),130,np.uint8))
    writer.release()
    class Model:
        def predict(self,crop):
            m=np.zeros(crop.shape[:2],np.uint8);m[25:40,25:65]=1
            return m,.95
    out,_=vl.refine_report(str(path),report([row(2,[20,20,80,50])]),Model(),threshold=.8)
    r=out['detections'][0]
    assert len(r.get('plate_quad',[]))==4
    assert r['poly']==[r['plate_quad']]


def test_learning_scan_records_every_plate_frame_even_with_fast_preset(tmp_path,monkeypatch):
    import openscrub
    path=tmp_path/'scan.mp4';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),30,(160,90))
    for i in range(30):writer.write(np.full((90,160,3),100,np.uint8))
    writer.release()
    class Detector:
        INPUT=640
        def __init__(self,*a,**k):pass
        def available(self):return True
        def find(self,*a,**k):return [(40,30,120,60,.95)]
    monkeypatch.setattr(openscrub,'PlateDetector',Detector)
    p=openscrub.build_parser()
    args=openscrub._prep_args(p.parse_args([str(path),'--categories','plate',
        '--no-backtrack','--scroll-track','off','--scan-speed','fast']),p)
    args.plate_learning_exact=True
    class Quiet(openscrub.Callbacks):
        def log(self,*a):pass
    state=openscrub.run_scan(args,Quiet())
    assert {d.frame_index for d in state['detections'] if d.category=='plate'}==set(range(30))


def test_inherited_negative_does_not_expand_to_a_newly_merged_track():
    vl=learning()
    old=report([row(2,[10,10,50,30],verified_label='not_plate')])
    old['detections'][0].update(enabled=False,track=88)
    new=report([row(2,[10,10,50,30]),row(4,[12,10,52,30])])
    inherited=vl.apply_constraints(new,vl.capture_constraints(old))
    second=vl.apply_constraints(new,vl.capture_constraints(inherited))
    assert second['detections'][0]['enabled'] is False
    assert second['detections'][1]['enabled'] is True


def test_negative_track_covers_new_intermediate_samples_without_extending_its_lifetime():
    vl=learning()
    old=report([row(2,[10,10,50,30],verified_label='not_plate'),row(6,[14,10,54,30])])
    for r in old['detections']:r['enabled']=False
    new=report([row(i,[10+i-2,10,50+i-2,30]) for i in (2,3,4,5,6,9)])
    result=vl.apply_constraints(new,vl.capture_constraints(old))
    assert [r['enabled'] for r in result['detections']]==[False]*5+[True]
