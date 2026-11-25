"""Review shows times as h:mm:ss.mmm, like the gap list, and the box editor's
from/to fields accept that format or plain seconds."""
import json
import re
import shutil
import subprocess

import pytest

import openscrub_web as web


def _fn(name):
    m = re.search(r"function %s\(.*?\n}\n" % name, web.PAGE, re.S)
    assert m, name
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_format_and_parse_round_trip():
    js = _fn("fmtTime") + _fn("parseTime") + """
const out={f:[fmtTime(0),fmtTime(83.4),fmtTime(3723.0456),fmtTime(-1)],
 p:[parseTime("0:01:23.400"),parseTime("1:23.4"),parseTime("83.4"),parseTime(" 1:02:03.5 "),
    parseTime("1:75:00"),parseTime("abc"),parseTime("")]};
console.log(JSON.stringify(out));"""
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert out["f"] == ["0:00:00.000", "0:01:23.400", "1:02:03.046", "0:00:00.000"]
    assert out["p"][:4] == [83.4, 83.4, 83.4, 3723.5]
    assert out["p"][4:] == [None, None, None]        # invalid -> rejected, never guessed


def test_review_uses_the_shared_format():
    page = web.PAGE
    assert "${fmtTime(x.t_start)}–${fmtTime(x.t_end)}" in page          # review cards
    assert 'textContent=fmtTime(BE.t)' in page                         # editor playhead
    assert "x.t_start.toFixed(1)}–${x.t_end.toFixed(1)}s" not in page
    assert 'id="beT0"' in page and 'type="number" id="beT0"' not in page
    assert "parseTime(document.getElementById(\"beT0\").value)" in page
    start = page.index("function lgOutTime(")
    assert "fmtTime(" in page[start:page.index("\n}\n", start)]
