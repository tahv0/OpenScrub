#!/usr/bin/env python3
"""Exercise the real Compose service and production browser UI with synthetic media.

Use fresh, dedicated host directories (they must already exist)::

    export OPENSCRUB_TEST_MEDIA_DIR=/tmp/openscrub-media
    export OPENSCRUB_TEST_DATA_DIR=/tmp/openscrub-data
    python tools/integration_smoke.py --prepare
    docker compose -f compose.windows-test.yml up --build -d
    python tools/integration_smoke.py --verify --evidence integration-evidence

On Windows set the same environment variables to existing D:/... directories.
The report always contains the *container* path /media/d/review fixture.mp4.
The manually supplied geometry tests review/render plumbing, not model recall.
Verification requires Playwright Chromium in the host Python environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from email.message import Message
from pathlib import Path
import sys
import time
import traceback
from urllib.parse import quote


JOB_ID = "integration-fixture"
VIDEO_NAME = "review fixture.mp4"
CONTAINER_VIDEO = "/media/d/" + VIDEO_NAME
FRAMES = 10
FPS = 10
WIDTH, HEIGHT = 640, 360
FIXTURE_MARKER = "manual synthetic geometry; not a model-recall benchmark"


def host_dirs():
    paths = []
    for name in ("OPENSCRUB_TEST_MEDIA_DIR", "OPENSCRUB_TEST_DATA_DIR"):
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"Set {name} to an existing, dedicated host directory")
        path = Path(value).resolve()
        if not path.is_dir():
            raise RuntimeError(f"{name} is not an existing directory: {path}")
        paths.append(path)
    return paths


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def prepare():
    import cv2
    import numpy as np

    media, data = host_dirs()
    source = media / VIDEO_NAME
    job_dir = data / "openscrub_jobs" / JOB_ID
    # Never replace a user's media, report, or completed job with a test fixture.
    if source.exists() or job_dir.exists():
        raise RuntimeError(
            "Fixture paths already exist. Use fresh dedicated media/data directories "
            "or remove only your previous integration fixture before preparing again."
        )
    job_dir.mkdir(parents=True)
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"),
                             FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError("OpenCV could not create the synthetic MP4 fixture")
    try:
        for index in range(FRAMES):
            frame = np.full((HEIGHT, WIDTH, 3), (65, 92, 118), dtype=np.uint8)
            left = 180 + 2 * index
            cv2.rectangle(frame, (left, 120), (left + 240, 240),
                          (215, 230, 245), -1)
            cv2.putText(frame, "DEMO", (left + 14, 208),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (32, 46, 58), 3)
            cv2.putText(frame, "SYNTHETIC - MANUAL GEOMETRY", (18, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (240, 240, 240), 1)
            cv2.putText(frame, f"frame {index}", (18, 335),
                        cv2.FONT_HERSHEY_SIMPLEX, .7, (240, 240, 240), 1)
            writer.write(frame)
    finally:
        writer.release()
    cap = cv2.VideoCapture(str(source))
    try:
        count = 0
        while cap.read()[0]:
            count += 1
        if count != FRAMES:
            raise RuntimeError(f"Prepared video has {count} frames, expected {FRAMES}")
    finally:
        cap.release()

    outer = [[0, 0], [1, 0], [1, 1], [0, 1]]
    hole = [[.35, .25], [.65, .25], [.65, .75], [.35, .75]]
    rows = []
    for index in range(FRAMES):
        rows.append({
            "t_start": index / FPS, "t_end": index / FPS,
            "cbox": [180 + 2 * index, 120, 420 + 2 * index, 240],
            "category": "plate", "text": "DEMO (synthetic)",
            "confidence": 1.0, "aoff": [0, 0], "last_seen": index / FPS,
            "dense": True, "track": 7, "person": -1,
            "poly": [outer], "poly_holes": [[hole]], "mask_pad": 0,
            "frame_index": index, "fallback_reason": "", "enabled": True,
        })
    report = {
        "integration_fixture": FIXTURE_MARKER,
        "provenance": {
            "tool": "openscrub-integration-fixture", "input": CONTAINER_VIDEO,
            "original_input": CONTAINER_VIDEO,
            "input_sha256": sha256(source.read_bytes()), "vfr_normalized": False,
            "settings": {"mode": "box", "pad": 8, "encoder": "x264",
                         "categories": "plate", "coverage": "tight",
                         "plate_coverage": "narrow", "plate_narrow_margin": 0,
                         "hdr_output": "sdr", "use_zones": False},
        },
        "render_state": {"fps": FPS, "cum": [[0, 0]] * FRAMES,
                         "bands": [[0, 0]] * FRAMES},
        "detections": rows,
    }
    (job_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Prepared synthetic fixture: {source}")
    print(f"Report: {job_dir / 'report.json'} (no output created)")


PICKER_STUB = r"""() => {
 const state=window.__integration={
  nativePickerAvailable:typeof window.showSaveFilePicker==='function',
  secureContext:window.isSecureContext,pickers:[],streams:[],fetches:[],
  cancelNext:false,cancellations:0
 };
 const originalFetch=window.fetch.bind(window);
 window.fetch=(input,...args)=>{
  state.fetches.push(typeof input==='string'?input:input.url);
  return originalFetch(input,...args);
 };
 window.showSaveFilePicker=async(options)=>{
  state.pickers.push(options);
  if(state.cancelNext){
   state.cancelNext=false;state.cancellations++;
   throw new DOMException('Integration cancellation','AbortError');
  }
  const stream={name:options.suggestedName,chunks:[],closed:false};
  state.streams.push(stream);
  return {createWritable:async()=>new WritableStream({
   write(chunk){stream.chunks.push(Array.from(new Uint8Array(chunk)));},
   close(){stream.closed=true;}
  })};
 };
}"""


def download_name(response):
    header = Message()
    header["Content-Disposition"] = response.headers.get("content-disposition", "")
    return header.get_filename()


class Evidence:
    def __init__(self, path, url):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.result = {"url": url, "fixture": FIXTURE_MARKER,
                       "checks": [], "page_errors": [], "ok": False}

    def check(self, name, condition, detail=None):
        record = {"name": name, "ok": bool(condition)}
        if detail is not None:
            record["detail"] = detail
        self.result["checks"].append(record)
        self.write()
        if not condition:
            raise AssertionError(f"{name}: {detail}")
        print(f"PASS {name}", flush=True)

    def write(self):
        (self.path / "checks.json").write_text(
            json.dumps(self.result, indent=2), encoding="utf-8")


def wait_for_frame(page, index):
    page.wait_for_function(
        "index => BE.indexed && BE.frame===index && !BE.pending && "
        "BE.imageFrame===index && BE.maskFrame===index", arg=index, timeout=15000)
    return page.evaluate("() => ({frame:BE.frame,imageFrame:BE.imageFrame,"
                         "maskFrame:BE.maskFrame,pending:BE.pending,"
                         "boxes:BE.boxes,raw:BE.raw})")


def open_fixture(page):
    page.locator("#jobs a").filter(has_text=VIDEO_NAME).click()


def check_track(page, evidence, label, enabled):
    state = page.evaluate("() => Object.values(EN)")
    evidence.check(label, len(state) == FRAMES and all(v is enabled for v in state), state)


def check_contours(evidence, state, index):
    boxes = state["boxes"]
    evidence.check(f"exact frame {index} has one shaped mask",
                   len(boxes) == 1 and boxes[0]["shaped"], state)
    box = boxes[0]
    rings = box["mask_contours"]
    evidence.check(f"exact frame {index} retains outer contour and exclusion",
                   len(rings) == 2 and all(len(ring) >= 4 for ring in rings), rings)
    evidence.check(f"exact frame {index} uses matching sample geometry",
                   box["i"] == index and
                   box["box"] == [180 + 2 * index, 120, 420 + 2 * index, 240], box)


def stream_digest(page, index):
    return page.evaluate("""async index => {
      const s=window.__integration.streams[index];
      const size=s.chunks.reduce((n,c)=>n+c.length,0),bytes=new Uint8Array(size);
      let offset=0;for(const chunk of s.chunks){bytes.set(chunk,offset);offset+=chunk.length;}
      const digest=await crypto.subtle.digest('SHA-256',bytes);
      return {name:s.name,closed:s.closed,size,sha256:
       Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('')};
    }""", index)


def verify_rendered_video(path, evidence):
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        count, first = 0, None
        dimensions = [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                      int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if first is None:
                first = frame
            count += 1
    finally:
        cap.release()
    evidence.check("rendered MP4 decodes with expected dimensions and frame count",
                   count == FRAMES and dimensions == [WIDTH, HEIGHT],
                   {"frames": count, "dimensions": dimensions})
    # Box-mode output makes the selected region black, while the compound
    # exclusion keeps the original bright plate visible. Stay away from edges
    # so codec quantization cannot turn this into a brittle pixel-equality test.
    outer_mean = float(first[130:145, 195:225].mean())
    hole_mean = float(first[157:170, 280:320].mean())
    evidence.check("real render blacks the outer mask and preserves its hole",
                   outer_mean < 20 and hole_mean > 100,
                   {"outer_mean": outer_mean, "hole_mean": hole_mean})


def verify(args):
    from playwright.sync_api import sync_playwright

    media, _data = host_dirs()
    source = media / VIDEO_NAME
    if not source.is_file():
        raise RuntimeError("Prepare the fixture before starting Compose and verification")
    evidence = Evidence(args.evidence, args.url)
    downloads = []
    page = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1365, "height": 1000},
                                          accept_downloads=True)
            context.add_init_script("(" + PICKER_STUB + ")();")
            api = context.request
            url = args.url.rstrip("/")
            deadline = time.monotonic() + args.startup_timeout
            while True:
                try:
                    response = api.get(url + "/api/jobs", timeout=5000)
                    if response.ok:
                        jobs = response.json()
                        break
                except Exception:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Compose service did not become ready before startup timeout")
                time.sleep(.5)
            # Keep all captured evidence synthetic, even when accidentally
            # pointed at an existing user installation.
            evidence.check("dedicated service contains only the synthetic review fixture",
                           len(jobs) == 1 and jobs[0]["id"] == JOB_ID and
                           jobs[0]["phase"] == "review" and not jobs[0]["has_output"],
                           [{"id": j["id"], "phase": j["phase"]} for j in jobs])
            expected_source_sha = sha256(source.read_bytes())
            source_response = api.get(url + "/api/server_video?path=" + quote(CONTAINER_VIDEO))
            evidence.check("container reads the mounted server video byte for byte",
                           source_response.ok and sha256(source_response.body()) == expected_source_sha)
            outside = "/tmp/openscrub-outside-media-root.mp4"
            refused = api.get(url + "/api/server_video?path=" + quote(outside))
            evidence.check("server video rejects paths outside the allowed media root",
                           refused.status == 400 and "outside OPENSCRUB_MEDIA_ROOT" in refused.text())
            refused_job = api.post(url + "/api/jobs", form={"server_path": outside,
                                                            "options": "{}"})
            evidence.check("job intake rejects paths outside the allowed media root",
                           refused_job.status == 400 and
                           "outside OPENSCRUB_MEDIA_ROOT" in refused_job.text())

            page = context.new_page()
            page.on("pageerror", lambda error: evidence.result["page_errors"].append(str(error)))
            page.on("download", lambda download: downloads.append(download.suggested_filename))
            page.on("dialog", lambda dialog: dialog.dismiss())
            page.goto(url, wait_until="domcontentloaded")
            page.locator("#plateCoverage").select_option("narrow")
            page.locator("#plateMargin").fill("0")
            controls = page.locator("#plateCoverageControls")
            evidence.check("homepage exposes lettering-only coverage and zero margin",
                           page.locator("#plateCoverage").input_value() == "narrow" and
                           page.locator("#plateMargin").input_value() == "0" and
                           page.locator("#plateMargin").is_enabled() and
                           page.locator("#plateMarginRow").is_visible())
            controls.screenshot(path=str(evidence.path / "settings.png"))
            open_fixture(page)
            page.locator("#review").wait_for()
            cards = page.locator("#review .det[data-cat='plate']")
            evidence.check("dense track collapses to one review card", cards.count() == 1)
            card = cards.first
            evidence.check("review identifies compound shaped mask",
                           card.get_by_text("shaped mask", exact=True).is_visible())
            blur = card.get_by_role("button", name="Blur", exact=True)
            keep = card.get_by_role("button", name="Keep visible", exact=True)
            for click in range(2):
                blur.click()
                check_track(page, evidence, f"Blur is explicit and idempotent ({click + 1})", True)
            for click in range(2):
                keep.click()
                check_track(page, evidence, f"Keep visible is explicit and idempotent ({click + 1})", False)
            evidence.check("Keep visible reports output state accessibly",
                           keep.get_attribute("aria-pressed") == "true" and
                           blur.get_attribute("aria-pressed") == "false" and
                           card.get_by_text("Will stay visible", exact=True).is_visible())
            blur.click()
            page.locator('#review button[onclick="loadBoxEdit(1)"]').click()
            state = wait_for_frame(page, 0)
            check_contours(evidence, state, 0)
            page.locator("#beNext").click()
            check_contours(evidence, wait_for_frame(page, 1), 1)
            page.locator("#bePrev").click()
            check_contours(evidence, wait_for_frame(page, 0), 0)
            keep.click()
            page.wait_for_function("() => !BE.pending && BE.boxes.length===0 && "
                                   "BE.raw.length===1 && BE.raw[0].enabled===false")
            check_track(page, evidence, "Keep visible updates every track member with preview mounted", False)
            blur.click()
            page.wait_for_function("() => !BE.pending && BE.boxes.length===1 && "
                                   "BE.raw[0].enabled===true")
            check_track(page, evidence, "Blur refreshes live masks with preview mounted", True)
            check_contours(evidence, wait_for_frame(page, 0), 0)
            page.locator("#review").screenshot(path=str(evidence.path / "review.png"))

            # An explicit Blur choice remains a human override even when the
            # final visibility equals the loaded value. It must not become a
            # positive/negative training label, or be lost as an unchanged map.
            with page.expect_response(lambda response: response.url.endswith(
                    f"/api/jobs/{JOB_ID}/detections") and response.request.method == "POST") as explicit:
                explicit_ok = page.evaluate("saveAndRender(true)")
            explicit_payload = explicit.value.request.post_data_json
            explicit_report = api.get(url + f"/api/jobs/{JOB_ID}/report").json()
            evidence.check("explicit same-value Blur is saved as a human override without a training label",
                           explicit_ok and explicit.value.ok and
                           explicit_payload["enabled"] == {str(i): True for i in range(FRAMES)} and
                           explicit_payload["verified_labels"] == {str(i): "clear" for i in range(FRAMES)} and
                           len(explicit_report["detections"]) == FRAMES and
                           all(d["enabled"] is True and d.get("plate_verification_override") is True
                               and not d.get("verified_label") for d in explicit_report["detections"]),
                           explicit_payload)
            # Once acknowledged, saving again without another click must stay
            # sparse and must not replay the explicit override command.
            unchanged_before = api.get(url + f"/api/jobs/{JOB_ID}/report").body()
            with page.expect_response(lambda response: response.url.endswith(
                    f"/api/jobs/{JOB_ID}/detections") and response.request.method == "POST") as unchanged:
                unchanged_ok = page.evaluate("saveAndRender(true)")
            unchanged_payload = unchanged.value.request.post_data_json
            unchanged_after = api.get(url + f"/api/jobs/{JOB_ID}/report").body()
            evidence.check("acknowledged unchanged choices produce a sparse no-op save",
                           unchanged_ok and unchanged.value.ok and
                           unchanged_payload["enabled"] == {} and
                           unchanged_payload["verified_labels"] == {} and
                           unchanged_after == unchanged_before,
                           unchanged_payload)
            # Commit an actual changed track before restoring Blur for render.
            # This preserves the full-member save assertion below and verifies
            # server persistence independently of the browser's displayed state.
            keep.click()
            page.wait_for_function("() => !BE.pending && BE.boxes.length===0")
            with page.expect_response(lambda response: response.url.endswith(
                    f"/api/jobs/{JOB_ID}/detections") and response.request.method == "POST") as kept:
                kept_ok = page.evaluate("saveAndRender(true)")
            kept_payload = kept.value.request.post_data_json["enabled"]
            kept_report = api.get(url + f"/api/jobs/{JOB_ID}/report").json()
            evidence.check("changed track choices reach the stored report",
                           kept_ok and kept.value.ok and len(kept_payload) == FRAMES and
                           all(v is False for v in kept_payload.values()) and
                           len(kept_report["detections"]) == FRAMES and
                           all(d["enabled"] is False for d in kept_report["detections"]),
                           kept_payload)
            blur.click()
            page.wait_for_function("() => !BE.pending && BE.boxes.length===1")
            with page.expect_response(lambda response: response.url.endswith(
                    f"/api/jobs/{JOB_ID}/detections") and response.request.method == "POST") as saved:
                page.locator("#review").get_by_role("button", name="Save edits & render",
                                                    exact=True).click()
            saved_response = saved.value
            payload = saved_response.request.post_data_json
            evidence.check("real review button saves all edited track choices",
                           saved_response.ok and len(payload["enabled"]) == FRAMES and
                           all(payload["enabled"].values()), payload["enabled"])
            deadline = time.monotonic() + args.render_timeout
            while True:
                status = api.get(url + f"/api/jobs/{JOB_ID}").json()
                if status["phase"] == "done":
                    break
                if status["phase"] in ("error", "cancelled"):
                    raise AssertionError(f"Real render failed: {status}")
                if time.monotonic() >= deadline:
                    raise AssertionError(f"Real render did not finish within {args.render_timeout}s: {status}")
                page.wait_for_timeout(250)
            evidence.check("container completed a real render", status["has_output"], status)
            rendered = api.get(url + f"/api/jobs/{JOB_ID}/download")
            report_response = api.get(url + f"/api/jobs/{JOB_ID}/report")
            output_name, report_name = "review fixture_redacted.mp4", "review fixture_audit.json"
            evidence.check("download headers use source-derived names",
                           rendered.ok and report_response.ok and
                           download_name(rendered) == output_name and
                           download_name(report_response) == report_name,
                           {"video": download_name(rendered), "report": download_name(report_response)})
            output_bytes, report_bytes = rendered.body(), report_response.body()
            rendered_path = evidence.path / "rendered.mp4"
            rendered_path.write_bytes(output_bytes)
            (evidence.path / "rendered_audit.json").write_bytes(report_bytes)
            verify_rendered_video(rendered_path, evidence)
            report = report_response.json()
            evidence.check("rendered report retains indexed compound masks and narrow settings",
                           len(report["detections"]) == FRAMES and
                           all(d["poly"] and d["poly_holes"] and d["mask_pad"] == 0 and
                               d["frame_index"] == i and d["track"] == 7 and d["enabled"] is True
                               for i, d in enumerate(report["detections"])) and
                           report["provenance"]["settings"]["plate_coverage"] == "narrow" and
                           report["provenance"]["settings"]["plate_narrow_margin"] == 0)

            video_button = page.locator('#actions button[onclick="saveExportAs(\'video\',this)"]')
            report_button = page.locator('#actions button[onclick="saveExportAs(\'report\',this)"]')
            video_button.wait_for(timeout=10000)
            evidence.result["browser"] = page.evaluate("() => ({secureContext:"
                "window.__integration.secureContext,nativePickerAvailable:"
                "window.__integration.nativePickerAvailable,userAgent:navigator.userAgent})")
            evidence.check("localhost provides a secure browser context",
                           evidence.result["browser"]["secureContext"])
            for index, (button, expected_name, body) in enumerate((
                    (video_button, output_name, output_bytes),
                    (report_button, report_name, report_bytes))):
                button.click()
                page.wait_for_function("index => window.__integration.streams.length>index && "
                                       "window.__integration.streams[index].closed", arg=index)
                streamed = stream_digest(page, index)
                evidence.check(f"Save As streams exact {('video', 'report')[index]} bytes",
                               streamed["sha256"] == sha256(body) and
                               streamed["size"] == len(body) and streamed["name"] == expected_name,
                               streamed)
            export_fetch_count = "() => window.__integration.fetches.filter(x=>" \
                r"/api\/jobs\/integration-fixture\/(download|report)(?:$|\?)/.test(x)).length"
            before = page.evaluate(export_fetch_count)
            before_downloads = len(downloads)
            page.evaluate("() => { window.__integration.cancelNext=true; }")
            video_button.click()
            page.wait_for_function("() => window.__integration.cancellations===1")
            page.wait_for_timeout(150)
            evidence.check("cancelled Save As starts no export fetch or automatic download",
                           page.evaluate(export_fetch_count) == before and
                           len(downloads) == before_downloads and
                           page.evaluate("() => window.__integration.streams.length") == 2)
            page.locator("#jobcard").screenshot(path=str(evidence.path / "done.png"))

            fallback = browser.new_context(viewport={"width": 1365, "height": 1000},
                                           accept_downloads=True)
            fallback.add_init_script("Object.defineProperty(window,'showSaveFilePicker',"
                                     "{value:undefined,configurable:true});")
            fallback_page = fallback.new_page()
            fallback_page.on("pageerror", lambda error: evidence.result["page_errors"].append(str(error)))
            fallback_page.goto(url, wait_until="domcontentloaded")
            open_fixture(fallback_page)
            for label, name, body, artifact in (
                    ("Download redacted video", output_name, output_bytes, "fallback_video.mp4"),
                    ("Download audit report", report_name, report_bytes, "fallback_audit.json")):
                button = fallback_page.get_by_role("button", name=label, exact=True)
                with fallback_page.expect_download() as pending_download:
                    button.click()
                download = pending_download.value
                destination = evidence.path / artifact
                download.save_as(str(destination))
                evidence.check(f"unsupported browser fallback downloads {artifact}",
                               download.suggested_filename == name and
                               sha256(destination.read_bytes()) == sha256(body))
            evidence.check("unsupported browser exposes direct links",
                           fallback_page.locator('#actions a[href$="/download"]').count() == 1 and
                           fallback_page.locator('#actions a[href$="/report"]').count() == 1)
            fallback_page.set_viewport_size({"width": 390, "height": 844})
            fallback_page.screenshot(path=str(evidence.path / "mobile.png"), full_page=True)
            layout = fallback_page.evaluate("() => ({viewport:innerWidth,document:"
                                            "document.documentElement.scrollWidth})")
            evidence.check("390px mobile page has no horizontal overflow",
                           layout["document"] <= layout["viewport"] + 1, layout)
            page.get_by_role("button", name="Re-open review", exact=True).click()
            card = page.locator("#review .det[data-cat='plate']").first
            card.scroll_into_view_if_needed()
            page.wait_for_function("!!document.querySelector('#review .plate-edit-thumb')._quadEdit")
            before_point = card.locator("img").evaluate("img=>img._quadEdit.points[0].slice()")
            size = card.bounding_box()
            handle = card.locator("img").evaluate("""img => {
                const q=img._quadEdit,c=q.meta.crop,b=q.cv.getBoundingClientRect(),p=q.points[0];
                return {x:b.left+(p[0]-c[0])*b.width/(c[2]-c[0]),
                        y:b.top+(p[1]-c[1])*b.height/(c[3]-c[1])};
            }""")
            page.mouse.move(handle["x"],handle["y"]);page.mouse.down()
            page.mouse.move(handle["x"]+9,handle["y"]+5,steps=5);page.mouse.up()
            page.wait_for_function("document.querySelector('#review .quad-status').textContent.startsWith('Saved')")
            moved_point = card.locator("img").evaluate("img=>img._quadEdit.points[0].slice()")
            evidence.check("dragging corners autosaves without expanding or extra buttons",
                           moved_point != before_point and
                           abs(card.bounding_box()["width"]-size["width"]) < 1 and
                           page.locator("#qSave,#qClose,#qTrack,#qRotateRight,#plateQuadEditor").count() == 0 and
                           page.locator(".marq").count() == 0)
            updated = api.get(url + f"/api/jobs/{JOB_ID}/report").json()["detections"]
            evidence.check("corner autosave applies to every detection on the track",
                           all(d.get("plate_quad") == updated[0].get("plate_quad")
                               for d in updated) and len(updated[0].get("plate_quad", [])) == 4)
            card.screenshot(path=str(evidence.path / "direct-corners.png"))
            evidence.check("production pages raise no JavaScript errors",
                           not evidence.result["page_errors"], evidence.result["page_errors"])
            evidence.result["ok"] = True
            evidence.write()
            browser.close()
    except Exception as error:
        evidence.result["error"] = str(error)
        evidence.result["traceback"] = traceback.format_exc()
        evidence.write()
        raise
    print(f"Integration smoke passed; evidence: {evidence.path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="create synthetic source/report before Compose starts")
    mode.add_argument("--verify", action="store_true", help="exercise running Compose HTTP service and real browser UI")
    parser.add_argument("--url", default="http://localhost:8384")
    parser.add_argument("--evidence", default="integration-evidence")
    parser.add_argument("--startup-timeout", type=float, default=90)
    parser.add_argument("--render-timeout", type=float, default=20)
    args = parser.parse_args()
    try:
        prepare() if args.prepare else verify(args)
    except Exception as error:
        print(f"Integration smoke failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
