"""Pinned subscription-CLI backends for the V2 A-F coder.

Both backends run in isolated temporary directories, make one request with no
automatic retry or fallback, require structured JSON, and independently bind
the served model identity. Codex receives a temporary copy of its OAuth file;
the temporary home and session record are deleted when the call returns.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from scripts.irr_code import RaterBackend, RaterResponse


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "enum": ["A", "B", "C", "D", "E", "F"]},
        "rationale": {"type": "string", "minLength": 1, "maxLength": 400},
    },
    "required": ["code", "rationale"],
    "additionalProperties": False,
}


def _run(
    argv: Sequence[str],
    *,
    cwd: Path,
    input_text: str,
    env: Mapping[str, str] | None = None,
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.perf_counter()
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=dict(env) if env is not None else None,
        timeout=timeout_seconds,
        check=False,
    )
    return completed, time.perf_counter() - started


def _version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"cannot identify {executable} version")
    return completed.stdout.strip()


def _parse_json_lines(text: str) -> tuple[Mapping[str, object], ...]:
    events: list[Mapping[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            events.append(value)
    return tuple(events)


class ClaudeCliBackend(RaterBackend):
    def __init__(
        self,
        coder_id: str,
        *,
        model_id: str,
        cli_version: str,
        executable: str = "claude",
        timeout_seconds: int = 240,
    ) -> None:
        observed_cli = _version(executable)
        if observed_cli != cli_version:
            raise ValueError(
                f"Claude CLI version drift: expected {cli_version!r}, observed {observed_cli!r}"
            )
        self.coder_id = coder_id
        self.model_id = model_id
        self.cli_version = cli_version
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.model_pin = f"claude-code/{cli_version}::{model_id}"

    def code_one(self, system_prompt: str, user_content: str) -> RaterResponse:
        schema = json.dumps(_OUTPUT_SCHEMA, separators=(",", ":"))
        with tempfile.TemporaryDirectory(prefix="d006-claude-") as temp:
            completed, wall_time = _run(
                [
                    self.executable,
                    "-p",
                    "--safe-mode",
                    "--no-session-persistence",
                    "--prompt-suggestions",
                    "false",
                    "--tools",
                    "",
                    "--model",
                    self.model_id,
                    "--output-format",
                    "json",
                    "--json-schema",
                    schema,
                    "--system-prompt",
                    system_prompt,
                ],
                cwd=Path(temp),
                input_text=user_content,
                timeout_seconds=self.timeout_seconds,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Claude coder exited {completed.returncode}: {completed.stderr[-500:]}"
            )
        events = _parse_json_lines(completed.stdout)
        if len(events) != 1:
            raise RuntimeError("Claude coder did not emit exactly one JSON receipt")
        receipt = events[0]
        if receipt.get("is_error") is not False or receipt.get("subtype") != "success":
            raise RuntimeError("Claude coder receipt is not a success")
        model_usage = receipt.get("modelUsage")
        if not isinstance(model_usage, Mapping) or self.model_id not in model_usage:
            raise RuntimeError("Claude coder receipt does not bind the requested model")
        structured = receipt.get("structured_output")
        if isinstance(structured, Mapping):
            raw_response = json.dumps(structured, ensure_ascii=False)
        else:
            result = receipt.get("result")
            if not isinstance(result, str):
                raise RuntimeError("Claude coder receipt lacks structured output")
            raw_response = result
        metadata = {
            "backend": "claude-cli",
            "cli_version": self.cli_version,
            "model_usage": model_usage,
            "usage": receipt.get("usage"),
            "wall_time_seconds": round(wall_time, 6),
            "automatic_retries": 0,
            "fallback_model": None,
        }
        request_id = receipt.get("uuid")
        return RaterResponse(
            raw_response=raw_response,
            observed_model_id=self.model_pin,
            refused=receipt.get("stop_reason") == "refusal",
            request_id=request_id if isinstance(request_id, str) else None,
            backend_metadata=metadata,
        )


class CodexCliBackend(RaterBackend):
    def __init__(
        self,
        coder_id: str,
        *,
        model_id: str,
        cli_version: str,
        executable: str = "codex",
        auth_path: Path | None = None,
        timeout_seconds: int = 240,
    ) -> None:
        if os.name == "nt" and executable == "codex":
            executable = shutil.which("codex.cmd") or executable
        observed_cli = _version(executable)
        if observed_cli != cli_version:
            raise ValueError(
                f"Codex CLI version drift: expected {cli_version!r}, observed {observed_cli!r}"
            )
        self.coder_id = coder_id
        self.model_id = model_id
        self.cli_version = cli_version
        self.executable = executable
        self.auth_path = (auth_path or Path.home() / ".codex" / "auth.json").resolve()
        self.timeout_seconds = timeout_seconds
        self.model_pin = f"codex-cli/{cli_version}::{model_id}"

    def code_one(self, system_prompt: str, user_content: str) -> RaterResponse:
        if not self.auth_path.is_file():
            raise RuntimeError("Codex OAuth source is missing")
        with tempfile.TemporaryDirectory(prefix="d006-codex-") as temp:
            root = Path(temp).resolve()
            codex_home = root / "codex-home"
            workspace = root / "workspace"
            codex_home.mkdir()
            workspace.mkdir()
            shutil.copyfile(self.auth_path, codex_home / "auth.json")
            schema_path = root / "output-schema.json"
            output_path = root / "last-message.json"
            schema_path.write_text(json.dumps(_OUTPUT_SCHEMA), encoding="utf-8")
            env = dict(os.environ)
            env["CODEX_HOME"] = str(codex_home)
            prompt = f"{system_prompt}\n\n--- BLINDED CASE ---\n{user_content}"
            completed, wall_time = _run(
                [
                    self.executable,
                    "exec",
                    "--json",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "-s",
                    "read-only",
                    "--skip-git-repo-check",
                    "-m",
                    self.model_id,
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(output_path),
                    "-",
                ],
                cwd=workspace,
                input_text=prompt,
                env=env,
                timeout_seconds=self.timeout_seconds,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Codex coder exited {completed.returncode}: {completed.stderr[-500:]}"
                )
            events = _parse_json_lines(completed.stdout)
            thread_ids = [
                event.get("thread_id")
                for event in events
                if event.get("type") == "thread.started"
                and isinstance(event.get("thread_id"), str)
            ]
            if len(thread_ids) != 1:
                raise RuntimeError("Codex coder did not expose exactly one thread id")
            forbidden_items = []
            for event in events:
                if event.get("type") != "item.completed":
                    continue
                item = event.get("item")
                if isinstance(item, Mapping) and item.get("type") not in {
                    "agent_message",
                    "reasoning",
                }:
                    forbidden_items.append(item.get("type"))
            if forbidden_items:
                raise RuntimeError(f"Codex coder used prohibited tools: {forbidden_items}")

            observed_models: set[str] = set()
            for session_path in codex_home.glob("sessions/**/*.jsonl"):
                for line in session_path.read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, Mapping) or event.get("type") != "turn_context":
                        continue
                    payload = event.get("payload")
                    if isinstance(payload, Mapping) and isinstance(payload.get("model"), str):
                        observed_models.add(str(payload["model"]))
            if observed_models != {self.model_id}:
                raise RuntimeError(
                    f"Codex coder model identity mismatch: {sorted(observed_models)}"
                )
            raw_response = output_path.read_text(encoding="utf-8").strip()
            turn_completed = [
                event for event in events if event.get("type") == "turn.completed"
            ]
            if len(turn_completed) != 1:
                raise RuntimeError("Codex coder lacks one completion receipt")
            metadata = {
                "backend": "codex-cli",
                "cli_version": self.cli_version,
                "usage": turn_completed[0].get("usage"),
                "wall_time_seconds": round(wall_time, 6),
                "automatic_retries": 0,
                "fallback_model": None,
                "prohibited_tool_items": forbidden_items,
            }
        return RaterResponse(
            raw_response=raw_response,
            observed_model_id=self.model_pin,
            request_id=str(thread_ids[0]),
            backend_metadata=metadata,
        )
