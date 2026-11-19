"""Live exact-source continuity across real vault transitions."""
import errno
import os

import pytest
import openscrub_web as web
from test_exact_samples import exact, sample, precondition, post, raw
from test_job_lifecycle import store, request


def test_exact_precondition_survives_real_vault_roundtrip(exact):
    exact.enable()
    before = sample(exact)
    pc = precondition(before)
    files = web.FILES.initialize(exact.job)
    selected = files.current_source
    epoch = files.source_epoch
    old_stamp = selected['stamp']
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    after = sample(exact)
    assert files.current_source is selected
    assert selected['stamp'] == web._file_stamp(os.stat(selected['path'])) != old_stamp
    assert files.source_epoch == epoch
    assert precondition(after) == pc
    response = post(exact, geometry_preconditions={'0': pc}, box_overrides={'0': [3,4,10,11]})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert raw(exact)['detections'][0]['cbox'] == [3,4,10,11]


def test_geometry_conflict_after_roundtrip(exact):
    exact.enable()
    pc = precondition(sample(exact))
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    doc = raw(exact)
    doc['detections'][0]['cbox'] = [9, 9, 12, 12]
    exact.path.write_text(__import__('json').dumps(doc))
    assert post(exact, geometry_preconditions={'0': pc}, box_overrides={'0': [3,4,10,11]}).status_code == 409


def test_repeated_roundtrips_and_wrong_password(exact):
    exact.enable()
    pc = precondition(sample(exact))
    selected = web.FILES.initialize(exact.job).current_source
    for _ in range(2):
        assert request('post', '/api/vault/lock').status_code == 200
        assert request('post', '/api/vault/unlock', json={'password': 'wrong-password'}).status_code == 403
        assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
        assert web.FILES.initialize(exact.job).current_source is selected
        assert precondition(sample(exact)) == pc


def test_rehydrate_failure_retires_and_recovery_cannot_reuse_proof(exact, monkeypatch):
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    assert request('post', '/api/vault/lock').status_code == 200
    old = files.current_source['stamp']
    real = web._rehydrate_jobs
    def fail():
        assert web.VAULT['closed']
        assert files.current_source['stamp'] == old
        raise OSError('injected rehydration failure')
    monkeypatch.setattr(web, '_rehydrate_jobs', fail)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 500
    assert files.source_retired and files.current_source is None and files.vault_transition is None
    assert web.VAULT['closed']
    monkeypatch.setattr(web, '_rehydrate_jobs', real)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200


def test_changed_source_on_noop_unlock_stays_stale(exact):
    exact.enable()
    pc = precondition(sample(exact))
    source = __import__('pathlib').Path(exact.job['video'])
    replacement = source.with_name('replacement')
    replacement.write_bytes(source.read_bytes())
    replacement.replace(source)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert post(exact, geometry_preconditions={'0': pc}, box_overrides={'0': [3,4,10,11]}).status_code == 409


def test_stale_subscriber_does_not_authorize_replaced_input(exact):
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    source = __import__('pathlib').Path(exact.job['video'])
    replacement = source.with_name('replacement')
    replacement.write_bytes(source.read_bytes())
    replacement.replace(source)
    assert request('post', '/api/vault/lock').status_code == 200
    assert files.source_retired and files.current_source is None
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200


def test_witness_receipts_bind_streams_and_nonce(tmp_path):
    import openscrub_vault as vault
    key = os.urandom(32)
    path = tmp_path / 'video'
    path.write_bytes(b'bounded plaintext')
    receipts = []
    def observe(direction, plain):
        assert plain == str(path)
        return receipts.append
    vault.encrypt_file(key, str(path), observe)
    sealed = receipts[-1]
    assert sealed.direction == 'encrypt' and sealed.plaintext_bytes == len(b'bounded plaintext')
    assert sealed.output_stamp == vault._entry_stamp(str(path) + vault.SUFFIX)
    vault.decrypt_file(key, str(path) + vault.SUFFIX, observe)
    restored = receipts[-1]
    assert restored.input_stamp == sealed.output_stamp and restored.nonce == sealed.nonce
    assert restored.output_stamp == vault._entry_stamp(str(path))
    assert path.read_bytes() == b'bounded plaintext'


