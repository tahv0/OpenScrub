"""Plate-free video intervals are source-bound, reversible and usable by training."""
from copy import deepcopy
import json
from pathlib import Path
import threading

import numpy as np
import pytest

import learning_session
import review_time_ranges as ranges
import video_learning
import openscrub_web as web
from test_findings_web import findings_job


def document():
    def row(frame, *, category='plate', track=7, **other):
        return dict(category=category, track=track, person=-1,
                    frame_index=frame, t_start=frame/10,
                    t_end=(frame+1)/10, cbox=[15, 20, 65, 50],
                    confidence=frame/200, enabled=True, **other)
    rows = [
        row(10),  # before
        row(50),  # inside; same physical track as before/after
        row(90),  # inside, stronger than the first
        row(100),  # outside, same track
        dict(category='plate', frame_index=-1, t_start=4.9,
             t_end=5.1, last_seen=5, track=8, person=-1,
             cbox=[15,20,65,50], enabled=True),  # straddles boundary
        row(60, track=20, verified_label='plate',
            human_confirmation={'label':'positive','source':'explicit'}),
        row(75, category='face', track=30),
    ]
    return dict(render_state=dict(fps=10, cum=[[0,0]]*200),
                provenance=dict(input_sha256='a'*64),
                source_identity=dict(input_sha256='a'*64, total_frames=200, fps=10),
                detections=rows)


def test_only_source_frames_in_the_interval_change_not_the_whole_track():
    doc=document()
    before=deepcopy(doc)
    preview=ranges.preview(doc, 5, 10)
    assert (preview['matched'], preview['protected'],
            preview['crossing_boundary']) == (2, 1, 1)
    result=ranges.apply(doc, 5, 10, training=True)
    assert result['matched']==2
    for i in (1,2):
        row=doc['detections'][i]
        assert row['enabled'] is False
        assert row['verified_label']=='not_plate'
        assert row['interval_negative']['training'] is True
        assert row['human_confirmation']['source']=='time_range'
    for i in (0,3,4,5,6):
        assert doc['detections'][i]==before['detections'][i]
    assert len(doc['plate_free_intervals'])==1


def test_training_opt_in_is_required_and_undo_restores_original_row_fields():
    doc=document()
    old=deepcopy(doc['detections'])
    ranges.apply(doc,5,10,training=False)
    assert all(doc['detections'][i]['verified_label']=='' for i in (1,2))
    assert all(doc['detections'][i]['human_confirmation']['training'] is False
               for i in (1,2))
    constraints=video_learning.capture_constraints(doc)
    assert len(constraints['plate_free_intervals'])==1
    assert not any(a['original'].get('interval_negative') for a in constraints['anchors'])
    answer=ranges.undo(doc)
    assert answer['undone']==2
    assert doc['detections']==old
    assert not doc['plate_free_intervals']
    assert 'plate_free_range_undo' not in doc


def test_overlaps_and_newer_review_edits_are_protected():
    doc=document()
    ranges.apply(doc,5,10,training=True)
    with pytest.raises(ranges.RangeConflict,match='overlap'):
        ranges.apply(doc,6,9,training=False)
    doc['detections'][1]['verified_label']='plate'
    with pytest.raises(ranges.RangeConflict,match='newer'):
        ranges.undo(doc)
    assert len(doc['plate_free_intervals'])==1


@pytest.mark.parametrize('start,end', [
    (0,0), (-1,1), (0,21), (True,9), (0,float('nan')),
    (0,float('inf')), ('00:00','02:00'),
])
def test_invalid_or_unscanned_intervals_never_change_data(start,end):
    doc=document()
    before=deepcopy(doc)
    with pytest.raises(ValueError):
        ranges.apply(doc,start,end,training=True)
    assert doc==before


def test_rescan_reapplies_negative_only_inside_same_source_frame_range():
    original=document()
    ranges.apply(original,5,10,training=True)
    constraints=video_learning.capture_constraints(original)
    # The old track crosses the boundaries; none of its OUTSIDE sightings
    # may be treated as reviewed negatives after retracking.
    assert not any(p['group'].endswith('7') for p in constraints['negative_paths'])
    new=document()
    new['detections']=[
        dict(original['detections'][0],frame_index=49,t_start=4.9,t_end=5),
        dict(original['detections'][0],frame_index=70,t_start=7.,t_end=7.1),
        dict(original['detections'][0],frame_index=100,t_start=10.,t_end=10.1)]
    result=video_learning.apply_constraints(new,constraints)
    assert [r['enabled'] for r in result['detections']]==[True,False,True]
    assert result['detections'][1]['verified_label']=='not_plate'
    assert result['detections'][1]['interval_negative']['training'] is True
    assert len(result['plate_free_intervals'])==1


def test_training_collects_one_hardest_negative_per_time_bucket_and_undo_revokes(tmp_path):
    doc=document()
    # Isolate this test to the two interval candidates, which share a
    # ten-second training bucket. Outside and face findings stay untouched.
    ranges.apply(doc,5,10,training=True)
    folder=tmp_path/'job';folder.mkdir()
    job={'dir':str(folder),'video':str(folder/'video.mp4'),
         'cancel':threading.Event(),'learning':{'stage':'collecting'},'log':[]}
    calls=[]
    def read(index):
        calls.append(index)
        return np.full((100,120,3),index,dtype=np.uint8)
    feedback=learning_session.collect_feedback(job,doc,read)
    samples=list(feedback['samples'].values())
    assert len(samples)==1
    assert samples[0]['label']=='negative'
    assert samples[0]['quality']=='human_hard_negative'
    assert samples[0]['frame']==90  # stronger false positive, same time bucket
    assert samples[0]['interval_negative_id']==doc['plate_free_intervals'][0]['id']
    assert calls==[90]
    ranges.undo(doc)
    after=learning_session.collect_feedback(job,doc,read)
    assert not any(v.get('interval_negative_id') for v in after['samples'].values())


def test_http_preview_classify_undo_persists_across_review_reopen(findings_job):
    client,job,_,report=findings_job
    endpoint='/api/jobs/'+job['id']+'/plate-free-range'
    original=report.read_bytes()
    dry=client.post(endpoint,json={'start':0,'end':1.1,'preview_only':True})
    assert dry.status_code==200, dry.get_data(as_text=True)
    assert report.read_bytes()==original
    result=client.post(endpoint,json={'start':0,'end':1.1,'training':True})
    assert result.status_code==200, result.get_data(as_text=True)
    assert result.get_json()['matched']>=1
    saved=json.loads(report.read_text())
    assert saved['plate_free_intervals'][0]['training'] is True
    listing=client.get('/api/jobs/'+job['id']+'/detections').get_json()
    assert len(listing['plate_free_intervals'])==1
    restore=client.post(endpoint,json={'undo':True})
    assert restore.status_code==200, restore.get_data(as_text=True)
    assert not json.loads(report.read_text())['plate_free_intervals']
    assert not client.get('/api/jobs/'+job['id']+'/detections').get_json()['plate_free_intervals']


def test_controls_available_in_review_html():
    assert 'plateFreeRangePanel' in web.PAGE
    assert 'previewPlateFreeRange' in web.PAGE
    assert 'applyPlateFreeRange' in web.PAGE
    assert 'plateFreeTrain' in web.PAGE
