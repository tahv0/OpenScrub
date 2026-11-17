from pathlib import Path
import sys
import cv2
import numpy
import openscrub
import openscrub_web
expected = Path(sys.argv[1]).resolve()
assert Path(openscrub.__file__).resolve() == expected / 'openscrub.py'
assert Path(openscrub_web.__file__).resolve() == expected / 'openscrub_web.py'
print(sys.version)
print('IMPORTS', openscrub.__file__, openscrub_web.__file__)
print('CV2', cv2.__version__, cv2.__file__)
print('NUMPY', numpy.__version__, numpy.__file__)
