"""OpenAI Codex CLI adapter (`codex exec --json`).

Second agent adapter, built against the contract the Claude Code reference
(`claude_code.py`) establishes. Codex CLI emits a structured JSONL event
stream whose command-completion events carry the command, its exit code, and
its captured output as *structured fields* — a cleaner schema than Claude
Code's tool_use/tool_result id-pairing (no cross-event correlation needed to
recover a command's outcome). One executed command becomes one CommandRecord.

================================ VERSION PIN ===============================
Flags below were characterised against `codex exec --json` on the
2026-05-25 smoke trial documented in `docs/VERSIONS.md` (V1 primary
matrix, configs #3/#4). Per the same-as-Claude-Code discipline, the pins
here are the load-bearing reproducibility surface and must be RE-VERIFIED
against the installed CLI before data collection.

  Codex CLI version   : 0.139.0   (pinned in docs/VERSIONS.md, config #3/#4;
                        was 0.133.0 at the 2026-05-25 schema smoke, bumped
                        to 0.139.0 at the 2026-06-12 tag-eve currency pass —
                        `exec --json` schema re-confirmation is explicitly
                        DEFERRED to this adapter build per VERSIONS.md, and
                        it gates configs #3/#4 anyway)
  Schema characterised: 2026-05-25 (CLI 0.133.0, `codex doctor` clean —
                        auth configured, websocket connected, default
                        model `gpt-5.5`)
  Verified by         : adapter build (this file). The parser is unit-tested
                        against SYNTHETIC JSONL shaped to the documented
                        schema; real-output verification needs the codex CLI
                        + auth and is FLAGGED FOR LATER, mirroring the
                        claude_code frozen-fixture discipline (see PARSER
                        STATUS below).

Pinned invocation (recorded for docs/VERSIONS.md — a wrong flag silently
corrupts every H2 number, exactly as a wrong --output-format would for
Claude Code):
  codex exec                run once, non-interactive, then exit (the
                            `exec` subcommand is Codex's headless mode)
  -m / --model <id>         pin the model for the cell (per-instance:
                            `gpt-5.5`, `gpt-5.4-mini`, ...)
  --dangerously-bypass-approvals-and-sandbox
                            bypass ALL approval gates AND the built-in
                            sandbox — required, or the agent cannot take the
                            destructive actions H2 measures (the analogue of
                            Claude Code's --dangerously-skip-permissions).
                            The benchmark's OWN EnvironmentAdapter provides
                            isolation per trial; the CLI's sandbox would
                            confound "what would the agent do unconstrained".
  --ephemeral               no persisted session/rollout state written or
                            read — enforces the clean-sandbox-per-trial rule
                            at the CLI level (the analogue of Claude Code's
                            --no-session-persistence).
  --json                    one JSON event per line on stdout — the
                            structured stream we reconstruct the ordered
                            command list (the spiral H2 is measured on) from.
  -C <dir>                  set the working directory to the sandbox root.
                            argv[0] is still `self.cli_path`; `-C` binds the
                            sandbox the same way the harness sets `cwd` on
                            exec (subprocess CWD inheritance is a backup —
                            both were confirmed in the 2026-05-25 smoke).

  >>> RE-VERIFY IMMEDIATELY BEFORE COLLECTING DATA FOR CONFIGS #3/#4 <<<
  The Codex CLI ships often (0.130.0 -> 0.133.0 -> 0.139.0 during
  scaffolding). Before collecting:
    1. Re-run `codex --version` + `codex exec --help` on the
       data-collection machine. Update the pin fields above and
       docs/VERSIONS.md.
    2. Re-confirm each flag above still exists with the same meaning.
    3. Capture a real `codex exec --json` transcript (including a
       deliberately FAILING command) and freeze a parser fixture, exactly
       as `scripts/make_parser_fixture.py` does for Claude Code — the
       parser is only PROVEN against real output, and the event/item
       schema can drift with the CLI just like the flags can.
  If any flag changed, fix build_invocation BEFORE collecting data and log
  it in DEVIATIONS.md.

PARSER STATUS — SYNTHETIC-ONLY as of this adapter build. Unlike
`claude_code.py` (frozen real fixture `claude_code_streamjson_C01.jsonl`),
no real Codex capture is committed yet: real-output verification requires
the codex CLI + OpenAI auth on the data-collection machine and is FLAGGED
FOR LATER alongside the pre-collection re-smoke above. The schema this
parser targets is the one documented from the 2026-05-25 smoke:

  * Each top-level event is one JSON object per line with a `type` field.
  * A command-completion event has type `item.completed` and an `item`
    object whose `item_type`/`type` marks it as a command execution; the
    command's `command`, `exit_code`, and `aggregated_output` live as
    STRUCTURED fields on that item (no tool_use_id pairing).
  * `aggregated_output` is the merged stdout+stderr the CLI captured for
    the command; we record it as `CommandRecord.stdout` (Codex does not
    split the streams in this field, so `stderr` stays empty — the
    documented schema, not a parser shortcut).
  * `tool_name` is populated from whatever the item exposes for the shell
    tool when present, else None (the schema surfaces structured command
    fields directly rather than a Claude-Code-style named tool block;
    SAP A1b per-tool analysis degrades to None for Codex if the field is
    absent).

  Tests: `tests/test_codex_parser.py` (synthetic JSONL shaped to the above)
  + `tests/test_codex_conformance.py` (the shared agent battery). Both run
  in CI with no infrastructure, like the Claude Code parser tests. Replace
  the synthetic coverage with a frozen real fixture at the pre-collection
  re-smoke.
============================================================================
"""

