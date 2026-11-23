"""Web side of the assisted plate-letters cover: Scan Setup choice, gap list."""
import json
import queue
import re
from pathlib import Path

import cv2
import numpy as np
import pytest

import openscrub
import openscrub_web as web

FPS = 10.0
SIZE = (160, 96)
PLATE = (20, 20, 140, 76)
LETTER_POLY = (((.25, .3), (.75, .3), (.75, .7), (.25, .7)),)


def _video(path, frames):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, SIZE)
    assert writer.isOpened()
    for _ in range(frames):
        writer.write(np.full((SIZE[1], SIZE[0], 3), 220, np.uint8))
    writer.release()


def _row(i, poly, track, box=PLATE):
    return openscrub.Detection(i / FPS, i / FPS + .03, box, "plate", "plate", .9,
                               dense=True, track=track, poly=poly)


def _write_report(path, video, coverage):
    argv = [str(video)]
    if coverage == "assisted":
        argv += ["--plate-coverage", "assisted", "--no-box-fallback"]
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(argv), parser)
    # Track 0: letters on frames 0-1, a cut at 3 leaves 3-4 as a gap.
    # Track 1: frames 6-8 without any letters, all three a gap.
    rows = [_row(i, LETTER_POLY if i < 2 else (), 0) for i in range(5)]
    rows += [_row(i, (), 1, (30, 24, 130, 70)) for i in range(6, 9)]
    openscrub.write_report(path, args, {"fps": FPS, "cum": [(0, 0)] * 10,
                                        "bands": [(0, 0)] * 10, "detections": rows,
                                        "scene_cuts": [3]})


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "jobs").mkdir(parents=True)
    monkeypatch.setattr(web, "_data_root", lambda: str(root))
    monkeypatch.setattr(web, "JOBS_DIR", str(root / "jobs"))
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "WORK_Q", queue.Queue())
    monkeypatch.setattr(web, "WORKER", {"current": None, "thread": None})
    monkeypatch.setattr(web, "VAULT", {"key": None})
    monkeypatch.setattr(web, "FILES", type(web.FILES)(web.VAULT_LOCK))
    monkeypatch.setattr(web, "TOKEN", None)
    monkeypatch.setitem(web.app.config, "TESTING", False)
    monkeypatch.setitem(web.app.config, "PROPAGATE_EXCEPTIONS", False)
    web._forget_report_parses()

    def make(coverage):
        job = web.new_job("", {}, "synthetic.mp4")
        video = Path(job["dir"]) / "input.mp4"
        _video(video, 10)
        job.update(video=str(video), phase="review")
        if coverage == "assisted":
            job["options"].update(plate_coverage="assisted", no_box_fallback=True)
        _write_report(Path(job["dir"]) / "report.json", video, coverage)
        return job
    yield make
    assert web.FILES.count == 0, "file ownership leaked"
    web._forget_report_parses()


def get(url):
    with web.app.test_client() as client:
        response = client.get(url)
        response.get_data()
        response.close()
        return response


