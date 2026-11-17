import json
from pathlib import Path
import subprocess
import sys

import cv2

ROOT = Path('/tmp/openscrub-task620')
job = json.loads((ROOT / 'job.json').read_text())
before = json.loads((ROOT / 'render-before.json').read_text())
after = json.loads((ROOT / 'render-after.json').read_text())
assert {k: v for k, v in before.items() if k != 'provenance'} == {
    k: v for k, v in after.items() if k != 'provenance'}
assert after['provenance']['output'] != before['provenance']['output']
assert after['provenance']['output_sha256'] != 'stale'
capture = cv2.VideoCapture(after['provenance']['output'])
frames = 0
while True:
    ok, frame = capture.read()
    if not ok:
        break
    for i in (0, 4, 8):
        assert frame[35, 8 + 16 * i].mean() > 100
    for i in (1, 2, 3, 5, 6, 7, 9):
        assert frame[35, 8 + 16 * i].mean() < 15
    frames += 1
capture.release()
assert frames == 60
script = '''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import baseline_isolation
baseline_isolation.ROOT=Path('/tmp/openscrub-task620')
web=baseline_isolation.configure('fresh-runtime')
job=json.loads(Path(sys.argv[2]).read_text())
job['name']='synthetic-task620.avi'
web.JOBS={'reopen':job}
web.TOKEN=None
with web.app.test_client() as client:
 response=client.get('/api/jobs/reopen/detections')
 report=client.get('/api/jobs/reopen/report')
 assert response.status_code == report.status_code == 200
 print(json.dumps({'status':response.status_code,'body':response.get_json(),
  'report':json.loads(report.data)}))
'''
proc = subprocess.run([sys.executable, '-c', script, job['source'], str(ROOT / 'job.json')],
    check=True, capture_output=True, text=True, cwd=job['source'])
reopened = json.loads(proc.stdout)
assert reopened['report'] == after
rows = reopened['body']['detections']
assert [r['i'] for r in rows] == list(range(10))
for i, row in enumerate(rows):
    for field in ('text', 'category', 'enabled', 'track', 'person'):
        assert row[field] == before['detections'][i][field]
assert rows[4]['zone_dropped'] is True
(ROOT / 'fresh-reopened.json').write_text(json.dumps(reopened, indent=2))
summary = {'before_rows': 10, 'saved_rows': 10, 'rendered_rows': 10,
 'fresh_reopened_rows': len(rows), 'fresh_status': reopened['status'],
 'full_review_document_equal_except_provenance': True, 'original_order_preserved': True,
 'disabled_rows': [0, 4, 8], 'manual_rows': [3, 8, 9], 'frames_checked': frames,
 'enabled_black_regions_per_frame': 7, 'disabled_visible_regions_per_frame': 3,
 'audio_fields_equal': {k: before[k] == after[k] for k in
     ('audio_redactions', 'audio_suggestions', 'audio_transcript')},
 'fresh_full_report_equal': True, 'source': job['source'],
 'output': after['provenance']['output']}
(ROOT / 'integration-summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
