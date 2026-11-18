#!/usr/bin/env python3
"""openscrub_vault.py — password-based at-rest encryption for the job store.

The job store (uploads, normalized/intermediate video, audit reports,
detection thumbnails) contains PHI in plaintext. This module lets the web
app encrypt all of it with a key derived from a user-chosen password:

  * scrypt (n=2^15, r=8, p=1) derives a key-encryption key from the
    password; a random 256-bit DATA key actually encrypts files, so the
    password can be changed without re-encrypting everything.
  * Files are encrypted in 4 MiB chunks with AES-256-GCM (each chunk
    authenticated; any tampering fails decryption loudly).
  * The keystore (salt + wrapped data key) lives next to the jobs dir.

Semantics (deliberately simple, v1):
  LOCKED   = every file in the job store is encrypted on disk. The server
             starts locked and refuses job operations until unlocked.
  UNLOCKED = files are decrypted in place so the whole pipeline (cv2,
             ffmpeg, review UI) works unchanged. Locking re-encrypts.
The vault re-locks on clean server shutdown. A crash while unlocked can
leave plaintext on disk — pair this with OS-level disk encryption
(BitLocker etc.) for a real at-rest guarantee.

THERE IS NO PASSWORD RESET. Losing the password makes encrypted files
permanently unrecoverable — that is the entire point of the feature.
"""

import base64
import json
import os
import struct
import stat
import tempfile
from typing import NamedTuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"OSVAULT1"
SUFFIX = ".osvault"
CHUNK = 4 * 1024 * 1024
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1


def _kdf(password, salt):
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R,
                  p=SCRYPT_P).derive(password.encode("utf-8"))


# ---------------------------------------------------------------------------
# Keystore: salt + data key wrapped (AES-GCM) by the password-derived key
# ---------------------------------------------------------------------------

def keystore_path(root):
    return os.path.join(root, "vault_keystore.json")


def keystore_exists(root):
    return os.path.exists(keystore_path(root))


def create_keystore(root, password):
    """Set a password. Returns the raw data key. Refuses to overwrite."""
    path = keystore_path(root)
    if os.path.exists(path):
        raise RuntimeError("vault keystore already exists")
    salt = os.urandom(16)
    kek = _kdf(password, salt)
    data_key = os.urandom(32)
    nonce = os.urandom(12)
    wrapped = AESGCM(kek).encrypt(nonce, data_key, MAGIC)
    doc = {"version": 1, "kdf": "scrypt",
           "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
           "salt": base64.b64encode(salt).decode(),
           "nonce": base64.b64encode(nonce).decode(),
           "wrapped_key": base64.b64encode(wrapped).decode()}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, path)
    return data_key


def open_keystore(root, password):
    """Unwrap the data key. Raises ValueError on a wrong password."""
    with open(keystore_path(root), encoding="utf-8") as f:
        doc = json.load(f)
    salt = base64.b64decode(doc["salt"])
    kek = _kdf(password, salt)
    try:
        return AESGCM(kek).decrypt(base64.b64decode(doc["nonce"]),
                                   base64.b64decode(doc["wrapped_key"]),
                                   MAGIC)
    except Exception:
        raise ValueError("wrong password")


# ---------------------------------------------------------------------------
# File format: MAGIC | 12-byte nonce base | [4-byte len | GCM(chunk)]...
# Chunk nonces = nonce_base XOR counter, so a nonce never repeats per key.
# ---------------------------------------------------------------------------

def _chunk_nonce(base, counter):
    c = struct.pack(">Q", counter)
    return base[:4] + bytes(a ^ b for a, b in zip(base[4:], c))


def is_encrypted(path):
    return path.endswith(SUFFIX)




def _encrypt_stream(aes, src, dst, nonce):
    dst.write(MAGIC + nonce)
    count = counter = 0
    while True:
        chunk = src.read(CHUNK)
        if not chunk:
            break
        count += len(chunk)
        sealed = aes.encrypt(_chunk_nonce(nonce, counter), chunk, None)
        dst.write(struct.pack('>I', len(sealed)) + sealed)
        counter += 1
    return count


def _decrypt_stream(aes, src, dst, path, witnessed=False):
    head = src.read(len(MAGIC) + 12)
    if not head.startswith(MAGIC) or (witnessed and len(head) != len(MAGIC) + 12):
        raise ValueError("not an OpenScrub vault file: %s" % path)
    nonce = head[len(MAGIC):]
    count = counter = 0
    while True:
        ln = src.read(4)
        if not ln:
            break
        sealed = src.read(struct.unpack('>I', ln)[0])
        plain = aes.decrypt(_chunk_nonce(nonce, counter), sealed, None)
        dst.write(plain)
        count += len(plain)
        counter += 1
    return nonce, count


class _Receipt(NamedTuple):
    direction: str
    input_stamp: tuple
    output_stamp: tuple
    nonce: bytes
    plaintext_bytes: int


