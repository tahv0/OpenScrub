import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import cv2
import numpy as np
import openscrub

art=Path('/tmp/openscrub-task621')
source=subprocess.check_output(['git','show','3795d49f6293baf7b8c35534862a4881447e1b16:openscrub.py'])
path=art/'baseline-engine.py'
path.write_bytes(source)
spec=importlib.util.spec_from_file_location('task621_baseline_engine',path)
base=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=base
spec.loader.exec_module(base)
video=art/'tracker-output-fixture.avi'
writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),30,(160,96))
assert writer.isOpened()
texture=np.random.default_rng(621).integers(0,255,(32,32,3),dtype=np.uint8)
for frame in range(60):
    image=np.zeros((96,160,3),dtype=np.uint8)
    x=20+frame
    image[30:62,x:x+32]=texture
    writer.write(image)
writer.release()
class Quiet(openscrub.Callbacks):
    def log(self,*args):
        pass
results=[]
for engine in [base,openscrub]:
    engine._vittrack_factory=lambda log:None
    samples=engine.track_manual_region(str(video),(50,30,82,62),1.0,0.1,1.8,cb=Quiet())
    results.append(samples)
assert results[0] == results[1] and len(results[1]) > 10
(art/'tracker-output-equality.json').write_text(json.dumps({'exact_samples_equal':True,
    'sample_count':len(results[1]),'samples':results[1]},indent=2))
print('Baseline and head NCC fallback sample sequences exactly equal:',len(results[1]))
