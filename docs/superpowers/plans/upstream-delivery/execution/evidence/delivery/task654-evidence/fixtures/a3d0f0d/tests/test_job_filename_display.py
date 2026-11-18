"""Literal accepted filenames at the ordinary job-list/title boundary.

Node evaluates the emitted JavaScript; HTMLParser checks the resulting HTML.
Only harmless text fixtures are used. Browser QA separately exercises the DOM.
"""
import io
import json
import shutil
import subprocess
from html.parser import HTMLParser

import pytest
import openscrub_web as web

NAMES = [
    "Family &amp; friends — café.mp4",
    "Friends' \"summer\" & snow ☃.MOV",
    "Literal &#38; and &quot; notes.mp4",
]


class Fragment(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def emitted_fragments(jobs):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to evaluate emitted job UI JavaScript")
    # The real emitted functions, including any local name boundary, run
    # with only their HTTP and output sinks supplied by this harness.
    script = 'let JOBSJSON="";\n' + web.APP_JS.split("// Job names are text", 1)[1].split("async function retryJob", 1)[0]
    script = script.replace(" inside the list link and detail heading.\n", "", 1)
    script += "function shellHtml(j)" + web.APP_JS.split("function shellHtml(j)", 1)[1].split(
        "// Save As exports", 1)[0]
    script += """
const data=JSON.parse(process.argv[1]);
const jobs={innerHTML:''};
const fetch=async()=>({status:200,json:async()=>data});
(async()=>{await loadJobs();console.log(JSON.stringify({
 list:jobs.innerHTML,titles:data.map(shellHtml)}));})();
"""
    result = subprocess.run([node, "-e", script, json.dumps(jobs)],
                            check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("surface", ["list", "title"])
def test_emitted_job_list_and_title_preserve_literal_name(name, surface):
    result = emitted_fragments([{"id": "a123456789ab", "name": name,
                                "phase": "queued"}])
    listing = Fragment(result["list"])
    title = Fragment(result["titles"][0])
    if surface == "list":
        assert listing.text[1] == name
    else:
        assert "".join(title.text).split("\n", 1)[0] == name
    assert [tag for tag, _ in listing.tags] == ["div", "a", "span", "span", "a"]
    assert listing.tags[1][1] == {
        "href": "#", "onclick": "openJob('a123456789ab');return false"}
    assert [tag for tag, _ in title.tags] == [
        "div", "h2", "span", "small", "progress", "div", "div", "img",
        "div", "div", "div"]
    assert title.tags[0][1]["id"] == "jobcard"
    assert title.tags[2][1]["id"] == "ph"


@pytest.mark.parametrize("intake", ["upload", "server"])
def test_intake_keeps_accepted_name_and_ordinary_downloads(intake, monkeypatch, tmp_path):
    # Catch changes to accepted basenames/metadata/download naming while
    # keeping the worker out of this route-only ownership test.
    monkeypatch.setattr(web, "JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr(web, "JOBS", {})
    queued = []
    monkeypatch.setattr(web, "enqueue", lambda job, mode: queued.append((job["id"], mode)))
    monkeypatch.setenv("OPENSCRUB_MEDIA_ROOT", str(tmp_path))
    client = web.app.test_client()
    name = NAMES[0]
    submitted = "folder/" + name if intake == "upload" else str(tmp_path / name)
    if intake == "upload":
        data = {"video": (io.BytesIO(b"synthetic input"), submitted), "options": "{}"}
    else:
        (tmp_path / name).write_bytes(b"synthetic input")
        data = {"server_path": submitted, "options": "{}"}
    response = client.post("/api/jobs", data=data)
    assert response.status_code == 200
    jid, = response.get_json()["jobs"]
    assert queued == [(jid, "scan")]
    job = web.JOBS[jid]
    assert job["name"] == name
    assert client.get("/api/jobs").get_json()[0]["name"] == name
    assert client.get("/api/jobs/" + jid).get_json()["name"] == name
    assert json.loads((tmp_path / "jobs" / jid / "options.json").read_text()) == {}
    if intake == "upload":
        assert job["video"] == str(tmp_path / "jobs" / jid / "input.mp4")
    else:
        assert job["video"] == submitted
    output = tmp_path / "jobs" / jid / "result.mkv"
    output.write_bytes(b"synthetic output")
    job["output"] = str(output)
    (output.parent / "report.json").write_bytes(b'{}')
    from urllib.parse import unquote
    for route, wanted, body in [
        ("download", "Family &amp; friends — café_redacted.mkv", b"synthetic output"),
        ("report", "Family &amp; friends — café_audit.json", b'{}'),
    ]:
        response = client.get("/api/jobs/" + jid + "/" + route)
        assert response.status_code == 200 and response.data == body
        disposition = response.headers["Content-Disposition"]
        assert unquote(disposition.split("filename*=UTF-8''", 1)[1]) == wanted
        response.close()
