"""Guarded dependency/platform observation, no benchmark."""
from importlib import metadata
import json
import platform
import sys
print(json.dumps(dict(python=sys.version,executable=sys.executable,
                     platform=platform.platform(),versions={name:metadata.version(name)
                     for name in ['numpy','opencv-python','Flask','cheroot','pytest']}),indent=2))
