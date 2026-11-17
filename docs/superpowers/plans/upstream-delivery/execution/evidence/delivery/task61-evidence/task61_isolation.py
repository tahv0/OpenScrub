import baseline_isolation

def pytest_configure(config):
    baseline_isolation.configure('task61-pytest')
