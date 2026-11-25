"""Transfer a stopped detector scan independently of the source video's path."""
import gzip
import hashlib
import io
import zlib
import json
from pathlib import Path

from . import scan_progress

FORMAT = "openscrub-stopped-scan-v1"
# Bound the JSON a browser-supplied compressed file may expand to.
MAX_JSON = 512 * 1024 * 1024


def engine_build(engine_file):
    engine = Path(engine_file)
    digest = hashlib.sha256()
    for path in [engine, *sorted(Path(__file__).parent.glob("*.py"))]:
        digest.update(path.name.encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest())
    return digest.hexdigest()


def write_package(stream, progress_path, options, video, engine_file):
    state = scan_progress.load(progress_path)
    meta = state.pop("meta", None) or {}
    build = engine_build(engine_file)
    if meta.get("engine_build") and meta["engine_build"] != build:
        raise ValueError("Export using the OpenScrub build that stopped this scan")
    package = dict(format=FORMAT, engine=build,
                   source_sha256=scan_progress.file_sha256(video), options=options, state=state)
    with gzip.GzipFile(fileobj=stream, mode="wb", compresslevel=3, mtime=0) as gz, io.BufferedWriter(gz) as writer:
        count = 0
        for part in json.JSONEncoder(allow_nan=False, separators=(",", ":")).iterencode(package):
            data = part.encode()
            count += len(data)
            if count > MAX_JSON:
                raise ValueError("Stopped scan exceeds the transfer package size limit")
            writer.write(data)


def read_package(stream, video, engine_file):
    try:
        with gzip.GzipFile(fileobj=stream) as reader:
            data = reader.read(MAX_JSON + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError("Unreadable stopped scan package") from error
    if len(data) > MAX_JSON:
        raise ValueError("Stopped scan exceeds the transfer package size limit")
    package = json.loads(data)
    if not isinstance(package, dict) or package.get("format") != FORMAT:
        raise ValueError("Choose an OpenScrub stopped scan package")
    if package.get("engine") != engine_build(engine_file):
        raise ValueError("The two PCs must use the same OpenScrub scan engine build")
    if package.get("source_sha256") != scan_progress.file_sha256(video):
        raise ValueError("The selected video differs from the video used for this package")
    options, state = package.get("options"), package.get("state")
    if not isinstance(options, dict) or not isinstance(state, dict) or options.get("checkpoint_review"):
        raise ValueError("Invalid stopped scan settings")
    frame, total = state.get("next_frame"), state.get("total")
    if type(frame) is not int or type(total) is not int or not 0 < frame <= total:
        raise ValueError("Invalid stopped scan frame")
    identity = state.get("identity")
    if not isinstance(identity, dict) or identity.get("format_version") != scan_progress.SCAN_PROGRESS_VERSION:
        raise ValueError("Unsupported scan progress version")
    state["meta"] = {"video": str(video), "name": Path(video).name, "report_before": None,
                     "engine_build": package["engine"]}
    return options, state
