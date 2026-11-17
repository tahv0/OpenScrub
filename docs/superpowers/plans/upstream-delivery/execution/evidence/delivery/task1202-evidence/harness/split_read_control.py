"""Exact-base job_public loss, controlled by events rather than sleeps."""
from task1202_isolation import configure
import threading
web=configure()
job=web.new_job('',{},'split-read control')
sliced, proceed=threading.Event(),threading.Event()
class HeldList(list):
    def __getitem__(self,key):
        value=super().__getitem__(key)
        sliced.set()
        assert proceed.wait(5)
        return value
job['log']=HeldList(['first'])
result=[]
reader=threading.Thread(target=lambda:result.append(web.job_public(job)))
reader.start()
assert sliced.wait(5)
web.WebCallbacks(job).log('second')
proceed.set()
reader.join(5)
assert not reader.is_alive()
assert result[0]['log_tail']==['first'] and result[0]['log_len']==2
print('ACTUAL_BASE_SPLIT_READ_LOSS tail_count=1 absolute_len=2 skipped_position=1')
