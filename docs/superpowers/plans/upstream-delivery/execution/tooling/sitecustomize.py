"""Fail closed: Python normally ignores exceptions raised by sitecustomize."""
import os
import sys
try:
    from verification_hook import configure
    configure()
except BaseException as error:
    sys.stderr.write('VERIFICATION STARTUP ERROR: ' + repr(error) + '\n')
    sys.stderr.flush()
    os._exit(78)
