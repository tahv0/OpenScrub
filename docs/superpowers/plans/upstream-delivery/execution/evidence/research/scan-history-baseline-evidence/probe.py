#!/usr/bin/env python3
"""Bounded counts in unmodified pinned modules; no timing measurements."""
import collections, dataclasses, hashlib, inspect, json, os, pathlib, platform, random, sys, threading, types
ROOT = pathlib.Path('/tmp/openscrub-scan-history-20261117')
SOURCE = ROOT / 'source'
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.path.expanduser = lambda path: str(ROOT/'runtime/profile') + path[1:] if str(path).startswith('~') else path
sys.path.insert(0, str(SOURCE))
import cv2, numpy as np, rapidfuzz
import openscrub as core
import openscrub_web as web
assert pathlib.Path(core.__file__).resolve() == SOURCE/'openscrub.py'
assert pathlib.Path(web.__file__).resolve() == SOURCE/'openscrub_web.py'
cv2.setNumThreads(1)
# All generated frames are identical; OCR inference alone is replaced.
rng = np.random.default_rng(1411)
FRAME = rng.integers(0, 256, (96, 160, 3), dtype=np.uint8)
clock_value = [1000.0]
web.time = types.SimpleNamespace(time=lambda: clock_value[0])
lines = (SOURCE/'openscrub.py').read_text().splitlines()
def line_of(text, after=0):
    matches = [i+1 for i, line in enumerate(lines) if line.strip() == text and i+1 > after]
    assert len(matches) == 1, (text, matches)
    return matches[0]
MARKS = {
 'merge_candidate_visits': line_of('if m.category != d.category or not boxes_overlap(m.cbox, d.cbox):'),
 'merge_tail_scan_visits': line_of('if st <= m.last_seen + 0.01:'),
 'merge_contradiction_scan_visits': line_of('if not (t_from + 0.01 < st < t_to - 0.01):'),
 'reverse_memory_key_visits': line_of('if cat not in cats:', after=7000),
}
# That line occurs once in source and its enclosing function is reverse_pass.
COUNTS = collections.Counter()
CALLS = collections.Counter()
def trace(frame, event, arg):
    if frame.f_code.co_filename not in (core.__file__, web.__file__): return None
    if event == 'call':
        name = frame.f_code.co_name
        if frame.f_code == core.PhiMemory.add.__code__: name = 'PhiMemory.add'
        if frame.f_code == core.PhiMemory.recall.__code__: name = 'PhiMemory.recall'
        CALLS[name] += 1
        return trace
    if event == 'line':
        for name, number in MARKS.items():
            if frame.f_code.co_filename == core.__file__ and frame.f_lineno == number:
                COUNTS[name] += 1
    return trace
class SyntheticOCR:
    def __init__(self, mode): self.mode, self.calls = mode, 0
    def read(self, image):
        i = self.calls if self.mode == 'unique' else 0
        rnd = random.Random(83011+i)
        text = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(24))+'@sample.invalid'
        self.calls += 1
        return [(text, (8,8,150,28), .99), ('pending', (8,40,70,60), .99), ('ready', (85,40,150,60), .99)]