def test_witness_does_not_receipt_failed_remove(tmp_path, monkeypatch):
    import pytest
    import openscrub_vault as vault
    key = os.urandom(32)
    path = tmp_path / 'video'
    path.write_bytes(b'plaintext')
    receipts = []
    real = vault.os.remove
    def fail(name):
        if str(name) == str(path):
            raise OSError('injected removal failure')
        return real(name)
    monkeypatch.setattr(vault.os, 'remove', fail)
    with pytest.raises(OSError):
        vault.encrypt_file(key, str(path), lambda *_: receipts.append)
    assert receipts == [] and path.exists()
    assert (tmp_path / 'video.osvault').exists()


def test_witness_rejects_existing_plaintext_on_decrypt(tmp_path):
    import pytest
    import openscrub_vault as vault
    key = os.urandom(32)
    path = tmp_path / 'video'
    path.write_bytes(b'plaintext')
    vault.encrypt_file(key, str(path))
    path.write_bytes(b'independent')
    receipts = []
    with pytest.raises(OSError):
        vault.decrypt_file(key, str(path) + vault.SUFFIX, lambda *_: receipts.append)
    assert not receipts and path.read_bytes() == b'independent'


def test_shared_source_valid_and_stale_subscribers(exact):
    import json
    from pathlib import Path
    exact.enable()
    sample(exact)
    old_files = web.FILES.initialize(exact.job)
    source = Path(exact.job['video'])
    replacement = source.with_name('replacement')
    replacement.write_bytes(source.read_bytes())
    replacement.replace(source)
    other = web.new_job('', {}, 'second.avi')
    other.update(video=str(source), phase='review')
    Path(other['dir'], 'report.json').write_text(json.dumps(raw(exact)))
    other_url = '/api/jobs/' + other['id']
    assert request('get', other_url + '/edit_sample?t=0.2').status_code == 200
    other_files = web.FILES.initialize(other)
    selected = other_files.current_source
    assert selected is not old_files.current_source
    assert request('post', '/api/vault/lock').status_code == 200
    assert old_files.source_retired and old_files.current_source is None
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert other_files.current_source is selected
    assert request('get', other_url + '/edit_sample?t=0.2').status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200


def test_later_encrypt_failure_invalidates_sealed_source(exact, monkeypatch):
    import openscrub_vault as vault
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    source = exact.job['video']
    real_walk, real_encrypt = vault._walk_files, vault.encrypt_file
    monkeypatch.setattr(vault, '_walk_files', lambda root: iter([source, str(exact.path)]))
    def fail_later(key, path, *args):
        if path == str(exact.path):
            raise OSError('injected later file failure')
        return real_encrypt(key, path, *args)
    monkeypatch.setattr(vault, 'encrypt_file', fail_later)
    assert request('post', '/api/vault/lock').status_code == 500
    assert files.source_retired and files.vault_transition is None
    assert web.VAULT['closed']
    monkeypatch.setattr(vault, '_walk_files', real_walk)
    monkeypatch.setattr(vault, 'encrypt_file', real_encrypt)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200


def test_authenticated_different_ciphertext_cannot_authorize_source(exact):
    from pathlib import Path
    import openscrub_vault as vault
    key = exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    source = Path(exact.job['video'])
    assert request('post', '/api/vault/lock').status_code == 200
    unrelated = source.with_name('unrelated')
    unrelated.write_bytes(b'x' * files.current_source['stamp'][2])
    vault.encrypt_file(key, str(unrelated))
    Path(str(unrelated) + vault.SUFFIX).replace(Path(str(source) + vault.SUFFIX))
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert files.source_retired and files.current_source is None


def test_witness_detects_mutation_while_streaming(tmp_path, monkeypatch):
    import pytest
    import openscrub_vault as vault
    path = tmp_path / 'source'
    path.write_bytes(b'synthetic')
    real_aes = vault.AESGCM
    class MutatingAES:
        def __init__(self, key):
            self.aes = real_aes(key)
        def encrypt(self, *args):
            result = self.aes.encrypt(*args)
            path.write_bytes(b'changed bytes')
            return result
    monkeypatch.setattr(vault, 'AESGCM', MutatingAES)
    receipts = []
    with pytest.raises(OSError):
        vault.encrypt_file(os.urandom(32), str(path), lambda *_: receipts.append)
    assert not receipts and path.read_bytes() == b'changed bytes'
    assert not list(tmp_path.glob('.vault-*.tmp'))


