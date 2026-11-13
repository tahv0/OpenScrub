"""SQLite Review architecture: durable small edits, immutable scans and crash recovery."""
import json
from pathlib import Path
import sqlite3

import pytest

import review_journal as journal
import review_preview_index as review_index
import stop_review


def fixture(tmp_path):
    report = tmp_path / 'report.json'
    rows = [
        dict(category='plate', track=12, person=-1, frame_index=i,
             t_start=i/30, t_end=(i+1)/30, enabled=True,
             plate_verification={'applied': True, 'previous_enabled': True},
             cbox=[10,20,50,40], plate_quad=[])
        for i in range(3)
    ]
    rows.append(dict(category='plate', track=13, person=-1, frame_index=3,
                     t_start=.1, t_end=.2, cbox=[50,30,80,50], enabled=True))
    doc = dict(detections=rows, render_state={'fps':30, 'cum':[[0,0]]*120},
               provenance={'input_sha256':'a'*64},
               source_identity={'input_sha256':'a'*64},
               preview_revision='original')
    report.write_text(json.dumps(doc), encoding='utf-8')
    return report, doc


def reject_group(journal_dir, row, index=0):
    journal.write(journal_dir,row,index,
        dict(enabled=False, output_choice_explicit=True,
             verified_label='not_plate', plate_verification_override=True,
             _remove_plate_verification=True,
             human_confirmation=dict(label='negative',category='plate',source='explicit')),
        dict(confirmed_finding_id='b'*64,confirmed_finding_revision=1))


def test_group_confirmation_does_not_rewrite_report_and_survives_restart(tmp_path):
    report, doc = fixture(tmp_path)
    original = report.read_bytes()
    reject_group(tmp_path, doc['detections'][0])
    assert report.read_bytes() == original
    # A fresh process can reconstruct exactly the same decisions from SQLite.
    restored = journal.apply(tmp_path, json.loads(original))
    for i in range(3):
        row = restored['detections'][i]
        assert row['enabled'] is False
        assert row['verified_label'] == 'not_plate'
        assert row['plate_verification_override'] is True
        assert 'plate_verification' not in row
        assert row['human_confirmation']['propagated'] is (i != 0)
    assert restored['detections'][0]['confirmed_finding_id'] == 'b'*64
    assert restored['detections'][1].get('confirmed_finding_id') is None
    assert restored['detections'][3]['enabled'] is True
    assert restored['render_required'] is True
    assert isinstance(journal.view(tmp_path,doc)['detections'],journal.PatchedRows)


def test_publish_once_creates_full_snapshot_and_retires_sqlite_changes(tmp_path):
    report, doc = fixture(tmp_path)
    reject_group(tmp_path, doc['detections'][0])
    assert journal.publish(tmp_path) is True
    snapshot = json.loads(report.read_text())
    assert snapshot['detections'][2]['enabled'] is False
    assert snapshot['detections'][3]['enabled'] is True
    assert len(snapshot[journal.MARKER]) == 32
    assert journal.has_changes(tmp_path) is False
    assert journal.publish(tmp_path) is False
    # A new scan is allowed to replace a clean published snapshot.
    stop_review.atomic_report(str(report),doc)
    assert journal.has_changes(tmp_path) is False
    reject_group(tmp_path,doc['detections'][0])
    assert journal.has_changes(tmp_path) is True


def test_report_write_failure_keeps_committed_sqlite_edits(tmp_path,monkeypatch):
    report,doc = fixture(tmp_path)
    reject_group(tmp_path,doc['detections'][0])
    original = report.read_bytes()
    real_write = stop_review.atomic_report
    def fail(*args):
        raise OSError('disk full before replace')
    monkeypatch.setattr(stop_review,'atomic_report',fail)
    with pytest.raises(OSError):
        journal.publish(tmp_path)
    assert report.read_bytes() == original
    assert journal.has_changes(tmp_path)
    monkeypatch.setattr(stop_review,'atomic_report',real_write)
    assert journal.publish(tmp_path)
    assert not journal.has_changes(tmp_path)


def test_crash_after_replace_recovers_only_matching_snapshot(tmp_path,monkeypatch):
    report,doc=fixture(tmp_path)
    reject_group(tmp_path,doc['detections'][0])
    real_write=stop_review.atomic_report
    def interrupted(*args):
        real_write(*args)
        raise OSError('process stopped after publish')
    monkeypatch.setattr(stop_review,'atomic_report',interrupted)
    with pytest.raises(OSError):
        journal.publish(tmp_path)
    # Before journal ACK, the published report includes the unique marker.
    assert json.loads(report.read_text())['detections'][0]['enabled'] is False
    assert journal.has_changes(tmp_path) is False
    assert journal.apply(tmp_path,json.loads(report.read_text()))['detections'][1]['enabled'] is False


def test_unrelated_report_replacement_preserves_journal_and_fails_closed(tmp_path):
    report,doc=fixture(tmp_path)
    reject_group(tmp_path,doc['detections'][0])
    newer=json.loads(report.read_text())
    newer['detections'][0]['track']=99
    stop_review.atomic_report(str(report),newer)
    with pytest.raises(journal.ConflictError):
        journal.view(tmp_path,newer)
    with sqlite3.connect(tmp_path/journal.NAME) as connection:
        assert connection.execute('SELECT count(*) FROM groups').fetchone()[0]==1


def test_indexed_group_count_uses_index_not_n_row_iteration(tmp_path):
    report,doc=fixture(tmp_path)
    assert review_index.prepare(report,doc)
    indexed=review_index.load(report)['detections']
    assert indexed.member_count(0)==3
    assert indexed.member_count(3)==1
    reject_group(tmp_path,doc['detections'][0])
    wrapped=journal.view(tmp_path,review_index.load(report))['detections']
    assert wrapped.member_count(1)==3
    assert wrapped[2]['enabled'] is False


def test_partial_listing_overlay_preserves_public_shape(tmp_path):
    _,doc=fixture(tmp_path)
    reject_group(tmp_path,doc['detections'][0])
    listing={'detections':[
        {'i':i,'category':r['category'],'person':r['person'],'track':r['track'],
         'enabled':r['enabled'],'verified_label':'','human_confirmation':None,
         'confirmed_finding_id':None,'confirmed_finding_revision':None,
         'output_choice_explicit':False,'plate_verification':r.get('plate_verification')}
        for i,r in enumerate(doc['detections'])]}
    updated=journal.overlay_listing(tmp_path,listing)
    assert updated['detections'][1]['enabled'] is False
    assert updated['detections'][1]['verified_label']=='not_plate'
    assert updated['detections'][1]['human_confirmation']['propagated']
    assert not updated['detections'][0]['human_confirmation']['propagated']
    assert '_remove_plate_verification' not in updated['detections'][0]
