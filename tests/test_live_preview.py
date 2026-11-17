"""Complete-generation preview publication and actual configured HTTP serving."""
import builtins
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import cheroot.wsgi
import werkzeug.wsgi

import openscrub_web as web


@pytest.fixture
def preview(tmp_path, monkeypatch):
    job = {"id": "preview-test", "dir": str(tmp_path), "log": [],
           "cancel": threading.Event()}
    monkeypatch.setitem(web.JOBS, job["id"], job)
    rng = np.random.default_rng(20261117)
    frames = [rng.integers(0, 256, (240, 720, 3), dtype=np.uint8),
              np.full((240, 720, 3), (24, 24, 224), dtype=np.uint8),
              rng.integers(0, 256, (240, 720, 3), dtype=np.uint8)]
    frames[2][:, :300] = (24, 224, 24)
    expected = [cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
                for frame in frames]
    assert len(expected[0]) > len(expected[2]) > 8192 > len(expected[1])
    return job, tmp_path / "preview.jpg", frames, expected


def publish(job, frame):
    # A fresh callback passes the real throttle without timing sleeps.
    web.WebCallbacks(job).scan_frame(frame, 0.0, 0)


@pytest.fixture
def http(monkeypatch):
    """Observe readiness only; run production _serve and real Cheroot sockets."""
    ready = threading.Event()
    holder, errors = {}, []
    prepare = cheroot.wsgi.Server.prepare

    def observed_prepare(server):
        prepare(server)
        holder["server"] = server
        ready.set()

    monkeypatch.setattr(cheroot.wsgi.Server, "prepare", observed_prepare)

    def serve():
        try:
            web._serve("127.0.0.1", 0, None)
        except BaseException as error:
            errors.append(error)
            ready.set()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        assert ready.wait(10), "configured server never prepared"
        assert not errors, errors
        port = holder["server"].socket.getsockname()[1]

        def fetch(jid="preview-test", headers=None):
            lines = [f"GET /api/jobs/{jid}/preview.jpg HTTP/1.1", "Host: 127.0.0.1",
                     "Connection: close"]
            lines += [f"{key}: {value}" for key, value in (headers or {}).items()]
            with socket.create_connection(("127.0.0.1", port), timeout=10) as conn:
                conn.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
                chunks = []
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
            head, body = b"".join(chunks).split(b"\r\n\r\n", 1)
            rows = head.decode("latin1").split("\r\n")
            actual = dict(row.split(": ", 1) for row in rows[1:])
            print("HTTP", rows[0], actual, "bytes", len(body), "sha256",
                  hashlib.sha256(body).hexdigest())
            return int(rows[0].split()[1]), actual, body

        yield fetch
    finally:
        if "server" in holder:
            holder["server"].stop()
        thread.join(10)
        assert not thread.is_alive(), "configured server did not stop"
        assert not errors, errors


def assert_jpeg(response, expected):
    status, headers, body = response
    assert status == 200
    assert body == expected
    assert int(headers["Content-Length"]) == len(body)
    assert headers["Content-Type"] == "image/jpeg"
    assert headers["Content-Disposition"] == "inline; filename=preview.jpg"
    assert headers["Cache-Control"] == "no-cache, max-age=0"
    assert headers["Server"] == "openscrub"
    assert headers["Accept-Ranges"] == "bytes"


@pytest.mark.parametrize("read_number,newer", [(1, 1), (2, 2)])
def test_http_publication_after_headers_and_between_chunks(preview, http, monkeypatch,
                                                          read_number, newer):
    """Later publication must not mutate a response already being iterated."""
    job, path, frames, expected = preview
    publish(job, frames[0])
    reached, resume = threading.Event(), threading.Event()
    original = werkzeug.wsgi.FileWrapper.__next__
    reads = []

    def observed_next(wrapper):
        reads.append(wrapper.buffer_size)
        if len(reads) == read_number:
            reached.set()
            assert resume.wait(10), "response read was not released"
        return original(wrapper)

    monkeypatch.setattr(werkzeug.wsgi.FileWrapper, "__next__", observed_next)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(http)
        try:
            assert reached.wait(10), "ordinary response read not reached"
            publish(job, frames[newer])
        finally:
            resume.set()
        response = result.result(timeout=10)
    assert reads[:read_number] == [8192] * read_number
    assert path.read_bytes() == expected[newer]
    assert_jpeg(response, expected[0])


