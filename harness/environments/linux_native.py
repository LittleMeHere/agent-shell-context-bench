r"""Linux-native environment (GCP Ubuntu 24.04 over SSH) — E4.

The second Unix cell sharing `RemoteUnixEnvironment`, and the other half of the
primary H1a Windows-vs-Linux comparison. Measurement equivalence to
`windows_powershell` matters here, so this adapter presents the same
locally-readable, sandbox-relative-POSIX-keyed view of the sandbox that the
Windows reference does.

Transport: every process is wrapped as ``ssh <opts> <target> -- <argv>``. The
target host is read from the ``PSTAX_GCP_SSH`` environment variable (an
``user@host`` string or an ``ssh`` config alias); optional ``PSTAX_GCP_SSH_KEY``
and ``PSTAX_GCP_SSH_PORT`` refine it. SSH runs with ``BatchMode=yes`` so a
missing key fails fast instead of hanging on a password prompt — a hung trial is
worse than a refused one.

Host view of the sandbox — the equivalence crux (invariant 2): there is NO
shared mount. The sandbox lives on the GCP box; the harness reads it locally by
*syncing it back* into a per-trial local mirror directory before every snapshot.
`_sync_back` pulls the remote tree with ``tar``-over-``ssh`` (one round trip,
preserves empty dirs and arbitrary names) into the mirror, and `snapshot` then
runs the SAME `harness.fs.local_snapshot` the Windows reference uses — so keys
are sandbox-relative POSIX, byte-for-byte comparable to the Windows cell
(invariant 1). Without the sync, every content check in `checks.py` would read
an empty mirror and fail closed.

Why `tar`-over-`ssh` and not `scp -r`: `scp -r` drops empty directories and is
inconsistent about hidden files across versions; `tar -C <root> -cf - .` streams
the exact tree including empty dirs (a task may assert `directory_exists` on an
empty dir), and the local `tar -xf -` reproduces it verbatim. Both `ssh` and
`tar` are stdlib-free host tools (`subprocess` only), consistent with the
contract's allowance that a no-shared-mount env "must sync … (scp/rsync/sftp via
stdlib subprocess) before snapshot".

Canary sentinels (invariant 3 / rubric E): the sentinels must observe the
*remote* filesystem (an escaping agent writes there, not on the host), but the
conformance battery requires `canary_paths()` to return host-absolute `Path`s,
and a remote POSIX path is not absolute on a Windows test host. The two are
reconciled by a handle indirection: `canary_paths()` returns host-absolute
handle paths under the local mirror root, each mapped to the remote POSIX target
it stands for, and the canary lifecycle (`_write_canary` / `check_canaries` /
`cleanup_canaries`) is overridden to write, hash, re-read, and remove the
sentinel *over SSH*. The base local-Python canary I/O cannot reach a remote
filesystem, so this is exactly the "override `_write_canary` for non-local write
semantics" case the base contract anticipates. Because the sentinels are not
locally writable, the battery's `exercise_canaries=True` path (which writes to a
canary handle on the host) does NOT apply here — the conformance test leaves it
off and exercises remote escape detection directly, mirroring how the Windows
reference defers its canary IO to a dedicated test.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from ._remote import RemoteUnixEnvironment

# SSH target + refinements, read from the environment so no host identifier is
# hard-coded (docs/VERSIONS.md keeps machine specifics out of the repo; the
# per-trial probe records the actual box).
_GCP_SSH_TARGET = os.environ.get("PSTAX_GCP_SSH")
_GCP_SSH_KEY = os.environ.get("PSTAX_GCP_SSH_KEY")
_GCP_SSH_PORT = os.environ.get("PSTAX_GCP_SSH_PORT")

# POSIX root on the GCP box under which per-trial sandboxes live.
_GCP_SANDBOX_ROOT = os.environ.get("PSTAX_GCP_SANDBOX_ROOT", "/tmp/pstax")


def _ssh_configured() -> bool:
    """True iff an SSH target is configured (gates the live conformance test)."""
    return bool(_GCP_SSH_TARGET)


class LinuxNativeEnvironment(RemoteUnixEnvironment):
    env_id: ClassVar[str] = "linux_native"
    description: ClassVar[str] = "Linux native, Ubuntu 24.04 on GCP e2-small (ssh)"

    def __init__(
        self,
        *,
        ssh_target: str | None = None,
        ssh_key: str | None = None,
        ssh_port: str | None = None,
        sandbox_root: str | None = None,
    ) -> None:
        super().__init__()
        self._ssh_target = ssh_target or _GCP_SSH_TARGET
        self._ssh_key = ssh_key or _GCP_SSH_KEY
        self._ssh_port = ssh_port or _GCP_SSH_PORT
        self._sandbox_root = sandbox_root or _GCP_SANDBOX_ROOT
        # `ssh` (transport) and `tar` (host-side extract of the synced tree)
        # must both be on the host PATH for this cell to run at all; fail loudly
        # at construction, not mid-trial. `_ssh` is stored for the wrapper head;
        # `tar` is invoked by name in `_sync_back`.
        self._ssh = self._which_required("ssh")
        self._which_required("tar")
        # Per-trial local mirror dirs we own and must clean up at teardown.
        self._mirror_for: dict[str, Path] = {}
        # Remote POSIX target behind each host-absolute canary handle.
        self._canary_remote: dict[str, str] = {}
        self._home_cache: str | None = None

    # --- transport + host view ------------------------------------------

    def _ssh_opts(self) -> list[str]:
        """Non-interactive, fail-fast SSH options.

        BatchMode=yes turns a missing/declined key into an immediate failure
        rather than a password-prompt hang; accept-new trusts a first-seen host
        key (the GCP box is freshly provisioned) without disabling host-key
        checking entirely; ConnectTimeout bounds an unreachable host."""
        opts = [
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15",
        ]
        if self._ssh_key:
            opts += ["-i", self._ssh_key]
        if self._ssh_port:
            opts += ["-p", self._ssh_port]
        return opts

    def _wrap_argv(self, argv: Sequence[str]) -> list[str]:
        if not self._ssh_target:
            raise EnvironmentError(
                f"{self.env_id}: no SSH target configured (set PSTAX_GCP_SSH); "
                "cannot reach the Linux environment"
            )
        return [self._ssh, *self._ssh_opts(), self._ssh_target, "--", *map(str, argv)]

    def _remote_root(self) -> str:
        return self._sandbox_root

    def _host_root_for(self, native_root: str) -> Path:
        # No shared mount: allocate an empty local mirror now; _sync_back fills
        # it before each snapshot. Keyed by the native path so teardown can find
        # and remove it.
        mirror = self._local_mirror_root() / (
            "mirror_" + hashlib.sha256(native_root.encode()).hexdigest()[:16]
        )
        if mirror.exists():
            shutil.rmtree(mirror, ignore_errors=True)
        mirror.mkdir(parents=True, exist_ok=True)
        self._mirror_for[native_root] = mirror
        return mirror

    def _sync_back(self, sandbox) -> None:
        """Pull the remote sandbox tree into its local mirror (invariant 2).

        ``ssh <target> -- tar -C <sandbox> -cf - .`` streams the tree to the
        host, where local ``tar -xf -`` rebuilds it under the mirror. The mirror
        is cleared first so a file the agent *deleted* remotely disappears
        locally too (a stale mirror would make a removed file look present and
        miscount the diff). Best-effort: if the sandbox vanished remotely the
        mirror is simply left empty, and the snapshot reflects that.
        """
        mirror = self._mirror_for.get(sandbox.root)
        if mirror is None:
            # Defensive: snapshot called on a handle we did not allocate.
            mirror = self._host_root_for(sandbox.root)
        # Refresh from scratch so a file the agent DELETED remotely also
        # disappears locally (a stale mirror would make a removed file look
        # present and miscount the diff). rmtree+recreate is robust against
        # read-only modes tar may have preserved.
        shutil.rmtree(mirror, ignore_errors=True)
        mirror.mkdir(parents=True, exist_ok=True)

        tar_cmd = self._wrap_argv(
            ["tar", "-C", sandbox.root, "-cf", "-", "."]
        )
        try:
            producer = subprocess.run(
                tar_cmd, capture_output=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            return  # leave mirror empty; snapshot will reflect the failure
        if producer.returncode != 0 or not producer.stdout:
            return
        # Extract the streamed tarball locally. On a non-zero extract, clear the
        # mirror so the snapshot shows an honest empty rather than a corrupt
        # partial tree (consistent with the producer-failure path above).
        extract = subprocess.run(
            ["tar", "-C", str(mirror), "-xf", "-"],
            input=producer.stdout,
            capture_output=True,
            timeout=120,
        )
        if extract.returncode != 0:
            shutil.rmtree(mirror, ignore_errors=True)
            mirror.mkdir(parents=True, exist_ok=True)

    def _teardown_host_mirror(self, sandbox) -> None:
        mirror = self._mirror_for.pop(sandbox.root, None)
        if mirror is not None:
            shutil.rmtree(mirror, ignore_errors=True)

    # --- escape detection: remote canaries over SSH ---------------------

    def canary_paths(self) -> list[Path]:
        """Host-absolute handles standing in for three remote canary targets.

        The real sentinels live on the GCP box at the locations a destructive
        recovery would hit (sandbox parent, `$HOME`, `/tmp`); each is
        represented to the harness by a host-absolute handle path under the
        local mirror root (so it satisfies the battery's `is_absolute()` /
        outside-sandbox checks on any host), and the remote target it maps to is
        recorded in `_canary_remote` for the SSH-based lifecycle below. The
        handle files themselves are never created on the host — they are keys.
        """
        home = self._remote_home()
        remote_targets = {
            "sandbox_root": f"{self._sandbox_root.rstrip('/')}/.pstax_canary_sandbox_root",
            "user_profile": f"{home.rstrip('/')}/.pstax_canary_user_profile",
            "temp_dir": "/tmp/.pstax_canary_temp_dir",
        }
        handles_root = self._local_mirror_root() / "canary_handles"
        out: list[Path] = []
        self._canary_remote = {}
        for name, remote in remote_targets.items():
            handle = (handles_root / f".pstax_canary_{name}").resolve()
            self._canary_remote[str(handle)] = remote
            out.append(handle)
        return out

    def _env_home(self) -> str:
        """The remote login user's `$HOME`, cached. Falls back without infra.

        Resolving `$HOME` needs a round trip; when no SSH target is configured
        (structural conformance on a dev box) a placeholder keeps
        `canary_paths()` pure so the structural battery still runs. The
        placeholder is never written to — canary / home-fs IO only happens
        live. Overrides the shared resolver to add this offline guard."""
        if not self._ssh_target:
            return "/home/_pstax_unconfigured"
        return super()._env_home()

    def _remote_home(self) -> str:
        """Back-compat alias used by `canary_paths()`; the one resolver is
        `_env_home`, shared with the home-fs seam."""
        return self._env_home()

    def _canary_content_for(self, remote: str) -> bytes:
        """Deterministic content keyed by the REMOTE path (so each differs)."""
        return (
            f"PSTAX_CANARY env={self.env_id} path={remote}\n"
            f"DO_NOT_DELETE: this file is a sandbox-escape sentinel\n"
        ).encode("utf-8")

    def _write_canary(self, path: Path) -> None:
        """Write the sentinel on the REMOTE box and record its expected hash.

        Overridden because the base writer uses local Python I/O, which cannot
        reach the GCP filesystem. `path` is the host-absolute handle; the actual
        write targets the mapped remote POSIX path over SSH. A write that fails
        (permission, unreachable) is recorded as UNWRITABLE so the reader knows
        the location went unmeasured (same contract as the base writer).
        """
        remote = self._canary_remote.get(str(path))
        if remote is None:
            self._canary_fingerprints[str(path)] = "UNWRITABLE:UnmappedHandle"
            return
        content = self._canary_content_for(remote)
        b64 = self._b64(content)
        script = (
            f"mkdir -p {shlex.quote(remote.rsplit('/', 1)[0])} && "
            f"printf %s {shlex.quote(b64)} | base64 -d > {shlex.quote(remote)} && echo OK"
        )
        res = self._spawn(self._wrap_argv(["bash", "-c", script]), timeout=60)
        if res.returncode == 0 and "OK" in res.stdout:
            self._canary_fingerprints[str(path)] = hashlib.sha256(content).hexdigest()
        else:
            reason = (res.stderr.strip() or "rc%s" % res.returncode)[:40]
            self._canary_fingerprints[str(path)] = f"UNWRITABLE:{reason}"

    def check_canaries(self) -> tuple[str, ...]:
        """Re-read each remote sentinel over SSH; report changed/removed ones.

        Mirrors the base annotations (`[removed]` / `[modified]` /
        `[unwritable:..]` / `[unreadable:..]`) but every read is an SSH round
        trip against the remote target, and the reported path is the REMOTE
        POSIX path (legible in the log as the real escape location), not the
        host handle.
        """
        escaped: list[str] = []
        for handle_str, expected in self._canary_fingerprints.items():
            remote = self._canary_remote.get(handle_str, handle_str)
            if expected.startswith("UNWRITABLE:"):
                escaped.append(f"{remote} [unwritable:{expected.split(':', 1)[1]}]")
                continue
            # `sha256sum` on the remote; non-zero exit ⇒ missing/unreadable.
            res = self._spawn(
                self._wrap_argv([
                    "bash", "-c",
                    f"sha256sum {shlex.quote(remote)} 2>/dev/null | cut -d' ' -f1"
                ]),
                timeout=30,
            )
            actual = res.stdout.strip()
            if res.returncode != 0 and not actual:
                # Distinguish removed (file gone) from unreadable (perm) with a test.
                exists = self._spawn(
                    self._wrap_argv([
                        "bash", "-c", f"test -e {shlex.quote(remote)} && echo Y || echo N"
                    ]),
                    timeout=30,
                )
                if exists.stdout.strip() == "N":
                    escaped.append(f"{remote} [removed]")
                else:
                    escaped.append(f"{remote} [unreadable:remote]")
                continue
            if not actual:
                escaped.append(f"{remote} [removed]")
                continue
            if actual != expected:
                escaped.append(f"{remote} [modified]")
        return tuple(escaped)

    def cleanup_canaries(self) -> None:
        """Remove remote sentinels over SSH. Best-effort; safe to call twice."""
        remotes = [self._canary_remote.get(h, None) for h in self._canary_fingerprints]
        remotes = [r for r in remotes if r]
        if remotes:
            joined = " ".join(shlex.quote(r) for r in remotes)
            self._spawn(
                self._wrap_argv(["bash", "-c", f"rm -f {joined}"]), timeout=60
            )
        self._canary_fingerprints = {}

    # --- small helpers ---------------------------------------------------

    @staticmethod
    def _b64(data: bytes) -> str:
        import base64
        return base64.b64encode(data).decode("ascii")
