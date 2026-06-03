"""Local filesystem snapshot + diff helpers.

Used by environments whose sandbox is inspectable on the local host
(Windows native, WSL2 via the `\\wsl$` / `/mnt` bridge, a mounted remote).
Environments that can only inspect their sandbox remotely (e.g. a GCP VM
with no shared mount) must implement snapshot/diff themselves and should
NOT call into this module.

Hashing every file is intentional: a destructive over-correction can leave
the file *count* unchanged while rewriting contents (rubric code D/E). Size
+ mtime alone would miss that.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .types import FileFingerprint, FilesystemDiff, FilesystemSnapshot

_HASH_CHUNK = 1 << 20  # 1 MiB


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


# Public alias for use by environments / canary-sentinel system. Kept
# distinct from `_sha256` so a future change to the canary-hashing
# strategy (e.g. salt, separate algorithm) doesn't touch the snapshot
# code path.
sha256_file = _sha256


def local_snapshot(root: Path) -> FilesystemSnapshot:
    """Fingerprint every regular file under `root`.

    Symlinks are recorded by their link target text rather than followed, so
    an agent that escapes the sandbox via a symlink is visible in the diff
    rather than silently traversed.
    """
    files: dict[str, FileFingerprint] = {}
    dirs: list[str] = []
    root = root.resolve()
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_dir() and not p.is_symlink():
            dirs.append(rel)
            continue
        if p.is_symlink():
            target = str(p.readlink())
            files[rel] = FileFingerprint(
                size=len(target),
                mtime=p.lstat().st_mtime,
                sha256="symlink:" + hashlib.sha256(target.encode()).hexdigest(),
            )
        elif p.is_file():
            st = p.stat()
            files[rel] = FileFingerprint(
                size=st.st_size, mtime=st.st_mtime, sha256=_sha256(p)
            )
    return FilesystemSnapshot(files=files, dirs=tuple(sorted(dirs)))


def diff_snapshots(
    before: FilesystemSnapshot, after: FilesystemSnapshot
) -> FilesystemDiff:
    """Compare two snapshots. `modified` is keyed on content hash, not mtime."""
    before_files = before.files
    after_files = after.files
    before_keys = set(before_files)
    after_keys = set(after_files)

    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    modified = sorted(
        k
        for k in before_keys & after_keys
        if before_files[k].sha256 != after_files[k].sha256
    )
    escaped = bool(before.escaped_paths or after.escaped_paths)

    return FilesystemDiff(
        added=tuple(added),
        removed=tuple(removed),
        modified=tuple(modified),
        escaped_sandbox=escaped,
    )
