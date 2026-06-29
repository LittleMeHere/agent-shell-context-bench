"""Shared remote-Unix environment logic (WSL2 + Linux-native).

This is the internal base the two remote environments share. It is NOT part
of the locked measurement contract (`environments/base.py`) and adds no new
public surface: it is a private helper class (`RemoteUnixEnvironment`) that
implements once everything WSL2 and Linux-native do identically, leaving each
concrete env to supply only what genuinely differs — its *transport* and its
*host-side view* of the sandbox.

Why one shared base rather than two near-duplicate adapters: the failure mode
`docs/ADAPTER_CONTRACT.md` warns about is independently-built adapters drifting
into subtly-incompatible measurement. WSL2 and Linux run the SAME Ubuntu shell;
the only true differences are:

  * how a process is launched (`wsl -d Ubuntu-24.04 -- argv`  vs  `ssh host -- argv`)
  * how the harness reads the sandbox back locally for `checks.py`
    (WSL2: the live `\\wsl$` / `wslpath -w` UNC bridge — a real shared mount;
     Linux: no shared mount, so the sandbox is copied back to a local mirror
     before every snapshot).

Everything else — sandbox creation, `initial_files` materialisation,
`required_tools` enforcement, the timeout-as-data spawn, the POSIX probe, and
the snapshot/diff path — is identical and lives here exactly once.

The two equivalence invariants this base is responsible for (see
`docs/ADAPTER_CONTRACT.md`):

  Invariant 1 — snapshot keys are sandbox-relative POSIX. Guaranteed by routing
  every snapshot through `harness.fs.local_snapshot(host_root)`, the same
  helper the Windows reference uses; it keys files by `Path.relative_to(...).
  as_posix()`. The remote env's only job is to make `host_root` a locally
  readable directory holding the sandbox tree, which `_host_root_for` /
  `_sync_back` do.

  Invariant 2 — `host_root` is a locally-readable directory at check time.
  WSL2 satisfies this with the always-live UNC bridge; Linux satisfies it by
  syncing the remote tree into a local temp mirror in `_sync_back` before the
  snapshot reads it.

Concrete subclasses implement the abstract seams marked below and override the
canary lifecycle for their filesystem. They do NOT override `exec`,
`run_shell`, `setup_sandbox`, `snapshot`, or `probe` — those are shared so the
two cells differ in exactly the transport, not in measured behaviour.
"""

from __future__ import annotations

import base64
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from abc import abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..fs import local_snapshot
from ..types import FilesystemSnapshot, ProcessResult, SandboxHandle
from .base import EnvironmentAdapter
from .home_fs import HomeFilesystem


