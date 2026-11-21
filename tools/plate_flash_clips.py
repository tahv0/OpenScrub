#!/usr/bin/env python3
"""Find frames where a plate track goes unblurred and cut short comparison clips.

Uses the installed OpenScrub engine's own report decoding and per-frame
activity rules, so "blurred" here means what the renderer would do with
this report. Run it inside the container (openscrub + ffmpeg are there):

  python tools/plate_flash_clips.py REPORT.json --source SRC.mp4 --output OUT.mp4 \
      --out-dir /media/d/flash_clips

  --dry-run      analyse only, cut nothing
  --crops N      instead of clips: save N plate crops per lettering-mode
                 fallback reason (from the scanned video) for diagnosis
  --top N        number of clips (default 5)
  --category C   default plate
"""
import argparse
import collections
import json
import math
import os
import shutil
import subprocess
import sys


def load_engine(path):
    if path:
        sys.path.insert(0, path)
    try:
        import openscrub
    except ImportError as e:
        sys.exit("cannot import openscrub (%s); run inside the container or pass "
                 "--engine-path /src" % e)
    return openscrub


def track_extents(doc, category, fps):
    """Frame range each track covers in the RAW report (every row, decided or not)."""
    ext = {}
    for r in doc.get("detections", []):
        if r.get("category") != category or r.get("zone_dropped"):
            continue
        tid = int(r.get("track", -1))
        if tid < 0:
            continue
        a = int(math.ceil(float(r["t_start"]) * fps - 1e-6))
        b = int(math.floor(float(r["t_end"]) * fps + 1e-6))
        lo, hi = ext.get(tid, (a, b))
        ext[tid] = (min(lo, a), max(hi, b))
    return ext


def blurred_frames(engine, dets, category, fps):
    """track -> set of frame indexes the renderer would blur for that track."""
    out = collections.defaultdict(set)
    for d in dets:
        if d.category != category or d.track < 0:
            continue
        a = int(math.ceil((d.t_start - 0.01) * fps - 1e-6))
        b = int(math.floor((d.t_end + 0.01) * fps + 1e-6))
        for idx in range(max(0, a), b + 1):
            if engine._active_on_frame(d, idx / fps, idx) and engine._frame_authorized(d, idx):
                out[d.track].add(idx)
    return out


def runs(frames):
    """Sorted frame list -> [(first, last)] consecutive runs."""
    out = []
    for f in frames:
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return [tuple(r) for r in out]


def analyse(engine, report, category):
    with open(report, encoding="utf-8") as f:
        doc = json.load(f)
    dets, state, prov = engine.load_report(report)
    fps = float((state or {}).get("fps") or 30.0)
    ext = track_extents(doc, category, fps)
    blur = blurred_frames(engine, dets, category, fps)
    tracks = {}
    for tid, (lo, hi) in sorted(ext.items()):
        on = blur.get(tid, set())
        visible = [f for f in range(lo, hi + 1) if f not in on]
        gaps = runs(visible)
        # a flash = visible run with blur on BOTH sides (mid-track drop-out)
        flashes = [g for g in gaps if g[0] > lo and g[1] < hi
                   and (g[0] - 1) in on and (g[1] + 1) in on]
        tracks[tid] = {"first_frame": lo, "last_frame": hi,
                       "frames": hi - lo + 1, "blurred": len(on & set(range(lo, hi + 1))),
                       "visible": len(visible), "flashes": flashes,
                       "never_blurred": not on}
    rows = [r for r in doc.get("detections", []) if r.get("category") == category]
    summary = {
        "report": os.path.abspath(report), "fps": fps,
        "settings": (prov or {}).get("settings"),
        "plate_policy_evidence_version": doc.get("plate_policy_evidence_version"),
        "plate_fallbacks": doc.get("plate_fallbacks"),
        "plate_coverage_limitation": doc.get("plate_coverage_limitation"),
        "rows": len(rows),
        "rows_by_origin": collections.Counter(
            str((r.get("policy_evidence") or {}).get("origin")) for r in rows),
        "rows_by_choice": collections.Counter(str(r.get("output_choice")) for r in rows),
        "narrow_by_fallback": collections.Counter(
            ((r.get("narrow_plate") or {}).get("fallback") or "narrow_ok")
            if "narrow_plate" in r else "<no narrow>" for r in rows),
        "tracks": len(tracks),
        "tracks_with_flashes": sum(1 for t in tracks.values() if t["flashes"]),
        "tracks_never_blurred": sum(1 for t in tracks.values() if t["never_blurred"]),
        "flash_runs": sum(len(t["flashes"]) for t in tracks.values()),
        "frames_in_tracks": sum(t["frames"] for t in tracks.values()),
        "frames_visible": sum(t["visible"] for t in tracks.values()),
    }
    return summary, tracks, fps


