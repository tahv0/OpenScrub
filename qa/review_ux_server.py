"""Serve the production app with a small synthetic review job for UI checks."""
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'OpenScrub-review-ux'))
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'

import cv2
import numpy as np
import openscrub_web as w

jobdir = ROOT / 'review-ux-fixture'
jobdir.mkdir(exist_ok=True)
frame = np.full((720, 1280, 3), (44, 39, 32), np.uint8)
boxes = [(110, 150, 360, 228), (480, 150, 730, 228), (850, 150, 1100, 228),
         (110, 410, 360, 488), (480, 410, 730, 488), (850, 410, 1100, 488)]
texts = ['ABC-123', 'DEF-456', 'GHI-789', 'JKL-012', 'LABEL 42', 'MNO-345']
for (x1, y1, x2, y2), text in zip(boxes, texts):
    cv2.rectangle(frame, (x1 - 48, y1 - 72), (x2 + 48, y2 + 60), (81, 76, 68), -1)
    cv2.rectangle(frame, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (24, 24, 24), -1)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (238, 237, 230), -1)
    cv2.putText(frame, text, (x1 + 10, y1 + 53), cv2.FONT_HERSHEY_SIMPLEX,
                .96, (28, 29, 31), 2, cv2.LINE_AA)
video = str(jobdir / 'sample.mp4')
out = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*'mp4v'), 30, (1280, 720))
for _ in range(90): out.write(frame)
out.release()
dets = []
for i, (box, text) in enumerate(zip(boxes, texts)):
    dets.append(dict(category='plate', text='plate', confidence=.97-i*.07,
                     t_start=0., t_end=2.9, cbox=list(box), aoff=[0, 0],
                     last_seen=1., enabled=i not in (1, 4, 5),
                     track=7 if i == 0 else -1, person=-1, dense=i == 0))
# A second sighting must follow the first card's choice.
dets.append(dict(dets[0], t_start=1.4, t_end=2.95, last_seen=2.))
dets[5]['zone_dropped'] = True
report = {'detections': dets, 'provenance': {'input': video},
          'render_state': {'fps': 30, 'cum': [[0, 0]]*90, 'bands': [[0, 0]]*90}}
(jobdir / 'report.json').write_text(json.dumps(report))
w.JOBS['review-demo'] = dict(id='review-demo', dir=str(jobdir), video=video,
    name='sample-recording.mp4', options={}, phase='review', progress=.5,
    size=Path(video).stat().st_size, log=['Scan complete. Review the findings below.'],
    error=None, output=None, created=time.time(), cancel=threading.Event(), stats={})
# Do not launch the processing queue: save/render checks observe the real
# saved report and queued render without invoking any detection models.
w.app.run(host='127.0.0.1', port=8384, use_reloader=False)