class Callback(web.WebCallbacks):
    def __init__(self, job):
        super().__init__(job)
        self.checkpoints = []
        self.frame_digests = []
        self.previous_calls = collections.Counter()
        self.previous_checkpoint_calls = collections.Counter()
    def progress(self, stage, cur, total):
        if stage == 'scan':
            f = inspect.currentframe().f_back
            n = f.f_locals['n_scans']
            if n in (1, max(1, total//4), total//2):
                self.checkpoints.append({'scan':n,'frame':cur,'raw':len(f.f_locals['raw']), 'ocr_history':len(f.f_locals['scans']), 'cum':len(f.f_locals['cum']), 'remembered':len(f.f_locals['memory'].items), 'this_scan_calls':{k:CALLS[k]-self.previous_calls[k] for k in ['read_adaptive','detect_phi','PhiMemory.recall','PhiMemory.add','reverse_pass','merge_detections','scan_frame']}})
            self.previous_calls = CALLS.copy()
        return super().progress(stage,cur,total)
    def scan_frame(self, frame, t, found):
        clock_value[0] += .5
        super().scan_frame(frame,t,found)
        self.frame_digests.append(hashlib.sha256((pathlib.Path(self.job['dir'])/'preview.jpg').read_bytes()).hexdigest())

def run_case(n, mode):
    jobdir = ROOT/'runtime'/f'{mode}-{n}'
    jobdir.mkdir(parents=True,exist_ok=True)
    video = jobdir/'fixed.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'FFV1'), 6.0, (160,96))
    assert writer.isOpened()
    for _ in range(2*n): writer.write(FRAME)
    writer.release()
    parser = core.build_parser()
    args = core._prep_args(parser.parse_args([str(video),'--categories','email','--engine','tesseract','--sample-interval','0.3333333333333333','--scroll-track','off','--adaptive','off','--ocr-upscale','off','--no-vfr-fix','--no-backtrack']),parser)
    ocr = SyntheticOCR(mode)
    core.make_ocr = lambda *a, **k: ocr
    job = {'dir':str(jobdir),'log':[],'cancel':threading.Event()}
    cb = Callback(job)
    COUNTS.clear(); CALLS.clear()
    sys.settrace(trace)
    try: state = core.run_scan(args,cb)
    finally: sys.settrace(None)
    out_counts=dict(COUNTS); out_calls=dict(CALLS)
    before_report = dict(COUNTS)
    asdict_count=[0]; dump_count=[0]
    real_asdict=core.asdict; real_dump=core.json.dump
    def count_asdict(d): asdict_count[0]+=1; return real_asdict(d)
    def count_dump(*a,**k): dump_count[0]+=1; return real_dump(*a,**k)
    core.asdict=count_asdict; core.json.dump=count_dump
    try: core.write_report(str(jobdir/'report.json'),args,state)
    finally: core.asdict=real_asdict; core.json.dump=real_dump
    doc=json.loads((jobdir/'report.json').read_text())
    expected=[dict(dataclasses.asdict(d),enabled=True) for d in state['detections']]
    assert json.loads(json.dumps(expected)) == doc['detections']
    assert len(state['cum'])==len(state['bands'])==2*n
    assert ocr.calls==state['stats']['scans']==n
    assert len(state['detections']) == (n if mode=='unique' else 1)
    assert len(set(cb.frame_digests))==1
    report_check={'all_detection_fields_equal':True,'cum_equal':doc['render_state']['cum']==[[round(x,1),round(y,1)] for x,y in state['cum']], 'bands_equal':doc['render_state']['bands']==[[round(x,1),round(y,1)] for x,y in state['bands']], 'asdict_calls':asdict_count[0], 'json_dump_calls':dump_count[0], 'bytes':(jobdir/'report.json').stat().st_size}
    return {'n':n,'mode':mode,'frames':2*n,'video_bytes':video.stat().st_size,'stats':state['stats'],'counts':out_counts,'calls':{k:out_calls.get(k,0) for k in ['run_scan','read_adaptive','detect_phi','PhiMemory.recall','PhiMemory.add','reverse_pass','merge_detections','scan_frame','progress','write_report']}, 'checkpoints':cb.checkpoints, 'all_published_preview_jpegs_equal':True,'report':report_check,'output_digest':hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest()}

cases=[run_case(n,mode) for mode in ['repeated','unique'] for n in [10,50,100]]
# Direct actual callbacks at fixed current inputs and only log-history growth.
callback_cases=[]
for history in [0,1000,10000]:
    jobdir=ROOT/'runtime'/f'callback-{history}';jobdir.mkdir(exist_ok=True)
    job={'dir':str(jobdir),'log':['synthetic prior scan']*history,'cancel':threading.Event()}
    cb=web.WebCallbacks(job);clock_value[0]=1000
    COUNTS.clear();CALLS.clear();sys.settrace(trace)
    try:
        cb.log('synthetic current scan');cb.progress('scan',10,100)
        clock_value[0]+=4
        cb.progress('scan',20,100);cb.scan_frame(FRAME,1.0,1)
    finally: sys.settrace(None)
    callback_cases.append({'prior_log_rows':history,'log_rows':len(job['log']), 'progress':job['progress'],'eta':job['eta'],'callback_calls':{k:CALLS[k] for k in ['log','progress','scan_frame']},'preview_sha256':hashlib.sha256((jobdir/'preview.jpg').read_bytes()).hexdigest()})
assert len({c['preview_sha256'] for c in callback_cases})==1
result={'source':'e21ebdf6e3ee46e6c65050dc956a9a3459152269','source_files':{str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE/'openscrub.py',SOURCE/'openscrub_web.py']},'environment':{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'opencv':cv2.__version__,'numpy':np.__version__,'rapidfuzz':rapidfuzz.__version__,'opencv_threads':cv2.getNumThreads()},'line_markers':MARKS,'cases':cases,'callback_cases':callback_cases,'timings':None}
(ROOT/'evidence/results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