def test_http_replacement_before_open_uses_same_generation_for_length(preview, http,
                                                                    monkeypatch):
    """Replacement at the old stat/open gap must keep length and bytes together."""
    job, path, frames, expected = preview
    publish(job, frames[0])
    stage = path.parent / "staged"
    stage.mkdir()
    publish({"dir": str(stage), "cancel": threading.Event()}, frames[1])
    reached, resume = threading.Event(), threading.Event()
    original_open = builtins.open

    def observed_open(file, mode="r", *args, **kwargs):
        if os.fspath(file) == str(path) and mode == "rb":
            reached.set()
            assert resume.wait(10), "preview open was not released"
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", observed_open)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(http)
        try:
            assert reached.wait(10), "preview open not reached"
            os.replace(stage / "preview.jpg", path)
        finally:
            resume.set()
        response = result.result(timeout=10)
    assert_jpeg(response, expected[1])


def test_publication_preserves_an_open_generation(preview):
    """A snapshot acquisition spanning publication must read the complete old JPEG."""
    job, path, frames, expected = preview
    publish(job, frames[0])
    with path.open("rb") as snapshot:
        prefix = snapshot.read(8192)
        publish(job, frames[2])
        body = prefix + snapshot.read()
    assert body == expected[0]
    assert path.read_bytes() == expected[2]
    assert sorted(p.name for p in path.parent.iterdir()) == ["preview.jpg"]


@pytest.mark.parametrize("failure", ["encode-false", "encode-empty", "encode-error",
                                     "temporary-create", "temporary-write", "replace"])
@pytest.mark.parametrize("prior", [False, True])
def test_failed_publication_retains_bytes_cleans_up_and_retries(preview, http, monkeypatch,
                                                              failure, prior):
    job, path, frames, expected = preview
    if prior:
        publish(job, frames[0])
    callback = web.WebCallbacks(job)
    clock = [10.0]
    monkeypatch.setattr(web, "time", SimpleNamespace(time=lambda: clock[0]))
    with monkeypatch.context() as fault:
        if failure == "encode-false":
            fault.setattr(cv2, "imencode", lambda *args: (False, None))
        elif failure == "encode-empty":
            fault.setattr(cv2, "imencode", lambda *args: (True, np.array([], dtype=np.uint8)))
        elif failure == "encode-error":
            def fail_encode(*args):
                raise cv2.error("synthetic JPEG encoding failure")
            fault.setattr(cv2, "imencode", fail_encode)
        elif failure == "temporary-create":
            def fail_create(*args, **kwargs):
                raise OSError("synthetic temporary creation failure")
            fault.setattr(tempfile, "NamedTemporaryFile", fail_create)
        elif failure == "temporary-write":
            real_temporary = tempfile.NamedTemporaryFile

            class FailedWrite:
                def __init__(self, *args, **kwargs):
                    self.file = real_temporary(*args, **kwargs)
                    self.name = self.file.name
                def __enter__(self):
                    self.file.__enter__()
                    return self
                def __exit__(self, *args):
                    return self.file.__exit__(*args)
                def write(self, data):
                    self.file.write(data[:20])
                    raise OSError("synthetic failure after partial temporary write")

            fault.setattr(tempfile, "NamedTemporaryFile", FailedWrite)
        else:
            def fail_replace(*args):
                raise OSError("synthetic replacement failure")
            fault.setattr(os, "replace", fail_replace)
        callback.scan_frame(frames[1], 1.0, 2)
    assert callback._last_frame == 10.0  # even a failed attempt consumes the interval
    assert sorted(p.name for p in path.parent.iterdir()) == (["preview.jpg"] if prior else [])
    if prior:
        assert path.read_bytes() == expected[0]
        assert_jpeg(http(), expected[0])
    else:
        assert http()[0] == 404
    clock[0] = 10.399
    callback.scan_frame(frames[1], 2.0, 3)
    assert path.exists() == prior
    if prior:
        assert path.read_bytes() == expected[0]
    clock[0] = 10.4
    callback.scan_frame(frames[1], 3.0, 4)
    assert_jpeg(http(), expected[1])
    assert sorted(p.name for p in path.parent.iterdir()) == ["preview.jpg"]


@pytest.mark.parametrize("error", [ValueError("programmer error"), KeyboardInterrupt(), SystemExit()])
def test_unrelated_errors_and_termination_propagate(preview, monkeypatch, error):
    job, path, frames, expected = preview
    publish(job, frames[0])

    def fail_encode(*args):
        raise error

    monkeypatch.setattr(cv2, "imencode", fail_encode)
    with pytest.raises(type(error)):
        publish(job, frames[1])
    assert path.read_bytes() == expected[0]


