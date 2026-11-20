"""A dead worker leader must not abandon its live OCR process group."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest
from openscrub_internal.plate_search import worker

pytestmark = pytest.mark.skipif(os.name != 'posix' or not Path('/proc').is_dir(),
                                reason='process-group oracle needs Linux /proc')


def dead(pid):
    try:
        os.kill(pid,0)
    except ProcessLookupError:
        return True
    status=Path('/proc')/str(pid)/'stat'
    return status.exists() and status.read_text().split()[2] == 'Z'


@pytest.mark.parametrize('outcome',['nonzero','bad_json','invalid_geometry','inherited_stdout','valid_orphan'])
def test_abnormal_leader_exit_reaps_group_and_job_temp(tmp_path,monkeypatch,outcome):
    marker=tmp_path/'orphan.pid'; job=tmp_path/'job';job.mkdir()
    monkeypatch.setenv('PLATE_TEST_ORPHAN',str(marker))
    original=subprocess.Popen
    output = {'nonzero':'', 'bad_json':'not json',
              'invalid_geometry':json.dumps({'complete':True,'truncated':False,'suggestions':[
                  {'box':[0,0,999,1], 'match':'fragment','boundary':'unknown'}]}),
              'inherited_stdout':'',
              'valid_orphan':json.dumps({'complete':True,'truncated':False,'suggestions':[]})}[outcome]
    destination = 'None' if outcome == 'inherited_stdout' else 'subprocess.DEVNULL'
    code = ('import os,subprocess,sys;from pathlib import Path;'
            "p=subprocess.Popen(['/bin/sleep','30'],stdin=subprocess.DEVNULL,stdout="+destination+",stderr=subprocess.DEVNULL);"
            "Path(os.environ['PLATE_TEST_ORPHAN']).write_text(str(p.pid));"
            'sys.stdout.write('+repr(output)+');sys.stdout.flush();'
            'sys.exit('+('9' if outcome=='nonzero' else '0')+')')
    def spawn(args,*a,**kw):
        assert 'KJF572' not in repr(args)
        return original([sys.executable,'-c',code],*a,**kw)
    monkeypatch.setattr(worker.subprocess,'Popen',spawn)
    payload={'query':'KJF572','mode':'fragment','width':64,'height':48}
    try:
        with pytest.raises(worker.WorkerFailed):
            worker.run(payload,str(job),lambda:False,timeout=3)
        assert marker.exists()
        assert dead(int(marker.read_text())), 'worker left its descendant running'
        assert not list(job.glob('.plate-search-*'))
    finally:
        if marker.exists():
            try: os.kill(int(marker.read_text()),signal.SIGKILL)
            except ProcessLookupError: pass


def test_clean_success_does_not_send_process_group_signal(tmp_path,monkeypatch):
    job=tmp_path/'job';job.mkdir()
    original=subprocess.Popen
    output=json.dumps({'complete':True,'truncated':False,'suggestions':[]})
    def spawn(args,*a,**kw):
        return original([sys.executable,'-c','print('+repr(output)+')'],*a,**kw)
    monkeypatch.setattr(worker.subprocess,'Popen',spawn)
    monkeypatch.setattr(worker.os,'killpg',lambda *args: pytest.fail('clean success killed a process group'))
    result=worker.run({'query':'KJF572','mode':'fragment','width':64,'height':48},
                      str(job),lambda:False,timeout=3)
    assert result['complete'] and result['suggestions']==[]
    assert not list(job.glob('.plate-search-*'))
