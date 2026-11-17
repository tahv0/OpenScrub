"""Static source inventory only; never imports or executes product modules."""
import hashlib
import json
from pathlib import Path
import subprocess

SHA = "6ae212a35b094fc9466f1616afb2c5bb5c0497f8"
REPO = Path("/home/tahv0/src/OpenScrub")
SOURCE = Path("/tmp/openscrub-bounded-logs-contract/source")
OUT = REPO / ".superpowers/sdd/README/bounded-logs-contract-evidence"
SECTIONS = {
    "openscrub_web.py": [(274,277),(325,377),(610,619),(625,682),
        (740,823),(952,957),(1031,1071),(1083,1100),(1367,1375),
        (1424,1437),(2080,2118),(2126,2163),(2210,2214),(2238,2248),
        (2301,2325),(3337,3337),(3387,3413),(3674,3685),(3703,3715),
        (3954,3967),(4001,4022),(4029,4050),(4067,4075)],
    "openscrub.py": [(3436,3445),(8404,8409)],
    "openscrub_gui.py": [(97,106),(488,492),(507,514)],
    "pyproject.toml": [(9,12),(80,89),(106,153)],
    "Dockerfile": [(59,64)],
    "Dockerfile.cuda": [(131,136)],
    "Dockerfile.intel": [(93,98)],
    "windows/openscrub.spec": [(59,76)],
    "openscrub_update.py": [(140,181)],
    "tests/test_job_polling_node.py": [(119,126)],
    "tests/test_job_polling_browser.py": [(18,28),(58,64),(119,127),(185,190)],
    "test_openscrub.py": [(488,489),(665,666),(3620,3629),(3680,3690)],
}
manifest = {"source_commit": SHA, "method": "git archive from original repository; static text only", "runtime_executed": False, "files": {}}
anchors = []
for name, ranges in SECTIONS.items():
    data = (SOURCE / name).read_bytes()
    blob = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", SHA + ":" + name], text=True).strip()
    manifest["files"][name] = {"git_blob": blob, "sha256": hashlib.sha256(data).hexdigest()}
    lines = data.decode("utf-8").splitlines()
    for lo, hi in ranges:
        anchors.append("\n%s:%s:%d-%d\n" % (SHA, name, lo, hi))
        anchors.extend("%5d %s\n" % (n, lines[n-1]) for n in range(lo, min(hi,len(lines))+1))
(OUT / "source-identity.json").write_text(json.dumps(manifest, indent=2) + "\n")
(OUT / "source-anchors.txt").write_text("".join(anchors))

operations = []
for line_no, line in enumerate((SOURCE / "openscrub_web.py").read_text().splitlines(), 1):
    if any(s in line for s in ('["log"]', '"log":', '"log_tail":', '"log_len":', 'get("log")')):
        operations.append("%d\t%s" % (line_no, line.strip()))
(OUT / "log-operations.tsv").write_text("source_commit\t%s\nfile\topenscrub_web.py\nline\tsource\n%s\n" % (SHA, "\n".join(operations)))
print("Wrote source identities, bounded source excerpts and lexical log-owner inventory; no product execution.")
