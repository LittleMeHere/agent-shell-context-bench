from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import irr_cli_backends as cli


def _completed(stdout: str, *, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["backend"], returncode, stdout, "")


def test_claude_backend_binds_cli_and_served_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_version", lambda _exe: "2.1.231 (Claude Code)")
    receipt = {
        "is_error": False,
        "subtype": "success",
        "stop_reason": "end_turn",
        "uuid": "request-1",
        "structured_output": {"code": "C", "rationale": "bounded retry"},
        "modelUsage": {"claude-sonnet-4-6": {"inputTokens": 20, "outputTokens": 8}},
        "usage": {"input_tokens": 20, "output_tokens": 8},
    }
    monkeypatch.setattr(
        cli,
        "_run",
        lambda *_args, **_kwargs: (_completed(json.dumps(receipt)), 1.25),
    )
    backend = cli.ClaudeCliBackend(
        "coder1", model_id="claude-sonnet-4-6", cli_version="2.1.231 (Claude Code)"
    )
    response = backend.code_one("rubric", "case")

    assert response.observed_model_id == backend.model_pin
    assert json.loads(response.raw_response)["code"] == "C"
    assert response.backend_metadata is not None
    assert response.backend_metadata["wall_time_seconds"] == 1.25


def test_claude_backend_rejects_unobserved_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_version", lambda _exe: "2.1.231 (Claude Code)")
    receipt = {
        "is_error": False,
        "subtype": "success",
        "structured_output": {"code": "A", "rationale": "done"},
        "modelUsage": {"some-other-model": {}},
    }
    monkeypatch.setattr(
        cli,
        "_run",
        lambda *_args, **_kwargs: (_completed(json.dumps(receipt)), 1.0),
    )
    backend = cli.ClaudeCliBackend(
        "coder1", model_id="claude-sonnet-4-6", cli_version="2.1.231 (Claude Code)"
    )
    with pytest.raises(RuntimeError, match="does not bind"):
        backend.code_one("rubric", "case")


def test_codex_backend_uses_temp_auth_and_observes_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"secret-test-value"}', encoding="utf-8")
    monkeypatch.setattr(cli, "_version", lambda _exe: "codex-cli 0.147.0")

    def fake_run(argv, *, cwd, input_text, env, timeout_seconds):
        del cwd, input_text, timeout_seconds
        home = Path(env["CODEX_HOME"])
        session = home / "sessions" / "2026" / "08" / "rollout.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text(
            json.dumps(
                {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}}
            )
            + "\n",
            encoding="utf-8",
        )
        output_path = Path(argv[argv.index("--output-last-message") + 1])
        output_path.write_text(
            '{"code":"B","rationale":"one correction"}', encoding="utf-8"
        )
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "ok"},
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 30, "output_tokens": 9},
                    }
                ),
            ]
        )
        assert (home / "auth.json").read_text(encoding="utf-8") == auth.read_text(
            encoding="utf-8"
        )
        return _completed(stdout), 2.5

    monkeypatch.setattr(cli, "_run", fake_run)
    backend = cli.CodexCliBackend(
        "coder2",
        model_id="gpt-5.6-terra",
        cli_version="codex-cli 0.147.0",
        auth_path=auth,
    )
    response = backend.code_one("rubric", "case")

    assert response.observed_model_id == backend.model_pin
    assert response.request_id == "thread-1"
    assert json.loads(response.raw_response)["code"] == "B"
    assert response.backend_metadata is not None
    assert response.backend_metadata["wall_time_seconds"] == 2.5


def test_codex_backend_rejects_tool_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "_version", lambda _exe: "codex-cli 0.147.0")

    def fake_run(argv, *, cwd, input_text, env, timeout_seconds):
        del cwd, input_text, timeout_seconds
        home = Path(env["CODEX_HOME"])
        session = home / "sessions" / "rollout.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text(
            json.dumps(
                {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}}
            ),
            encoding="utf-8",
        )
        Path(argv[argv.index("--output-last-message") + 1]).write_text(
            '{"code":"A","rationale":"bad"}', encoding="utf-8"
        )
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "command_execution", "command": "dir"},
                    }
                ),
                json.dumps({"type": "turn.completed", "usage": {}}),
            ]
        )
        return _completed(stdout), 1.0

    monkeypatch.setattr(cli, "_run", fake_run)
    backend = cli.CodexCliBackend(
        "coder2",
        model_id="gpt-5.6-terra",
        cli_version="codex-cli 0.147.0",
        auth_path=auth,
    )
    with pytest.raises(RuntimeError, match="prohibited tools"):
        backend.code_one("rubric", "case")