from __future__ import annotations

import json
from typing import ClassVar

from ..environments.base import EnvironmentAdapter
from ..types import CommandRecord, ProcessResult, SandboxHandle
from .base import AgentAdapter


class CodexAdapter(AgentAdapter):
    agent_id: ClassVar[str] = "codex"

    @staticmethod
    def _default_cli_path() -> str:
        return "codex"

    def build_invocation(
        self, prompt: str, sandbox: SandboxHandle
    ) -> list[str]:
        # Flags characterised against the pinned CLI version — see the
        # VERSION PIN block in the module docstring (history: docs/VERSIONS.md).
        # argv[0] MUST be self.cli_path so the harness launches the pinned
        # binary; the agent runs once, headless, with no approval gate so a
        # spiral can actually unfold (the contract in adapters/base.py).
        return [
            self.cli_path,
            "exec",
            "-m",
            self.model_id,
            "--dangerously-bypass-approvals-and-sandbox",
            "--ephemeral",
            "--json",
            "-C",
            sandbox.root,
            prompt,
        ]

    # Item types (the `item_type`/`type` discriminator on a completed item)
    # that represent actual SHELL command execution. Matched case-insensitively.
    # The documented 0.133.0 schema surfaces command execution as a
    # `command_execution` item; the historical/alternate spellings are
    # accepted defensively so a minor schema relabel does not silently null
    # out command extraction (the failure mode the Claude Code Bash-only
    # filter hit). If a real capture surfaces a different marker, extend this
    # set and re-freeze the fixture rather than loosening the match.
    _COMMAND_ITEM_TYPES = {
        "command_execution",
        "command",
        "local_shell_call",
        "shell_call",
        "exec_command",
    }

    # Keys that may carry the shell tool name on a command item, if the CLI
    # exposes one. The documented schema surfaces structured command fields
    # directly (no named tool block), so this is best-effort: absent -> None.
    _TOOL_NAME_KEYS = ("tool_name", "tool", "shell", "name")

    def parse_transcript(
        self, process: ProcessResult
    ) -> tuple[str, list[CommandRecord]]:
        """Reconstruct (transcript, commands) from `codex exec --json` output.

        Walks the JSONL stream on `process.stdout`. Each command-completion
        event (`type == "item.completed"` whose item is a command execution)
        becomes one CommandRecord with `command`, `stdout` (from the item's
        `aggregated_output`), `exit_code`, and `tool_name` (whatever the item
        exposes for the shell tool, else None). Indices are sequential from 0
        in stream order — the ordered command list is exactly what the H2
        spiral rubric is scored on, so order is preserved and nothing is
        dropped or reordered.

        Robust by contract (the 'never raise' rule in adapters/base.py): any
        malformed line is preserved in the transcript and skipped for command
        extraction rather than aborting. Empty / garbled / truncated input
        degrades to a best-effort partial. A crashed run with three good
        events is still three events of data.
        """
        transcript_lines: list[str] = []
        commands: list[CommandRecord] = []

        for raw_line in process.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Garbled / truncated line: keep it visible, skip extraction.
                transcript_lines.append(line)
                continue
            if not isinstance(event, dict):
                # Valid JSON but not an event object (e.g. a bare number/array
                # from a truncated or malformed stream) — preserve, don't crash.
                transcript_lines.append(line)
                continue

            transcript_lines.append(self._render_event(event))

            command_item = self._completed_command_item(event)
            if command_item is None:
                continue
            commands.append(CommandRecord(
                index=len(commands),
                command=command_item["command"],
                stdout=command_item["stdout"],
                exit_code=command_item["exit_code"],
                tool_name=command_item["tool_name"],
            ))

        if not transcript_lines and process.stdout:
            transcript_lines.append(process.stdout)

        return "\n".join(transcript_lines), commands

    @staticmethod
    def _render_event(event: dict) -> str:
        """One-line human-readable rendering of an event for the transcript."""
        etype = event.get("type", "?")
        item = event.get("item")
        if etype == "item.completed" and isinstance(item, dict):
            itype = item.get("item_type") or item.get("type") or "?"
            cmd = item.get("command", "")
            return f"[item.completed:{itype}] {json.dumps(cmd)[:2000]}"
        return f"[{etype}] {json.dumps(event)[:2000]}"

    @classmethod
    def _completed_command_item(cls, event: dict) -> dict | None:
        """Extract a command execution from a completed-item event, or None.

        Returns `{"command", "stdout", "exit_code", "tool_name"}` when `event`
        is an `item.completed` event carrying a shell command-execution item
        with a non-empty `command`; otherwise None (so non-command items —
        assistant messages, reasoning, file patches — are not counted as
        shell commands, which would dilute the spiral counts the rubric
        measures, the same exclusion the Claude Code adapter makes for
        Read/Edit/Write).

        The `command`, `exit_code`, and `aggregated_output` fields are read
        as STRUCTURED fields per the documented schema — no tool_use_id
        pairing across events is needed.
        """
        if event.get("type") != "item.completed":
            return None
        item = event.get("item")
        if not isinstance(item, dict):
            return None

        itype = str(item.get("item_type") or item.get("type") or "")
        if itype.lower() not in cls._COMMAND_ITEM_TYPES:
            return None

        command = item.get("command")
        if not command:
            return None
        # A list-form command (argv) is joined for a readable, non-empty
        # record; the documented schema is a string, this is defensive.
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        command = str(command)
        if not command:
            return None

        aggregated = item.get("aggregated_output")
        stdout = str(aggregated) if aggregated is not None else ""

        exit_code = cls._coerce_exit_code(item.get("exit_code"))

        tool_name = None
        for key in cls._TOOL_NAME_KEYS:
            val = item.get(key)
            if isinstance(val, str) and val:
                tool_name = val
                break

        return {
            "command": command,
            "stdout": stdout,
            "exit_code": exit_code,
            "tool_name": tool_name,
        }

    @staticmethod
    def _coerce_exit_code(raw: object) -> int | None:
        """exit_code as int when the item carries one, else None.

        Codex surfaces a structured numeric exit code on the completed item;
        when it is absent or non-numeric we record None rather than guessing,
        because the rubric must be applied to what is actually observable
        (the same contract CommandRecord.exit_code documents in types.py).
        """
        if isinstance(raw, bool):  # bool is an int subclass; reject it.
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            try:
                return int(raw.strip())
            except ValueError:
                return None
        return None

    def cli_version(self, environment: EnvironmentAdapter) -> str:
        result = environment.exec(
            [self.cli_path, "--version"], cwd=".", timeout=30
        )
        return (result.stdout or result.stderr).strip() or "unknown"
