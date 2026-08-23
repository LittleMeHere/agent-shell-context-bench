from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import coder_backend_shakedown as shakedown
from scripts.irr_code import RaterResponse


class FakeBackend:
    model_pin = "fake-cli/1::fake-model"

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def code_one(self, system_prompt: str, user_content: str) -> RaterResponse:
        assert "Spiral Classification" in system_prompt
        assert "TRANSCRIPT" in user_content
        return RaterResponse(
            raw_response='{"code":"A","rationale":"completed directly"}',
            observed_model_id=self.model_pin,
            request_id="request-1",
            backend_metadata={"wall_time_seconds": 1.5},
        )


def test_private_stratified_shakedown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = []
    for index, stratum in enumerate(["a", "b", "c", "d", "e"]):
        source = tmp_path / f"source-{index}.json"
        source.write_text(
            json.dumps(
                {
                    "prompt": "do task",
                    "agent": {"transcript": "completed"},
                    "outcome": {"success": True},
                }
            ),
            encoding="utf-8",
        )
        cases.append(
            {
                "case_id": f"case-{index}",
                "stratum": stratum,
                "source_path": str(source),
                "source_sha256": shakedown._sha256(source.read_bytes()),
            }
        )
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "analysis_excluded": True,
                "packet_digest": "a" * 64,
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(shakedown, "ClaudeCliBackend", FakeBackend)
    monkeypatch.setattr(
        shakedown,
        "check_prompt_frozen",
        lambda: "# Spiral Classification — Coding Task\n",
    )
    output = tmp_path / "private" / "receipt.json"
    payload = shakedown.run_shakedown(
        provenance_path=provenance,
        output_path=output,
        backend_name="claude-cli",
        coder_id="coder1",
        model_id="fake-model",
        backend_version="1",
    )

    assert len(payload["receipts"]) == 5
    assert output.is_file()
    assert payload["automatic_retries"] == 0
    with pytest.raises(ValueError, match="overwrite"):
        shakedown.run_shakedown(
            provenance_path=provenance,
            output_path=output,
            backend_name="claude-cli",
            coder_id="coder1",
            model_id="fake-model",
            backend_version="1",
        )
