import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import task161_isolation

task161_isolation.pytest_configure(None)
import openscrub

art=Path('/tmp/openscrub-task161')
root=Path.cwd()
base='e21ebdf6e3ee46e6c65050dc956a9a3459152269'
source=subprocess.check_output(['git','show',base+':openscrub.py'])
p=art/'baseline-openscrub.py'
p.write_bytes(source)
spec=importlib.util.spec_from_file_location('baseline_openscrub',p)
baseline=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=baseline
spec.loader.exec_module(baseline)
spec=importlib.util.spec_from_file_location('coverage_tests',root/'tests/test_hdr_chroma_coverage.py')
tests=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
source=source.decode()
candidate=(root/'openscrub.py').read_text()
start=source.index('def _blur_silhouette_yuv10(')
end=source.index('\n\ndef apply_coverage',start)
cstart=candidate.index('def _blur_silhouette_yuv10(')
cend=candidate.index('\n\ndef apply_coverage',cstart)
assert source[:start]==candidate[:cstart] and source[end:]==candidate[cend:]
counts={'luma_comparisons':0,'sdr_silhouette_comparisons':0,'hdr_face_rectangle_comparisons':0}
rng=np.random.default_rng(161)
for region,vertices in tests.CASES:
    for pad in (0,1,3):
        for mode in tests.MODES:
            before=tests._planes()
            old=[p.copy() for p in before]
            new=[p.copy() for p in before]
            args=(*region,mode,tests._poly(region,vertices),region)
            baseline._blur_silhouette_yuv10(*old,*args,pad_px=pad)
            openscrub._blur_silhouette_yuv10(*new,*args,pad_px=pad)
            np.testing.assert_array_equal(old[0],new[0])
            counts['luma_comparisons']+=1
            frame=rng.integers(0,256,(32,32,3),dtype=np.uint8)
            a,b=frame.copy(),frame.copy()
            baseline.blur_silhouette(a,*args,pad_px=pad)
            openscrub.blur_silhouette(b,*args,pad_px=pad)
            assert a.tobytes()==b.tobytes()
            counts['sdr_silhouette_comparisons']+=1
for region in tests.REGIONS+((-2,-1,11,12),(23,23,36,36)):
    for mode in tests.MODES:
        for shape in ('rect','ellipse'):
            old=tests._planes()
            new=[p.copy() for p in old]
            baseline._blur_yuv10(*old,*region,mode,shape)
            openscrub._blur_yuv10(*new,*region,mode,shape)
            assert all(a.tobytes()==b.tobytes() for a,b in zip(old,new))
            counts['hdr_face_rectangle_comparisons']+=1

def decode(path,pix_fmt):
    return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','rawvideo','-pix_fmt',pix_fmt,'pipe:1'])

def sha(data):
    return hashlib.sha256(data).hexdigest()

result={'engine_delta_only_existing_hdr_silhouette_owner':True,**counts,'media':{}}
for name,subdir,pre,out,pix in [
    ('sdr','test_report_run_render_sdr_con0','preencode.bgr','sdr.mp4','bgr24'),
    ('unmasked_hdr','test_report_run_render_hdr_exa1','preencode.yuv','hdr.mp4','yuv420p10le'),
    ('sparse_hdr','test_report_run_render_hdr_exa0','preencode.yuv','hdr.mp4','yuv420p10le')]:
    a=art/'red-tmp'/subdir
    b=art/'green-tmp'/subdir
    aw=(a/pre).read_bytes()
    bw=(b/pre).read_bytes()
    ad,bd=decode(a/out,pix),decode(b/out,pix)
    (art/(name+'-red-decoded.raw')).write_bytes(ad)
    (art/(name+'-green-decoded.raw')).write_bytes(bd)
    meta_a,meta_b=tests._metadata(a/out),tests._metadata(b/out)
    assert meta_a==meta_b
    row={'preencode_equal':aw==bw,'decoded_equal':ad==bd,
         'preencode_sha256':[sha(aw),sha(bw)],'decoded_sha256':[sha(ad),sha(bd)],
         'output_metadata':meta_b,'decoded_pixels_are_lossy_not_mask_oracle':True}
    if name!='sparse_hdr':
        assert aw==bw and ad==bd
    else:
        old=np.frombuffer(aw[:12288],np.uint16)
        new=np.frombuffer(bw[:12288],np.uint16)
        assert old[:4096].tobytes()==new[:4096].tobytes()
        cells=(np.array([2,3]),np.array([3,3]))
        row['required_cells_yx']=[[2,3],[3,3]]
        row['u_before_after']=[old[4096:5120].reshape(32,32)[cells].tolist(),new[4096:5120].reshape(32,32)[cells].tolist()]
        row['v_before_after']=[old[5120:].reshape(32,32)[cells].tolist(),new[5120:].reshape(32,32)[cells].tolist()]
        assert row['u_before_after']==[[800,512],[512,512]]
        assert row['v_before_after']==[[300,512],[512,512]]
        row['source_exact']=decode(a/'source.mp4',pix)==(a/'source.yuv').read_bytes()
        assert row['source_exact']
        row['changed_preencode_samples_old_new']=[int(np.count_nonzero(old!=np.frombuffer((a/'source.yuv').read_bytes()[:12288],np.uint16))),int(np.count_nonzero(new!=np.frombuffer((b/'source.yuv').read_bytes()[:12288],np.uint16)))]
    result['media'][name]=row
(art/'control-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
