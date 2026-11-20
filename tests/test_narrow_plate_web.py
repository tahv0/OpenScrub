"""Optional lettering-only scan admission and saved-report rendering."""
import json
from pathlib import Path

import pytest
import openscrub
import openscrub_web as web


@pytest.fixture
def job(tmp_path,monkeypatch):
    monkeypatch.setattr(web,'load_custom_cats',lambda:[])
    monkeypatch.setattr(web,'load_model_select',lambda:{})
    monkeypatch.setattr(web,'JOBS_DIR',str(tmp_path))
    monkeypatch.setattr(web,'ZONES_PATH',str(tmp_path/'zones.json'))
    source=tmp_path/'source.mp4';source.write_bytes(b'fixture')
    return {'video':str(source),'dir':str(tmp_path),'options':{'categories':'plate'}}


def test_only_explicit_narrow_scan_enables_lettering(job):
    default=web.build_args(job)
    assert default.plate_coverage=='full' and not default._plate_coverage_explicit
    assert 'plate_coverage' not in openscrub._settings_dict(default)
    job['options']['plate_coverage']='narrow'
    selected=web.build_args(job)
    assert selected.plate_coverage=='narrow' and selected._plate_coverage_explicit
    assert selected.plate_narrow_margin==0
    assert openscrub._settings_dict(selected)['plate_coverage']=='narrow'


@pytest.mark.parametrize('value',['full','',None,'other',True,{'narrow':True}])
def test_absent_or_unrecognized_values_keep_upstream_full_default(job,value):
    job['options']['plate_coverage']=value
    args=web.build_args(job)
    assert args.plate_coverage=='full' and not args._plate_coverage_explicit
    assert 'plate_coverage' not in openscrub._settings_dict(args)


def test_render_uses_saved_report_not_job_options(job,monkeypatch):
    job['options']['plate_coverage']='narrow'
    args=web.build_args(job,for_render=True)
    assert args.plate_coverage=='full' and not args._plate_coverage_explicit
    report=Path(job['dir'])/'report.json'
    report.write_text(json.dumps({'provenance':{'settings':{'plate_coverage':'narrow'}},
        'render_state':{'fps':1,'cum':[[0,0]],'bands':[[0,0]]},'detections':[]}))
    monkeypatch.setattr(openscrub,'normalize_vfr',lambda *args:None)
    seen=[]
    monkeypatch.setattr(openscrub,'run_render',lambda a,state,cb: seen.append(a.plate_coverage) or {})
    openscrub.run_pipeline(args)
    assert seen==['narrow']
    # A saved ordinary report must not inherit an unrelated job's narrow setting.
    doc=json.loads(report.read_text());doc['provenance']['settings'].pop('plate_coverage')
    report.write_text(json.dumps(doc));args=web.build_args(job,for_render=True)
    openscrub.run_pipeline(args)
    assert seen==['narrow','full']


from test_scan_options import intake


@pytest.mark.parametrize('kind',['upload','server-path'])
def test_explicit_narrow_option_survives_real_admission(intake,kind):
    client,post,video,source,jobs_dir=intake
    response=post(kind,json.dumps({'categories':'plate','plate_coverage':'narrow'}))
    assert response.status_code==200
    job=web.JOBS[response.json['jobs'][0]]
    assert job['options']['plate_coverage']=='narrow'
    assert json.loads((Path(job['dir'])/'options.json').read_text())['plate_coverage']=='narrow'
    assert web.build_args(job).plate_coverage=='narrow'
    assert not web.build_args(job,for_render=True)._plate_coverage_explicit
