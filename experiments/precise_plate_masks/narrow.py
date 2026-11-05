#!/usr/bin/env python3
"""Experimental number-lettering mode, separate from production redaction.

Detect text within a supplied plate box without recognizing/storing characters.
Extra padding defaults to zero. Ground-truth lettering is used only for scoring.
"""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import statistics
import time
import urllib.request

import cv2
import numpy as np
import onnxruntime as ort

from evaluate import baseline_mask, openscrub, png_uri, redact
from fixtures import make_cases


def offset_convex(points, distance):
    """Offset convex edges in image pixels; zero is an exact identity."""
    points = np.asarray(points, np.float64)
    if distance == 0:
        return points.copy()
    center = points.mean(axis=0)
    normals, constants = [], []
    for p, q in zip(points, np.roll(points, -1, axis=0)):
        delta = q-p
        norm = np.linalg.norm(delta)
        if norm < 1e-8:
            raise ValueError("degenerate polygon")
        n = np.array([delta[1], -delta[0]])/norm
        if np.dot(n, center-p) > 0:
            n = -n
        normals.append(n)
        constants.append(np.dot(n, p)+distance)
    vertices = []
    for i in range(len(points)):
        m = np.array([normals[i-1], normals[i]])
        if abs(np.linalg.det(m)) < 1e-8:
            raise ValueError("parallel polygon edges")
        vertices.append(np.linalg.solve(m, [constants[i-1], constants[i]]))
    return np.array(vertices)


def text_model(root):
    root.mkdir(parents=True, exist_ok=True)
    p = root / "text_detection_ppocrv5_mobile.onnx"
    if not p.exists():
        tmp = p.with_suffix(".part")
        try:
            with urllib.request.urlopen(openscrub.PPDET_URL, timeout=60) as r, tmp.open("wb") as f:
                while block := r.read(1024*1024):
                    f.write(block)
            if hashlib.sha256(tmp.read_bytes()).hexdigest() != openscrub.PPDET_SHA256:
                raise ValueError("text detector hash mismatch")
            tmp.replace(p)
        finally:
            tmp.unlink(missing_ok=True)
    if hashlib.sha256(p.read_bytes()).hexdigest() != openscrub.PPDET_SHA256:
        raise ValueError("text detector hash mismatch")
    return p


