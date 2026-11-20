"""A Resume acknowledgement identifies the exact report generation."""

import os

import pytest
from werkzeug.exceptions import Conflict

import openscrub_web as web
from test_job_lifecycle import store


def token(job):
    files = web.FILES.initialize(job)
    with files.report_lock:
        return web._checkpoint_resume_token_locked(job)


def test_resume_token_tracks_incarnation_commit_epoch_and_report_stamp(store):
    initial = token(store.job)
    assert len(initial) == 64 and all(c in '0123456789abcdef' for c in initial)
    assert token(store.job) == initial
    files = web.FILES.initialize(store.job)
    files.committed_report_epoch += 1
    after_commit = token(store.job)
    assert after_commit != initial
    store.path.write_text(store.path.read_text() + ' ')
    after_external_edit = token(store.job)
    assert after_external_edit != after_commit
    replacement = store.path.with_name('replacement.json')
    replacement.write_bytes(store.path.read_bytes())
    os.replace(replacement, store.path)
    assert token(store.job) != after_external_edit
    before_incarnation = token(store.job)
    files.incarnation = 'f' * 32
    assert token(store.job) != before_incarnation


def test_resume_token_rejects_missing_or_nonregular_report(store):
    store.path.unlink()
    with pytest.raises(Conflict):
        token(store.job)
    store.path.mkdir()
    with pytest.raises(Conflict):
        token(store.job)
