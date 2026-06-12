"""Claude Code CLI adapter (reference implementation).

Implemented first because Claude Code is the primary agent (RESEARCH_PLAN.md
A1) and its headless JSON output is the cleanest to parse — it sets the bar
the other adapters' parsers are tested against.

================================ VERSION PIN ===============================
Flags below were VERIFIED against `claude --help` on:

  Claude Code version : 2.1.176
  Verified on (date)  : 2026-06-12
  Verified by         : tag-eve currency pass (updated 2.1.159 -> 2.1.176
                        the same day; was 2.1.150 / 2026-05-24, 2.1.143 /
                        2026-05-18; still within 2.1.x, NO major version
                        change; all six flags below re-checked unchanged
                        against `claude --help` on 2026-06-12; step 3
                        satisfied by live stream-json schema checks on
                        BOTH 2.1.159 and 2.1.176 (2026-06-12) — all
                        load-bearing event structures identical to the
                        frozen fixture, parser verified end-to-end on both
                        captures (the 2.1.176 run exercised the PowerShell
                        tool branch), fixture stands; see docs/VERSIONS.md
                        change log 2026-06-12)

Verified flag semantics (re-confirmed unchanged on 2.1.143; first verified 2.1.119):
  -p / --print              run once, print response, exit (non-interactive)
  --output-format stream-json   one JSON event per step (only works with -p);
                            lets us reconstruct the ordered command list H2
                            (the spiral) is measured on
  --verbose                 required for full event stream under --print
  --dangerously-skip-permissions   bypass ALL approval gates — required, or
                            the agent cannot take the destructive actions H2
                            measures. (Distinct from the merely-enabling
                            flag --allow-dangerously-skip-permissions.)
  --model <id|alias>        pin the model for the cell
  --no-session-persistence  no resume state written/read — enforces the
                            clean-sandbox-per-trial rule at the CLI level

  >>> RE-VERIFY IMMEDIATELY BEFORE CUTTING `pre-registration-v1` <<<
  The Claude Code CLI ships often (already 2.1.119 -> 2.1.143 during
  scaffolding). Right before tagging the pre-registration commit:
    1. Re-run `claude --version` + `claude --help` on the data-collection
       machine. Update the three pin fields above and RESEARCH_PLAN.md.
    2. Re-confirm each flag above still exists with the same meaning.
    3. Re-capture a real stream-json transcript and refresh the frozen
       parser fixture (see PARSER STATUS below) — the parser is only proven
       against real output, and the event/tool schema can change with the
       CLI just like the flags can.
  If any flag changed, fix build_invocation BEFORE collecting data and log
  it in DEVIATIONS.md. A wrong --output-format silently corrupts every H2
  number — this is the single highest-leverage reproducibility check.

PARSER STATUS — RE-VERIFIED against real output 2026-05-25 (CLI 2.1.150,
claude-sonnet-4-6, Windows, C01 smoke trial — fixture re-capture for
pre-reg-v1). Originally verified 2026-05-18 on CLI 2.1.143; parser
extended 2026-05-24 (D1 hybrid framing per docs/DECISIONS.md) to walk
`user` events and pair `tool_result.is_error` into `CommandRecord.exit_code`,
and to populate `CommandRecord.tool_name` from the originating tool_use's
`name` field for SAP A1b per-tool stratified analysis.
  * Real-output bug found & fixed (2026-05-18): on the original capture
    Windows agent used the `PowerShell` tool, not `Bash`. The original
    Bash-only filter extracted ZERO commands while the task still passed
    — i.e. it would have nulled every H2 number silently. Fixed:
    `_SHELL_TOOLS` (bash/powershell/..., case-insensitive), and all
    tool_use blocks per event are captured.
  * Empirical finding from 2026-05-25 re-capture: agent picked the `Bash`
    tool on Windows for C01 on this run (CLI 2.1.150, Sonnet 4.6) —
    different from the 2026-05-18 capture where the same model picked
    `PowerShell`. The parser correctly extracted both calls and tagged
    them with their actual tool name. This is the D1 hybrid framing
    working as intended: agent tool choice is a measured variable
    (SAP A1b), not a methodology assumption. If a future re-capture
    surfaces a tool not in `_SHELL_TOOLS`, extend the set.
  * Frozen fixture: `tests/fixtures/claude_code_streamjson_C01.jsonl`
    (machine PII redacted by `scripts/make_parser_fixture.py`).
  * Regression tests: `tests/test_claude_code_parser.py` (12 tests as of
    2026-05-25 fixture refresh, incl. PII-clean assertion + is_error
    pairing + tool_name populated-and-in-_SHELL_TOOLS). Run before any
    data collection.
============================================================================
"""

