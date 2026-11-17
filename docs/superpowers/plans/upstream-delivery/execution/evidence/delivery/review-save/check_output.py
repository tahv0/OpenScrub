from pathlib import Path
import cv2,json
root=Path('/tmp/openscrub-task71')
def frame(path):
 cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,500);ok,image=cap.read();cap.release();assert ok,str(path);return image
before=frame(root/'synthetic-input.mp4');after=frame(root/'actual-output.mp4')
# User-added box at50,60..110,120 covers textured pixels that otherwise remain visible.
a=before[65:115,55:105];b=after[65:115,55:105]
result={'source_roi_mean':float(a.mean()),'rendered_manual_roi_mean':float(b.mean()),'source_roi_std':float(a.std()),'rendered_manual_roi_std':float(b.std())}
assert result['source_roi_std']>50,result
assert result['rendered_manual_roi_mean']<5,result
assert result['rendered_manual_roi_std']<5,result
# A separate clear area remains recognizable; this is not a wholly black frame.
assert float(after[270:320,350:450].mean())>200
(root/'actual-output-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