@pytest.mark.parametrize("height,width,out_height", [(101, 301, 241), (401, 1001, 288)])
def test_callback_preserves_scale_quality_and_throttle(preview, monkeypatch, height, width,
                                                      out_height):
    job, path, _, _ = preview
    frame = np.random.default_rng(3).integers(0, 256, (height, width, 3), dtype=np.uint8)
    expected = cv2.imencode(".jpg", cv2.resize(frame, (720, out_height)),
                            [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
    clock = [20.0]
    monkeypatch.setattr(web, "time", SimpleNamespace(time=lambda: clock[0]))
    callback = web.WebCallbacks(job)
    callback.scan_frame(frame, 0.0, 0)
    assert path.read_bytes() == expected
    assert cv2.imdecode(np.frombuffer(expected, np.uint8), cv2.IMREAD_COLOR).shape == (out_height, 720, 3)
    clock[0] = 20.399
    callback.scan_frame(np.zeros_like(frame), 1.0, 1)
    assert path.read_bytes() == expected
    clock[0] = 20.401
    callback.scan_frame(np.zeros_like(frame), 2.0, 2)
    assert path.read_bytes() != expected


def test_http_missing_conditional_range_and_changed_etag(preview, http):
    job, path, frames, expected = preview
    assert http()[0] == 404
    assert http(jid="no-such-job")[0] == 404
    publish(job, frames[0])
    response = http()
    assert_jpeg(response, expected[0])
    etag = response[1]["ETag"]
    status, headers, body = http(headers={"If-None-Match": etag})
    assert status == 304 and body == b""
    assert headers["ETag"] == etag
    assert headers["Cache-Control"] == "no-cache, max-age=0"
    status, headers, body = http(headers={"Range": "bytes=10-99", "If-Range": etag})
    assert status == 206 and body == expected[0][10:100]
    assert headers["Content-Length"] == "90"
    assert headers["Content-Range"] == f"bytes 10-99/{len(expected[0])}"
    assert headers["ETag"] == etag
    assert http(headers={"Range": f"bytes={len(expected[0])}-"})[0] == 416
    # Equal size and mtime must not let a path-metadata ETag validate new bytes.
    publish(job, frames[1])
    first_solid = path.read_bytes()
    solid_response = http()
    stat = path.stat()
    alternate = np.full_like(frames[1], (224, 24, 24))
    publish(job, alternate)
    second_solid = path.read_bytes()
    assert second_solid != first_solid and len(second_solid) == len(first_solid)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert_jpeg(http(headers={"If-None-Match": solid_response[1]["ETag"]}), second_solid)
    assert http(headers={"Range": "bytes=10-99", "If-Range": etag})[0] == 200


def test_publication_helper_returns_boolean_status(preview, monkeypatch):
    _, path, frames, expected = preview
    assert web._publish_preview_jpeg(path, frames[0], 70) is True
    monkeypatch.setattr(cv2, "imencode", lambda *args: (False, None))
    assert web._publish_preview_jpeg(path, frames[1], 70) is False
    assert path.read_bytes() == expected[0]


def test_termination_during_replace_cleans_temporary_and_propagates(preview, monkeypatch):
    job, path, frames, expected = preview
    publish(job, frames[0])

    def terminate(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(os, "replace", terminate)
    with pytest.raises(KeyboardInterrupt):
        publish(job, frames[1])
    assert path.read_bytes() == expected[0]
    assert sorted(p.name for p in path.parent.iterdir()) == ["preview.jpg"]


@pytest.mark.parametrize("failure,status", [("disappeared", 404), ("read-error", 500)])
def test_http_acquisition_failure_never_serves_partial_jpeg(preview, http, monkeypatch,
                                                          failure, status):
    job, path, frames, _ = preview
    publish(job, frames[0])
    original_open = builtins.open

    class FailedRead:
        def __init__(self, file):
            self.file = file
        def __getattr__(self, name):
            return getattr(self.file, name)
        def __enter__(self):
            self.file.__enter__()
            return self
        def __exit__(self, *args):
            return self.file.__exit__(*args)
        def read(self, *args):
            self.file.read(8192)
            raise OSError("synthetic preview snapshot read failure")

    def observed_open(file, mode="r", *args, **kwargs):
        if os.fspath(file) == str(path) and mode == "rb":
            if failure == "disappeared":
                path.unlink()
            else:
                return FailedRead(original_open(file, mode, *args, **kwargs))
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", observed_open)
    actual, headers, body = http()
    assert actual == status
    assert headers["Content-Type"].startswith("text/html")
    assert int(headers["Content-Length"]) == len(body)
    assert not body.startswith(b"\xff\xd8")
