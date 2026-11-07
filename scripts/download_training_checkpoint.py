#!/usr/bin/env python3
"""Opt-in download of the fixed official segmentation checkpoint, verified by SHA256.

Run only after reviewing Ultralytics' AGPL/Enterprise terms. This is not a
runtime dependency and does not activate a model or upload user data.
"""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import urlopen

URL = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-seg.pt'
SHA256 = '55ed65c56c91713d23e8402371c6c49a6fd84f257f7dce452e8d70e41dcbe152'


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def download(destination):
    destination = Path(destination).expanduser()
    if destination.exists():
        if digest(destination) != SHA256:
            raise ValueError('Existing checkpoint differs from the pinned official file; it was NOT replaced')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as out:
            temporary = Path(out.name)
            with urlopen(URL, timeout=60) as response:
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 32 * 1024 * 1024:
                        raise ValueError('Checkpoint exceeded expected size limit')
                    out.write(chunk)
        if digest(temporary) != SHA256:
            raise ValueError('Checkpoint SHA256 verification failed; file not installed')
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path,
        default=Path('/root/.local/share/OpenScrub/training/yolo11n-seg.pt'))
    parser.add_argument('--accept-ultralytics-license', action='store_true')
    args = parser.parse_args()
    if not args.accept_ultralytics_license:
        parser.error('Review https://www.ultralytics.com/license, then acknowledge with --accept-ultralytics-license')
    try:
        print('Verified local checkpoint:', download(args.destination))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
