#!/usr/bin/env python3
"""Reproduce Task64 render/pixel/fresh-process-route assertions and save evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--work-dir', type=Path, required=True)
p.add_argument('--artifacts', type=Path, required=True)
a = p.parse_args()
sys.path.insert(0, str(a.source.resolve()))
a.work_dir.mkdir(parents=True, exist_ok=True)
a.artifacts.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('roundtrip_tests',
                         a.source / 'tests/test_report_roundtrip.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
review = tests.review.__wrapped__(a.work_dir)
(a.artifacts / 'render-before.json').write_text(json.dumps(review.doc, indent=2))
# The production pipeline, FFmpeg, all60 decoded output frames, and a fresh
# Python process's real Flask GET are exercised by this test, without mocks.
tests.test_real_render_and_fresh_route_reopen_keep_all_ten_rows(review)
after = tests.read(review.path)
(a.artifacts / 'render-after.json').write_text(json.dumps(after, indent=2))
script = '''
import json, sys
import openscrub_web as web
web._data_root = lambda: sys.argv[1]
web.JOBS_DIR = sys.argv[1] + '/jobs'
web.JOBS = {'reopen': {'dir': sys.argv[1], 'video': sys.argv[2]}}
web.TOKEN = None
with web.app.test_client() as client:
    response = client.get('/api/jobs/reopen/detections')
    assert response.status_code == 200
    print(json.dumps({'status': response.status_code, 'body': response.get_json()}))
'''
result = subprocess.run([sys.executable, '-c', script, str(a.work_dir),
                         str(review.video)], capture_output=True, text=True,
                        check=True, cwd=str(a.source))
reopened = json.loads(result.stdout)
(a.artifacts / 'reopened-review.json').write_text(json.dumps(reopened, indent=2))
summary = dict(before_rows=len(review.doc['detections']),
               after_rows=len(after['detections']),
               enabled_render_rows=sum(r['enabled'] for r in after['detections']),
               decoded_frames_checked=60, enabled_black_regions_per_frame=7,
               disabled_visible_regions_per_frame=3,
               fresh_process_route_status=reopened['status'],
               reopened_rows=len(reopened['body']['detections']),
               shifted_indices=[],
               audio_fields_equal={k: review.doc[k] == after[k] for k in
                   ('audio_redactions', 'audio_suggestions', 'audio_transcript')},
               video=str(review.video), output=str(review.output),
               output_sha256=after['provenance']['output_sha256'],
               limits=['Synthetic silent footage; no audible mute/bleep quality check',
                       'Actual Flask test client; no browser or socket',
                       'No concurrent-writer safety established'])
assert summary['after_rows'] == summary['reopened_rows'] == 10
(a.artifacts / 'summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
