"""Deterministic, synthetic inputs; no application input/model/cache dependency."""
CASES = ('short', 'unicode', 'multiline', 'maximum')
COUNTS = (500, 5000, 20000)
JOBS = 3
WARMUPS = 3
OBSERVATIONS = 5
HTTP_REPETITIONS = 6

def message(case, index):
    label = '%08d' % index
    if case == 'short':
        return 'scan frame ' + label + ': ordinary synthetic message'
    if case == 'unicode':
        return 'Frame ' + label + ' — äö漢字 😀 ' * 10
    if case == 'multiline':
        return 'scan ' + label + '\nline two\nline three\n'
    if case == 'maximum':
        return label + 'm' * (8192 - len(label))
    raise ValueError(case)

def retained(case, count):
    # Independent expectation: walk newest to oldest using product policy limits.
    result, payload = [], 0
    for i in range(count - 1, -1, -1):
        value = message(case, i)
        size = len(value.encode('utf-8'))
        if len(result) == 2000 or payload + size > 524288:
            break
        result.append(value)
        payload += size
    result.reverse()
    return count - len(result), result, payload
