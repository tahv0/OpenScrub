"""Transient staging names must not abort an otherwise successful vault pass."""
import os
from pathlib import Path
import threading

import pytest

import openscrub_vault as vault
import openscrub_web as web
from openscrub_internal import reports


def test_successful_report_publication_does_not_abort_vault_lock(tmp_path, monkeypatch):
    report = tmp_path / 'report.json'
    report.write_bytes(b'{"synthetic": "old"}')
    video = tmp_path / 'input.avi'
    video.write_bytes(b'synthetic input bytes')
    key = os.urandom(32)
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    monkeypatch.setattr(web, 'VAULT', {'key': key})
    staged, snapshotted, published = (threading.Event() for _ in range(3))
    errors, new_bytes = [], []
    real_replace, real_walk = os.replace, vault._walk_files

    def gated_replace(source, destination):
        if Path(source).name.startswith('.report-'):
            staged.set()
            assert snapshotted.wait(5), 'vault did not snapshot the active stage'
        return real_replace(source, destination)

    def snapshot_before_publication(root):
        paths = list(real_walk(root))
        assert any(p.endswith('.tmp') for p in paths)
        # os.walk may enumerate the stage first; freeze that permitted order.
        paths.sort(key=lambda p: not p.endswith('.tmp'))
        snapshotted.set()
        assert published.wait(5), 'report publication did not finish'
        yield from paths

    def publish():
        try:
            reports.atomic_report(report, {'synthetic': 'new'})
            new_bytes.append(report.read_bytes())
        except Exception as error:
            errors.append(error)
        finally:
            published.set()

    with monkeypatch.context() as gate:
        gate.setattr(reports.os, 'replace', gated_replace)
        gate.setattr(vault, '_walk_files', snapshot_before_publication)
        thread = threading.Thread(target=publish)
        thread.start()
        try:
            assert staged.wait(5), 'report stage was not created'
            encrypted = web._vault_lock_now()
        finally:
            snapshotted.set()
            thread.join(5)
        assert not thread.is_alive()
        assert not errors
    assert encrypted == 2
    assert web.VAULT['key'] is None
    assert vault.tree_locked_state(str(tmp_path)) == (2, 0)
    assert not report.exists() and not video.exists()
    assert vault.decrypt_tree(key, str(tmp_path)) == 2
    assert report.read_bytes() == new_bytes[0] == b'{\n "synthetic": "new"\n}'
    assert video.read_bytes() == b'synthetic input bytes'
    assert not list(tmp_path.glob('*.tmp'))


def test_decrypt_continues_after_snapshotted_temporary_file_disappears(tmp_path, monkeypatch):
    key = os.urandom(32)
    report = tmp_path / 'report.json'
    report.write_bytes(b'{"synthetic": true}')
    video = tmp_path / 'input.avi'
    video.write_bytes(b'synthetic input')
    assert vault.encrypt_tree(key, str(tmp_path)) == 2
    vanished = tmp_path / '.report-vanished.tmp'
    leftover = tmp_path / 'crash-leftover.tmp'
    vanished.write_bytes(b'synthetic stage')
    leftover.write_bytes(b'synthetic crash leftover')
    real_walk = vault._walk_files
    def snapshot_then_remove(root):
        paths = list(real_walk(root))
        paths.sort(key=lambda p: not p.endswith('.tmp'))
        vanished.unlink()
        return iter(paths)
    monkeypatch.setattr(vault, '_walk_files', snapshot_then_remove)
    assert vault.decrypt_tree(key, str(tmp_path)) == 2
    assert report.read_bytes() == b'{"synthetic": true}'
    assert video.read_bytes() == b'synthetic input'
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('operation', [vault.encrypt_tree, vault.decrypt_tree])
@pytest.mark.parametrize('error', [PermissionError, OSError])
def test_temporary_cleanup_errors_other_than_missing_file_propagate(
        tmp_path, monkeypatch, operation, error):
    temporary = tmp_path / '.report-blocked.tmp'
    temporary.write_bytes(b'synthetic stage')
    real_remove = os.remove
    def denied(path):
        if path == str(temporary):
            raise error('injected cleanup failure')
        return real_remove(path)
    monkeypatch.setattr(vault.os, 'remove', denied)
    with pytest.raises(error, match='injected cleanup failure'):
        operation(os.urandom(32), str(tmp_path))
    assert temporary.read_bytes() == b'synthetic stage'


@pytest.mark.parametrize('operation', [vault.encrypt_tree, vault.decrypt_tree])
def test_disappearing_ordinary_source_still_aborts_vault_pass(tmp_path, monkeypatch, operation):
    key = os.urandom(32)
    source = tmp_path / 'report.json'
    source.write_bytes(b'{"synthetic": true}')
    if operation is vault.decrypt_tree:
        source = Path(vault.encrypt_file(key, str(source)))
    real_walk = vault._walk_files
    def snapshot_then_remove(root):
        paths = list(real_walk(root))
        source.unlink()
        return iter(paths)
    monkeypatch.setattr(vault, '_walk_files', snapshot_then_remove)
    with pytest.raises(FileNotFoundError):
        operation(key, str(tmp_path))
