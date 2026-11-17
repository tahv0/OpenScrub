"""Use the supplied compatible/model-fetch guard with task-local web data."""
import baseline_isolation

def pytest_configure(config):
    baseline_isolation.configure('/tmp/openscrub-task621/runtime')
