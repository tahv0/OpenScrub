"""Actual dependency/tool identities for task16330; no timing."""
import importlib.metadata
import json
import subprocess
import sys
import cv2, numpy
print(json.dumps(dict(python=sys.version, executable=sys.executable, opencv=cv2.__version__, numpy=numpy.__version__, packages={n:importlib.metadata.version(n) for n in ['Flask','cheroot','cryptography','pytest','onnxruntime']}, ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]),sort_keys=True))