def test_later_decrypt_failure_invalidates_candidate(exact, monkeypatch):
    import openscrub_vault as vault
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    assert request('post', '/api/vault/lock').status_code == 200
    real_walk, real_decrypt = vault._walk_files, vault.decrypt_file
    source = exact.job['video'] + vault.SUFFIX
    report = str(exact.path) + vault.SUFFIX
    monkeypatch.setattr(vault, '_walk_files', lambda root: iter([source, report]))
    def fail_later(key, path, *args):
        if path == report:
            raise OSError('injected later decrypt failure')
        return real_decrypt(key, path, *args)
    monkeypatch.setattr(vault, 'decrypt_file', fail_later)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 500
    assert files.source_retired and files.current_source is None and files.vault_transition is None
    monkeypatch.setattr(vault, '_walk_files', real_walk)
    monkeypatch.setattr(vault, 'decrypt_file', real_decrypt)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200


def test_restored_source_changed_before_commit_is_retired(exact, monkeypatch):
    from pathlib import Path
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    assert request('post', '/api/vault/lock').status_code == 200
    real = web._rehydrate_jobs
    def change():
        result = real()
        path = Path(exact.job['video'])
        replacement = path.with_name('replacement')
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
        return result
    monkeypatch.setattr(web, '_rehydrate_jobs', change)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert files.source_retired and files.current_source is None and files.vault_transition is None


def test_witness_rejects_published_output_substitution(tmp_path, monkeypatch):
    import pytest
    import openscrub_vault as vault
    path = tmp_path / 'source'
    path.write_bytes(b'synthetic')
    replace = vault.os.replace
    def substitute(src, dst):
        replace(src, dst)
        replacement = tmp_path / 'substitute'
        replacement.write_bytes(b'different')
        replace(replacement, dst)
    monkeypatch.setattr(vault.os, 'replace', substitute)
    receipts = []
    with pytest.raises(OSError):
        vault.encrypt_file(os.urandom(32), str(path), lambda *_: receipts.append)
    assert not receipts and path.exists()


def test_outside_store_source_stays_current(exact):
    import json
    from pathlib import Path
    exact.enable()
    outside = exact.root / 'external.avi'
    outside.write_bytes(Path(exact.job['video']).read_bytes())
    exact.job['video'] = str(outside)
    doc = raw(exact)
    doc['provenance']['input'] = str(outside)
    exact.path.write_text(json.dumps(doc))
    pc = precondition(sample(exact))
    files = web.FILES.initialize(exact.job)
    selected = files.current_source
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert files.current_source is selected and precondition(sample(exact)) == pc


def test_reappearing_plaintext_blocks_observed_unlock(exact):
    from pathlib import Path
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    assert request('post', '/api/vault/lock').status_code == 200
    source = Path(exact.job['video'])
    foreign = exact.root / 'foreign'
    foreign.write_bytes(b'independent')
    source.symlink_to(foreign)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 500
    assert source.is_symlink() and foreign.read_bytes() == b'independent'
    assert files.source_retired and files.vault_transition is None


def test_shared_streams_cross_small_chunk_boundaries(tmp_path, monkeypatch):
    import openscrub_vault as vault
    monkeypatch.setattr(vault, 'CHUNK', 7)
    key = os.urandom(32)
    payload = bytes(range(31))
    for observed in (False, True):
        path = tmp_path / ('observed' if observed else 'legacy')
        path.write_bytes(payload)
        receipts = []
        if observed:
            vault.encrypt_file(key, str(path), lambda *_: receipts.append)
            vault.decrypt_file(key, str(path) + vault.SUFFIX, lambda *_: receipts.append)
            assert [r.plaintext_bytes for r in receipts] == [len(payload), len(payload)]
        else:
            vault.encrypt_file(key, str(path))
            vault.decrypt_file(key, str(path) + vault.SUFFIX)
        assert path.read_bytes() == payload


def _second_source(exact):
    import json
    from pathlib import Path
    job = web.new_job('', {}, 'another.avi')
    video = Path(job['dir']) / 'input.avi'
    video.write_bytes(Path(exact.job['video']).read_bytes())
    job.update(video=str(video), phase='review')
    doc = raw(exact)
    doc['provenance']['input'] = str(video)
    Path(job['dir'], 'report.json').write_text(json.dumps(doc))
    return job, '/api/jobs/' + job['id']


