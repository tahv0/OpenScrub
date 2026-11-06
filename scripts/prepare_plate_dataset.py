#!/usr/bin/env python3
"""Prepare a local YOLO plate dataset from explicit OpenScrub review feedback.

No periodic frame sampling: only manually confirmed detections and manually
drawn plate quadrilaterals are eligible. Propagated tracker shapes and
default-enabled detections are NOT training ground truth.

Examples:
    python scripts/prepare_plate_dataset.py --jobs-dir openscrub_jobs --out plate-data --task detect
    python scripts/prepare_plate_dataset.py --jobs-dir openscrub_jobs --out plate-seg --task segment

The output contains original, UNREDACTED pixels. Keep it private.
This script exports data; it does not train or activate a model.
"""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np


def dhash(image):
    """64-bit difference hash; close crops differ by few bits."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    v = 0
    for b in bits.flat:
        v = (v << 1) | int(b)
    return v


def _split(job, track, index, ratio):
    # A whole tracked object belongs to ONE split. Never scatter adjacent
    # frames of the same plate across train and validation.
    key = f"{job}:{track if track >= 0 else 'single-' + str(index)}"
    frac = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xffffffff
    return "val" if frac < ratio else "train"


def _yolo_line(points):
    # normalized polygon vertices: x1 y1 x2 y2 ...
    return "0 " + " ".join(f"{min(1, max(0, float(v))):.6f}"
                          for pt in points for v in pt)


def _bbox_line(points):
    x = [max(0., min(1., float(p[0]))) for p in points]
    y = [max(0., min(1., float(p[1]))) for p in points]
    x1, x2 = min(x), max(x)
    y1, y2 = min(y), max(y)
    return f"0 {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {x2-x1:.6f} {y2-y1:.6f}"


def _crop_for_box(frame, box):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    margin = max(16, int(max(x2 - x1, y2 - y1) * .4))
    left = max(0, int(x1) - margin)
    top = max(0, int(y1) - margin)
    right = min(w, int(x2) + margin + 1)
    bottom = min(h, int(y2) + margin + 1)
    if right - left < 8 or bottom - top < 8:
        return None, None
    crop = frame[top:bottom, left:right]
    rel = [[(x1-left)/(right-left), (y1-top)/(bottom-top)],
           [(x2-left)/(right-left), (y1-top)/(bottom-top)],
           [(x2-left)/(right-left), (y2-top)/(bottom-top)],
           [(x1-left)/(right-left), (y2-top)/(bottom-top)]]
    return crop, rel


def gather(jobs_dir, task):
    positives, negatives = [], []
    for report in sorted(jobs_dir.glob("*/report.json")):
        job = report.parent
        try:
            doc = json.loads(report.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        rows = doc.get("detections", [])
        # Human-corrected quadrilateral crops are strong segmentation labels.
        manifest = job / "plate_annotations" / "annotations.jsonl"
        if manifest.exists():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                    if item.get("verified_by_user") is not True:
                        continue
                    image_path = manifest.parent / Path(item["image"]).name
                    i = int(item.get("detection_index", -1))
                    corners = np.asarray(item["corners"], dtype=np.float64)
                    if corners.shape != (4, 2) or not np.isfinite(corners).all():
                        continue
                    if not image_path.is_file():
                        continue
                    row = rows[i] if 0 <= i < len(rows) else {}
                    positives.append({"job": job.name, "index": i,
                         "track": int(row.get("track", -1)), "kind": "quad",
                         "image": image_path, "points": corners.tolist()})
                except (KeyError, ValueError, TypeError):
                    continue
        src = Path(doc.get("provenance", {}).get("input") or "")
        if not src.is_file():
            # The job may have been moved. Its verified quad crops can still
            # be exported without a video; report-only labels cannot.
            continue
        for i, row in enumerate(rows):
            if row.get("category") != "plate":
                continue
            label = row.get("verified_label")
            if label not in ("plate", "not_plate"):
                continue
            # A quadrilateral label is only trusted via the manually saved
            # source frame, never by copying a polygon along an auto-track.
            if label == "plate" and row.get("plate_quad"):
                continue
            try:
                conf = float(row.get("confidence", 0))
                frame_time = float(row.get("last_seen", row["t_start"]))
                box = [float(v) for v in row["cbox"]]
                if len(box) != 4:
                    continue
            except (TypeError, KeyError, ValueError):
                continue
            entry = {"job": job.name, "index": i,
                     "track": int(row.get("track", -1)), "kind": label,
                     "video": src, "time": frame_time, "box": box,
                     "confidence": conf}
            (positives if label == "plate" else negatives).append(entry)
    # Strong geometry first; uncertain true positives and confidently wrong
    # negatives make better use of the review budget than random frames.
    positives.sort(key=lambda x: (x["kind"] != "quad",
                                  x.get("confidence", 0.0)))
    negatives.sort(key=lambda x: -x.get("confidence", 0.0))
    return positives, negatives


def export(jobs_dir, out_dir, task, val_ratio=0.2, negative_ratio=2.0,
           dedup_hamming=4):
    positives, negatives = gather(jobs_dir, task)
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = {"positive": [], "negative": []}
    stats = {"positive": 0, "negative": 0, "duplicate": 0, "unreadable": 0}
    manifest = []
    caps = {}

    def write(item, polarity):
        if item["kind"] == "quad":
            image = cv2.imread(str(item["image"]))
            points = item["points"]
            label_quality = "human_quad"
        else:
            src = str(item["video"])
            if src not in caps:
                caps[src] = cv2.VideoCapture(src)
            cap = caps[src]
            cap.set(cv2.CAP_PROP_POS_MSEC, 1000 * item["time"])
            ok, frame = cap.read()
            if not ok:
                stats["unreadable"] += 1
                return False
            # OpenScrub's detections are stored in content coordinates; the
            # scrolling offset must be restored for a correct crop.
            report = jobs_dir / item["job"] / "report.json"
            doc = documents.get(item["job"])
            if doc is None:
                doc = json.loads(report.read_text(encoding="utf-8"))
                documents[item["job"]] = doc
            rs = doc.get("render_state", {})
            fps = float(rs.get("fps") or 30)
            cum = rs.get("cum") or [[0, 0]]
            fidx = min(len(cum)-1, max(0, int(item["time"]*fps)))
            ox, oy = cum[fidx]
            box = [item["box"][0] + ox, item["box"][1] + oy,
                   item["box"][2] + ox, item["box"][3] + oy]
            image, points = _crop_for_box(frame, box)
            if image is None:
                stats["unreadable"] += 1
                return False
            label_quality = ("human_bbox_weak" if polarity == "positive"
                             else "human_hard_negative")
        if image is None or image.size == 0:
            stats["unreadable"] += 1
            return False
        # YOLO-segmentation needs actual manually verified polygons.
        if task == "segment" and polarity == "positive" and item["kind"] != "quad":
            return False
        key = dhash(image)
        if any((key ^ old).bit_count() <= dedup_hamming
               for old in seen[polarity]):
            stats["duplicate"] += 1
            return False
        seen[polarity].append(key)
        split = _split(item["job"], item["track"], item["index"], val_ratio)
        folder = out_dir / "images" / split
        labels = out_dir / "labels" / split
        folder.mkdir(parents=True, exist_ok=True)
        labels.mkdir(parents=True, exist_ok=True)
        name = f"{item['job']}_{item['index']}_{len(manifest):06d}"
        image_path = folder / (name + ".jpg")
        if not cv2.imwrite(str(image_path), image,
                           [cv2.IMWRITE_JPEG_QUALITY, 95]):
            return False
        if polarity == "negative":
            line = ""  # Explicit not-a-plate hard negative.
        elif task == "segment":
            line = _yolo_line(points)
        else:
            line = _bbox_line(points)
        (labels / (name + ".txt")).write_text(
            line + ("\n" if line else ""), encoding="utf-8")
        stats[polarity] += 1
        manifest.append({"image": str(image_path.relative_to(out_dir)),
                         "label": polarity, "quality": label_quality,
                         "split": split, "job": item["job"],
                         "detection_index": item["index"],
                         "track": item["track"]})
        return True

    documents = {}
    try:
        for item in positives:
            write(item, "positive")
        max_neg = int(stats["positive"] * max(0, negative_ratio))
        for item in negatives:
            if stats["negative"] >= max_neg:
                break
            write(item, "negative")
    finally:
        for cap in caps.values():
            cap.release()
    (out_dir / "manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in manifest), encoding="utf-8")
    (out_dir / "data.yaml").write_text(
        "path: " + str(out_dir.resolve()) + "\n"
        "train: images/train\nval: images/val\n"
        "names:\n  0: plate\n", encoding="utf-8")
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", choices=("detect", "segment"),
                        default="detect")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--negative-ratio", type=float, default=2.0)
    parser.add_argument("--dedup-hamming", type=int, default=4)
    args = parser.parse_args()
    if not args.jobs_dir.is_dir():
        parser.error("--jobs-dir must be an existing OpenScrub job directory")
    if not 0 <= args.val_ratio <= 0.5:
        parser.error("--val-ratio must be between 0 and 0.5")
    if not 0 <= args.dedup_hamming <= 64:
        parser.error("--dedup-hamming must be between 0 and 64")
    stats = export(args.jobs_dir, args.out, args.task, args.val_ratio,
                   args.negative_ratio, args.dedup_hamming)
    print(json.dumps(stats, indent=2))
    print("Exported crops contain unredacted PII. Keep the output private.")
    print("This script does not train or activate a model.")


if __name__ == "__main__":
    main()