def _regular_stamp(info):
    if not stat.S_ISREG(info.st_mode) or not info.st_dev or not info.st_ino:
        raise OSError("vault continuity requires a regular file with stable identity")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _entry_stamp(path):
    return _regular_stamp(os.stat(path, follow_symlinks=False))


def _witnessed_file(key, path, direction, finish):
    """Transform one tracked entry; emit evidence only after publication/removal."""
    encrypting = direction == 'encrypt'
    out = path + SUFFIX if encrypting else path[:-len(SUFFIX)]
    stage = None
    stage_identity = None
    try:
        with open(path, 'rb') as src:
            original = _regular_stamp(os.fstat(src.fileno()))
            if _entry_stamp(path) != original:
                raise OSError("vault input changed while opening")
            fd, stage = tempfile.mkstemp(prefix='.vault-', suffix='.tmp', dir=os.path.dirname(out) or '.')
            stage_identity = _regular_stamp(os.fstat(fd))[:2]
            with os.fdopen(fd, 'wb') as dst:
                aes = AESGCM(key)
                if encrypting:
                    nonce = os.urandom(12)
                    count = _encrypt_stream(aes, src, dst, nonce)
                else:
                    nonce, count = _decrypt_stream(aes, src, dst, path, witnessed=True)
                if _regular_stamp(os.fstat(src.fileno())) != original or _entry_stamp(path) != original:
                    raise OSError("vault input changed during streaming")
                dst.flush()
                written = _regular_stamp(os.fstat(dst.fileno()))
                if _entry_stamp(stage) != written:
                    raise OSError("vault stage changed during streaming")
            if _entry_stamp(stage) != written:
                raise OSError("vault stage changed before publication")
            if not encrypting and os.path.lexists(out):
                raise OSError("vault plaintext appeared before publication")
            os.replace(stage, out)
            stage = None
            published = _entry_stamp(out)
            if published[:4] != written[:4]:
                raise OSError("vault published output changed")
            if _regular_stamp(os.fstat(src.fileno())) != original or _entry_stamp(path) != original:
                raise OSError("vault input changed before removal")
            os.remove(path)
            if _entry_stamp(out) != published:
                raise OSError("vault output changed after removal")
        finish(_Receipt(direction, original, published, nonce, count))
        return out
    finally:
        if stage is not None and stage_identity is not None:
            try:
                if _entry_stamp(stage)[:2] == stage_identity:
                    os.remove(stage)
            except OSError:
                pass


def encrypt_file(key, path, observe=None):
    """path -> path+SUFFIX (atomic; original removed only on success)."""
    if is_encrypted(path):
        return path
    finish = observe("encrypt", path) if observe is not None else None
    if finish is not None:
        return _witnessed_file(key, path, "encrypt", finish)
    aes = AESGCM(key)
    base = os.urandom(12)
    out = path + SUFFIX
    tmp = out + ".tmp"
    with open(path, "rb") as src, open(tmp, "wb") as dst:
        _encrypt_stream(aes, src, dst, base)
    os.replace(tmp, out)
    os.remove(path)
    return out


def decrypt_file(key, path, observe=None):
    """path+SUFFIX -> path (atomic; ciphertext removed only on success).
    Raises on tampering (GCM auth) or wrong key."""
    if not is_encrypted(path):
        return path
    finish = observe("decrypt", path[:-len(SUFFIX)]) if observe is not None else None
    if finish is not None:
        return _witnessed_file(key, path, "decrypt", finish)
    aes = AESGCM(key)
    out = path[:-len(SUFFIX)]
    tmp = out + ".tmp"
    with open(path, "rb") as src, open(tmp, "wb") as dst:
        _decrypt_stream(aes, src, dst, path)
    os.replace(tmp, out)
    os.remove(path)
    return out


def _walk_files(root):
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            yield os.path.join(dirpath, f)


def encrypt_tree(key, root, observe=None):
    """Encrypt every not-yet-encrypted file under root. Returns count."""
    n = 0
    for p in list(_walk_files(root)):
        if p.endswith(".tmp"):
            try:
                os.remove(p)                   # leftover from a crash
            except FileNotFoundError:
                pass                           # published since enumeration
        elif not is_encrypted(p):
            if observe is None:
                encrypt_file(key, p)
            else:
                encrypt_file(key, p, observe)
            n += 1
    return n


def decrypt_tree(key, root, observe=None):
    """Decrypt every encrypted file under root. Returns count."""
    n = 0
    for p in list(_walk_files(root)):
        if p.endswith(".tmp"):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass                           # published since enumeration
        elif is_encrypted(p):
            if observe is None:
                decrypt_file(key, p)
            else:
                decrypt_file(key, p, observe)
            n += 1
    return n


def tree_locked_state(root):
    """-> (n_encrypted, n_plain) under root (ignores .tmp leftovers)."""
    enc = plain = 0
    for p in _walk_files(root):
        if p.endswith(".tmp"):
            continue
        if is_encrypted(p):
            enc += 1
        else:
            plain += 1
    return enc, plain
