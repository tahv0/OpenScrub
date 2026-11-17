import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import openscrub as candidate

art=Path('/tmp/openscrub-task162')
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
assert Path.cwd()==root
assert Path(candidate.__file__).resolve()==root/'openscrub.py'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

base=load('polygon_baseline',art/'baseline-openscrub.py')
test=load('polygon_tests',root/'tests/test_polygon_fallback.py')
result={'direct':[], 'actual_media':[]}
for path in ['sdr','hdr']:
    for mode in test.MODES:
        for case,(poly,_) in enumerate(test.VALID):
            for pad in [0,2]:
                outputs=[]
                for module in [base,candidate]:
                    test.scrub=module
                    planes=test.source_planes(path)
                    test.apply(path,planes,(4,4,16,16),mode,poly,(4,4,16,16),pad)
                    outputs.append(planes)
                assert all(np.array_equal(a,b) for a,b in zip(*outputs)),(path,mode,case,pad)
                result['direct'].append({'path':path,'mode':mode,'case':case,'pad':pad,'exact':True})

src=art/'red-replay-tmp/polygon-media0'
media=art/'control-media'
media.mkdir(exist_ok=True)
for path in ['sdr','hdr']:
    for name,poly,box,pad in [('concave',test.CONCAVE,[4,4,16,16],2),
        ('bowtie',test.BOWTIE,[4,4,16,16],2),
        ('clipped',test.VALID[3][0],[-2,4,10,16],2),
        ('full-box',None,[4,4,16,16],2)]:
        outputs=[]
        for label,module in [('base',base),('candidate',candidate)]:
            test.scrub=module
            report=media/(path+'-'+name+'-'+label+'.json')
            report.write_text(json.dumps({'detections':[{'t_start':0,'t_end':1,
                'cbox':box,'category':'person','text':'','confidence':1,'enabled':True,'poly':poly}],
                'render_state':{'fps':2,'cum':[[0,0]]*2,'bands':[[0,0]]*2}}))
            det,state,_=module.load_report(str(report))
            dst=report.with_suffix('.mp4')
            with test.observe_render(pytest.MonkeyPatch(),path) as frames:
                args=(str(src/(path+'.mp4')),str(dst),det,state['cum'],state['bands'],2,pad,'box')
                if path=='hdr':
                    module.render_hdr(*args,'libx265',{'-color_primaries':'bt2020','-color_trc':'smpte2084','-colorspace':'bt2020nc'})
                else:
                    module.render(*args,False,encoder='x264')
            wire=b''.join(frames)
            decoded=test.ffmpeg('-i',str(dst),'-f','rawvideo','-pix_fmt','yuv420p10le' if path=='hdr' else 'bgr24','pipe:1')
            outputs.append((wire,decoded))
        assert outputs[0]==outputs[1],(path,name)
        result['actual_media'].append({'path':path,'case':name,'preencode_exact':True,
            'decoded_exact':True,'preencode_sha256':hashlib.sha256(outputs[0][0]).hexdigest(),
            'decoded_sha256':hashlib.sha256(outputs[0][1]).hexdigest()})
(art/'control-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'direct_exact_controls':len(result['direct']),'actual_media_exact_controls':len(result['actual_media'])}))
