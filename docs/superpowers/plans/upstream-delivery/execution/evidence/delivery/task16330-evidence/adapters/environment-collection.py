import json, subprocess, sys
import cv2, numpy
print(json.dumps(dict(python=sys.version, opencv=cv2.__version__, numpy=numpy.__version__, ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0])))
