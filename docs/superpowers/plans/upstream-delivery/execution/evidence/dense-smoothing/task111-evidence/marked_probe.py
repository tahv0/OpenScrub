import sys
import importlib.util
import dataclasses
import json
import hashlib
import cv2
import numpy as np
spec = importlib.util.spec_from_file_location('before', '/tmp/openscrub-task111/before/openscrub.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
path='/tmp/openscrub-task111/marked.avi'
rng=np.random.default_rng(111)
patch=rng.integers(0,256,(32,32,3),dtype=np.uint8)
w=cv2.VideoWriter(path,cv2.VideoWriter_fourcc(*'FFV1'),10,(128,96))
assert w.isOpened()
for k in range(130):
    frame=np.full((96,128,3),60,np.uint8)
    frame[:8,:]=k
    if 50<=k<=70:
        x=40+(k-50)//5*2
        frame[40:72,x:x+32]=patch
    w.write(frame)
w.release()
dets=[m.Detection(t,t,(44,40,76,72),'face','synthetic',.95,dense=True,track=1,poly=()) for t in (6.,6.2,6.3)]
result=m.smooth_dense_tracks(dets,10,path)
rows=[dataclasses.asdict(d) for d in dets]
print(result,len(dets),hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
print(json.dumps(rows,indent=2))
