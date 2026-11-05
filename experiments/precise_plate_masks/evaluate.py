#!/usr/bin/env python3
"""Experimental plate-mask comparison. Never used by OpenScrub's pipeline.

Correct synthetic detector boxes isolate mask refinement from detection recall.
Model quality predictions are not a guarantee of complete redaction coverage.
"""

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import urllib.request

import cv2
import numpy as np
import onnxruntime as ort

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import openscrub
from fixtures import make_cases

MODELS = {
    "efficientsam_ti_encoder.onnx":
        "84ed466ffcc5c1f8d08409bc34a23bb364ab2c15e402cb12d4335a42be0e0951",
    "efficientsam_ti_decoder.onnx":
        "a62f8fa5ea080447c0689418d69e58f1e83e0b7adf9c142e2bd9bcc8045c0b11",
}
MODEL_SOURCE = "https://huggingface.co/yunyangx/EfficientSAM/resolve/d53228e/"


def model_files(root):
    root.mkdir(parents=True, exist_ok=True)
    for name, digest in MODELS.items():
        path = root / name
        if not path.exists():
            tmp = path.with_suffix(".part")
            try:
                with urllib.request.urlopen(MODEL_SOURCE + name, timeout=60) as r:
                    with tmp.open("wb") as f:
                        while block := r.read(1024 * 1024):
                            f.write(block)
                if hashlib.sha256(tmp.read_bytes()).hexdigest() != digest:
                    raise ValueError("Model SHA256 mismatch: " + name)
                tmp.replace(path)
            finally:
                tmp.unlink(missing_ok=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Model SHA256 mismatch: " + name)


class Refiner:
    def __init__(self, root, threads=2):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.encoder = ort.InferenceSession(
            str(root / "efficientsam_ti_encoder.onnx"), opts,
            providers=["CPUExecutionProvider"])
        self.decoder = ort.InferenceSession(
            str(root / "efficientsam_ti_decoder.onnx"), opts,
            providers=["CPUExecutionProvider"])

    def refine(self, frame, box):
        """Return all selected mask pixels, score, component count and timing.

        Crop adds context; box tokens 2/3 are the original local box corners.
        No ground-truth masks influence inference or candidate selection.
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = box
        mx, my = max(12, int((x2-x1)*.25)), max(12, int((y2-y1)*.35))
        cx1, cy1 = max(0, x1-mx), max(0, y1-my)
        cx2, cy2 = min(w, x2+mx), min(h, y2+my)
        crop = frame[cy1:cy2, cx1:cx2]
        inp = np.ascontiguousarray(crop[:, :, ::-1].transpose(2, 0, 1)[None],
                                   dtype=np.float32) / 255.
        points = np.array([[[[x1-cx1, y1-cy1],
                              [x2-1-cx1, y2-1-cy1]]]], np.float32)
        labels = np.array([[[2., 3.]]], np.float32)
        t0 = time.perf_counter()
        embedding = self.encoder.run(None, {"batched_images": inp})[0]
        t1 = time.perf_counter()
        logits, scores, _ = self.decoder.run(None, {
            "image_embeddings": embedding,
            "batched_point_coords": points,
            "batched_point_labels": labels,
            "orig_im_size": np.array(crop.shape[:2], np.int64),
        })
        t2 = time.perf_counter()
        k = int(np.argmax(scores[0, 0]))
        local = logits[0, 0, k] >= 0
        mask = np.zeros((h, w), bool)
        mask[cy1:cy2, cx1:cx2] = local
        components = cv2.connectedComponents(mask.astype(np.uint8))[0]-1
        return mask, float(scores[0, 0, k]), components, {
            "encoder_ms": (t1-t0)*1000,
            "decoder_ms": (t2-t1)*1000,
            "inference_ms": (t2-t0)*1000,
        }


def baseline_mask(shape, box, pad=8):
    """Use the actual engine's rectangular fill with its default render pad."""
    sentinel = np.full((*shape, 3), 127, np.uint8)
    x1, y1, x2, y2 = box
    openscrub.blur_region(sentinel, x1-pad, y1-pad, x2+pad, y2+pad, "box")
    return sentinel[:, :, 0] == 0


def measure(mask, truth):
    covered = int(np.count_nonzero(mask & truth))
    missed = int(np.count_nonzero(truth & ~mask))
    extra = int(np.count_nonzero(mask & ~truth))
    n = int(truth.sum())
    return {"plate_pixels": n, "covered_plate_pixels": covered,
            "missed_plate_pixels": missed, "extra_pixels": extra,
            "coverage_pct": 100*covered/max(1, n),
            "iou": covered/max(1, n+extra)}


def occlusion_measure(mask, full, visible):
    occluder = full & ~visible
    count = int(occluder.sum())
    hidden = int(np.count_nonzero(mask & occluder))
    return {"occluder_pixels": count, "occluder_pixels_redacted": hidden,
            "occluder_preserved_pct": (100*(count-hidden)/count if count else None)}


def redact(frame, mask):
    """Prototype raster compositing preserves all components and holes."""
    result = frame.copy()
    result[mask] = 0
    return result


def png_uri(img):
    ok, data = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("PNG encoding failed")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def write_report(out, rows, summary, images):
    parts = ["<!doctype html><html lang='en'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<title>Precise plate masks — prototype results</title>",
             "<style>body{font:16px/1.5 system-ui;max-width:1250px;margin:32px auto;",
             "padding:0 20px;color:#202630;background:#fafafa}h1{font-size:28px}",
             ".grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}",
             "figure{margin:0}img{width:100%;display:block}figcaption{font-size:13px}",
             "section{padding:20px 0;border-top:1px solid #ccc}table{border-collapse:collapse}",
             "td,th{padding:7px 14px;text-align:left;border-bottom:1px solid #ddd}",
             "@media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}",
             "@media(max-width:420px){.grid{grid-template-columns:1fr}}",
             "</style><h1>Precise plate masks</h1>",
             "<p>Throwaway experiment · synthetic scenes only · CPU inference · solid-fill visualization</p>",
             "<p>The supplied detector boxes come from known synthetic geometry. This isolates mask refinement; "
             "it does not measure plate detection recall or demonstrate real-world redaction safety. "
             "Masks are selected by the model's predicted quality, never by ground truth.</p>",
             "<p>Current rectangle: detector box expanded 8% on each side, plus OpenScrub's default 8-pixel pad. "
             "Refined candidates: full predicted raster mask with the same eight-pixel render padding, "
             "and an experimental smaller three-pixel padding. "
             "A separate numerical fallback experiment uses the rectangle if predicted quality is below "
             "0.85 or the mask is empty. That score rule is experimental and cannot certify coverage; "
             "predicted quality is an uncalibrated regression score, not a probability.</p>",
             "<p>EfficientSAM-Ti: 41,365,489 bytes of SHA256-verified ONNX weights; "
             "Apache-2.0 upstream listing. No additional model is enabled in the application.</p>",
             "<h2>Measured result</h2><table><tr><th>Variant</th><th>Plate coverage</th><th>Extra pixels</th></tr>"]
    for key, label in [("baseline", "Current rectangle + 8px"),
                       ("refined_same_padding", "Refined mask + 8px (same render padding)"),
                       ("refined", "Refined mask + 3px"),
                       ("score_fallback", "Score-based fallback")]:
        value = summary[key]
        parts.append(f"<tr><td>{label}</td><td>{value['coverage_pct']:.3f}%</td>"
                     f"<td>{value['extra_pixels']:,}</td></tr>")
    parts.append("</table><p>Warmed median inference: "
                 f"{summary['median_inference_ms']:.1f} ms per plate crop; "
                     f"{summary['threads']} CPU threads. Shared execution-host timings are indicative only; "
                     "ORT reported that CPU feature detection was unavailable on this host.</p>")
    rejects = sum(not row['accepted_by_score'] for row in rows)
    parts.append(f"<p>The illustrative score gate rejected {rejects} of {len(rows)} masks. "
                 "A high score is not proof that an occluder is excluded or every plate pixel is covered.</p>")
    for row in rows:
        oc = row['occlusion']['raw']
        if 'hole' in row['name'] and oc['occluder_pixels']:
            parts.append(f"<p><strong>Observed limitation:</strong> in the interior-occluder case, "
                         f"the raw model redacted {oc['occluder_pixels_redacted']} of "
                         f"{oc['occluder_pixels']} occluder pixels despite quality "
                         f"{row['quality']:.3f}. The full visible-only objective is not met.</p>")
    for row, (source, baseline, equal_pad, refined) in zip(rows, images):
        parts.append(f"<section><h2>{html.escape(row['name'])}</h2>"
                     f"<p>{html.escape(row['note'])}</p><div class='grid'>")
        for label, img in [("Source — synthetic", source), ("Current rectangle + 8px", baseline),
                           ("Refined mask + 8px", equal_pad), ("Refined mask + 3px", refined)]:
            parts.append(f"<figure><img alt='{html.escape(label)}' src='{png_uri(img)}'>"
                         f"<figcaption>{html.escape(label)}</figcaption></figure>")
        m = row["refined"]
        parts.append(f"</div><p>Three-pixel candidate coverage {m['coverage_pct']:.3f}% · "
                     f"missed {m['missed_plate_pixels']:,} plate pixels · "
                     f"model quality {row['quality']:.3f} · "
                     f"{row['components']} predicted component(s) · "
                     f"{row['inference_ms']:.1f} ms</p>")
        oc = row["occlusion"]["raw"]
        if oc['occluder_pixels']:
            parts.append(f"<p>Occluder pixels over the plate left untouched: "
                         f"raw model {oc['occluder_preserved_pct']:.1f}%; "
                         f"with 8px padding {row['occlusion']['refined_same_padding']['occluder_preserved_pct']:.1f}%; "
                         f"with 3px padding {row['occlusion']['refined']['occluder_preserved_pct']:.1f}%. "
                         "A mask supporting holes does not mean the model detects those holes.</p>")
        parts.append("</section>")
    metrics = base64.b64encode(json.dumps({"summary": summary, "cases": rows},
                                         indent=2).encode()).decode("ascii")
    parts.append("<p>Reproduction and caveats are in the experiment README. "
                 f"<a download='metrics.json' href='data:application/json;base64,{metrics}'>"
                 "Download all measurements (JSON)</a></p></html>")
    (out / "plate-mask-comparison.html").write_text("".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()
    model_files(a.models)
    model = Refiner(a.models, threads=a.threads)
    cases = make_cases()
    # Warm both sessions outside the timed cases.
    model.refine(cases[0].frame, cases[0].detector_box)
    a.output.mkdir(parents=True, exist_ok=True)
    rows, images = [], []
    for case in cases:
        baseline = baseline_mask(case.frame.shape[:2], case.detector_box)
        raw, quality, components, times = model.refine(case.frame, case.detector_box)
        refined = cv2.dilate(raw.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        equal_pad = cv2.dilate(raw.astype(np.uint8), np.ones((17, 17), np.uint8)) > 0
        accepted = quality >= .85 and raw.any()
        fallback = refined if accepted else baseline
        row = {"name": case.name, "note": case.note,
               "detector_box": list(case.detector_box), "quality": quality,
               "components": int(components), "accepted_by_score": bool(accepted),
               **times, "baseline": measure(baseline, case.visible_mask),
               "raw": measure(raw, case.visible_mask),
               "refined": measure(refined, case.visible_mask),
               "refined_same_padding": measure(equal_pad, case.visible_mask),
               "score_fallback": measure(fallback, case.visible_mask)}
        row["occlusion"] = {key: occlusion_measure(mask, case.full_mask, case.visible_mask)
                            for key, mask in [("baseline", baseline), ("raw", raw),
                                              ("refined", refined), ("refined_same_padding", equal_pad)]}
        rows.append(row)
        images.append((case.frame, redact(case.frame, baseline),
                       redact(case.frame, equal_pad), redact(case.frame, refined)))
        cv2.imwrite(str(a.output / (case.name + "-source.png")), case.frame)
        cv2.imwrite(str(a.output / (case.name + "-truth.png")),
                    case.visible_mask.astype(np.uint8)*255)
        cv2.imwrite(str(a.output / (case.name + "-mask.png")), refined.astype(np.uint8)*255)
        cv2.imwrite(str(a.output / (case.name + "-raw-mask.png")), raw.astype(np.uint8)*255)
        print(json.dumps(row), flush=True)
    summary = {"case_count": len(rows), "threads": a.threads,
               "median_inference_ms": statistics.median(r['inference_ms'] for r in rows),
               "environment": {"python": platform.python_version(), "opencv": cv2.__version__,
                               "onnxruntime": ort.__version__, "numpy": np.__version__,
                               "providers": model.encoder.get_providers()},
               "model_sha256": MODELS, "engine_version": openscrub.VERSION}
    for key in ("baseline", "refined_same_padding", "refined", "score_fallback"):
        summary[key] = {metric: sum(r[key][metric] for r in rows)
                        for metric in ("plate_pixels", "covered_plate_pixels",
                                       "missed_plate_pixels", "extra_pixels")}
        summary[key]["coverage_pct"] = (100*summary[key]['covered_plate_pixels'] /
                                        max(1, summary[key]['plate_pixels']))
    (a.output / "metrics.json").write_text(json.dumps({"summary": summary, "cases": rows}, indent=2))
    write_report(a.output, rows, summary, images)
    print("SUMMARY", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
