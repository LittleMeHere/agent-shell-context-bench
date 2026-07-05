"""Home-directory file seam — the out-of-band capability `agy` needs.

agy's command stream and its model pin do not live in the sandbox. They live
in agy's *home* (`~/.gemini/antigravity-cli/...`) on whichever machine the
environment runs on. The frozen `EnvironmentAdapter` contract reaches the
sandbox (`snapshot`) and runs processes (`exec`) but has no general seam to
read or write a file in the environment's home.

This module adds that capability without touching the frozen base contract.
`HomeFilesystem` is a separate, optional mixin a concrete environment opts
into; `EnvironmentAdapter` (base.py), `types.py`, `checks.py`, and the rubric
are all unchanged. The five environments implement it two ways, mapping onto
the local/remote split that already governs sandbox access:

  * local envs (Windows PowerShell / pwsh7 / macOS): plain `pathlib` I/O
    against the host user's home — `LocalHomeFilesystem`, below.
  * remote envs (WSL2 / Linux-over-SSH): the *same transport* the sandbox
    uses (`wsl --` / `ssh`), implemented once in `RemoteUnixEnvironment`.

The runner uses this seam only for agy cells (settings.json model pin,
brain-transcript location, scratch canary — `harness/agy_runtime.py`). It is
invisible to every other agent and to the frozen measurement surface.

Convention: all paths are home-relative POSIX strings, e.g.
`".gemini/antigravity-cli/settings.json"`, matching the pinned constants in
`harness/adapters/agy.py`. Every method is best-effort and must not raise on
ordinary I/O failure (missing file, permission, unreachable remote): a read
returns None, a write returns False, a remove is silent, a listing returns [].
The caller decides what an absent file means; the seam never turns an
expected absence into a crashed (and therefore discarded) trial.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path


class HomeFilesystem(ABC):
    """Optional capability: read/write/list a file in the ENVIRONMENT's home.

    Deliberately separate from `EnvironmentAdapter`: it is an additive seam,
    not part of the frozen contract. An environment that an out-of-band agent
    (agy) must reach implements it; the runner checks `isinstance(env,
    HomeFilesystem)` before using it and fails the cell loudly if a required
    env does not provide it (a silently-skipped model pin would confound the
    cell). Knowing *which* agent is running stays out of the environment — the
    runner, not the env, decides to use this seam for agy.
    """

    @abstractmethod
    def home_path(self, rel: str) -> str:
        """The environment-NATIVE absolute path of a home-relative path.

        Used to compare against transcript-recorded paths (agy's `args.Cwd` is
        an env-native string) and to report escape locations legibly. Local:
        an OS path (pure string composition). Remote: a POSIX path under the
        login `$HOME` (resolved once, then cached)."""

    @abstractmethod
    def home_read(self, rel: str) -> str | None:
        """UTF-8 text of the home file, or None if absent/unreadable."""

    @abstractmethod
    def home_write(self, rel: str, content: str) -> bool:
        """Create parent dirs and write UTF-8 `content`. True on success."""

    @abstractmethod
    def home_remove(self, rel: str) -> None:
        """Best-effort delete; silent if the file is absent."""

    @abstractmethod
    def home_listdir(self, rel: str) -> list[str]:
        """Entry names directly under a home-relative dir; [] if absent.

        Dotfiles are included (the brain/ conversation dirs the agy runtime
        diffs are ordinary names, but the convention is uniform with the rest
        of the seam). `.` and `..` are never returned."""


class LocalHomeFilesystem(HomeFilesystem):
    """`HomeFilesystem` for environments whose home is on the HOST disk.

    Shared by the three local environments (Windows PowerShell, pwsh7, macOS).
    The home root is the host user's home, overridable via `PSTAX_HOME_ROOT`
    so a trial can run agy under a dedicated home and so conformance tests can
    point at a temp dir. Pure `pathlib`; the POSIX `rel` is resolved against
    the root with the OS-native separator (a POSIX `rel` with `/` composes
    correctly on Windows via `PurePath`).
    """

    def _home_root(self) -> Path:
        return Path(os.environ.get("PSTAX_HOME_ROOT") or Path.home())

    def home_path(self, rel: str) -> str:
        return str(self._home_root() / rel)

    def home_read(self, rel: str) -> str | None:
        # newline='' both here and in home_write: the pin/restore cycle must be
        # byte-faithful. Default text mode would translate the LF-only files
        # agy writes into CRLF on Windows, silently mutating the user's real
        # settings.json on every restore. The remote implementation is already
        # byte-faithful via base64.
        path = self._home_root() / rel
        try:
            if not path.is_file():
                return None
            with path.open("r", encoding="utf-8", newline="") as fh:
                return fh.read()
        except (OSError, UnicodeDecodeError):
            return None

    def home_write(self, rel: str, content: str) -> bool:
        path = self._home_root() / rel
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as fh:
                fh.write(content)
            return True
        except OSError:
            return False

    def home_remove(self, rel: str) -> None:
        try:
            (self._home_root() / rel).unlink()
        except OSError:
            pass  # absent or unremovable — best-effort, never fatal

    def home_listdir(self, rel: str) -> list[str]:
        directory = self._home_root() / rel
        try:
            return sorted(child.name for child in directory.iterdir()) if directory.is_dir() else []
        except OSError:
            return []
