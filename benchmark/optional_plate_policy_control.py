"""Timed synthetic control for the optional plate policy (not calibration).

Run with an already downloaded YOLOv9-T ONNX file and FFmpeg on PATH:
    python benchmark/optional_plate_policy_control.py --model /path/to/model.onnx
The output contains synthetic fixture metadata and aggregate counts only.
"""

import argparse
import hashlib
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openscrub

MODEL_SHA256 = 'c3c1026ca7d0585dd88084d68182dd897113712fa734ae1557ca70174440c076'


class Quiet(openscrub.Callbacks):
    def log(self, message):
        pass


def fixtures():
    rng = np.random.default_rng(747)
    out = {}
    for kind, segment in [('clean', 236), ('partial_shadow', 214), ('dim', 130), ('empty', 95)]:
        frame = rng.integers(50, 85, size=(360, 640, 3), dtype=np.uint8)
        if kind != 'empty':
            x, y, width, height = 204, 146, 232, 62
            cv2.rectangle(frame, (x, y), (x + width, y + height), (segment,) * 3, -1)
            cv2.rectangle(frame, (x, y), (x + width, y + height), (20,) * 3, 2)
            cv2.rectangle(frame, (x + 4, y + 3), (x + 28, y + height - 3), (178, 49, 20), -1)
            cv2.putText(frame, 'QZ 27 KTX', (x + 32, y + 42), cv2.FONT_HERSHEY_SIMPLEX,
                        1.12, (19,) * 3, 2, cv2.LINE_AA)
            if kind == 'partial_shadow':
                frame[y:y + height, x + 140:x + width] //= 2
        out[kind] = frame
    return out


def mask_fractions(path):
    cap = cv2.VideoCapture(str(path))
    fractions = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame[110:245, 150:470], cv2.COLOR_BGR2GRAY)
        fractions.append(round(float(np.mean(gray < 10)), 4))
    cap.release()
    return fractions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    options = parser.parse_args()
    model = Path(options.model).resolve()
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise ValueError('unexpected model sha256')
    cv2.setNumThreads(1)
    images = fixtures()
    sequence = (['empty'] * 2 + ['partial_shadow'] + ['empty'] * 2 +
                ['clean'] * 4 + ['empty'] * 2 + ['dim'] * 3 + ['empty'] * 2)
    with tempfile.TemporaryDirectory(prefix='openscrub-optional-control-') as temp:
        directory = Path(temp)
        source = directory / 'source.avi'
        writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'FFV1'), 8., (640, 360))
        if not writer.isOpened():
            raise RuntimeError('FFV1 fixture codec unavailable')
        for name in sequence:
            writer.write(images[name])
        writer.release()
        results = []
        for policy in ('off', 'manual_review', 'blur_candidates'):
            output = directory / (policy + '.mp4')
            report_path = directory / (policy + '.json')
            flags = ([] if policy == 'off' else
                     ['--uncertain-policy', policy, '--plate-auto-cutoff', '.48'])
            parser = openscrub.build_parser()
            args = openscrub._prep_args(parser.parse_args([
                str(source), '--categories', 'plate', '--plate-model', str(model),
                '--plate-threshold', '.1', '--tile', 'off', '--no-vfr-fix',
                '--scan-speed', 'thorough', '--mode', 'box', '--pad', '0',
                '--encoder', 'x264', '--output', str(output), '--report', str(report_path),
                *flags]), parser)
            start = time.perf_counter()
            state = openscrub.run_scan(args, Quiet())
            scan_s = time.perf_counter() - start
            start = time.perf_counter()
            openscrub.run_render(args, state, Quiet())
            render_s = time.perf_counter() - start
            report = json.loads(report_path.read_text())
            direct = [{'frame': row['policy_evidence']['frame'],
                       'score': row['confidence'], 'enabled': row['enabled']}
                      for row in report['detections']
                      if row.get('policy_evidence', {}).get('origin') == 'detection']
            results.append({'policy': policy, 'scan_seconds': round(scan_s, 3),
                            'render_seconds': round(render_s, 3),
                            'report_rows': len(report['detections']),
                            'direct': direct, 'black_roi_fraction': mask_fractions(output)})
        print(json.dumps({'model_sha256': digest, 'python': platform.python_version(),
                          'opencv': cv2.__version__, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                          'fps': 8, 'frames': sequence, 'candidate_floor': .1,
                          'auto_cutoff_control_only': .48, 'scan_stride': 1,
                          'backend': 'onnxruntime', 'results': results}, indent=2))


if __name__ == '__main__':
    main()
