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
import errno
import os
import stat
from pathlib import Path

from .types import FileFingerprint, FilesystemDiff, FilesystemSnapshot

_HASH_CHUNK = 1 << 20  # 1 MiB


class SandboxUnreadableError(OSError):
    """A path inside a previously readable trial sandbox became unreadable.

    The runner only treats this as agent-induced measurement loss when the
    clean pre-invocation snapshot succeeded and this error is raised by the
    post-invocation snapshot.  Snapshot-wide transport or adapter failures
    remain ordinary infrastructure exceptions.
    """

    def __init__(self, path: Path, operation: str, cause: OSError) -> None:
        self.path = path
        self.operation = operation
        self.cause = cause
        self.cause_type = type(cause).__name__
        self.cause_errno = cause.errno
        self.cause_winerror = getattr(cause, "winerror", None)
        super().__init__(
            f"sandbox path became unreadable during {operation}: "
            f"{path} ({self.cause_type}: {cause})"
        )

    @property
    def evidence(self) -> str:
        return f"{self.path} [{self.operation}:{self.cause_type}]"

    @property
    def agent_attributable(self) -> bool:
        """Whether the failure shape can result from sandbox mutation.

        Transport, media, and generic I/O errors are infrastructure failures.
        Missing paths, changed path types, access changes, and live file locks
        are the mutation-shaped cases a sandboxed agent can cause between the
        successful baseline and post-invocation snapshots.
        """

        return (
            isinstance(
                self.cause,
                (
                    FileNotFoundError,
                    NotADirectoryError,
                    IsADirectoryError,
                    PermissionError,
                ),
            )
            or self.cause_errno
            in {
                errno.ENOENT,
                errno.ENOTDIR,
                errno.EISDIR,
                errno.EACCES,
                errno.EPERM,
            }
            or self.cause_winerror in {2, 3, 5, 32, 33}
        )


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
    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise SandboxUnreadableError(
                directory, "enumerate", exc
            ) from exc
        for entry in entries:
            p = Path(entry.path)
            rel = p.relative_to(root).as_posix()
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode):
                    target = os.readlink(p)
                    files[rel] = FileFingerprint(
                        size=len(target),
                        mtime=entry.stat(follow_symlinks=False).st_mtime,
                        sha256="symlink:"
                        + hashlib.sha256(target.encode()).hexdigest(),
                    )
                elif stat.S_ISDIR(mode):
                    dirs.append(rel)
                    visit(p)
                elif stat.S_ISREG(mode):
                    st = entry.stat(follow_symlinks=False)
                    files[rel] = FileFingerprint(
                        size=st.st_size,
                        mtime=st.st_mtime,
                        sha256=_sha256(p),
                    )
            except OSError as exc:
                raise SandboxUnreadableError(
                    p, "fingerprint", exc
                ) from exc

    visit(root)
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
        measurement_incomplete=bool(
            before.measurement_errors or after.measurement_errors
        ),
    )
