"""Failure injection for persistent diagnostics; no footage or GPU required."""
import importlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest


def module():
    assert importlib.util.find_spec('openscrub_logging'), 'Persistent logging is missing'
    return importlib.import_module('openscrub_logging')


@pytest.fixture
def diagnostics(tmp_path):
    d = module()
    output = io.StringIO()
    runtime = d.configure(tmp_path, stream=output, install_hooks=False,
                          max_bytes=8192, backups=2)
    yield d, runtime, output, tmp_path
    d.shutdown()


def contents(root):
    return '\n'.join(p.read_text() for p in (root/'logs').glob('openscrub.log*'))


def test_exception_is_on_disk_and_console_with_context(diagnostics):
    d, runtime, console, root = diagnostics
    job = {'id':'abc123', 'phase':'learning', 'learning':{'stage':'refining'}}
    try:
        raise RuntimeError('injected CUDA failure')
    except RuntimeError:
        d.exception('learning_failed', job)
    text = contents(root)
    for phrase in ('learning_failed', 'abc123', 'refining', 'Traceback', 'injected CUDA failure'):
        assert phrase in text and phrase in console.getvalue()


def test_job_list_messages_persist_without_losing_list_semantics(diagnostics):
    d, runtime, console, root = diagnostics
    job = {'id':'job123', 'phase':'scanning','log':['prior line']}
    d.attach_job(job)
    job['log'].append('first')
    job['log'].extend(['second','third'])
    assert job['log'][-3:] == ['first','second','third']
    assert json.loads(json.dumps(job['log'])) == ['prior line','first','second','third']
    assert contents(root).count('message=first') == 1
    assert 'prior line' not in contents(root)


def test_log_rotation_is_bounded(diagnostics):
    d, runtime, console, root = diagnostics
    for i in range(1000):
        d.event('sample', sequence=i, message='x'*180)
    files = list((root/'logs').glob('openscrub.log*'))
    assert 1 <= len(files) <= 3
    assert sum(p.stat().st_size for p in files) < 30000
    assert 'sequence=999' in contents(root)


def test_tokens_ansi_and_newline_forgery_are_removed(diagnostics):
    d, runtime, console, root = diagnostics
    d.set_secrets(['super-secret-value'])
    d.event('request_error', message='\x1b[31mbad\x1b[0m ?token=private123 password=private456 super-secret-value\nFORGED')
    text=contents(root)
    for secret in ('private123','private456','super-secret-value','\x1b'):
        assert secret not in text
    assert '\nFORGED' not in text


def test_failed_disk_handler_does_not_raise_and_warns_on_console(diagnostics,monkeypatch):
    d, runtime, console, root = diagnostics
    def broken(*a,**k): raise OSError(28,'No space left on device')
    monkeypatch.setattr(runtime.file_handler, 'shouldRollover', broken)
    d.event('still_visible', message='job failure')
    assert 'still_visible' in console.getvalue()
    assert 'persistent_log_write_failed' in console.getvalue()


def test_unwritable_log_directory_has_explicit_console_fallback(tmp_path):
    d=module(); (tmp_path/'logs').write_text('not a directory'); console=io.StringIO()
    try:
        d.configure(tmp_path,stream=console,install_hooks=False)
        d.event('fallback_evidence')
        assert 'persistent_logging_unavailable' in console.getvalue()
        assert 'fallback_evidence' in console.getvalue()
    finally: d.shutdown()


def test_unclean_exit_marker_is_reported_on_next_start(tmp_path):
    d=module(); logs=tmp_path/'logs';logs.mkdir()
    (logs/'running.json').write_text(json.dumps({'pid':123,'active_jobs':[{'id':'lostjob','stage':'refining'}]}))
    console=io.StringIO()
    try:
        d.configure(tmp_path,stream=console,install_hooks=False)
        assert 'previous_process_did_not_shutdown_cleanly' in console.getvalue()
        assert 'lostjob' in console.getvalue()
    finally:d.shutdown()
    assert not (logs/'running.json').exists()


def test_heartbeat_has_stage_progress_and_stall_without_changing_job(diagnostics):
    d, runtime, console, root = diagnostics
    job={'id':'abc','phase':'learning','learning':{'stage':'refining'},'progress':.5}
    d.start_job(job,'learn');d.progress(job,'refining',12,100)
    runtime.heartbeat_once(now=runtime.clock()+400)
    text=contents(root)
    assert 'job_heartbeat' in text and 'refining' in text and 'current=12' in text
    assert 'no_recent_progress' in text
    assert job['phase']=='learning' and job['progress']==.5
    d.finish_job(job,'learn')


