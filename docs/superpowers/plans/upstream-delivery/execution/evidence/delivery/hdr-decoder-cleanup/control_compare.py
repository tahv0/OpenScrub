from pathlib import Path
import hashlib
import json
import subprocess
import numpy as np
art = Path('/tmp/openscrub-task109')
results = {}
def command(args):
    return subprocess.run(args, check=True, capture_output=True, timeout=30).stdout
for stage in ('red', 'green'):
    directory = art / (stage + '-tmp') / 'test_hdr_success_keeps_source_0'
    src = directory / 'source.mp4'
    out = directory / 'success.mp4'
    raw = (directory / 'source.yuv').read_bytes()
    decoded_source = command(['ffmpeg', '-v', 'error', '-i', str(src), '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', 'pipe:1'])
    assert decoded_source == raw
    decoded_output = command(['ffmpeg', '-v', 'error', '-i', str(out), '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', 'pipe:1'])
    metadata = json.loads(command(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,pix_fmt,width,height,nb_read_frames,color_transfer,color_primaries,color_space', '-of', 'json', str(out)]))
    assert len(decoded_output) == 36864
    (art / (stage + '-decoded.yuv')).write_bytes(decoded_output)
    values = np.frombuffer(decoded_output, np.uint16).reshape(3, 6144)
    results[stage] = {'source_raw_sha256': hashlib.sha256(raw).hexdigest(), 'source_decode_exact': True,
        'preencoder_exact': 'asserted in actual success regression read-only trace',
        'output_sha256': hashlib.sha256(out.read_bytes()).hexdigest(), 'decoded_sha256': hashlib.sha256(decoded_output).hexdigest(),
        'decoded_matches_source': decoded_output == raw, 'metadata': metadata,
        'plane_ranges': [[int(p.min()), int(p.max())] for p in (values[:, :4096], values[:, 4096:5120], values[:, 5120:])]}
assert (art / 'red-decoded.yuv').read_bytes() == (art / 'green-decoded.yuv').read_bytes()
assert results['red']['metadata'] == results['green']['metadata']
assert results['red']['source_raw_sha256'] == results['green']['source_raw_sha256']
results['before_after_decoded_bytes_equal'] = True
(art / 'control-comparison.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