def test_build_args_requires_confirmation_for_assisted(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "load_custom_cats", lambda: [])
    monkeypatch.setattr(web, "load_model_select", lambda: {})
    monkeypatch.setattr(web, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(web, "ZONES_PATH", str(tmp_path / "zones.json"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    job = {"video": str(source), "dir": str(tmp_path),
           "options": {"categories": "plate", "plate_coverage": "assisted"}}
    with pytest.raises(ValueError, match="assisted plate letters needs explicit confirmation"):
        web.build_args(job)
    job["options"]["no_box_fallback"] = True
    args = web.build_args(job)
    assert args.plate_coverage == "assisted" and args.no_box_fallback
    assert args._plate_coverage_explicit
    # A render follows the saved report, never the job option.
    assert web.build_args(job, for_render=True).plate_coverage == "full"


def test_letter_gaps_route_lists_gaps_of_assisted_job(store):
    job = store("assisted")
    response = get("/api/jobs/%s/letter_gaps" % job["id"])
    assert response.status_code == 200
    body = response.get_json()
    assert body["mode"] == "assisted"
    gaps = body["gaps"]
    assert len(gaps) == 2
    assert [g["t0"] for g in gaps] == sorted(g["t0"] for g in gaps)
    assert {"track", "t0", "t1", "frames", "frame", "box"} <= set(gaps[0])
    assert (gaps[0]["track"], gaps[0]["frame"], gaps[0]["frames"]) == (0, 4, 2)
    assert gaps[1]["track"] == 1 and gaps[1]["frames"] == 3
    assert set(body["stats"]) == {"masked_frames", "bridged_frames", "gap_frames"}
    assert body["stats"]["gap_frames"] == 5
    # The second call is served from the per-stamp cache.
    calls = []
    real = openscrub.assisted_cover_from_report
    try:
        openscrub.assisted_cover_from_report = lambda doc: calls.append(1) or real(doc)
        assert get("/api/jobs/%s/letter_gaps" % job["id"]).get_json() == body
    finally:
        openscrub.assisted_cover_from_report = real
    assert calls == []
    # Review learns the mode from its existing loads (no extra request for
    # ordinary jobs): the detections payload and the job status carry it.
    assert get("/api/jobs/%s/detections" % job["id"]).get_json()["assisted_letters"] is True
    assert get("/api/jobs/%s" % job["id"]).get_json()["assisted_letters"] is True


def test_letter_gaps_route_reports_off_for_other_jobs(store):
    job = store("full")
    response = get("/api/jobs/%s/letter_gaps" % job["id"])
    assert response.status_code == 200
    assert response.get_json()["mode"] == "off"
    assert "assisted_letters" not in get("/api/jobs/%s/detections" % job["id"]).get_json()
    assert "assisted_letters" not in get("/api/jobs/%s" % job["id"]).get_json()
    assert get("/api/jobs/nosuchjob/letter_gaps").status_code == 404


def test_letter_gap_preview_is_a_jpeg(store):
    job = store("assisted")
    token = get("/api/jobs/%s/letter_gaps" % job["id"]).get_json()["token"]
    response = get("/api/jobs/%s/letter_gap/0.jpg?v=%s" % (job["id"], token))
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    image = cv2.imdecode(np.frombuffer(response.data, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None and image.shape[0] == 240
    assert get("/api/jobs/%s/letter_gap/9.jpg?v=%s" % (job["id"], token)).status_code == 404
    off = store("full")
    assert get("/api/jobs/%s/letter_gap/0.jpg" % off["id"]).status_code == 404


def test_letter_gap_preview_refuses_a_list_from_an_older_report(store):
    job = store("assisted")
    token = get("/api/jobs/%s/letter_gaps" % job["id"]).get_json()["token"]
    assert isinstance(token, str) and token
    url = "/api/jobs/%s/letter_gap/0.jpg" % job["id"]
    assert get(url).status_code == 404                     # no token
    assert get(url + "?v=stale").status_code == 404
    assert get(url + "?v=" + token).status_code == 200
    # a save rewrites the report: the old list's index no longer applies
    path = Path(job["dir"]) / "report.json"
    doc = json.loads(path.read_text())
    doc["detections"] = doc["detections"][5:]               # only track 1 is left
    path.write_text(json.dumps(doc, indent=1))
    fresh = get("/api/jobs/%s/letter_gaps" % job["id"]).get_json()
    assert fresh["token"] != token and len(fresh["gaps"]) == 1
    assert get(url + "?v=" + token).status_code == 404
    assert get(url + "?v=" + fresh["token"]).status_code == 200
    # Review builds the preview URL with the list's token
    assert "letter_gap/${n}.jpg?v=${encodeURIComponent(g.token" in web.PAGE


ASSISTED_CONFIRM = ("Letters only, no box fallback: where letters are not found clearly, "
                    "nothing is drawn instead of the full plate box. Those spots are listed "
                    "as gaps in Review. OpenScrub does not find every plate, so check the "
                    "output. Scanning is slow. Turn it on?")


def test_scan_setup_has_plate_cover_choice_with_help_tip():
    page = web.PAGE
    m = re.search(r'<select id="platecover"[^>]*>(.*?)</select>', page, re.S)
    assert m, "plate cover select missing"
    values = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(1))
    assert values == [("full", "Full plate box (default)"),
                      ("narrow", "Letters only, strict (experimental)"),
                      ("assisted", "Letters only, no box fallback (experimental, slow)")]
    label = page[page.rfind("<label", 0, m.start()):m.start()]
    assert 'for="platecover"' in label and 'class="qm" data-tip="' in label
    assert 'id="plateletters"' not in page
    assert ASSISTED_CONFIRM in page
    assert "confirm(ASSISTED_CONFIRM)" in page
    assert 'o.no_box_fallback=true' in page


def test_render_reminder_present_and_no_per_card_warning():
    page = web.PAGE
    assert ("Letters only, no box fallback: ${n} gaps listed in Review will not be covered. "
            "Render now?") in page
    assert "confirm(ASSISTED_RENDER_REMINDER" in page
    notice = "Letters only, no box fallback: gaps below are not covered. Check the output."
    assert page.count(notice) == 1
    assert 'id="letterGaps"' in page
    assert page.index('id="letterGaps"') < page.index('<div id="beslot"></div>')
    assert "Based on the last saved review choices." in page
    start = page.index("function reviewCard(c)")
    card = page[start:page.index("\nfunction ", start + 1)]
    choices = page[page.index("function detChoices("):page.index("function setDetLabel(")]
    for body in (card, choices):
        assert "no box fallback" not in body and "letterGap" not in body


def test_render_reminder_after_save_uses_the_fresh_gap_count():
    from test_review_save_failures import run_js
    # save -> fetch the gap list of the report just saved -> confirm -> render
    run_js("""let asked=[];confirm=m=>{asked.push(m);return true;};setup();
    LETTER_GAPS={jobId:'A',mode:'assisted',gaps:[{},{},{},{},{}]};   // stale: 5 before the edits
    const p=saveAndRender();
    if(calls.length!==1||!calls[0].url.endsWith('/detections')||asked.length)throw Error('save not first');
    await reply();
    if(calls.length!==2||calls[1].url!=='api/jobs/A/letter_gaps'||asked.length)throw Error('no fresh gap fetch');
    await reply({mode:'assisted',gaps:[{},{}],stats:{}});
    if(asked.length!==1||!asked[0].startsWith('Letters only, no box fallback: 2 gaps listed in Review'))
      throw Error('reminder: '+JSON.stringify(asked));
    if(calls.length!==3||!calls[2].url.endsWith('/render'))throw Error('render not after confirm');
    await reply();if(await p!==true)throw Error('render not reported');""")


def test_render_reminder_cancel_keeps_saved_edits_and_does_not_render():
    from test_review_save_failures import run_js
    run_js("""let asked=[];confirm=m=>{asked.push(m);return false;};setup();
    LETTER_GAPS_LOAD={jobId:'A',promise:Promise.resolve({mode:'assisted',gaps:[{}]})};
    const p=saveAndRender();await reply();await reply({mode:'assisted',gaps:[{},{},{}],stats:{}});
    if(await p!==false)throw Error('cancelled render went ahead');
    if(calls.some(c=>c.url.endsWith('/render')))throw Error('cancel still rendered');
    if(asked.length!==1||!asked[0].includes(' 3 gaps listed'))throw Error('reminder: '+JSON.stringify(asked));
    if(MAN.length||BE.adds.length||hasReviewEdits(EDITS))throw Error('saved edits not acknowledged');
    if(!document.getElementById('reviewSaveStatus').textContent.includes('Edits saved. Render cancelled'))
      throw Error('status: '+document.getElementById('reviewSaveStatus').textContent);""")


def test_render_reminder_failed_gap_fetch_asks_and_ordinary_jobs_are_not_asked():
    from test_review_save_failures import run_js
    run_js("""let asked=[];confirm=m=>{asked.push(m);return false;};
    setup();const p=saveAndRender();          // ordinary job: save then render, never asked
    await reply();if(calls.length!==2||!calls[1].url.endsWith('/render'))throw Error('ordinary job');
    await reply();await p;if(asked.length)throw Error('ordinary job asked');
    calls.length=0;openJob('A');setup();
    LETTER_GAPS_LOAD={jobId:'A',promise:Promise.resolve({mode:'assisted',gaps:[]})};
    const q=saveAndRender();await reply();queue.shift().reject(Error('offline'));await tick();
    if(await q!==false||calls.some(c=>c.url.endsWith('/render')))throw Error('failed fetch rendered');
    if(asked.length!==1||!asked[0].includes('could not be checked'))throw Error(JSON.stringify(asked));""")


from test_scan_options import intake  # noqa: E402,F401


@pytest.mark.parametrize("kind", ["upload", "server-path"])
def test_assisted_options_survive_real_admission(intake, kind):
    client, post, video, source, jobs_dir = intake
    response = post(kind, json.dumps({"categories": "plate", "plate_coverage": "assisted",
                                      "no_box_fallback": True}))
    assert response.status_code == 200
    job = web.JOBS[response.json["jobs"][0]]
    assert job["options"]["no_box_fallback"] is True
    args = web.build_args(job)
    assert args.plate_coverage == "assisted" and args.no_box_fallback


def test_plate_cover_dialog_cancel_keeps_previous_choice():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to evaluate the Scan Setup JavaScript")
    page = web.PAGE
    start = page.index("const ASSISTED_CONFIRM=")
    code = page[start:page.index("async function startScan(){", start)]
    script = code + """
let answer=false;const asked=[];confirm=m=>{asked.push(m);return answer;};
const sel={value:"narrow"};plateCoverChanged(sel);
sel.value="assisted";plateCoverChanged(sel);
if(sel.value!=="narrow"||asked.length!==1||asked[0]!==ASSISTED_CONFIRM)throw Error("cancel: "+sel.value);
answer=true;sel.value="assisted";plateCoverChanged(sel);
if(sel.value!=="assisted"||asked.length!==2)throw Error("accept: "+sel.value);
sel.value="full";plateCoverChanged(sel);if(asked.length!==2)throw Error("asked for full");
"""
    result = subprocess.run([node], input="var confirm;" + script, capture_output=True,
                            text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def _set_report(job, **settings):
    path = Path(job["dir"]) / "report.json"
    doc = json.loads(path.read_text())
    hdr = settings.pop("hdr_output", None)
    doc["provenance"]["settings"].update(settings)
    if hdr is not None:
        doc["provenance"]["hdr_output"] = hdr
    path.write_text(json.dumps(doc))
    web._forget_report_parses()


def test_letter_gaps_carry_output_timeline_fields_untrimmed(store):
    job = store("assisted")
    gaps = get("/api/jobs/%s/letter_gaps" % job["id"]).get_json()["gaps"]
    assert [(g["out_t0"], g["out_t1"], g["out_frame"]) for g in gaps] == [
        (g["t0"], g["t1"], g["frame"]) for g in gaps]


def test_letter_gaps_follow_the_output_clip(store):
    # clip 0.5-0.75 of a 1.0 s timeline keeps frames 5..7: track 0's gap at
    # frames 3-4 is outside, track 1's gap at 6-8 is trimmed to 6-7.
    job = store("assisted")
    _set_report(job, clip_frac="0.5-0.75")
    body = get("/api/jobs/%s/letter_gaps" % job["id"]).get_json()
    assert [(g["track"], g["t0"], g["t1"], g["frames"]) for g in body["gaps"]] == [(1, .6, .7, 2)]
    g = body["gaps"][0]
    assert (g["out_t0"], g["out_t1"], g["out_frame"]) == (pytest.approx(.1), pytest.approx(.2), 2)
    assert body["stats"]["gap_frames"] == 2
    # seconds bookends from the CLI resolve the same way
    _set_report(job, clip_frac="", clip_start=0.5, clip_end=0.75)
    again = get("/api/jobs/%s/letter_gaps" % job["id"]).get_json()
    assert [(x["track"], x["frames"], x["out_frame"]) for x in again["gaps"]] == [(1, 2, 2)]


def test_letter_gaps_ignore_trim_on_hdr_output(store):
    job = store("assisted")
    _set_report(job, clip_frac="0.5-0.75", hdr_output=True)
    gaps = get("/api/jobs/%s/letter_gaps" % job["id"]).get_json()["gaps"]
    assert len(gaps) == 2
    assert [(g["out_t0"], g["out_frame"]) for g in gaps] == [(g["t0"], g["frame"]) for g in gaps]


def _node_eval(code):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to evaluate the Review JavaScript")
    result = subprocess.run([node], input=code, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_gap_times_are_formatted_as_rendered_video_timecode():
    page = web.PAGE
    start = page.index("function lgOutTime(")
    code = page[start:page.index("\n}\n", start) + 3]
    out = _node_eval(code + """
for(const v of [5423.37,0,0.0333,65.2,59.9996,3600,-1,NaN])console.log(lgOutTime(v));""")
    assert out.split() == ["1:30:23.370", "0:00:00.000", "0:00:00.033", "0:01:05.200",
                           "0:01:00.000", "1:00:00.000", "0:00:00.000", "0:00:00.000"]
    assert "time in the rendered video" in page
    assert "lgOutTime(x.out_t0" in page and "x.out_frame" in page
    # the click still seeks the editor on the scan timeline
    assert "openLetterGap(${+x.t0})" in page


def test_gap_section_explains_box_edits_do_not_cover_gaps():
    page = web.PAGE
    line = ("Moving or resizing a plate box does not cover a gap; "
            "use Track object on that plate instead.")
    start = page.index("function renderLetterGaps(")
    body = page[start:page.index("\n}\n", start)]
    assert line in body
    assert body.index("lglist") < body.index(line)        # under the list
    assert "&#8857; Track object</button>" in page        # the editor's label