def test_caught_learning_failure_has_traceback_and_preserves_report(diagnostics,monkeypatch):
    d, runtime, console, root = diagnostics
    import openscrub_web as web
    job={'id':'learningjob','dir':str(root),'phase':'learning','learning_previous_phase':'paused',
         'learning_request':{},'cancel':threading.Event(),'stop':threading.Event(),'log':[]}
    report=root/'report.json';report.write_text('{"original": true}')
    def failure(*a,**k): raise RuntimeError('injected refiner failure')
    monkeypatch.setattr(web.learning_session,'preflight',lambda:{'ready':True})
    monkeypatch.setattr(web.learning_session,'run_session',failure)
    web.perform_learning(job)
    assert job['phase']=='paused'
    assert report.read_text()=='{"original": true}'
    assert 'injected refiner failure' in contents(root) and 'Traceback' in contents(root)


def test_http_failure_logs_route_without_query_or_request_payload(diagnostics,monkeypatch):
    d, runtime, console, root = diagnostics
    import openscrub_web as web
    monkeypatch.setattr(web,'TOKEN',None)
    monkeypatch.setitem(web.app.config,'TESTING',False)
    response=web.app.test_client().post('/api/jobs/no-such-job/learning?token=DO_NOT_LOG',json={'private':'never-log-body'})
    assert response.status_code==404
    text=contents(root)
    assert 'http_request_failed' in text and 'status=404' in text
    assert 'DO_NOT_LOG' not in text and 'never-log-body' not in text


def test_preview_failure_includes_tool_exit_and_stderr(diagnostics,monkeypatch):
    d, runtime, console, root = diagnostics
    import openscrub_web as web
    monkeypatch.setattr(web.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a[0],9,b'',b'injected codec failure'))
    with web.app.test_request_context('/api/jobs/job1/plate_quad/2'):
        with pytest.raises(Exception): web._review_process(['ffmpeg','-i','secret-video'])
    text=contents(root)
    assert 'preview_process_failed' in text and 'returncode=9' in text and 'injected codec failure' in text


@pytest.mark.skipif(os.name == "nt", reason="Uses POSIX abort and core-dump controls")
def test_native_abort_leaves_fault_file_and_unclean_marker(tmp_path):
    d=module()
    code='''import resource,os
import openscrub_logging as d
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
d.configure(%r)
os.abort()
''' % str(tmp_path)
    p=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=15)
    assert p.returncode != 0
    assert (tmp_path/'logs'/'running.json').exists()
    assert 'Fatal Python error' in (tmp_path/'logs'/'faults.log').read_text()


def test_unhandled_thread_has_full_traceback(tmp_path):
    d=module()
    code='''import threading
import openscrub_logging as d
d.configure(%r)
def fail(): raise RuntimeError('thread injection')
t=threading.Thread(target=fail,name='failing-test-worker');t.start();t.join()
d.shutdown()
''' % str(tmp_path)
    p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=15)
    assert p.returncode==0,p.stderr
    text=contents(tmp_path)
    assert 'thread_unhandled_exception' in text and 'thread injection' in text and 'Traceback' in text


def test_logging_module_is_packaged_and_copied_into_docker():
    from pathlib import Path
    root=Path(__file__).parent
    assert 'openscrub_logging.py' in (root/'pyproject.toml').read_text()
    for path in root.glob('Dockerfile*'):
        text=path.read_text()
        if 'COPY openscrub.py' in text: assert 'openscrub_logging.py' in text,path


def test_http_500_has_traceback_in_persistent_log(diagnostics,monkeypatch):
    d, runtime, console, root=diagnostics
    import openscrub_web as web
    monkeypatch.setattr(web,'TOKEN',None)
    monkeypatch.setitem(web.app.config,'TESTING',False)
    def broken():raise RuntimeError('HTTP 500 injection')
    monkeypatch.setitem(web.app.view_functions,'index',broken)
    response=web.app.test_client().get('/?token=secret-query')
    assert response.status_code==500
    text=contents(root)
    assert 'http_unhandled_exception' in text and 'HTTP 500 injection' in text and 'Traceback' in text
    assert 'secret-query' not in text


def test_actual_worker_logs_failure_and_completes_queue_task(diagnostics,monkeypatch):
    d, runtime, console, root=diagnostics
    import openscrub_web as web
    job={'id':'workerjob','dir':str(root),'phase':'queued','log':[], 'error':None,
         'cancel':threading.Event(),'stop':threading.Event()}
    class EndWorker(BaseException):pass
    class Queue:
        def __init__(self):self.n=0;self.completed=0
        def get(self):
            self.n+=1
            if self.n>1:raise EndWorker()
            return 'workerjob','scan'
        def task_done(self):self.completed+=1
    q=Queue()
    def fail(*a,**k):raise RuntimeError('worker path injection')
    monkeypatch.setattr(web,'WORK_Q',q)
    monkeypatch.setattr(web,'JOBS',{'workerjob':job})
    monkeypatch.setattr(web,'build_args',fail)
    with pytest.raises(EndWorker):web.worker()
    assert q.completed==1 and job['phase']=='error'
    assert 'job_action_failed' in contents(root) and 'worker path injection' in contents(root)
    assert 'Traceback' in contents(root) and not runtime.active


