"""Configured Cheroot + real sockets; file responses remain owned after teardown."""
import http.client
import json
from pathlib import Path
import socket
import threading

import pytest
from cheroot import wsgi

import openscrub_web as web
from test_job_lifecycle import store


@pytest.mark.parametrize('endpoint', ['download', 'report', 'video'])
@pytest.mark.parametrize('ending', ['complete', 'iterator_error', 'disconnect'])
def test_configured_wsgi_closes_stream_owner_exactly_once(store, monkeypatch, endpoint, ending):
    store.enable()
    payload = bytes(range(256)) * 16384
    if endpoint == 'report':
        doc = dict(store.doc, synthetic_padding='x' * len(payload))
        store.path.write_text(json.dumps(doc))
        payload = store.path.read_bytes()
    else:
        output = Path(store.job['dir']) / 'output.mp4'
        output.write_bytes(payload)
        Path(store.job['video']).write_bytes(payload)
        store.job.update(output=str(output), phase='done')
    ready, entered, release, closed = (threading.Event() for _ in range(4))
    servers, errors, releases, logs = [], [], [], []
    real_prepare = wsgi.Server.prepare
    def prepare(server):
        real_prepare(server)
        server.error_log = lambda message='', **kw: logs.append(str(message))
        servers.append(server)
        ready.set()
    monkeypatch.setattr(wsgi.Server, 'prepare', prepare)
    real_send, real_close = web.send_file, web.OwnedIterable.close
    class Gate:
        def __init__(self, source):
            self.source, self.iterator, self.calls = source, iter(source), 0
        def __iter__(self):
            return self
        def __next__(self):
            self.calls += 1
            if self.calls == 2:
                entered.set()
                assert release.wait(8), 'socket schedule did not release file read'
                if ending == 'iterator_error':
                    raise OSError('synthetic streaming read failure')
            return next(self.iterator)
        def close(self):
            self.source.close()
    def send(*args, **kwargs):
        response = real_send(*args, **kwargs)
        response.response = Gate(response.response)
        return response
    def close(owner):
        was_released = owner.lease.released
        try:
            return real_close(owner)
        finally:
            if not was_released and owner.lease.released:
                releases.append(1)
            closed.set()
    monkeypatch.setattr(web, 'send_file', send)
    monkeypatch.setattr(web.OwnedIterable, 'close', close)
    def serve():
        try:
            web._serve('127.0.0.1', 0, None)
        except BaseException as error:
            errors.append(error)
            ready.set()
    thread = threading.Thread(target=serve, name='task621-cheroot')
    thread.start()
    connection = response = None
    try:
        assert ready.wait(8) and not errors, errors
        server = servers[0]
        port = server.socket.getsockname()[1]
        assert server.requests.min == 64  # exercise actual _serve configuration
        def api(method, path):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                conn.request(method, path, headers={'Connection': 'close'})
                result = conn.getresponse()
                result.read()
                return result.status
            finally:
                conn.close()
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        connection.request('GET', store.url + '/' + endpoint,
                           headers={'Range': 'bytes=3-1048578', 'Connection': 'close'})
        client_socket = connection.sock
        response = connection.getresponse()
        assert response.status == 206
        assert response.getheader('Content-Length') == '1048576'
        assert response.getheader('Content-Range') == 'bytes 3-1048578/%d' % len(payload)
        if endpoint == 'download':
            assert 'synthetic_redacted.mp4' in response.getheader('Content-Disposition')
        if endpoint == 'report':
            assert 'synthetic_audit.json' in response.getheader('Content-Disposition')
        assert entered.wait(5), 'iterator was never genuinely active'
        assert web.FILES.count == 1, 'request teardown released the stream too early'
        assert api('DELETE', store.url) == 409
        assert api('POST', '/api/vault/lock') == 409
        if ending == 'disconnect':
            client_socket.shutdown(socket.SHUT_RDWR)
            response.close()
            connection.close()
        release.set()
        if ending == 'complete':
            body = response.read()
            assert len(body) == 1048576 and body == payload[3:1048579]
        elif ending == 'iterator_error':
            with pytest.raises(http.client.IncompleteRead):
                response.read()
        assert closed.wait(8), 'Cheroot did not close the WSGI iterable'
        assert web.FILES.count == 0 and releases == [1]
        assert api('POST', '/api/vault/lock') == 200
    finally:
        release.set()
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()
        for server in servers:
            server.stop()
        thread.join(8)
        assert not thread.is_alive() and not errors, errors