class NarrowDetector:
    def __init__(self, path, threads=2):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), opts,
                                           providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def find(self, frame, box):
        """Return restored text polygons and inference ms; no OCR or GT input.

        DB predicts shrunken text kernels. The standard area/perimeter unclip
        restores the text region; optional user padding is a separate operation.
        Relative text height filters tiny plate captions, not recognized words.
        """
        x1, y1, x2, y2 = box
        crop = frame[y1:y2, x1:x2]
        h, w = crop.shape[:2]
        scale = 640/max(h, w)
        nw = max(32, int(round(w*scale/32))*32)
        nh = max(32, int(round(h*scale/32))*32)
        img = cv2.resize(crop, (nw, nh)).astype(np.float32)/255.
        img = (img[:, :, ::-1]-(.485, .456, .406))/(.229, .224, .225)
        blob = img.transpose(2, 0, 1)[None].astype(np.float32)
        t0 = time.perf_counter()
        prob = self.session.run(None, {self.input_name: blob})[0][0, 0]
        elapsed = (time.perf_counter()-t0)*1000
        cnts, _ = cv2.findContours((prob > .3).astype(np.uint8),
                                   cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for contour in cnts:
            area = cv2.contourArea(contour)
            if area < 9:
                continue
            m = np.zeros(prob.shape, np.uint8)
            cv2.drawContours(m, [contour], -1, 1, -1)
            score = float(prob[m != 0].mean())
            if score < .5:
                continue
            rect = cv2.minAreaRect(contour)
            if min(rect[1]) < 2:
                continue
            # Follow DB's quad decode: restore the same min-area box whose
            # area/perimeter determines the expansion, not a different contour.
            poly = cv2.boxPoints(rect)
            perimeter = cv2.arcLength(poly, True)
            poly_area = cv2.contourArea(poly)
            # Reconstruction of DB's shrunken kernel, not extra safety padding.
            distance = 1.5*poly_area/max(perimeter, 1e-6)
            poly = offset_convex(poly, distance)
            poly *= (w/float(prob.shape[1]), h/float(prob.shape[0]))
            poly += (x1, y1)
            height = min(rect[1])*min(w/float(prob.shape[1]), h/float(prob.shape[0]))
            candidates.append((poly, height, score))
        if not candidates:
            return [], elapsed
        max_height = max(c[1] for c in candidates)
        # A geometric prototype heuristic; same-size auxiliary text is ambiguous.
        return [(p, score) for p, height, score in candidates
                if height >= .45*max_height], elapsed


def polygon_mask(shape, polygons, padding):
    mask = np.zeros(shape, np.uint8)
    for poly, _ in polygons:
        p = offset_convex(poly, padding)
        cv2.fillPoly(mask, [np.rint(p).astype(np.int32)], 255)
    return mask != 0


def residual_text_evidence(frame, box, polygons, covered):
    """Flag uncovered, character-sized contrast components aligned to text.

    This image-only heuristic can reject a missed isolated character. Passing
    is not proof of completeness, especially with glare/complex plate designs.
    """
    if not polygons:
        return 0
    x1, y1, x2, y2 = box
    gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    local_covered = covered[y1:y2, x1:x2]
    pixels = gray[local_covered]
    if len(pixels) < 8 or int(pixels.max())-int(pixels.min()) < 25:
        return 0
    threshold, _ = cv2.threshold(pixels[:, None], 0, 255,
                                  cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    # Characters are normally the minority contrast class within a text box.
    dark = int((pixels <= threshold).sum()) < len(pixels)/2
    rows = [cv2.minAreaRect(np.asarray(p, np.float32)) for p, _ in polygons]
    nominal_height = float(np.median([min(r[1]) for r in rows]))
    # Remove broad background/occluder regions first: an exposed character can
    # touch a foreground pole and would merge into its huge threshold component.
    k = max(3, int(.3*nominal_height) | 1)
    contrast = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT if dark else cv2.MORPH_TOPHAT,
                                np.ones((k, k), np.uint8))
    ink = (contrast > 20).astype(np.uint8)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(ink, connectivity=8)
    evidence = 0
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if x <= 0 or y <= 0 or x+w >= gray.shape[1] or y+h >= gray.shape[0]:
            continue
        if not (.3*nominal_height <= h <= 1.4*nominal_height
                and 2 <= w <= 1.5*nominal_height and area >= 8):
            continue
        cx, cy = centers[i] + (x1, y1)
        aligned = False
        for center, size, angle in rows:
            theta = np.deg2rad(angle + (90 if size[0] < size[1] else 0))
            perpendicular = np.array([-np.sin(theta), np.cos(theta)])
            if abs(np.dot(np.array([cx, cy])-center, perpendicular)) < .65*min(size):
                aligned = True
                break
        if not aligned:
            continue
        component = labels == i
        missing = int(np.count_nonzero(component & ~local_covered))
        if missing >= 10 and missing > .15*area:
            evidence += 1
    return evidence


def metrics(mask, case):
    text = case.text_mask
    missed = int(np.count_nonzero(text & ~mask))
    count = int(text.sum())
    background = case.visible_mask & ~text
    return {"letter_pixels": count, "missed_letter_pixels": missed,
            "letter_coverage_pct": 100*(count-missed)/max(1, count),
            "extra_pixels": int(np.count_nonzero(mask & ~text)),
            "plate_background_pixels": int(background.sum()),
            "plate_background_pixels_preserved": int(np.count_nonzero(background & ~mask))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--narrow-padding", type=float, default=0.,
                    help="Extra outward padding in source pixels; default: 0")
    a = ap.parse_args()
    if a.narrow_padding < 0 or not np.isfinite(a.narrow_padding):
        ap.error("--narrow-padding must be finite and nonnegative")
    path = text_model(a.models)
    model = NarrowDetector(path)
    cases = make_cases()
    model.find(cases[0].frame, cases[0].detector_box)
    a.output.mkdir(parents=True, exist_ok=True)
    rows = []
    panels = []
    for case in cases:
        polys, elapsed = model.find(case.frame, case.detector_box)
        baseline = baseline_mask(case.frame.shape[:2], case.detector_box)
        narrow = polygon_mask(case.frame.shape[:2], polys, a.narrow_padding)
        plus_one = polygon_mask(case.frame.shape[:2], polys, a.narrow_padding+1)
        candidate = narrow.copy()
        residual = residual_text_evidence(case.frame, case.detector_box, polys, narrow)
        # Reject empty localization and visible evidence of an incomplete line.
        fallback = not polys or residual > 0
        if fallback:
            narrow, plus_one = baseline, baseline
        row = {"name": case.name, "text_region_count": len(polys),
               "fallback_to_plate": fallback, "inference_ms": elapsed,
               "residual_text_components": residual,
               "fallback_reason": ('no_text_detected' if not polys else
                                   'residual_text_evidence' if residual else None),
               "baseline": metrics(baseline, case), "narrow": metrics(narrow, case),
               "ungated_candidate": metrics(candidate, case),
               "narrow_plus_one": metrics(plus_one, case)}
        rows.append(row)
        panels.append((case.frame, redact(case.frame, baseline),
                       redact(case.frame, narrow), redact(case.frame, plus_one)))
        cv2.imwrite(str(a.output/(case.name+'-narrow.png')), redact(case.frame, narrow))
        cv2.imwrite(str(a.output/(case.name+'-target.png')), case.text_mask.astype(np.uint8)*255)
        print(json.dumps(row), flush=True)
    summary = {"case_count": len(rows), "padding_px": a.narrow_padding,
               "median_text_detection_ms": statistics.median(r['inference_ms'] for r in rows),
               "model_bytes": path.stat().st_size, "model_sha256": openscrub.PPDET_SHA256,
               "fallback_count": sum(r['fallback_to_plate'] for r in rows)}
    for key in ('baseline', 'narrow', 'narrow_plus_one'):
        s = {field: sum(r[key][field] for r in rows) for field in
             ('letter_pixels', 'missed_letter_pixels', 'extra_pixels',
              'plate_background_pixels', 'plate_background_pixels_preserved')}
        s['letter_coverage_pct'] = 100*(s['letter_pixels']-s['missed_letter_pixels'])/max(1, s['letter_pixels'])
        s['plate_background_preserved_pct'] = 100*s['plate_background_pixels_preserved']/max(1, s['plate_background_pixels'])
        summary[key] = s
    data = {"summary": summary, "cases": rows}
    (a.output/'narrow-metrics.json').write_text(json.dumps(data, indent=2))
    report = ["<!doctype html><html lang='en'><meta charset='utf-8'>",
              "<meta name='viewport' content='width=device-width,initial-scale=1'>",
              "<title>Narrow plate lettering — prototype</title>",
              "<style>body{font:16px/1.5 system-ui;color:#202630;background:#fafafa;",
              "max-width:1250px;margin:30px auto;padding:0 18px}",
              ".grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}",
              "img{width:100%;display:block}figure{margin:0}figcaption{font-size:13px}",
              "section{padding:20px 0;border-top:1px solid #bbb}td,th{padding:8px;text-align:left}",
              "@media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}",
              "@media(max-width:420px){.grid{grid-template-columns:1fr}}</style>",
              "<h1>Narrow plate lettering</h1><p>Experimental comparison · synthetic scenes · no OCR/recognition</p>",
              "<p>Narrow mode targets the dominant text region(s) inside a supplied plate box. "
              "Plate edges and background may remain visible. Extra user padding defaults to zero. "
              "DB kernel restoration is still necessary to recover text boundaries predicted by the model; "
              "zero extra padding does not mean a mask of individual ink pixels.</p>",
              "<p>This reuses OpenScrub's approximately 4.7 MB PP-OCRv5 text detector, not EfficientSAM. "
              "Correct synthetic plate boxes isolate text localization from plate detection. "
              "Ground-truth glyph masks are only used for scoring. Tiny captions are filtered by relative "
              "text height, which cannot reliably distinguish same-size auxiliary text from the plate number.</p>",
              "<p>Empty text results or detected residual character-like strokes fall back to the full plate "
              "and are explicitly reported. This image-only incompleteness heuristic does not certify "
              "that all target letters were found; a zero-padding candidate may still miss edge pixels. "
              "Both padding variants share the zero-padding gate decision, so the extra-pixel column "
              "isolates the padding change rather than independently retesting that gate.</p>",
              "<h2>Measured comparison</h2><table><tr><th>Mode</th><th>Letter pixels covered</th><th>Plate background preserved</th></tr>"]
    for key,label in [('baseline','Current plate box'),('narrow',f'Narrow + {a.narrow_padding:g}px'),
                      ('narrow_plus_one',f'Narrow + {a.narrow_padding+1:g}px')]:
        m=summary[key]
        report.append(f"<tr><td>{label}</td><td>{m['letter_coverage_pct']:.3f}%</td>"
                      f"<td>{m['plate_background_preserved_pct']:.1f}%</td></tr>")
    report.append(f"</table><p>Warmed median text detection: {summary['median_text_detection_ms']:.1f} ms "
                  f"per crop on this CPU host, two ORT threads. Fallbacks: {summary['fallback_count']}. "
                  "These synthetic results do not establish real-footage reliability.</p>")
    for row, imgs in zip(rows, panels):
        report.append(f"<section><h2>{html.escape(row['name'])}</h2><div class='grid'>")
        labels=['Synthetic source','Current plate box',f'Narrow + {a.narrow_padding:g}px',
                f'Narrow + {a.narrow_padding+1:g}px']
        for label, img in zip(labels, imgs):
            report.append(f"<figure><img src='{png_uri(img)}' alt='{html.escape(label)}'>"
                          f"<figcaption>{label}</figcaption></figure>")
        m=row['narrow']
        report.append(f"</div><p>Found {row['text_region_count']} text region(s); "
                      f"missed {m['missed_letter_pixels']} of {m['letter_pixels']} visible letter pixels "
                      f"at {a.narrow_padding:g}px extra padding. Full-plate fallback: "
                      f"{row['fallback_to_plate']} ({html.escape(str(row['fallback_reason']))}). "
                      f"Unrejected candidate would miss {row['ungated_candidate']['missed_letter_pixels']} "
                      "letter pixels.</p></section>")
    encoded=base64.b64encode(json.dumps(data,indent=2).encode()).decode('ascii')
    report.append(f"<a download='narrow-metrics.json' href='data:application/json;base64,{encoded}'>"
                  "Download measurements (JSON)</a></html>")
    (a.output/'narrow-plate-comparison.html').write_text(''.join(report),encoding='utf-8')
    print('SUMMARY',json.dumps(summary),flush=True)


if __name__ == '__main__':
    main()
