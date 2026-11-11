"""Rebased diagnostics/recovery retain current progress and portable policies."""
import io
import threading
from copy import deepcopy

import pytest

import learned_models as lm
import learning_session as ls
import openscrub_logging as logs
import openscrub_web as web

VALIDATION = {'threshold': .75, 'held_out_positive': 8, 'accepted': 6,
              'excess_pixels_removed': 120, 'minimum_known_coverage': .995}


def test_saved_model_metadata_retains_calibrated_margin():
    supplied = dict(VALIDATION, margin_fraction=.03, warning='not a guarantee')
    result = lm._validation(supplied, allow_warning=True)
    assert result == dict(VALIDATION, margin_fraction=.03)
    assert lm._validation(result) == result
    assert lm._validation(VALIDATION) == VALIDATION  # Old portable models remain valid.


@pytest.mark.parametrize('value', [-.01, .051, float('nan'), float('inf'), True, '0.03'])
def test_portable_policy_refuses_invalid_margin(value):
    with pytest.raises(lm.ModelError):
        lm._validation(dict(VALIDATION, margin_fraction=value), allow_warning=True)


def test_selected_model_reuses_margin_and_section_bounds(monkeypatch):
    meta = {'id': 'model', 'name': 'Camera', 'contract': 1, 'model_sha256': 'a'*64,
            'input_size': 640, 'threshold': .75,
            'validation': dict(VALIDATION, margin_fraction=.03)}
    job = {'id':'job', 'dir':'unused', 'phase':'scanning', 'log':[],
           'cancel':threading.Event(),
           'options':{'learned_plate_model':'model','section_context':[10,30]}}
    original = {'provenance':{'input':'unused.mp4'}}
    calls = []
    monkeypatch.setattr(lm,'load_snapshot',lambda _: (meta, b'not executed'))
    monkeypatch.setattr(web.video_learning,'CropRefiner',lambda _: object())
    def refine(video, report, model, **kwargs):
        calls.append(kwargs)
        return deepcopy(report), {'refined':1,'disagreements':0}
    monkeypatch.setattr(web.video_learning,'refine_report',refine)
    result = web.apply_selected_plate_model(job,original)
    assert calls[0]['margin_fraction'] == .03
    assert calls[0]['frame_range'] == (10,30)
    assert result['refinement']['margin_fraction'] == .03
    assert original == {'provenance':{'input':'unused.mp4'}}


def test_learning_progress_reaches_logs_without_polling_reset(tmp_path,monkeypatch):
    stream = io.StringIO()
    runtime = logs.configure(tmp_path, stream=stream, install_hooks=False)
    try:
        job = {'id':'train', 'phase':'learning','log':[]}
        logs.start_job(job,'learn')
        ls.update_learning(job,'training','Training',done=2,total=20,epoch=1)
        activity = job['_diagnostic_activity']
        ls.update_learning(job)  # A status heartbeat is not completed work.
        assert job['_diagnostic_activity'] == activity
        runtime.heartbeat_once(now=activity+400)
        text=stream.getvalue()
        assert 'stage=training' in text and 'no_recent_progress' in text
        assert 'current=(2, 1' in text
        logs.finish_job(job,'learn')
    finally:
        logs.shutdown()
