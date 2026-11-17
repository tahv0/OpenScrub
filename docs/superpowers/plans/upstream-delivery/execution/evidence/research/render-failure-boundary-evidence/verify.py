"""Verify the retained bounded evidence; do not rerun product renders."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = Path('/tmp/openscrub-render-failure-20261117')
r = json.loads((HERE / 'results.json').read_text())
cases = {c['name']: c for c in r['cases']}
assert len(cases) == 7
children = 0
for c in cases.values():
    assert c['before']['report'] == c['after']['report']
    assert c['partial_paths'] == []
    clean = c['after_harness_cleanup']
    assert not any(clean['captures_open'])
    assert all(clean['stderr_temps_closed'])
    for p in clean['children']:
        children += 1
        assert p['returncode'] is not None and p['proc_state'] is None
        assert p['stdin_closed'] is not False and p['stdout_closed'] is not False

early = cases['pre_encoder_concealed_source_nan']
assert early['production_terminal']['children'] == []
assert early['before'] == early['after']
for name in ('default_source_nan', 'sdr_mid_render_nonfinite_translation',
             'hdr_mid_render_nonfinite_translation'):
    c = cases[name]
    assert c['exception']['type'] in ('ValueError', 'OverflowError')
    assert any(p['returncode'] is None for p in c['production_terminal']['children'])
for name in ('sdr_mid_render_nonfinite_translation', 'hdr_mid_render_nonfinite_translation'):
    c = cases[name]
    assert c['after_resource_cleanup_files']['video'] != c['before']['video']
    assert len(c['harness_removed_partial_paths']) == 1
    assert not c['after_harness_cleanup_files']['video']['exists']
assert not cases['direct_checkpoint_cancel']['after']['video']['exists']

for name, phase in (('worker_final_report_replace_failure', 'error'),
                    ('worker_cancel_after_video_before_report_ack', 'cancelled')):
    c = cases[name]
    assert c['job_terminal']['phase'] == phase
    assert c['before']['video'] != c['after']['video']
    assert c['job_terminal']['files_count'] == c['job_terminal']['files_work'] == 0
    assert c['job_terminal']['global_files_count'] == 0
    assert c['job_terminal']['active'] is False
    assert c['job_terminal']['worker_current'] is None
cancel = cases['worker_cancel_after_video_before_report_ack']
assert cancel['cancel_http_status'] == 200
assert cancel['at_hash_gate']['ownership']['active_operation_current']
assert cancel['after_cancel_ack']['active']
assert cancel['after_cancel_ack']['files_work'] == 1
assert cancel['after_cancel_ack']['operation_present'] is False

# Prove both original fixtures and changed final worker outputs are videos.
media = {}
for name in ('input.mp4', 'previous.mp4',
             'worker_final_report_replace_failure/output.mp4',
             'worker_cancel_after_video_before_report_ack/output.mp4'):
    p = ROOT / name
    proc = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                           '-show_entries', 'stream=codec_name,width,height,nb_frames',
                           '-of', 'json', str(p)], capture_output=True,
                          text=True, check=True, timeout=10)
    info = json.loads(proc.stdout)['streams'][0]
    assert info['width'] == info['height'] == 64 and int(info['nb_frames']) == 8
    media[name] = info

manifest = dict(r['modules'])
for name in ('openscrub_internal/lifetimes.py', 'openscrub_gui.py',
             'tests/test_report_transactions.py', 'tests/test_job_lifecycle.py'):
    manifest[name] = hashlib.sha256((ROOT / 'pinned' / name).read_bytes()).hexdigest()
for name in ('probe.py', 'verify.py'):
    ast.parse((HERE / name).read_text(), feature_version=(3, 9))
summary = {'status': 'verified bounded evidence', 'case_count': len(cases),
           'observed_children_all_reaped_by_harness': children,
           'all_tracked_pipes_temps_captures_closed_by_harness': True,
           'all_changed_direct_failure_partials_removed_by_harness': True,
           'prior_reports_preserved_in_all_cases': True,
           'worker_failure_and_cancel_changed_final_video': True,
           'valid_media': media, 'pinned_source_sha256': manifest,
           'harness_syntax_accepts_python39_grammar': True}
print(json.dumps(summary, indent=2))