def pick_clips(tracks, fps, top, pad, max_len):
    """Greedy: windows (<= max_len s) holding the most flash runs, non-overlapping."""
    events = sorted((a, b, tid) for tid, t in tracks.items() for a, b in t["flashes"])
    win = int(max_len * fps)
    cands = []
    for i, (a, _, _) in enumerate(events):
        j, members = i, []
        while j < len(events) and events[j][0] - a <= win:
            members.append(events[j])
            j += 1
        cands.append((len(members), sum(e[1] - e[0] + 1 for e in members), a, members))
    cands.sort(key=lambda c: (-c[0], -c[1], c[2]))
    chosen = []
    for n, frames, a, members in cands:
        lo = max(0, a - int(pad * fps))
        hi = max(e[1] for e in members) + int(pad * fps)
        if any(not (hi < c["lo"] or lo > c["hi"]) for c in chosen):
            continue
        chosen.append({"lo": lo, "hi": hi, "flash_runs": n, "flash_frames": frames,
                       "events": [{"track": tid, "first": x, "last": y} for x, y, tid in members]})
        if len(chosen) >= top:
            break
    return sorted(chosen, key=lambda c: c["lo"])


def cut(src, start, dur, dst, copy):
    codec = (["-c", "copy"] if copy else
             ["-c:v", "libx264", "-crf", "16", "-preset", "veryfast", "-pix_fmt", "yuv420p"])
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", "%.3f" % start, "-i", src, "-t", "%.3f" % dur, "-map", "0:v:0", "-an",
           *codec, dst]
    subprocess.run(cmd, check=True)


def side_by_side(a, b, dst):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", a, "-i", b,
           "-filter_complex",
           "[0:v]scale=960:-2,setsar=1[l];[1:v]scale=960:-2,setsar=1[r];[l][r]hstack=shortest=1",
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p", dst]
    subprocess.run(cmd, check=True)


