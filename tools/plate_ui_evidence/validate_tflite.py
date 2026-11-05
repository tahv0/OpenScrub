#!/usr/bin/env python3
"""Synthetic-only, full-frame evaluation of a pinned plate segmentation model.

No ground truth is used to select outputs, threshold, or preprocessing.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from fixtures import make_cases

URL = ('https://github.com/amirreza-hos/tflite-license-plate-segmentation/'
       'releases/download/v1.0/plate_seg_unet_mobilenetv2_quant_dynamic.tflite')
SHA256 = '96b2f877d3c055c8e0bc4e538420bd54f4f856554e4ca9886a4f3be8569f21c4'
SIZE = 8320992


def obtain_model(path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + '.part')
        try:
            with urllib.request.urlopen(URL, timeout=120) as source, part.open('wb') as out:
                while block := source.read(1024 * 1024):
                    out.write(block)
            if part.stat().st_size != SIZE or hashlib.sha256(part.read_bytes()).hexdigest() != SHA256:
                raise ValueError('Downloaded model failed size or SHA-256 verification')
            part.replace(path)
        finally:
            part.unlink(missing_ok=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.stat().st_size != SIZE or digest != SHA256:
        raise ValueError('Model failed size or SHA-256 verification')
    return digest


def counts(mask, truth):
    total = int(truth.sum())
    hit = int(np.count_nonzero(mask & truth))
    return {'total': total, 'covered': hit, 'missed': total - hit,
            'coverage_pct': 100.0 * hit / total if total else None}


def nearest_tf(mask, height, width):
    # tf.image.resize(method='nearest') uses half-pixel centers.
    y = np.minimum(((np.arange(height) + .5) * mask.shape[0] / height).astype(int), mask.shape[0]-1)
    x = np.minimum(((np.arange(width) + .5) * mask.shape[1] / width).astype(int), mask.shape[1]-1)
    return mask[y[:, None], x[None, :]]


def save(path, image):
    if not cv2.imwrite(str(path), image):
        raise OSError(f'Could not write {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=Path('plate_seg_unet_mobilenetv2_quant_dynamic.tflite'))
    parser.add_argument('--output', type=Path, default=Path('tflite-results'))
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('--threads must be positive')
    digest = obtain_model(args.model)
    from ai_edge_litert.interpreter import Interpreter
    interpreter = Interpreter(model_path=str(args.model), num_threads=args.threads)
    interpreter.allocate_tensors()
    inputs, outputs = interpreter.get_input_details(), interpreter.get_output_details()
    if len(inputs) != 1 or len(outputs) != 1:
        raise ValueError('Expected exactly one input and one output tensor')
    inp, out = inputs[0], outputs[0]
    if tuple(inp['shape']) != (1, 512, 512, 3) or inp['dtype'] != np.float32:
        raise ValueError(f'Unexpected input tensor: {inp}')
    if tuple(out['shape']) != (1, 512, 512, 1) or out['dtype'] != np.float32:
        raise ValueError(f'Unexpected output tensor: {out}')
    args.output.mkdir(parents=True, exist_ok=True)

    def infer(frame):
        # The author's example uses full-frame RGB, bilinear resize, and /255.
        # Convert to float BEFORE resize to avoid uint8 interpolation rounding.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32)
        batch = np.ascontiguousarray(cv2.resize(rgb, (512, 512), interpolation=cv2.INTER_LINEAR)[None] / 255.0)
        interpreter.set_tensor(inp['index'], batch)
        start = time.perf_counter()
        interpreter.invoke()
        ms = (time.perf_counter() - start) * 1000
        prob = interpreter.get_tensor(out['index'])[0, :, :, 0]
        if not np.isfinite(prob).all() or prob.min() < -1e-5 or prob.max() > 1.00001:
            raise ValueError('Output is not finite sigmoid-like probability in [0,1]')
        raw512 = prob > .5
        return raw512, nearest_tf(raw512, *frame.shape[:2]), ms, float(prob.min()), float(prob.max())

    cases = make_cases()
    infer(cases[0].frame)  # warmup excluded
    rows = []
    for case in cases:
        raw512, mask, ms, pmin, pmax = infer(case.frame)
        visible = case.visible_mask
        occluder = case.full_mask & ~visible
        occ = counts(mask, occluder)
        components = int(cv2.connectedComponents(mask.astype(np.uint8))[0] - 1)
        row = {'name': case.name, 'note': case.note, 'inference_ms': ms,
               'visible_plate': counts(mask, visible),
               'visible_lettering': counts(mask, case.text_mask),
               'extra_pixels_outside_visible_plate': int(np.count_nonzero(mask & ~visible)),
               'occluder': {'total': occ['total'], 'redacted': occ['covered'],
                            'preserved': occ['missed'],
                            'preserved_pct': 100.0 * occ['missed'] / occ['total'] if occ['total'] else None},
               'components': components, 'output_min': pmin, 'output_max': pmax}
        rows.append(row)
        save(args.output / f'{case.name}-source.png', case.frame)
        for suffix, arr in [('visible-truth', visible), ('letter-truth', case.text_mask),
                            ('occluder-truth', occluder), ('mask-512', raw512), ('mask', mask)]:
            save(args.output / f'{case.name}-{suffix}.png', arr.astype(np.uint8) * 255)
        preview = case.frame.copy()
        preview[mask] = 0
        save(args.output / f'{case.name}-redacted.png', preview)
    result = {'scope': 'synthetic only; full frame; no truth-guided selection; no dilation',
              'model_url': URL, 'model_bytes': SIZE, 'model_sha256': digest,
              'model_input': {'shape': list(map(int, inp['shape'])), 'dtype': str(inp['dtype'])},
              'model_output': {'shape': list(map(int, out['shape'])), 'dtype': str(out['dtype'])},
              'preprocessing': 'full frame BGR to RGB; float bilinear resize to 512x512; divide by 255',
              'postprocessing': 'probability > 0.5 at 512x512; nearest half-pixel resize to frame',
              'latency': {'unit': 'ms', 'measures': 'invoke only; excludes preprocessing and model setup',
                          'warmup_runs': 1, 'threads': args.threads,
                          'median': statistics.median(x['inference_ms'] for x in rows)},
              'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                              'numpy': np.__version__, 'opencv': cv2.__version__,
                              'ai_edge_litert': importlib.metadata.version('ai-edge-litert')},
              'cases': rows}
    (args.output / 'metrics.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
