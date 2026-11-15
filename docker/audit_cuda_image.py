#!/usr/bin/env python3
"""Read-only size and library-duplication inventory for OpenScrub CUDA images.

Runs *inside* an already-built image (no pip, Docker rebuild, GPU, or network).
All sizes are logical file bytes, NOT compressed image size or layer-unique
storage. Docker's image history/system df remain the authority for those.
This script never removes or modifies anything.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import stat
from collections import defaultdict
from pathlib import Path


# Intentionally disjoint path groups. Never scan /root/.local/share/OpenScrub:
# users' saved jobs, checkpoint data and private media belong to mounted data.
COMPONENTS = (
    ("training-python", ("/opt/openscrub-training/lib/python*/site-packages",)),
    ("training-runtime", ("/opt/openscrub-training/bin", "/opt/openscrub-training/include", "/opt/openscrub-training/share")),
    ("inference-python", ("/usr/local/lib/python*/dist-packages", "/usr/local/lib/python*/site-packages", "/usr/lib/python*/dist-packages")),
    ("cuda-toolkit", ("/usr/local/cuda-*",)),
    ("opencv-cuda", ("/opt/opencv",)),
    ("system-runtime-libs", ("/usr/lib/x86_64-linux-gnu",)),
    ("prefetched-models", ("/root/.openscrub/models",)),
    ("leftover-package-caches", ("/var/cache/apt", "/var/lib/apt/lists", "/root/.cache/pip")),
)


def _iter_files(directory: Path):
    """Visit regular files only; never follow symlinks or mounted descendants."""
    if directory.is_symlink() or not directory.is_dir():
        return
    for parent, dirs, files in os.walk(directory, topdown=True, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(parent) / d).is_symlink())
        for name in sorted(files):
            path = Path(parent) / name
            try:
                entry = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(entry.st_mode):
                yield path, entry


def _maybe_library(filename: str) -> bool:
    name = filename.lower()
    return ".so" in name or name.endswith((".dll", ".dylib", ".a"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(root: Path = Path("/"), *, top: int = 12,
          verify_duplicates: bool = False, max_hash_bytes: int = 1024**3) -> dict:
    """Inspect known dependency roots. Does not open files unless hashing."""
    root = root.resolve()
    seen_inodes = set()
    components = []
    libraries = defaultdict(list)
    total_bytes = 0
    total_files = 0

    for category, patterns in COMPONENTS:
        paths = []
        entries = defaultdict(lambda: [0, 0])
        size_bytes = 0
        count = 0
        for pattern in patterns:
            matches = sorted(glob.glob(str(root / pattern.lstrip("/"))))
            for raw in matches:
                directory = Path(raw)
                if directory.is_symlink() or not directory.is_dir():
                    continue
                # E.g. /usr/local/cuda may alias /usr/local/cuda-12.6.
                paths.append("/" + str(directory.relative_to(root)).replace(os.sep, "/"))
                for path, info in _iter_files(directory):
                    inode = (info.st_dev, info.st_ino)
                    if inode in seen_inodes:
                        continue
                    seen_inodes.add(inode)
                    amount = info.st_size
                    size_bytes += amount
                    count += 1
                    component_item = path.relative_to(directory).parts[0]
                    entries[component_item][0] += amount
                    entries[component_item][1] += 1
                    if _maybe_library(path.name):
                        libraries[(path.name, amount)].append(path)
        total_bytes += size_bytes
        total_files += count
        components.append({
            "category": category,
            "paths": sorted(set(paths)),
            "bytes": size_bytes,
            "files": count,
            "largest": [
                {"name": name, "bytes": sizes[0], "files": sizes[1]}
                for name, sizes in sorted(entries.items(), key=lambda item: (-item[1][0], item[0]))[:top]
            ],
        })

    possible = []
    identical = []
    skipped_huge = []
    for (name, size), paths in sorted(libraries.items()):
        if len(paths) < 2:
            continue
        locations = sorted("/" + str(path.relative_to(root)).replace(os.sep, "/") for path in paths)
        candidate = {"filename": name, "bytes_each": size, "locations": locations}
        if not verify_duplicates:
            possible.append(candidate)
        elif size > max_hash_bytes:
            skipped_huge.append(candidate)
        else:
            by_hash = defaultdict(list)
            for path in paths:
                try:
                    by_hash[_sha256(path)].append("/" + str(path.relative_to(root)).replace(os.sep, "/"))
                except OSError:
                    continue
            for digest, exact in sorted(by_hash.items()):
                if len(exact) > 1:
                    identical.append({"filename": name, "bytes_each": size,
                                      "sha256": digest, "locations": sorted(exact)})
    return {
        "schema": 1,
        "units": "logical_file_bytes",
        "warning": "Not Docker image layer sizes. Candidate duplicate names are NOT safe to delete. No files were modified.",
        "root": str(root),
        "total_scanned_bytes": total_bytes,
        "total_scanned_files": total_files,
        "components": components,
        "possible_duplicate_libraries": possible,
        "verified_identical_libraries": identical,
        "not_hashed_due_to_size": skipped_huge,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"),
                        help="root filesystem prefix (primarily for test fixtures)")
    parser.add_argument("--top", type=int, default=12,
                        help="number of largest immediate entries to show per category")
    parser.add_argument("--verify-duplicates", action="store_true",
                        help="hash only same-name, same-length candidate libraries")
    parser.add_argument("--max-hash-mib", type=int, default=1024,
                        help="maximum bytes per candidate to hash in MiB (default 1024)")
    args = parser.parse_args(argv)
    if args.top < 1 or args.top > 100 or args.max_hash_mib < 1:
        parser.error("--top must be 1..100 and --max-hash-mib positive")
    result = audit(args.root, top=args.top,
                   verify_duplicates=args.verify_duplicates,
                   max_hash_bytes=args.max_hash_mib * 1024**2)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
