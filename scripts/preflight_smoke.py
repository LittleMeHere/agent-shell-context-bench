"""Pre-data re-smoke driver for the Codex and agy gates.

`docs/VERSIONS.md` (hard gate, "PRE-DATA obligation") blocks all config
#3-#7 collection until a real-CLI re-smoke passes for Codex 0.139.0 and
agy 1.0.7, each including a deliberately failing command — a drifted real
schema would parse to zero commands and silently zero H2 for those
configs. This script runs that re-smoke end to end and evaluates the gate
criteria, so the researcher's part is one deliberate command per arm:

    python scripts/preflight_smoke.py codex --yes
    python scripts/preflight_smoke.py agy --yes

Without `--yes` the script is a DRY RUN: it prints the exact argv, the
sandbox location, and what would be checked, then exits. The real run
consumes the researcher's vendor account, so executing it must always be
an explicit human action — this tool never fires as a side effect of
anything else.

Where things run and land:
  * The agent CLI runs in a fresh sandbox under the system temp directory,
    never in this repo (the smoke prompt is benign — one deliberately
    failing command, one small file write — but the repo is still not a
    place agents get pointed at).
  * Raw captures, a parsed summary, and a NOTE.md land in
    `data/pre-registration/<timestamp>-<agent>-resmoke/`, the
    pre-registered no-clock staging ground (SAP: writes there do not
    start data collection). Remember to add the one-line note to
    `data/pre-registration/README.md` — the script prints it.

Gate criteria evaluated (exit 0 pass / 1 fail):
  codex: stream parses to >= 1 CommandRecord; the failing command appears
         with a nonzero exit code; exit codes are populated ints.
  agy:   brain transcript located via dir-diff; parses to >= 1
         CommandRecord; the failing command carries a failure signal (the
         A1b ingredient); per-command Cwd tags classify; settings.json
         model pin round-trips (byte-identical restore, belt over the
         runtime's own restore); scratch canary intact.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness.adapters.codex import CodexAdapter  # noqa: E402
from harness.adapters.agy import AgyAdapter  # noqa: E402
from harness.environments.powershell import PowerShellEnvironment  # noqa: E402
from harness.agy_runtime import AgyTrialRuntime  # noqa: E402
from harness.types import ProcessResult, SandboxHandle  # noqa: E402

# The bogus command name is unique enough to grep for in any capture and
# cannot collide with a real binary.
FAILING_CMD = "pstax-smoke-nonexistent-cmd-1247"

SMOKE_PROMPT = (
    "Do exactly these two steps in the current working directory and "
    "nothing else:\n"
    f"1. Run this exact shell command and note that it fails: {FAILING_CMD}\n"
    "2. Create a file named smoke_ok.txt containing exactly the single "
    "line: OK\n"
    "Then stop."
)

# Workhorse-tier defaults (configs #4 / #6) — the cheapest pinned cells.
DEFAULT_MODEL = {
    "codex": "gpt-5.4-mini",
    "agy": "Gemini 3.5 Flash (Medium)",
}
PINNED_CLI_VERSION = {"codex": "0.139.0", "agy": "1.0.7"}

TIMEOUT_SECONDS = 900


def _utc_stamp() -> str:
    # Same filename-safe form the runner uses (dashes in the time part).
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _out_dir(agent: str) -> Path:
    out = REPO_ROOT / "data" / "pre-registration" / f"{_utc_stamp()}-{agent}-resmoke"
    out.mkdir(parents=True, exist_ok=False)
    return out


def _make_sandbox(agent: str) -> SandboxHandle:
    root = Path(tempfile.mkdtemp(prefix=f"pstax_{agent}_resmoke_"))
    return SandboxHandle(
        task_id=f"{agent}-resmoke",
        trial_index=0,
        env_id="powershell_5_1",
        root=str(root),
        host_root=root,
    )


def _cli_version_line(cli: str) -> str:
    try:
        proc = subprocess.run(
            [cli, "--version"], capture_output=True, text=True, timeout=60
        )
        return (proc.stdout or proc.stderr).strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001 — version is advisory here
        return f"<version check failed: {exc}>"


def _version_gate(agent: str, observed: str, notes: list[str]) -> None:
    pin = PINNED_CLI_VERSION[agent]
    if pin not in observed:
        notes.append(
            f"WARNING: installed {agent} version line {observed!r} does not "
            f"contain the pinned {pin} — VERSIONS.md pins the smoke to that "
            f"version; re-pin or install the pinned build before collecting."
        )


def _run(argv: list[str], cwd: str) -> ProcessResult:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        return ProcessResult(
            argv=tuple(argv),
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_seconds=time.monotonic() - start,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ProcessResult(
            argv=tuple(argv),
            returncode=None,
            stdout=(exc.stdout or b"").decode("utf-8", "replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or ""),
            stderr=(exc.stderr or b"").decode("utf-8", "replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or ""),
            duration_seconds=time.monotonic() - start,
            timed_out=True,
        )


def _command_summaries(commands: list) -> list[dict]:
    out = []
    for cmd in commands:
        out.append(
            {
                "index": getattr(cmd, "index", None),
                "command": getattr(cmd, "command", ""),
                "exit_code": getattr(cmd, "exit_code", None),
                "stdout_chars": len(getattr(cmd, "stdout", "") or ""),
                "stderr_chars": len(getattr(cmd, "stderr", "") or ""),
            }
        )
    return out


def _evaluate_failing_command(commands: list, checks: dict) -> None:
    hits = [c for c in commands if FAILING_CMD in (getattr(c, "command", "") or "")]
    checks["failing_command_captured"] = bool(hits)
    checks["failing_command_signals_failure"] = any(
        (getattr(c, "exit_code", None) not in (0, None))
        or (getattr(c, "stderr", "") or "").strip()
        for c in hits
    )


def smoke_codex(model: str, execute: bool) -> int:
    adapter = CodexAdapter(model)
    sandbox = _make_sandbox("codex")
    argv = adapter.build_invocation(SMOKE_PROMPT, sandbox)

    print(f"sandbox : {sandbox.root}")
    print(f"argv    : {argv}")
    print(
        "CAUTION : the pinned argv includes "
        "--dangerously-bypass-approvals-and-sandbox; docs/TOS_COMPLIANCE.md "
        "forbids dangerous bypass flags on the researcher's workstation — "
        "run this arm inside a disposable VM."
    )
    if not execute:
        print("\nDRY RUN — rerun with --yes to consume the Codex account.")
        return 2

    notes: list[str] = []
    version = _cli_version_line(adapter.cli_path)
    _version_gate("codex", version, notes)

    process = _run(argv, cwd=sandbox.root)
    transcript, commands = adapter.parse_transcript(process)

    checks = {
        "cli_exited_ok": process.returncode == 0 and not process.timed_out,
        "commands_extracted": len(commands) >= 1,
        "exit_codes_populated": bool(commands)
        and all(isinstance(getattr(c, "exit_code", None), int) for c in commands),
    }
    _evaluate_failing_command(commands, checks)

    out = _out_dir("codex")
    (out / "codex_stream.jsonl").write_text(process.stdout, encoding="utf-8")
    (out / "codex_stderr.txt").write_text(process.stderr, encoding="utf-8")
    return _finish(
        out,
        agent="codex",
        version=version,
        checks=checks,
        commands=commands,
        notes=notes,
        extra={"transcript_chars": len(transcript)},
    )


def smoke_agy(model: str, execute: bool) -> int:
    adapter = AgyAdapter(model)
    env = PowerShellEnvironment()
    sandbox = _make_sandbox("agy")
    argv = adapter.build_invocation(SMOKE_PROMPT, sandbox)

    settings_rel = adapter.settings_rel_path
    settings_host = Path(env.home_path(settings_rel))

    print(f"sandbox  : {sandbox.root}")
    print(f"argv     : {argv}")
    print(f"settings : {settings_host} (pinned, then byte-restored)")
    if not execute:
        print("\nDRY RUN — rerun with --yes to consume the agy account.")
        return 2

    notes: list[str] = []
    version = _cli_version_line(adapter.cli_path)
    _version_gate("agy", version, notes)

    runtime = AgyTrialRuntime(adapter, env)
    # Byte-level backup independent of the runtime's own save/restore: if
    # the fake-home-tested restore path has a real-home bug, this still
    # puts the researcher's settings back exactly.
    settings_backup = (
        settings_host.read_bytes() if settings_host.is_file() else None
    )

    out = _out_dir("agy")
    checks: dict[str, bool] = {}
    try:
        runtime.pin_model()
        ctx = runtime.before_trial()
        process = _run(argv, cwd=sandbox.root)
        raw_transcript, commands = adapter.parse_transcript(process)
        # after_trial only touches .commands / .raw_transcript; a real
        # AgentRunResult would drag in fields irrelevant to a smoke.
        result = SimpleNamespace(raw_transcript=raw_transcript, commands=commands)
        outcome = runtime.after_trial(ctx, result, sandbox)

        checks["cli_exited_ok"] = process.returncode == 0 and not process.timed_out
        checks["brain_transcript_located"] = outcome.brain_located
        checks["commands_extracted"] = len(result.commands) >= 1
        checks["cwd_tags_classified"] = bool(outcome.cwd_tags)
        checks["scratch_canary_intact"] = outcome.scratch_escape is None
        _evaluate_failing_command(result.commands, checks)

        (out / "agy_stdout.txt").write_text(process.stdout, encoding="utf-8")
        (out / "agy_stderr.txt").write_text(process.stderr, encoding="utf-8")
        (out / "brain_transcript_parsed.json").write_text(
            json.dumps(outcome.as_log_dict(), indent=2), encoding="utf-8"
        )
        commands = result.commands
    finally:
        runtime.restore_model()
        restored = settings_host.read_bytes() if settings_host.is_file() else None
        if restored != settings_backup:
            if settings_backup is None:
                settings_host.unlink(missing_ok=True)
            else:
                settings_host.write_bytes(settings_backup)
            notes.append(
                "runtime restore did not reproduce the original settings "
                "bytes; byte-level backup was applied instead — inspect "
                "AgyTrialRuntime.restore_model against the real home."
            )
        checks["settings_restored_byte_identical"] = (
            (settings_host.read_bytes() if settings_host.is_file() else None)
            == settings_backup
        )

    return _finish(
        out,
        agent="agy",
        version=version,
        checks=checks,
        commands=commands,
        notes=notes,
        extra={},
    )


def _finish(
    out: Path,
    *,
    agent: str,
    version: str,
    checks: dict,
    commands: list,
    notes: list[str],
    extra: dict,
) -> int:
    passed = all(checks.values())
    summary = {
        "agent": agent,
        "cli_version_line": version,
        "pinned_version": PINNED_CLI_VERSION[agent],
        "prompt": SMOKE_PROMPT,
        "gate_checks": checks,
        "gate_passed": passed,
        "commands": _command_summaries(commands),
        "notes": notes,
        **extra,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "NOTE.md").write_text(
        f"# {agent} pre-data re-smoke\n\n"
        f"Gate: docs/VERSIONS.md pre-data obligation for {agent} "
        f"(re-smoke with a deliberately failing command).\n"
        f"Result: {'PASS' if passed else 'FAIL'} — see summary.json.\n"
        f"Raw capture in this folder; excluded from all inference per "
        f"data/pre-registration/README.md.\n",
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    for note in notes:
        print(f"  NOTE  {note}")
    print(f"{'=' * 60}")
    print(f"gate: {'PASS' if passed else 'FAIL'}   outputs: {out}")
    print(
        "\nAdd to data/pre-registration/README.md:\n"
        f"  - `{out.name}/` — {agent} pre-data re-smoke "
        f"({'PASS' if passed else 'FAIL'}), VERSIONS.md hard-gate discharge."
    )
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("agent", choices=("codex", "agy"))
    parser.add_argument(
        "--model", default=None, help="model id/label (default: workhorse tier)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="actually invoke the vendor CLI (default: dry run)",
    )
    args = parser.parse_args()
    model = args.model or DEFAULT_MODEL[args.agent]
    if args.agent == "codex":
        return smoke_codex(model, execute=args.yes)
    return smoke_agy(model, execute=args.yes)


if __name__ == "__main__":
    sys.exit(main())
