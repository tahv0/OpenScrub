#!/usr/bin/env python3
"""Read-only pinned-source probes; no application checkout or model use.

Run after sourcing /tmp/openscrub-baseline-20261116/env-opencv4.sh.
Media/snapshots remain in --scratch; JSON is written to --output.
"""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

import cv2
import numpy as np

BASE = '5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f'
DONOR = '8697c2811db6cfda644f730284e037f7294b47cc'


def snapshot(ref, scratch, name):
    source = subprocess.check_output(['git', 'show', ref + ':openscrub.py'], text=True)
    path = scratch / (name + '.py')
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module, source


def union_from_luma(mask):
    """Independent coverage oracle: enumerate global luma pixel coordinates."""
    result = np.zeros((mask.shape[0] // 2, mask.shape[1] // 2), bool)
    for row, col in np.argwhere(mask):
        result[int(row) // 2, int(col) // 2] = True
    return result


def invoke(module, path, region, polys, poly_box=None, pad=0):
    before = [np.full((32, 32), 900, np.uint16),
              np.full((16, 16), 800, np.uint16),
              np.full((16, 16), 300, np.uint16)] if path == 'hdr' else [np.full((32, 32, 3), 200, np.uint8)]
    planes = [p.copy() for p in before]
    try:
        if path == 'hdr':
            module._blur_silhouette_yuv10(*planes, *region, 'box', polys,
                                           region if poly_box is None else poly_box, pad_px=pad)
        else:
            module.blur_silhouette(planes[0], *region, 'box', polys,
                                   region if poly_box is None else poly_box, pad_px=pad)
        result = {'status': 'ok', 'changed': [int(np.count_nonzero(p != q)) for p, q in zip(planes, before)]}
        if path == 'hdr':
            result['full_box'] = bool(np.all(planes[0][4:16, 4:16] == 64))
        else:
            result['full_box'] = bool(np.all(planes[0][4:16, 4:16] == 0))
        return result, planes
    except Exception as exc:
        return {'status': type(exc).__name__, 'message': str(exc),
                'source_trace': traceback.format_exc().splitlines()[-5:]}, planes


def chroma_probes(modules):
    polygons = {
        'full_square_control': (((0, 0), (1, 0), (1, 1), (0, 1)),),
        'sparse_triangle': (((1/12, 1/12), (2/12, 1/12), (1/12, 2/12)),),
        'right_edge_triangle': (((10/12, 0), (1, 0), (1, 2/12)),),
        'diagonal_triangle': (((0, 0), (1, 1), (10/12, 1)),),
    }
    results = []
    for origin in [(4, 4), (5, 4), (4, 5), (5, 5)]:
        region = (*origin, origin[0] + 12, origin[1] + 12)
        for name, poly in polygons.items():
            for pad in [0, 1, 3]:
                row = {'case': name, 'origin': list(origin), 'pad': pad, 'implementations': {}}
                ref_luma = None
                for label, module in modules.items():
                    status, planes = invoke(module, 'hdr', region, poly, pad=pad)
                    assert status['status'] == 'ok', status
                    luma = planes[0] == 64
                    expected = union_from_luma(luma)
                    actual = planes[1] == 512
                    ref_luma = luma if ref_luma is None else ref_luma
                    row['implementations'][label] = {
                        'luma_pixels': int(luma.sum()), 'luma_same_as_baseline': bool(np.array_equal(ref_luma, luma)),
                        'required_chroma_cells': int(expected.sum()), 'actual_chroma_cells': int(actual.sum()),
                        'missing_cells_yx': np.argwhere(expected & ~actual).tolist(),
                        'extra_cells_yx': np.argwhere(actual & ~expected).tolist(),
                        'uv_same_coverage': bool(np.array_equal(actual, planes[2] == 512)),
                        'unrelated_chroma_unchanged': bool(np.all(planes[1][~expected] == 800) and np.all(planes[2][~expected] == 300)),
                    }
                results.append(row)
    # Exact donor-tip full-square fixture; the control must pass the baseline too.
    fixture = {}
    for label, m in modules.items():
        y = np.full((8, 8), 900, np.uint16)
        u = np.full((4, 4), 800, np.uint16)
        v = u.copy()
        m._blur_silhouette_yuv10(y, u, v, 1, 1, 5, 5, 'box', polygons['full_square_control'], (1, 1, 5, 5))
        fixture[label] = bool(np.all(u[:3, :3] == 512) and u[3, 3] == 800)
    return {'donor_tip_full_square_fixture_pass': fixture, 'cases': results}


def geometry_probes(modules):
    square = (((0, 0), (1, 0), (1, 1), (0, 1)),)
    cases = {
        'valid_square': (square, (4, 4, 16, 16), None),
        'nan_point': ((((float('nan'), 0), (1, 0), (1, 1)),), (4, 4, 16, 16), None),
        'infinite_point': ((((0, 0), (float('inf'), 0), (1, 1)),), (4, 4, 16, 16), None),
        'missing_coordinate': ((((0,), (1, 0), (1, 1)),), (4, 4, 16, 16), None),
        'extra_coordinate': ((((0, 0, 0), (1, 0), (1, 1)),), (4, 4, 16, 16), None),
        'nonnumeric_coordinate': (((('bad', 0), (1, 0), (1, 1)),), (4, 4, 16, 16), None),
        'two_points': ((((0, 0), (1, 1)),), (4, 4, 16, 16), None),
        'collinear': ((((0, 0), (.5, .5), (1, 1)),), (4, 4, 16, 16), None),
        'repeated_point': ((((.5, .5), (.5, .5), (.5, .5)),), (4, 4, 16, 16), None),
        'empty_polygon': (((),), (4, 4, 16, 16), None),
        'outside_empty': ((((2, 2), (3, 2), (3, 3)),), (4, 4, 16, 16), None),
        'empty_component_plus_valid': (((), *square), (4, 4, 16, 16), None),
        'invalid_poly_box_only': (square, (4, 4, 16, 16), (float('nan'), 4, 16, 16)),
        'reversed_poly_box_only': (square, (4, 4, 16, 16), (16, 4, 4, 16)),
        'nan_region': (square, (float('nan'), 4, 16, 16), None),
        'infinite_region': (square, (4, 4, float('inf'), 16), None),
        'nonnumeric_region': (square, ('bad', 4, 16, 16), None),
        'reversed_region': (square, (16, 4, 4, 16), None),
        'zero_region': (square, (4, 4, 4, 16), None),
    }
    return {name: {label: {path: invoke(module, path, region, poly, pb)[0] for path in ['sdr', 'hdr']}
                   for label, module in modules.items()}
            for name, (poly, region, pb) in cases.items()}


def run_ffmpeg(args, scratch):
    proc = subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *args], capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode(errors='replace'))
    return proc.stdout


def decode(path, scratch):
    raw = run_ffmpeg(['-i', str(path), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', 'pipe:1'], scratch)
    buf = np.frombuffer(raw, np.uint16)
    return [buf[:4096].reshape(64, 64), buf[4096:5120].reshape(32, 32), buf[5120:].reshape(32, 32)]


def metadata(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,pix_fmt,width,height,nb_frames,color_transfer,color_primaries,color_space',
        '-of', 'json', str(path)], text=True))


def media_probes(base, donor, scratch):
    """Actual baseline renderer, with donor leaf function swapped only for N02 contrast.

    Track subprocesses solely to clean up geometry-error probes, because these
    exceptions escape the renderer before its own normal process cleanup.
    """
    src = scratch / 'synthetic-hdr.mp4'
    tags = {'-color_primaries': 'bt2020', '-color_trc': 'smpte2084', '-colorspace': 'bt2020nc'}
    raw = np.concatenate([np.full(4096, 900, np.uint16), np.full(1024, 800, np.uint16), np.full(1024, 300, np.uint16)]).tobytes()
    (scratch / 'synthetic.yuv').write_bytes(raw * 3)
    color_args = [v for kv in tags.items() for v in kv]
    run_ffmpeg(['-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', '-s', '64x64', '-r', '3',
                *color_args, '-i', str(scratch / 'synthetic.yuv'), '-c:v', 'libx265',
                '-x265-params', 'lossless=1:pools=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc',
                *color_args, str(src)], scratch)
    source_planes = decode(src, scratch)
    square = (((0, 0), (1, 0), (1, 1), (0, 1)),)
    sparse = (((1/12, 1/12), (2/12, 1/12), (1/12, 2/12)),)
    cases = [('sparse_baseline', sparse, (5, 4, 17, 16), base._blur_silhouette_yuv10),
             ('sparse_donor_leaf', sparse, (5, 4, 17, 16), donor._blur_silhouette_yuv10),
             ('nan_point', (((float('nan'), 0), (1, 0), (1, 1)),), (4, 4, 16, 16), base._blur_silhouette_yuv10),
             ('infinite_point', ((((0, 0), (float('inf'), 0), (1, 1))),), (4, 4, 16, 16), base._blur_silhouette_yuv10),
             ('malformed_point', ((((0,), (1, 0), (1, 1))),), (4, 4, 16, 16), base._blur_silhouette_yuv10),
             ('two_points', ((((0, 0), (1, 1))),), (4, 4, 16, 16), base._blur_silhouette_yuv10),
             ('collinear', ((((0, 0), (.5, .5), (1, 1))),), (4, 4, 16, 16), base._blur_silhouette_yuv10),
             ('nan_box', square, (float('nan'), 4, 16, 16), base._blur_silhouette_yuv10),
             ('reversed_box', square, (16, 4, 4, 16), base._blur_silhouette_yuv10)]
    result = {'source_metadata': metadata(src), 'source_plane_exact': [bool(np.all(p == v)) for p, v in zip(source_planes, [900, 800, 300])], 'cases': {}}
    original_leaf = base._blur_silhouette_yuv10
    original_popen = subprocess.Popen
    class Quiet(base.Callbacks):
        def log(self, message):
            pass
    for name, poly, box, leaf in cases:
        report = scratch / (name + '-report.json')
        report.write_text(json.dumps({'detections': [{'t_start': 0, 't_end': 1, 'cbox': box,
            'category': 'person', 'text': '', 'confidence': 1, 'enabled': True, 'poly': poly}],
            'render_state': {'fps': 3, 'cum': [[0, 0]] * 3, 'bands': [[0, 0]] * 3}}))
        detections, state, _ = base.load_report(str(report))
        dst = scratch / (name + '.mp4')
        procs = []
        captured = []
        class CaptureWriter:
            def __init__(self, underlying):
                self.underlying = underlying
            def write(self, data):
                captured.append(data)
                return self.underlying.write(data)
            def close(self):
                return self.underlying.close()
        def tracked_popen(*args, **kwargs):
            p = original_popen(*args, **kwargs)
            procs.append(p)
            if p.stdin is not None and 'pipe:0' in args[0]:
                p.stdin = CaptureWriter(p.stdin)
            return p
        subprocess.Popen = tracked_popen
        base._blur_silhouette_yuv10 = leaf
        try:
            base.render_hdr(str(src), str(dst), detections, state['cum'], state['bands'], 3, 0, 'box', 'libx265', tags, cb=Quiet())
            outcome = {'status': 'ok', 'output_metadata': metadata(dst)}
            decoded = decode(dst, scratch)
            wire = np.frombuffer(captured[0], np.uint16)
            preencode = [wire[:4096].reshape(64, 64), wire[4096:5120].reshape(32, 32), wire[5120:].reshape(32, 32)]
            (scratch / (name + '-preencode.yuv')).write_bytes(captured[0])
            outcome['preencode_changed_pixels'] = [int(np.count_nonzero(a != b)) for a, b in zip(preencode, source_planes)]
            if name.startswith('sparse'):
                exact = [p.copy() for p in source_planes]
                leaf(*exact, *box, 'box', poly, box)
                required = union_from_luma(exact[0] == 64)
                outcome.update({'required_chroma_cells_yx': np.argwhere(required).tolist(),
                    'preencode_u_at_required': preencode[1][required].tolist(), 'preencode_v_at_required': preencode[2][required].tolist(),
                    'preencode_exact_leaf_match': [bool(np.array_equal(a, b)) for a, b in zip(preencode, exact)],
                    'preencode_luma_pixels_yx': np.argwhere(preencode[0] == 64).tolist(),
                    'preencode_unrelated_chroma_unchanged': bool(np.array_equal(preencode[1][~required], source_planes[1][~required]) and np.array_equal(preencode[2][~required], source_planes[2][~required])),
                    'decoded_u_at_required': decoded[1][required].tolist(), 'decoded_v_at_required': decoded[2][required].tolist(),
                    'decoded_plane_max_abs_vs_exact': [int(np.max(np.abs(a.astype(int) - b.astype(int)))) for a, b in zip(decoded, exact)]})
            else:
                outcome['decoded_luma_changed_pixels'] = int(np.count_nonzero(decoded[0] != source_planes[0]))
            result['cases'][name] = outcome
        except Exception as exc:
            result['cases'][name] = {'status': type(exc).__name__, 'message': str(exc), 'source_trace': traceback.format_exc().splitlines()[-7:]}
        finally:
            subprocess.Popen = original_popen
            base._blur_silhouette_yuv10 = original_leaf
            for p in procs:
                if p.poll() is None:
                    p.terminate()
                for stream in [p.stdin, p.stdout, p.stderr]:
                    if stream:
                        try:
                            stream.close()
                        except OSError:
                            pass
                p.wait(timeout=10)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scratch', type=Path, default=Path('/tmp/openscrub-mask-fidelity-research'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    # Keep this tiny functional exercise from competing with P07 browser work.
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    base, base_source = snapshot(BASE, args.scratch, 'mask_baseline')
    donor, donor_source = snapshot(DONOR, args.scratch, 'mask_donor')
    ranges = {}
    for label, source in [('baseline', base_source), ('donor', donor_source)]:
        ranges[label] = {n.name: [n.lineno, n.end_lineno] for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in ['blur_silhouette', '_blur_silhouette_yuv10', 'rasterize_mask', 'render_hdr', 'render', 'load_report', 'Detection']}
    results = {'baseline': BASE, 'donor': DONOR, 'opencv': cv2.__version__, 'numpy': np.__version__,
               'source_ranges': ranges, 'chroma': chroma_probes({'baseline': base, 'donor': donor}),
               'geometry': geometry_probes({'baseline': base, 'donor': donor})}
    args.output.write_text(json.dumps(results, indent=2) + '\n')
    results['media'] = media_probes(base, donor, args.scratch)
    args.output.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'chroma_cases': len(results['chroma']['cases']),
                      'geometry_cases': len(results['geometry']), 'media_cases': len(results['media']['cases'])}))


if __name__ == '__main__':
    main()