class RemoteUnixEnvironment(EnvironmentAdapter, HomeFilesystem):
    """Abstract base for environments whose shell is Unix and reached over a
    process-launch wrapper (WSL2's `wsl --`, GCP's `ssh`).

    Subclasses MUST set `env_id` / `description` and implement:
      * `_wrap_argv(argv)`        — prepend the transport to a raw argv.
      * `_remote_root()`          — POSIX dir under which per-trial sandboxes live.
      * `_host_root_for(native)`  — local, readable path mirroring a native path.
      * `_sync_back(sandbox)`     — refresh `host_root` from the live sandbox
                                    (no-op when host_root is a live mount).
      * canary overrides          — `canary_paths()` and, where the canary fs is
                                    not directly writable with local Python I/O,
                                    `_write_canary()` (see base.py hint).
    """

    # Sentinel directory-name prefix for per-trial sandboxes, mirrored from the
    # Windows reference's `{task}_t{n}_{ms}` scheme so logs read the same.
    _SANDBOX_PREFIX = "pstax"

    # --- transport + host view (the only true per-env differences) -------

    @abstractmethod
    def _wrap_argv(self, argv: Sequence[str]) -> list[str]:
        """Return the LOCAL argv that runs `argv` inside this environment.

        WSL2: ``["wsl", "-d", "Ubuntu-24.04", "--", *argv]``.
        Linux: ``["ssh", *opts, target, "--", *argv]``.

        The wrapped command is spawned by `_spawn` on the host; this is the
        single seam where the execution context enters, so it is the ONLY
        cross-cell variable (`docs/ADAPTER_CONTRACT.md` invariant 4 — the
        agent CLI runs only through `exec`, which calls this).
        """

    @abstractmethod
    def _remote_root(self) -> str:
        """POSIX directory (in the environment's own filesystem) under which
        per-trial sandbox subdirectories are created."""

    @abstractmethod
    def _host_root_for(self, native_root: str) -> Path:
        """Local, readable `Path` mirroring the native sandbox path.

        For WSL2 this is the UNC bridge translation of the WSL path (a live
        shared mount). For Linux it is a freshly-created local temp directory
        that `_sync_back` will populate by copying the remote tree. Either way
        the returned path is what `checks.py` reads (invariant 2)."""

    def _sync_back(self, sandbox: SandboxHandle) -> None:
        """Refresh `host_root` so it reflects the sandbox's current contents.

        Default no-op: correct for a live shared mount (WSL2), where the host
        view is always current. Environments with no shared mount (Linux over
        SSH) override this to copy the remote tree into the local mirror before
        each snapshot, or every content check fails closed (invariant 2)."""
        return None

    # --- the one process seam (timeout is data, never an exception) ------

    def _spawn(
        self,
        wrapped_argv: list[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        """Launch an already-wrapped argv on the host.

        Mirrors `PowerShellEnvironment._spawn`: a timeout yields
        ``ProcessResult(timed_out=True)`` rather than raising (invariant 5 — a
        hung agent is rubric F, not a harness failure). `argv` on the result is
        the wrapped argv actually launched, so the log records the true command
        line including the transport.
        """
        full_env = {**os.environ, **(env or {})}
        start = time.monotonic()
        try:
            proc = subprocess.run(
                wrapped_argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=full_env,
            )
        except subprocess.TimeoutExpired as exc:
            return ProcessResult(
                argv=tuple(wrapped_argv),
                returncode=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                duration_seconds=time.monotonic() - start,
                timed_out=True,
            )
        return ProcessResult(
            argv=tuple(wrapped_argv),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_seconds=time.monotonic() - start,
            timed_out=False,
        )

    # --- execution seams -------------------------------------------------

    def exec(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        """Run an arbitrary executable inside this environment (the agent CLI).

        `cwd` is an environment-native POSIX path (`SandboxHandle.root`). It is
        applied INSIDE the environment via `cd` rather than as the host
        subprocess's cwd, because the host cannot `chdir` into a WSL/remote
        path.

        The agent's argv is shell-quoted into the script string rather than
        passed as trailing positionals: `wsl.exe` does NOT forward arguments
        after a `bash -c <script>` into the script's `$@` (verified — they are
        silently dropped), so a `"$@"` form would run an empty command. Each
        argv element is `shlex.quote`d, so the agent CLI invocation is
        preserved exactly regardless of spaces/quotes. A login shell (`-lc`)
        resolves the same PATH a real session has, so the agent binary
        (`node`/`claude`/...) is found where the user would find it.

        `env` is merged into the HOST process that launches the transport.
        Whether it reaches the agent depends on the transport: `wsl` forwards
        only `$WSLENV`-listed vars, and `ssh` does not forward client env at
        all. The runner does not pass `env` (the agent's model/flags travel in
        its argv), so this asymmetry does not affect the measured cells; the
        parameter is honoured best-effort for signature parity with the local
        reference env.
        """
        quoted = " ".join(shlex.quote(str(a)) for a in argv)
        inner = f"cd {shlex.quote(cwd)} && exec {quoted}"
        return self._spawn(
            self._wrap_argv(["bash", "-lc", inner]), timeout=timeout, env=env
        )

    def run_shell(
        self, sandbox: SandboxHandle, script: str, *, timeout: float
    ) -> ProcessResult:
        """Run a snippet in this environment's native shell (used by `probe`).

        `-l` so the login shell resolves the same PATH a real session has (the
        agent-relevant tool versions the probe reports must match what the
        agent would actually find).
        """
        remote = ["bash", "-lc", f"cd {shlex.quote(sandbox.root)} 2>/dev/null; {script}"]
        return self._spawn(self._wrap_argv(remote), timeout=timeout)

    def _run_remote(self, script: str, *, timeout: float = 60) -> ProcessResult:
        """Run a bash snippet in the environment, not bound to any sandbox.

        Internal helper for sandbox lifecycle (mkdir / write / rmtree / tool
        probing). Uses a non-login shell — these are mechanical filesystem ops
        that must not depend on profile state."""
        return self._spawn(self._wrap_argv(["bash", "-c", script]), timeout=timeout)

    def _run_remote_quiet(self, script: str, *, timeout: float = 60) -> ProcessResult | None:
        """`_run_remote` that returns None instead of raising when the transport
        is unavailable. The `HomeFilesystem` seam must never raise (see its
        contract); a concrete transport (`LinuxNativeEnvironment._wrap_argv`)
        raises when unconfigured, so home-fs ops route through here and degrade
        to None — read→None, write→False, listdir→[]."""
        try:
            return self._run_remote(script, timeout=timeout)
        except EnvironmentError:
            return None

    # --- home-directory seam (HomeFilesystem) over the same transport -----

    def _env_home(self) -> str:
        """The environment login user's `$HOME`, cached (one round trip).

        Shared resolver for both the canary `$HOME` target and the home-fs
        seam. Subclasses may override to add an offline fallback when no
        transport is configured (Linux does, for structural conformance)."""
        cached = getattr(self, "_home_cache", None)
        if cached is None:
            res = self._run_remote('printf %s "$HOME"')
            cached = (res.stdout.strip() if res else "") or "/root"
            self._home_cache = cached
        return cached

    def home_path(self, rel: str) -> str:
        tail = rel.replace("\\", "/").lstrip("/")
        return f"{self._env_home().rstrip('/')}/{tail}"

    def home_read(self, rel: str) -> str | None:
        # base64 the file on the far side so arbitrary text/encoding survives
        # the transport; decode locally. Missing file -> non-zero rc -> None.
        res = self._run_remote_quiet(
            f"base64 < {shlex.quote(self.home_path(rel))} 2>/dev/null"
        )
        if res is None or res.returncode != 0:
            return None
        try:
            return base64.b64decode(res.stdout).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

    def home_write(self, rel: str, content: str) -> bool:
        target = self.home_path(rel)
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        parent = target.rsplit("/", 1)[0]
        res = self._run_remote_quiet(
            f"mkdir -p {shlex.quote(parent)} && "
            f"printf %s {shlex.quote(b64)} | base64 -d > {shlex.quote(target)} && echo OK"
        )
        return res is not None and res.returncode == 0 and "OK" in res.stdout

    def home_remove(self, rel: str) -> None:
        self._run_remote_quiet(f"rm -f {shlex.quote(self.home_path(rel))}")

    def home_listdir(self, rel: str) -> list[str]:
        # -1 one entry per line, -A includes dotfiles but excludes . and ..
        res = self._run_remote_quiet(
            f"ls -1A {shlex.quote(self.home_path(rel))} 2>/dev/null"
        )
        if res is None or res.returncode != 0:
            return []
        return [line for line in res.stdout.splitlines() if line]

    # --- reproducibility -------------------------------------------------

    # One `bash -lc` snippet that fingerprints the Unix context as TAB-delimited
    # key/value lines. Deliberately heredoc-free and with NO nested double
    # quotes: it is passed as a single argument through `wsl --` / `ssh`, and
    # either layer can mangle nested quoting or a heredoc. `os_release` is
    # emitted raw (the `PRETTY_NAME=...` line) and cleaned host-side so spaces in
    # the distro name survive. Login shell (`-lc`) so tool versions reflect the
    # PATH the agent would resolve. Field set mirrors the Windows reference
    # probe's spirit (OS, shell+version, locale, git/node/python versions).
    _PROBE_SCRIPT = (
        'printf "os\\t%s\\n" "$(uname -o 2>/dev/null)"; '
        'grep -h "^PRETTY_NAME=" /etc/os-release 2>/dev/null | head -n1 '
        '| sed "s/^/os_release_raw\\t/"; '
        'printf "kernel\\t%s\\n" "$(uname -sr 2>/dev/null)"; '
        'printf "shell\\t%s\\n" "$(bash --version 2>/dev/null | head -n1)"; '
        'printf "locale\\t%s\\n" "${LANG:-}"; '
        'printf "git\\t%s\\n" "$(git --version 2>/dev/null)"; '
        'printf "node\\t%s\\n" "$(node --version 2>/dev/null)"; '
        'printf "python\\t%s\\n" "$(python3 --version 2>/dev/null || python3 --version 2>&1)"'
    )

    def probe(self) -> dict[str, str]:
        """Fingerprint the Unix context for the log header.

        Runs `_PROBE_SCRIPT` once over a login shell and parses its TAB-delimited
        key/value lines. Always tagged with `env_id`. Tool versions use the
        login-shell PATH so they reflect what the agent would resolve.
        """
        result = self._spawn(
            self._wrap_argv(["bash", "-lc", self._PROBE_SCRIPT]), timeout=90
        )
        info: dict[str, str] = {"env_id": self.env_id}
        for line in result.stdout.splitlines():
            if "\t" not in line:
                continue
            key, value = line.split("\t", 1)
            if key == "os_release_raw":
                # Raw `PRETTY_NAME="Ubuntu 24.04 LTS"` -> the unquoted value.
                value = value.split("=", 1)[1] if "=" in value else value
                value = value.strip().strip('"')
                key = "os_release"
            info[key] = value.strip()
        if len(info) == 1:  # only env_id — the probe produced nothing parseable
            info["probe_error"] = (result.stdout + result.stderr)[:2000]
        return info

    # --- sandbox lifecycle ----------------------------------------------

    def setup_sandbox(
        self,
        task_id: str,
        trial_index: int,
        preconditions: Mapping[str, object],
    ) -> SandboxHandle:
        """Create a fresh per-trial sandbox in the environment's filesystem.

        Steps, all run INSIDE the environment so the bytes are native to it:
          1. mkdir a unique sandbox dir under `_remote_root()`.
          2. materialise every `initial_files` entry at its relative path.
          3. enforce `required_tools`: a missing tool raises (invariant 6 — a
             silently-degraded run would confound the cell).
        Then bind a `host_root` (via `_host_root_for`) so the harness can read
        the sandbox locally for checks.
        """
        root = self._remote_root()
        native = f"{root}/{task_id}_t{trial_index}_{int(time.time() * 1000)}"

        mk = self._run_remote(
            f"rm -rf {shlex.quote(native)} && mkdir -p {shlex.quote(native)} && echo OK"
        )
        if mk.returncode != 0 or "OK" not in mk.stdout:
            raise EnvironmentError(
                f"{self.env_id}: could not create sandbox {native!r}: "
                f"rc={mk.returncode} stderr={mk.stderr.strip()[:300]}"
            )

        for entry in preconditions.get("initial_files", []) or []:
            self._materialize_initial_file(native, entry)

        for tool in preconditions.get("required_tools", []) or []:
            if not self._tool_present(str(tool)):
                self._run_remote(f"rm -rf {shlex.quote(native)}")
                raise EnvironmentError(
                    f"required tool {tool!r} not found on PATH for "
                    f"{self.env_id}; refusing to run a confounded trial"
                )

        handle = SandboxHandle(
            task_id=task_id,
            trial_index=trial_index,
            env_id=self.env_id,
            root=native,
            host_root=self._host_root_for(native),
        )
        # Make the host view reflect the freshly-materialised sandbox NOW, not
        # only at first snapshot: a caller (and the conformance battery) may
        # read `host_root` directly between setup and the first snapshot, and
        # for a no-shared-mount env the mirror would otherwise be empty until
        # `_sync_back` runs. No-op for a live mount (WSL2).
        self._sync_back(handle)
        return handle

    def _materialize_initial_file(self, native_root: str, entry: object) -> None:
        """Create one `initial_files` entry inside the environment.

        Accepts the same two shapes as the Windows reference: a bare string
        path (empty file) or a mapping with `path` + optional `content`.
        Content is written via a base64 pipe so arbitrary bytes (newlines,
        quotes, non-ASCII) survive the transport without shell-quoting hazards.
        """
        if isinstance(entry, str):
            rel, content = entry, ""
        elif isinstance(entry, Mapping):
            rel = str(entry["path"])
            content = str(entry.get("content", ""))
        else:
            raise ValueError(f"unsupported initial_files entry: {entry!r}")

        target = self._posix_join(native_root, rel)
        parent = target.rsplit("/", 1)[0]
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        script = (
            f"mkdir -p {shlex.quote(parent)} && "
            f"printf %s {shlex.quote(b64)} | base64 -d > {shlex.quote(target)} && echo OK"
        )
        res = self._run_remote(script)
        if res.returncode != 0 or "OK" not in res.stdout:
            raise EnvironmentError(
                f"{self.env_id}: failed to materialise initial file {rel!r}: "
                f"rc={res.returncode} stderr={res.stderr.strip()[:300]}"
            )

    def _tool_present(self, tool: str) -> bool:
        """True iff `tool` resolves on the environment's login PATH.

        `command -v` under a login shell mirrors what the agent CLI would
        find. A non-zero exit means absent (invariant 6 enforcement point).
        """
        res = self._spawn(
            self._wrap_argv(["bash", "-lc", f"command -v {shlex.quote(tool)}"]),
            timeout=30,
        )
        return res.returncode == 0 and bool(res.stdout.strip())

    @staticmethod
    def _posix_join(root: str, rel: str) -> str:
        """Join a POSIX root and a (possibly back-slashed) relative path.

        Relative paths come from task YAML and are POSIX by convention, but a
        stray backslash is normalised so the remote `mkdir`/write always sees a
        forward-slash path."""
        rel = rel.replace("\\", "/").lstrip("/")
        return f"{root.rstrip('/')}/{rel}"

    def teardown_sandbox(self, sandbox: SandboxHandle) -> None:
        """Destroy the sandbox in the environment and its local mirror.

        Safe to call after a failed setup and twice (both deletes ignore
        missing targets), per the base contract.
        """
        self._run_remote(f"rm -rf {shlex.quote(sandbox.root)}")
        self._teardown_host_mirror(sandbox)

    def _teardown_host_mirror(self, sandbox: SandboxHandle) -> None:
        """Remove the local mirror dir, if this env owns one.

        Default no-op: a live mount (WSL2) has no separate local copy to
        delete. Linux overrides to remove its synced temp mirror."""
        return None

    # --- filesystem truth ------------------------------------------------

    def snapshot(self, sandbox: SandboxHandle) -> FilesystemSnapshot:
        """Fingerprint the sandbox via the local host view + canary escape check.

        Refreshes the host view (`_sync_back`; no-op for a live mount), then
        runs the SAME `local_snapshot` the Windows reference uses, so keys are
        sandbox-relative POSIX (invariant 1). `escaped_paths` is populated from
        `check_canaries()` (invariant 3).
        """
        self._sync_back(sandbox)
        snap = local_snapshot(Path(sandbox.host_root))
        return FilesystemSnapshot(
            files=snap.files,
            dirs=snap.dirs,
            escaped_paths=self.check_canaries(),
        )

    # --- small local helpers shared by both remote envs ------------------

    @staticmethod
    def _local_mirror_root() -> Path:
        """Host-side root for sandbox mirrors / UNC bookkeeping.

        Used by Linux for its synced mirrors. Lives under the host temp dir,
        overridable via PSTAX_HOST_MIRROR_ROOT for a researcher who wants the
        mirrors on a specific volume."""
        root = Path(
            os.environ.get(
                "PSTAX_HOST_MIRROR_ROOT",
                Path(tempfile.gettempdir()) / "pstax_host_mirror",
            )
        )
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _which_required(tool: str) -> str:
        """Resolve a host-side transport tool (wsl/ssh/scp) or raise.

        The transport binaries are the remote env's own `required_tools`: if
        `ssh` is absent the Linux cell cannot run at all, and that must fail
        loudly at construction rather than mid-trial."""
        path = shutil.which(tool)
        if path is None:
            raise EnvironmentError(
                f"host transport tool {tool!r} not found on PATH; it is "
                "required to reach this environment"
            )
        return path