def test_pending_owner_and_fresh_rehydrated_owner_keep_separate_semantics(exact):
    exact.enable()
    pc = precondition(sample(exact))
    files = web.FILES.initialize(exact.job)
    selected, old_stamp = files.current_source, files.current_source['stamp']
    import threading
    from types import SimpleNamespace
    operation = threading.Event()
    with files.report_lock:
        files.operation = operation
        web._report_committed_locked(exact.job, raw(exact), SimpleNamespace(operation=operation))
        pending_pair = files.source_pair
    other, url = _second_source(exact)
    old_owner = web.FILES.initialize(other)
    with web.JOBS_LOCK:
        del web.JOBS[other['id']]
    assert request('post', '/api/vault/lock').status_code == 200
    assert files.vault_transition is None
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert files.source_status == 'pending' and files.source_pair == pending_pair
    assert files.current_source is selected
    assert selected['stamp'] == old_stamp and files.vault_transition is None
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code == 409
    assert post(exact, geometry_preconditions={'0': pc}, box_overrides={'0': [3,4,10,11]}).status_code == 409
    recovered = web.JOBS[other['id']]
    new_owner = web.FILES.initialize(recovered)
    assert recovered is not other and new_owner is not old_owner
    assert new_owner.current_source is None and new_owner.vault_transition is None
    assert request('get', url + '/edit_sample?t=0.2').status_code == 200
    assert new_owner.current_source is not selected


def test_replacement_immediately_before_open_retires_only_old_source(exact, monkeypatch):
    from pathlib import Path
    import openscrub_vault as vault
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    source = Path(exact.job['video'])
    old_stamp = files.current_source['stamp']
    foreign = exact.root / 'foreign'
    foreign.write_bytes(b'outside remains intact')
    real = vault._witnessed_file
    changed = []
    def replace_before_open(key, path, direction, finish):
        if path == str(source) and direction == 'encrypt':
            replacement = source.with_name('replacement')
            replacement.write_bytes(source.read_bytes())
            replacement.replace(source)
            changed.append(web._file_stamp(os.stat(source)))
        return real(key, path, direction, finish)
    monkeypatch.setattr(vault, '_witnessed_file', replace_before_open)
    assert request('post', '/api/vault/lock').status_code == 200
    assert changed and changed[0] != old_stamp
    assert files.source_retired and files.current_source is None and files.vault_transition is None
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200
    assert foreign.read_bytes() == b'outside remains intact'


