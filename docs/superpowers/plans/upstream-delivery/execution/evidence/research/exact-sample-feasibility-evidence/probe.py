"""Bounded existing-fixture decoder probe; no production imports or media generation."""
import ast, hashlib, json, platform, subprocess, sys, types
from pathlib import Path
import cv2
import numpy as np

EVID = Path(__file__).resolve().parent
SOURCE = Path('/tmp/openscrub-plate-quad-contract-12919c9')
BASE = EVID.parent/'frame-identity-baseline-evidence/results.json'
prior = json.loads(BASE.read_text())
manifest = json.loads((EVID.parent/'plate-quad-contract-evidence/source-identities.json').read_text())
verified = []
for entry in manifest['files']:
    p = SOURCE/entry['path']
    data = p.read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry['sha256'], p
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == entry['blob'], p
    verified.append(entry['path'])

# Execute exactly the pinned existing reader body, with only its dependency bindings.
# No openscrub/web import, module-level initialization, job setup, model resolution or routes.
tree = ast.parse((SOURCE/'openscrub_web.py').read_text())
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_frame_at')
captures = []
def marker(frame):
    return None if frame is None else sum((int(frame[14,14+12*k,0]) > 128)<<k for k in range(6))
def digest(frame):
    return None if frame is None else hashlib.sha256(frame.tobytes()).hexdigest()
class Capture:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(path)
        self.trace = {'path':str(path), 'opened':self.cap.isOpened(), 'released':False, 'seeks':[]}
        if self.cap.isOpened(): self.trace['backend'] = self.cap.getBackendName()
        captures.append(self.trace)
    def set(self, prop, value):
        ok = self.cap.set(prop, value)
        self.trace['seeks'].append({'property':int(prop),'value':value,'setter_return':bool(ok)})
        return ok
    def read(self):
        ok, frame = self.cap.read()
        self.trace['read'] = {'ok':bool(ok), 'marker':marker(frame), 'sha256':digest(frame),
                              'pos_msec':self.cap.get(cv2.CAP_PROP_POS_MSEC),
                              'pos_frames':self.cap.get(cv2.CAP_PROP_POS_FRAMES),
                              'pts_fps_units':self.cap.get(cv2.CAP_PROP_PTS)}
        return ok, frame
    def release(self):
        self.cap.release(); self.trace['released'] = True
ns = {'cv2':types.SimpleNamespace(VideoCapture=Capture,CAP_PROP_POS_FRAMES=cv2.CAP_PROP_POS_FRAMES),
      '_job_video':lambda job:job['video']}
exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE/'openscrub_web.py'), 'exec'), ns)

commands = []
def run(cmd):
    commands.append(cmd)
    return subprocess.check_output(cmd, timeout=15)
result = {'source':{'commit':manifest['commit'],'tree':manifest['tree'],'export':str(SOURCE),
                    'verified_export_files':len(verified),'reader_lines':[fn.lineno,fn.end_lineno],
                    'reader_sha256':hashlib.sha256(ast.get_source_segment((SOURCE/'openscrub_web.py').read_text(),fn).encode()).hexdigest(),
                    'execution':'AST-extracted exact pinned _frame_at only; dependency bindings shown in this script'},
          'tools':{'python':sys.version,'platform':platform.platform(),'opencv':cv2.__version__,
                   'cv2_path':cv2.__file__,'opencv_build':cv2.getBuildInformation(),
                   'ffprobe_version':run(['ffprobe','-version']).decode().splitlines()[0]},
          'media':{},'samples':[],'commands':commands}
for label, old in prior['media'].items():
    path = Path(old['path']); data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == old['sha256']
    probe = json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
                          'stream=index,codec_name,width,height,r_frame_rate,avg_frame_rate,time_base,start_pts,start_time,nb_frames,duration',
                          '-show_entries','frame=stream_index,pts,pts_time,best_effort_timestamp,best_effort_timestamp_time,pict_type',
                          '-show_frames','-of','json',str(path)]))
    cap=cv2.VideoCapture(str(path)); refs=[]
    try:
        fps=cap.get(cv2.CAP_PROP_FPS); count=cap.get(cv2.CAP_PROP_FRAME_COUNT);backend=cap.getBackendName()
        while True:
            ok, fr=cap.read()
            if not ok: break
            refs.append(fr)
            assert len(refs) <= 60
    finally: cap.release()
    assert len(refs) == len(probe['frames'])
    n=len(refs)
    seq=[{'index':i,'marker':marker(fr),'sha256':digest(fr),'pts':probe['frames'][i]['pts'],
          'pts_time':probe['frames'][i]['pts_time']} for i,fr in enumerate(refs)]
    result['media'][label]={'path':str(path),'sha256':old['sha256'],'bytes':len(data),'probe':probe,
                          'fps':fps,'capture_count':count,'backend':backend,'sequential_reference':seq}
    ts=[0,.2,.9,(n-1)/fps,n/fps,(n+1)/fps]
    if label=='cfr5':ts.append(1.9)
    if label=='normalized':ts.extend([.5,3/fps,12/fps,13/fps])
    for t in dict.fromkeys(ts):
        before=len(captures)
        actual=ns['_frame_at']({'video':str(path)},t,{'fps':fps})
        matches=[i for i,ref in enumerate(refs) if actual is not None and np.array_equal(ref,actual)]
        selected=int(t*fps)
        sample={'label':label,'requested_time':t,'selected_index':selected,'matches_sequential_indices':matches,
                'marker':marker(actual),'trace':captures[before],
                'expected_index_pixels_equal':actual is not None and selected<n and np.array_equal(actual,refs[selected])}
        if actual is not None:
            crop=actual[71:113,53:97]
            sample['odd_crop_sha256']=digest(crop)
            sample['odd_crop_matches_selected']=selected<n and np.array_equal(crop,refs[selected][71:113,53:97])
        result['samples'].append(sample)
    # Proposed clamping is tested separately; never misreport it as current function behavior.
    for t in [n/fps,(n+1)/fps]:
        idx=min(int(t*fps),n-1)
        actual=ns['_frame_at']({'video':str(path)},idx/fps,{'fps':fps})
        result['samples'].append({'label':label,'requested_time':t,'mode':'proposed explicit clamp then existing reader',
                                  'selected_index':idx,'matches_sequential_indices':[i for i,r in enumerate(refs) if np.array_equal(actual,r)],
                                  'trace':captures[-1], 'expected_index_pixels_equal':np.array_equal(actual,refs[idx])})
result['captures']=len(captures)
result['all_released']=all(t['released'] for t in captures)
assert result['all_released']
(EVID/'results.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'verified_export_files':len(verified),'tools':{k:v for k,v in result['tools'].items() if k!='opencv_build'},
                  'samples':[{k:v for k,v in s.items() if k not in ('trace','odd_crop_sha256')} for s in result['samples']],
                  'captures':result['captures'],'all_released':result['all_released']},indent=2))
