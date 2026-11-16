import importlib.util
import sys
spec=importlib.util.spec_from_file_location('openscrub','/tmp/openscrub-task111/before/openscrub.py')
module=importlib.util.module_from_spec(spec)
sys.modules['openscrub']=module
spec.loader.exec_module(module)
import pytest
sys.exit(pytest.main(['tests/test_dense_smoothing_io.py','-q','--basetemp=/tmp/openscrub-task111/red','-o','cache_dir=/tmp/openscrub-task111/pytest-cache']))