def test_ciphertext_mutated_during_authenticated_decrypt_cannot_reuse_receipt(exact, monkeypatch):
    from pathlib import Path
    import openscrub_vault as vault
    exact.enable()
    pc = precondition(sample(exact))
    files = web.FILES.initialize(exact.job)
    assert request('post', '/api/vault/lock').status_code == 200
    cipher = Path(exact.job['video'] + vault.SUFFIX)
    foreign = exact.root / 'foreign'
    foreign.write_bytes(b'outside remains intact')
    real_stream, real_witness = vault._decrypt_stream, vault._witnessed_file
    completed, failures = [], []
    def mutate_at_eof(aes, src, dst, path, witnessed=False):
        nonce, count = real_stream(aes, src, dst, path, witnessed=witnessed)
        if path == str(cipher):
            assert not src.closed and src.read(1) == b''
            info = cipher.stat()
            os.utime(cipher, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
            completed.append((nonce, count))
        return nonce, count
    def capture(key, path, direction, finish):
        try:
            return real_witness(key, path, direction, finish)
        except OSError as error:
            if path == str(cipher):
                failures.append(str(error))
            raise
    monkeypatch.setattr(vault, '_decrypt_stream', mutate_at_eof)
    monkeypatch.setattr(vault, '_witnessed_file', capture)
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 500
    assert completed and failures == ['vault input changed during streaming']
    assert cipher.exists() and not Path(exact.job['video']).exists()
    assert web.VAULT['closed'] and files.source_retired and files.vault_transition is None
    assert foreign.read_bytes() == b'outside remains intact'
    monkeypatch.setattr(vault, '_decrypt_stream', real_stream)
    monkeypatch.setattr(vault, '_witnessed_file', real_witness)
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert post(exact, geometry_preconditions={'0':pc}, box_overrides={'0':[3,4,10,11]}).status_code != 200
    assert files.source_retired and files.current_source is None and files.vault_transition is None


def test_decrypt_length_mismatch_retires_even_with_matching_cipher_and_nonce(exact, monkeypatch):
    import openscrub_vault as vault
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    assert request('post', '/api/vault/lock').status_code == 200
    marker = files.vault_transition
    expected_stamp, expected_nonce = marker['cipher'], marker['nonce']
    original = vault._decrypt_stream
    measured = []
    def short_count(aes, src, dst, path, witnessed=False):
        actual_stamp = vault._regular_stamp(os.fstat(src.fileno()))
        nonce, count = original(aes, src, dst, path, witnessed=witnessed)
        if path == exact.job['video'] + vault.SUFFIX:
            measured.append((actual_stamp, nonce, count))
            return nonce, count - 1
        return nonce, count
    monkeypatch.setattr(vault, '_decrypt_stream', short_count)
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 500
    assert measured == [(expected_stamp, expected_nonce, marker['old_stamp'][2])]
    assert files.source_retired and files.current_source is None and files.vault_transition is None
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200


def test_route_remove_failure_after_publication_closes_and_retry_cannot_reuse(exact, monkeypatch):
    from pathlib import Path
    import openscrub_vault as vault
    exact.enable()
    pc = precondition(sample(exact))
    files = web.FILES.initialize(exact.job)
    source = Path(exact.job['video'])
    foreign = exact.root / 'foreign'
    foreign.write_bytes(b'outside remains intact')
    real_remove = vault.os.remove
    def fail_source(path):
        if str(path) == str(source):
            assert Path(str(source) + vault.SUFFIX).is_file()
            raise OSError('injected predecessor removal failure')
        return real_remove(path)
    monkeypatch.setattr(vault.os, 'remove', fail_source)
    assert request('post', '/api/vault/lock').status_code == 500
    assert source.exists() and Path(str(source) + vault.SUFFIX).exists()
    assert web.VAULT['closed'] and files.source_retired and files.vault_transition is None
    assert foreign.read_bytes() == b'outside remains intact'
    monkeypatch.setattr(vault.os, 'remove', real_remove)
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert post(exact, geometry_preconditions={'0':pc}, box_overrides={'0':[3,4,10,11]}).status_code != 200
    assert files.source_retired and files.current_source is None and files.vault_transition is None


def test_later_failure_leaves_unattempted_coherent_consumer_usable(exact, monkeypatch):
    import openscrub_vault as vault
    exact.enable()
    sample(exact)
    affected = web.FILES.initialize(exact.job)
    other, url = _second_source(exact)
    assert request('get', url + '/edit_sample?t=0.2').status_code == 200
    untouched = web.FILES.initialize(other)
    selected, stamp = untouched.current_source, untouched.current_source['stamp']
    real_walk, real_encrypt = vault._walk_files, vault.encrypt_file
    monkeypatch.setattr(vault, '_walk_files', lambda root: iter([exact.job['video'], str(exact.path), other['video']]))
    def fail_middle(key, path, *args):
        if path == str(exact.path):
            raise OSError('failure before unrelated source')
        return real_encrypt(key, path, *args)
    monkeypatch.setattr(vault, 'encrypt_file', fail_middle)
    assert request('post', '/api/vault/lock').status_code == 500
    assert web.VAULT['closed'] and affected.source_retired and affected.vault_transition is None
    assert untouched.current_source is selected and not untouched.source_retired
    assert selected['stamp'] == stamp == web._file_stamp(os.stat(other['video']))
    assert untouched.vault_transition is None
    monkeypatch.setattr(vault, '_walk_files', real_walk)
    monkeypatch.setattr(vault, 'encrypt_file', real_encrypt)
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert request('get', url + '/edit_sample?t=0.2').status_code == 200
    assert untouched.current_source is selected


def test_alias_job_video_preserves_strict_precondition(exact):
    from pathlib import Path
    exact.enable()
    source = Path(exact.job['video'])
    exact.job['video'] = str(source.parent / '..' / source.parent.name / source.name)
    pc = precondition(sample(exact))
    files = web.FILES.initialize(exact.job)
    selected = files.current_source
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert precondition(sample(exact)) == pc and files.current_source is selected
    assert post(exact, geometry_preconditions={'0':pc}, box_overrides={'0':[3,4,10,11]}).status_code == 200


def test_short_decrypted_writer_is_rejected_before_publication(exact, monkeypatch):
    from pathlib import Path
    import openscrub_vault as vault
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    assert request('post', '/api/vault/lock').status_code == 200
    marker = files.vault_transition
    expected = marker['cipher'], marker['nonce'], marker['old_stamp'][2]
    original = vault._decrypt_stream
    observed = []
    def shorten(aes, src, dst, path, witnessed=False):
        stamp = vault._regular_stamp(os.fstat(src.fileno()))
        nonce, count = original(aes, src, dst, path, witnessed=witnessed)
        if path == exact.job['video'] + vault.SUFFIX:
            observed.append((stamp, nonce, count))
            dst.flush()
            dst.truncate(count - 1)
        return nonce, count
    monkeypatch.setattr(vault, '_decrypt_stream', shorten)
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 500
    assert observed == [expected]
    assert not Path(exact.job['video']).exists()
    assert Path(exact.job['video'] + vault.SUFFIX).exists()
    assert web.VAULT['closed'] and files.source_retired and files.vault_transition is None


def test_observed_fifo_does_not_block_closed_store(exact):
    from pathlib import Path
    import pytest
    from test_job_lifecycle import start_call, finish
    if not hasattr(os, 'mkfifo'):
        pytest.skip('named pipes unavailable')
    exact.enable()
    sample(exact)
    files = web.FILES.initialize(exact.job)
    source = Path(exact.job['video'])
    source.unlink()
    os.mkfifo(source)
    call = start_call('post', '/api/vault/lock')
    thread, done, _, _ = call
    try:
        prompt = done.wait(1)
    finally:
        try:
            if not done.is_set():
                try:
                    fd = os.open(str(source), os.O_WRONLY | os.O_NONBLOCK)
                except OSError as error:
                    if error.errno != errno.ENXIO: raise
                else:
                    os.close(fd)
        finally:
            result = finish(call)
    assert prompt, 'vault waited for a FIFO writer'
    assert result.status_code == 500
    assert source.exists() and web.VAULT['closed']
    assert files.source_retired and files.vault_transition is None


def test_predecessor_reader_closed_before_unlink(tmp_path, monkeypatch):
    import openscrub_vault as vault
    source = tmp_path / 'video'
    source.write_bytes(b'bounded plaintext')
    original_stream, original_remove = vault._encrypt_stream, vault.os.remove
    readers, receipts = [], []
    def track(aes, src, dst, nonce):
        readers.append(src)
        return original_stream(aes, src, dst, nonce)
    def remove(path):
        if str(path) == str(source):
            assert readers and readers[0].closed, 'input reader still open at unlink'
        return original_remove(path)
    monkeypatch.setattr(vault, '_encrypt_stream', track)
    monkeypatch.setattr(vault.os, 'remove', remove)
    vault.encrypt_file(os.urandom(32), str(source), lambda *_: receipts.append)
    assert len(receipts) == 1 and not source.exists()


def test_interrupted_owner_preflight_does_not_mutate_multiple_sealed_owners(exact):
    exact.enable()
    sample(exact)
    other, url = _second_source(exact)
    assert request('get', url + '/edit_sample?t=0.2').status_code == 200
    first, second = web.FILES.initialize(exact.job), web.FILES.initialize(other)
    assert request('post', '/api/vault/lock').status_code == 200
    markers = first.vault_transition, second.vault_transition
    assert all(m and m['phase'] == 'sealed' for m in markers)
    old_status = first.source_status
    first.source_status = 'pending'
    real_lock = second.report_lock
    class FailingLock:
        def __enter__(self):
            raise OSError('injected discovery interruption')
        def __exit__(self, *args):
            return False
    second.report_lock = FailingLock()
    try:
        assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 500
    finally:
        second.report_lock = real_lock
        first.source_status = old_status
    assert (first.vault_transition, second.vault_transition) == markers
    assert web.VAULT['closed'] and web.VAULT['error'] is None
    assert not os.path.exists(exact.job['video']) and not os.path.exists(other['video'])
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code == 200
    assert request('get', url + '/edit_sample?t=0.2').status_code == 200


def test_selected_cipher_witness_detects_change_after_authenticated_eof(tmp_path, monkeypatch):
    import pytest
    import openscrub_vault as vault
    source = tmp_path / 'video'
    source.write_bytes(bytes(range(60)))
    key = os.urandom(32)
    vault.encrypt_file(key, str(source))
    cipher = str(source) + vault.SUFFIX
    stream = vault._decrypt_stream
    completed, receipts = [], []
    def mutate_at_eof(aes, src, dst, path, witnessed=False):
        nonce, count = stream(aes, src, dst, path, witnessed=witnessed)
        assert path == cipher and not src.closed and src.read(1) == b''
        info = os.stat(cipher)
        os.utime(cipher, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
        completed.append((nonce, count))
        return nonce, count
    monkeypatch.setattr(vault, '_decrypt_stream', mutate_at_eof)
    with pytest.raises(OSError, match='vault input changed during streaming'):
        vault.decrypt_file(key, cipher, lambda *_: receipts.append)
    assert completed and completed[0][1] == 60 and not receipts
    assert os.path.exists(cipher) and not source.exists()


def test_input_replaced_by_fifo_after_precheck_is_opened_nonblocking(tmp_path, monkeypatch):
    import pytest
    import openscrub_vault as vault
    if not hasattr(os, 'mkfifo') or not hasattr(os, 'O_NONBLOCK'):
        pytest.skip('nonblocking named pipes unavailable')
    source = tmp_path / 'source'
    source.write_bytes(b'plaintext')
    real_open = vault.os.open
    attempted = []
    def swap(path, flags, *args, **kwargs):
        if str(path) == str(source):
            attempted.append(flags)
            assert flags & os.O_NONBLOCK
            source.unlink()
            os.mkfifo(source)
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(vault.os, 'open', swap)
    receipts = []
    with pytest.raises(OSError):
        vault.encrypt_file(os.urandom(32), str(source), lambda *_: receipts.append)
    assert attempted and not receipts and source.exists()


def test_stage_fd_closed_if_initial_identity_check_fails(tmp_path, monkeypatch):
    import pytest
    import openscrub_vault as vault
    source = tmp_path / 'source'
    source.write_bytes(b'plaintext')
    real_mkstemp, real_fstat = vault.tempfile.mkstemp, vault.os.fstat
    stage = []
    def create(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        stage.append((fd, path))
        return fd, path
    def fail(fd):
        if stage and fd == stage[0][0]:
            raise OSError('injected stage identity failure')
        return real_fstat(fd)
    monkeypatch.setattr(vault.tempfile, 'mkstemp', create)
    monkeypatch.setattr(vault.os, 'fstat', fail)
    with pytest.raises(OSError, match='stage identity failure'):
        vault.encrypt_file(os.urandom(32), str(source), lambda *_: lambda receipt: None)
    monkeypatch.setattr(vault.os, 'fstat', real_fstat)
    with pytest.raises(OSError):
        real_fstat(stage[0][0])
    assert os.path.exists(stage[0][1]) and source.exists()


def test_substituted_stage_is_never_cleaned_as_owned(tmp_path, monkeypatch):
    import pytest
    import openscrub_vault as vault
    source = tmp_path / 'source'
    source.write_bytes(b'plaintext')
    original_stream, original_entry = vault._encrypt_stream, vault._entry_stamp
    writers, stage_checks, substituted = [], [], []
    def track(aes, src, dst, nonce):
        writers.append(dst)
        return original_stream(aes, src, dst, nonce)
    def swap_after_close(path):
        from pathlib import Path
        stage = Path(path)
        if stage.name.startswith('.vault-'):
            stage_checks.append(stage)
            if len(stage_checks) == 2:
                assert writers and writers[0].closed
                stage.replace(tmp_path / 'owned-stage')
                stage.write_bytes(b'foreign replacement')
                substituted.append(stage)
        return original_entry(path)
    monkeypatch.setattr(vault, '_encrypt_stream', track)
    monkeypatch.setattr(vault, '_entry_stamp', swap_after_close)
    with pytest.raises(OSError, match='stage changed'):
        vault.encrypt_file(os.urandom(32), str(source), lambda *_: lambda receipt: None)
    assert substituted[0].read_bytes() == b'foreign replacement' and source.exists()


@pytest.mark.parametrize('failing_mode', ['rb', 'wb'])
def test_wrapper_construction_failure_keeps_original_error_and_one_raw_close(tmp_path, monkeypatch, failing_mode):
    import openscrub_vault as vault
    real_fdopen, real_close, real_fstat = vault.os.fdopen, vault.os.close, vault.os.fstat
    class ConstructionFailure(RuntimeError):
        pass
    source = tmp_path / 'source'
    source.write_bytes(b'bounded plaintext')
    target, closes, receipts = [], [], []
    def fail_after_wrapping(fd, mode, *args, **kwargs):
        if mode == failing_mode:
            target.append(fd)
            wrapper = real_fdopen(fd, mode, *args, **kwargs)
            wrapper.close()  # Simulate cleanup after ownership was acquired.
            raise ConstructionFailure('synthetic wrapper construction failure')
        return real_fdopen(fd, mode, *args, **kwargs)
    def count_close(fd):
        if target and fd == target[0]:
            closes.append(fd)
        return real_close(fd)
    with monkeypatch.context() as patch:
        patch.setattr(vault.os, 'fdopen', fail_after_wrapping)
        patch.setattr(vault.os, 'close', count_close)
        with pytest.raises(ConstructionFailure, match='synthetic wrapper construction failure'):
            vault.encrypt_file(os.urandom(32), str(source), lambda *_: receipts.append)
    assert len(target) == 1 and closes == target
    with pytest.raises(OSError):
        real_fstat(target[0])
    assert source.exists() and not receipts


def test_wrapper_failure_does_not_close_an_unrelated_open_file(tmp_path, monkeypatch):
    import openscrub_vault as vault
    source = tmp_path / 'source'
    source.write_bytes(b'plaintext')
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(b'unrelated')
    real_fdopen, real_open, real_close = vault.os.fdopen, vault.os.open, vault.os.close
    reopened = []
    class ConstructionFailure(RuntimeError):
        pass
    def fail_after_wrapping(fd, mode, *args, **kwargs):
        if mode == 'rb':
            wrapper = real_fdopen(fd, mode, *args, **kwargs)
            wrapper.close()
            reopened.append(real_open(str(foreign), os.O_RDONLY))
            raise ConstructionFailure('after wrapping')
        return real_fdopen(fd, mode, *args, **kwargs)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(vault.os, 'fdopen', fail_after_wrapping)
            with pytest.raises(ConstructionFailure, match='after wrapping'):
                vault.encrypt_file(os.urandom(32), str(source), lambda *_: lambda receipt: None)
        assert len(reopened) == 1 and os.read(reopened[0], 9) == b'unrelated'
    finally:
        if reopened:
            try:
                real_close(reopened[0])
            except OSError:
                pass


@pytest.mark.parametrize('lock_path', ['manual', 'nonblocking'])
def test_vault_stays_busy_until_operation_cleanup_finishes(exact, lock_path):
    import threading
    import time
    from pathlib import Path
    key = exact.enable()
    pc = precondition(sample(exact))
    files = web.FILES.initialize(exact.job)
    selected, epoch = files.current_source, files.source_epoch
    source = Path(exact.job['video'])
    before = source.read_bytes()
    stamp = selected['stamp']
    report = exact.path.read_bytes()
    owner = web._prepare_work(exact.job, 'scan')
    with files.report_lock:
        web._begin_operation(exact.job, owner)
    exact.job['phase'] = 'review'
    real_lock = files.report_lock
    entered, resume = threading.Event(), threading.Event()
    errors, admission_report_locks = [], []
    class FinishGate:
        def __enter__(self):
            if threading.current_thread() is worker:
                entered.set()
                assert resume.wait(8)
                return real_lock.__enter__()
            admission_report_locks.append(True)
            return real_lock.__enter__()
        def __exit__(self, *args):
            return real_lock.__exit__(*args)
    def finish():
        try:
            web._finish_operation(exact.job, owner)
        except BaseException as error:
            errors.append(error)
    worker = threading.Thread(target=finish, name='held-operation-finish')
    files.report_lock = FinishGate()
    worker.start()
    try:
        assert entered.wait(5)
        assert web.FILES.count == 0 and files.active is owner
        assert owner.released and exact.job['phase'] == 'review'
        if lock_path == 'manual':
            assert request('post', '/api/vault/lock').status_code == 409
            assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 409
        else:
            start = time.monotonic()
            with pytest.raises(web.FilesBusy):
                web._vault_lock_now(blocking=False)
            assert time.monotonic() - start < 2
        assert not admission_report_locks
        assert source.read_bytes() == before and exact.path.read_bytes() == report
        assert web.VAULT['key'] == key and not web.vault_locked()
        assert files.current_source is selected and selected['stamp'] == stamp
        assert files.source_epoch == epoch and files.vault_transition is None
    finally:
        resume.set()
        worker.join(8)
        files.report_lock = real_lock
        assert not worker.is_alive() and not errors
    assert files.active is None and web.FILES.count == 0
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('post', '/api/vault/unlock', json={'password':'synthetic-password'}).status_code == 200
    assert files.current_source is selected and files.source_epoch == epoch
    assert precondition(sample(exact)) == pc
    assert post(exact, geometry_preconditions={'0':pc}, box_overrides={'0':[3,4,10,11]}).status_code == 200
    assert raw(exact)['detections'][0]['cbox'] == [3,4,10,11]


def test_vault_busy_check_does_not_create_missing_owner(store):
    orphan = {'phase': 'review'}
    with web.JOBS_LOCK:
        web.JOBS['uninitialized-test-job'] = orphan
    try:
        with web.VAULT_LOCK:
            assert not web._files_busy_locked()
        assert '_files' not in orphan
    finally:
        with web.JOBS_LOCK:
            del web.JOBS['uninitialized-test-job']