def test_child_process_failure_logs_exit_and_final_output(diagnostics,monkeypatch):
    d, runtime, console, root=diagnostics
    import learning_session as ls
    script=root/'fail.py';script.write_text("print('final child output',flush=True)\nraise SystemExit(23)\n")
    monkeypatch.setenv('OPENSCRUB_TRAIN_PYTHON',sys.executable)
    monkeypatch.setattr(ls,'trainer_script',lambda:script)
    job={'id':'child','cancel':threading.Event(),'log':[]}
    with pytest.raises(ValueError):ls.run_training(root/'dataset',root/'versions',root/'weights',job,{})
    text=contents(root)
    assert 'training_process_started' in text and 'training_process_exited' in text and 'returncode=23' in text
    assert 'final child output' in '\n'.join(job['log'])


def test_training_child_enables_native_fault_traceback():
    import learning_session as ls
    cmd=ls._training_command(Path('/trusted/trainer.py'),'train')
    assert cmd[cmd.index('-X')+1]=='faulthandler'


def test_background_model_download_error_is_persisted(diagnostics,monkeypatch):
    d, runtime, console, root=diagnostics
    import openscrub_web as web
    class InlineThread:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    def fail(*a,**k):raise RuntimeError('model download injection')
    monkeypatch.setattr(web.threading,'Thread',InlineThread)
    monkeypatch.setattr(web,'TOKEN',None)
    monkeypatch.setattr(web,'_model_dl',{'state':'idle'})
    monkeypatch.setattr(web.openscrub,'load_model_registry',lambda kind:[{'id':'fixture'}])
    monkeypatch.setattr(web.openscrub,'download_model',fail)
    result=web.app.test_client().post('/api/models/plate/fixture/download')
    assert result.status_code==200
    assert web._model_dl['state']=='error'
    assert 'model_download_failed' in contents(root) and 'model download injection' in contents(root)


def test_preflight_failure_records_full_captured_stderr(diagnostics,monkeypatch):
    d, runtime, console, root=diagnostics
    import learning_session as ls
    monkeypatch.setattr(ls.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a[0],1,'','Traceback: intermediate detail\nERROR: final line'))
    state=ls.preflight()
    assert not state['ready']
    text=contents(root)
    assert 'training_preflight_failed' in text and 'intermediate detail' in text


def test_auth_failure_is_logged_without_exposing_token(diagnostics,monkeypatch):
    d, runtime, console, root=diagnostics
    import openscrub_web as web
    monkeypatch.setattr(web,'TOKEN','real-auth-secret')
    d.set_secrets(['real-auth-secret'])
    response=web.app.test_client().get('/api/jobs?token=wrong-auth-secret')
    assert response.status_code in (401,403)
    text=contents(root)
    assert 'http_request_failed' in text
    assert 'real-auth-secret' not in text and 'wrong-auth-secret' not in text


def test_regular_logs_survive_normal_server_restart(tmp_path):
    d=module();stream=io.StringIO()
    try:
        d.configure(tmp_path,stream=stream,install_hooks=False)
        d.event('before_restart',{'id':'old-job','phase':'learning'})
        d.shutdown()
        d.configure(tmp_path,stream=stream,install_hooks=False)
        d.event('after_restart')
        text=contents(tmp_path)
        assert 'before_restart' in text and 'old-job' in text and 'after_restart' in text
        assert 'previous_process_did_not_shutdown_cleanly' not in text
    finally:d.shutdown()


def test_structured_training_progress_reaches_persistent_heartbeat(diagnostics):
    d, runtime, console, root = diagnostics
    import learning_session as ls
    job = {'id': 'telemetry', 'phase': 'learning', 'log': []}
    d.start_job(job, 'learn')
    ls.update_learning(job, 'training', 'Training', done=2, total=8,
                       epoch=1, epochs=40, unit='batches')
    runtime.heartbeat_once()
    text = contents(root)
    assert 'stage=training' in text and 'current=2 total=8' in text
    assert job['learning']['epoch'] == 1
    assert job['learning']['done'] == 2
    activity = job['_diagnostic_activity']
    ls.update_learning(job)  # A status refresh is not completed work.
    assert job['_diagnostic_activity'] == activity
    d.finish_job(job, 'learn')


def test_repeated_learning_scan_progress_does_not_reset_stall_clock(diagnostics):
    d, runtime, console, root = diagnostics
    import openscrub_web as web
    job = {'id': 'scan-progress', 'phase': 'learning', 'log': [], 'options': {}}
    callback = web.WebCallbacks(job)
    callback.progress('scan', 12, 100)
    activity = job['_diagnostic_activity']
    callback.progress('scan', 12, 100)
    assert job['_diagnostic_activity'] == activity
    assert job['_diagnostic_progress']['current'] == 12