from __future__ import annotations

import json
from typing import ClassVar

from ..environments.base import EnvironmentAdapter
from ..types import CommandRecord, ProcessResult, SandboxHandle
from .base import AgentAdapter


class ClaudeCodeAdapter(AgentAdapter):
    agent_id: ClassVar[str] = "claude_code"

    @staticmethod
    def _default_cli_path() -> str:
        return "claude"

    def build_invocation(
        self, prompt: str, sandbox: SandboxHandle
    ) -> list[str]:
        # Flags re-verified against Claude Code 2.1.159 (2026-06-09); first
        # verified on 2.1.119 — see VERSION PIN in the module docstring.
        #
        # DECISION FOR THE RESEARCHER (not silently hardcoded): the CLI
        # supports `--max-budget-usd <amount>`, a hard per-run dollar cap.
        # Adding it would protect the $50/mo compute budget against a
        # spiraling agent burning tokens — BUT a too-low cap would itself
        # truncate runs and confound the result (a budget-killed run looks
        # like rubric F when it might have recovered). If you want it, set
        # `self.max_budget_usd` and it is appended below. Left unset = no cap.
        argv = [
            self.cli_path,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--no-session-persistence",
            "--model",
            self.model_id,
        ]
        if getattr(self, "max_budget_usd", None) is not None:
            argv += ["--max-budget-usd", str(self.max_budget_usd)]
        return argv

    def parse_transcript(
        self, process: ProcessResult
    ) -> tuple[str, list[CommandRecord]]:
        """Reconstruct (transcript, commands) from stream-json output.

        Walks BOTH `assistant` events (which carry tool_use blocks — the
        commands the agent issued) AND `user` events (which carry
        tool_result blocks — the outcome of each command, including
        `is_error` and stdout/stderr).

        Each tool_use becomes a CommandRecord with `tool_name` populated
        (for SAP A1b per-tool stratified analysis). When a subsequent
        tool_result arrives with the same `tool_use_id`, the CommandRecord
        is updated with `exit_code` (0 if is_error=false, 1 if true) and
        the structured stdout/stderr from `tool_use_result` if present.
        Tool_uses without a matching tool_result keep `exit_code=None` and
        empty stdout/stderr — the agent may have been killed mid-call.

        Robust by contract: any malformed line is preserved in the
        transcript and skipped for command extraction rather than aborting.
        A crashed run with three good events is still three events of data.
        """
        transcript_lines: list[str] = []
        commands: list[CommandRecord] = []
        # Map tool_use_id -> index in `commands` list (only populated when
        # the tool_use block carries an `id`; synthetic test events may
        # lack one and just won't get paired).
        pending: dict[str, int] = {}

        for raw_line in process.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                transcript_lines.append(line)
                continue

            transcript_lines.append(self._render_event(event))

            for tool_use in self._shell_tool_uses_from_event(event):
                idx = len(commands)
                commands.append(CommandRecord(
                    index=idx,
                    command=tool_use["command"],
                    tool_name=tool_use["name"],
                ))
                if tool_use["id"]:
                    pending[tool_use["id"]] = idx

            for result in self._tool_results_from_event(event):
                tool_use_id = result["tool_use_id"]
                idx = pending.pop(tool_use_id, None)
                if idx is None:
                    continue
                old = commands[idx]
                commands[idx] = CommandRecord(
                    index=old.index,
                    command=old.command,
                    stdout=result["stdout"],
                    stderr=result["stderr"],
                    exit_code=1 if result["is_error"] else 0,
                    offset_seconds=old.offset_seconds,
                    tool_name=old.tool_name,
                )

        if not transcript_lines and process.stdout:
            transcript_lines.append(process.stdout)

        return "\n".join(transcript_lines), commands

    @staticmethod
    def _render_event(event: dict) -> str:
        etype = event.get("type", "?")
        if etype == "assistant":
            return f"[assistant] {json.dumps(event.get('message', event))[:2000]}"
        if etype == "result":
            return f"[result] {event.get('result', '')}"
        return f"[{etype}] {json.dumps(event)[:2000]}"

    # Tool names that represent actual SHELL command execution. Verified
    # against real stream-json (smoke test 2026-05-18): on Windows the agent
    # uses the `PowerShell` tool; on Linux/macOS/WSL it uses `Bash`. Matched
    # case-insensitively. File Read/Edit/Write tool calls are deliberately
    # excluded — they are not shell behaviour and would dilute the
    # recovery-attempt / spiral counts the rubric measures.
    _SHELL_TOOLS = {"bash", "powershell", "pwsh", "shell", "sh", "cmd"}

    @classmethod
    def _shell_tool_uses_from_event(cls, event: dict) -> list[dict]:
        """All shell tool_use blocks in one assistant event, in order.

        Returns list of {"id", "name", "command"} dicts. `id` may be None
        for synthetic events that omit the field; pairing with tool_results
        is skipped in that case but the CommandRecord is still emitted.

        Returning a list (not a single tool_use): one assistant message can
        contain multiple tool_use blocks, and every shell call is a
        separate command for the spiral rubric — dropping the 2nd+ would
        undercount escalation, the exact thing H2 measures.
        """
        if event.get("type") != "assistant":
            return []
        out: list[dict] = []
        for block in (event.get("message", {}).get("content") or []):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name", ""))
            if name.lower() not in cls._SHELL_TOOLS:
                continue
            command = (block.get("input") or {}).get("command")
            if not command:
                continue
            out.append({
                "id": block.get("id"),
                "name": name,
                "command": str(command),
            })
        return out

    @staticmethod
    def _tool_results_from_event(event: dict) -> list[dict]:
        """All tool_result blocks in one user event, in order.

        Returns list of {"tool_use_id", "stdout", "stderr", "is_error"}
        dicts. `stdout` / `stderr` are pulled from the event's structured
        `tool_use_result` payload when present (Claude Code emits this as
        a sibling to `message` in user events); falls back to the
        tool_result block's `content` field if the structured payload is
        absent or doesn't carry stdout. `is_error` is taken from the
        tool_result block itself.

        Note: Claude Code's stream-json packs structured stdout/stderr at
        the event top level (one per event), not per tool_result block, so
        an event containing multiple tool_results would attribute the same
        stdout/stderr to each. In practice each user event contains exactly
        one tool_result (verified against the fixture); this is robust to
        the multi-result case in the sense of preserving exit_code
        correctly while accepting that stdout attribution may be coarse.
        """
        if event.get("type") != "user":
            return []
        structured = event.get("tool_use_result") or {}
        struct_stdout = ""
        struct_stderr = ""
        if isinstance(structured, dict):
            struct_stdout = str(structured.get("stdout", "") or "")
            struct_stderr = str(structured.get("stderr", "") or "")

        out: list[dict] = []
        for block in (event.get("message", {}).get("content") or []):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_use_id = block.get("tool_use_id")
            if not tool_use_id:
                continue
            stdout = struct_stdout
            stderr = struct_stderr
            if not stdout and not stderr:
                content = block.get("content")
                if isinstance(content, str):
                    stdout = content
            out.append({
                "tool_use_id": tool_use_id,
                "stdout": stdout,
                "stderr": stderr,
                "is_error": bool(block.get("is_error", False)),
            })
        return out

    def cli_version(self, environment: EnvironmentAdapter) -> str:
        result = environment.exec(
            [self.cli_path, "--version"], cwd=".", timeout=30
        )
        return (result.stdout or result.stderr).strip() or "unknown"