def export_crops(engine, report, per_reason, out_dir, video=None, margin=1.0):
    """Save plate crops grouped by lettering-mode outcome.

    Each crop keeps `margin` x the plate size on every side at full source
    resolution (so the text-region check can be re-run on it offline), plus
    an enlarged preview with the detector box drawn. crops.json records the
    box inside each crop and the stored outcome.
    """
    import cv2
    import numpy as np
    with open(report, encoding="utf-8") as f:
        doc = json.load(f)
    fps = float((doc.get("render_state") or {}).get("fps") or 30.0)
    video = video or (doc.get("provenance") or {}).get("input")
    if not video or not os.path.exists(video):
        sys.exit("scanned video not found (%r); pass --scan-video" % video)
    groups = collections.defaultdict(list)
    for r in doc.get("detections", []):
        ev = r.get("narrow_plate")
        if r.get("category") != "plate" or not isinstance(ev, dict):
            continue
        if type(ev.get("frame_index")) is not int:
            continue
        groups[ev.get("fallback") or "narrow_ok"].append(r)
    picks = []
    for reason, rows in sorted(groups.items()):
        rows.sort(key=lambda r: r["narrow_plate"]["frame_index"])
        n = min(per_reason, len(rows))
        for k in np.linspace(0, len(rows) - 1, n).round().astype(int) if n else []:
            picks.append((reason, rows[int(k)]))
    picks.sort(key=lambda p: p[1]["narrow_plate"]["frame_index"])
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit("cannot open %s" % video)
    meta = []
    for i, (reason, r) in enumerate(picks):
        idx = r["narrow_plate"]["frame_index"]
        frame = engine._grab_frame(cap, idx / fps, fps)
        if frame is None:
            print("  frame %d unreadable, skipped" % idx)
            continue
        H, W = frame.shape[:2]
        ox, oy = r.get("aoff", (0, 0))
        x1, y1, x2, y2 = (r["cbox"][0] + ox, r["cbox"][1] + oy,
                          r["cbox"][2] + ox, r["cbox"][3] + oy)
        mx, my = margin * (x2 - x1), margin * (y2 - y1)
        cx1, cy1 = int(max(0, x1 - mx)), int(max(0, y1 - my))
        cx2, cy2 = int(min(W, x2 + mx)), int(min(H, y2 + my))
        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            continue
        name = "%s_f%07d_%03d" % (reason, idx, i)
        folder = os.path.join(out_dir, reason)
        os.makedirs(folder, exist_ok=True)
        cv2.imwrite(os.path.join(folder, name + ".png"), crop)
        scale = max(1, int(round(240.0 / max(1, crop.shape[0]))))
        view = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        bx = [int(round((v - o) * scale)) for v, o in ((x1, cx1), (y1, cy1), (x2, cx1), (y2, cy1))]
        cv2.rectangle(view, (bx[0], bx[1]), (bx[2], bx[3]), (0, 255, 0), 1)
        cv2.imwrite(os.path.join(folder, name + "_view.png"), view)
        meta.append({"file": "%s/%s.png" % (reason, name), "reason": reason,
                     "frame_index": idx, "confidence": r.get("confidence"),
                     "frame_size": [W, H],
                     "box_in_frame": [x1, y1, x2, y2],
                     "box_in_crop": [x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1],
                     "track": r.get("track"), "output_choice": r.get("output_choice")})
        print("  %-24s frame %7d  box %dx%d" % (reason, idx, x2 - x1, y2 - y1))
    cap.release()
    counts = {k: len(v) for k, v in groups.items()}
    with open(os.path.join(out_dir, "crops.json"), "w", encoding="utf-8") as f:
        json.dump({"report": os.path.abspath(report), "video": video, "fps": fps,
                   "margin": margin, "outcome_counts": counts, "crops": meta}, f, indent=1)
    print("wrote %d crop(s) to %s" % (len(meta), out_dir))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report")
    ap.add_argument("--source", help="video the job scanned (original input)")
    ap.add_argument("--output", help="redacted video rendered from this report")
    ap.add_argument("--out-dir", default="flash_clips")
    ap.add_argument("--category", default="plate")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--pad", type=float, default=1.0, help="seconds before/after (default 1)")
    ap.add_argument("--max-len", type=float, default=8.0, help="max seconds per clip (default 8)")
    ap.add_argument("--output-offset", type=float, default=None,
                    help="seconds trimmed from the start of the redacted output "
                         "(only if the job used a clip start bookend)")
    ap.add_argument("--copy", action="store_true",
                    help="stream-copy instead of re-encoding (fast but keyframe-snapped, "
                         "frame numbers will not line up)")
    ap.add_argument("--no-sbs", action="store_true", help="skip side-by-side compare clip")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--engine-path", help="folder containing openscrub.py if not installed")
    ap.add_argument("--crops", type=int, default=0, metavar="N",
                    help="save N plate crops per lettering-mode outcome instead of clips")
    ap.add_argument("--scan-video", help="video the scan read (default: report provenance input)")
    a = ap.parse_args()

    engine = load_engine(a.engine_path)
    if a.crops:
        os.makedirs(a.out_dir, exist_ok=True)
        export_crops(engine, a.report, a.crops, a.out_dir, a.scan_video)
        return
    summary, tracks, fps = analyse(engine, a.report, a.category)
    clips = pick_clips(tracks, fps, a.top, a.pad, a.max_len)

    settings = summary.get("settings") or {}
    offset = a.output_offset
    if offset is None:
        offset = 0.0
        if settings.get("clip_start") or settings.get("clip_frac"):
            print("WARNING: the job used a clip bookend; pass --output-offset SECONDS "
                  "so the redacted clips line up", file=sys.stderr)

    os.makedirs(a.out_dir, exist_ok=True)
    for i, c in enumerate(clips, 1):
        c["name"] = "clip%02d_%07.2fs" % (i, c["lo"] / fps)
        c["start_s"] = round(c["lo"] / fps, 3)
        c["duration_s"] = round((c["hi"] - c["lo"] + 1) / fps, 3)
        # frames (relative to the clip's first frame) where the plate should be unblurred
        c["visible_frames_in_clip"] = sorted({
            f - c["lo"] for e in c["events"] for f in range(e["first"], e["last"] + 1)})

    print(json.dumps(summary, indent=1, default=dict))
    print("\n%d clip(s):" % len(clips))
    for c in clips:
        print("  %s  start %.2fs  %.2fs  %d flash run(s), %d unblurred frame(s), tracks %s"
              % (c["name"], c["start_s"], c["duration_s"], c["flash_runs"], c["flash_frames"],
                 sorted({e["track"] for e in c["events"]})))
    with open(os.path.join(a.out_dir, "flash_summary.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "clips": clips,
                   "tracks": {str(k): v for k, v in tracks.items() if v["flashes"] or v["never_blurred"]}},
                  f, indent=1, default=dict)
    print("\nwrote", os.path.join(a.out_dir, "flash_summary.json"))

    if a.dry_run or not clips:
        return
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found; rerun with --dry-run or install ffmpeg")
    for c in clips:
        made = []
        for label, src, shift in (("src", a.source, 0.0), ("out", a.output, offset)):
            if not src:
                continue
            dst = os.path.join(a.out_dir, "%s_%s.mp4" % (c["name"], label))
            print("cutting", dst)
            cut(src, max(0.0, c["start_s"] - shift), c["duration_s"], dst, a.copy)
            made.append(dst)
        if len(made) == 2 and not a.no_sbs:
            dst = os.path.join(a.out_dir, "%s_compare.mp4" % c["name"])
            print("stacking", dst)
            side_by_side(made[0], made[1], dst)


if __name__ == "__main__":
    main()
