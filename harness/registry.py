"""Name -> class lookup for environments and agents.

The CLI takes strings (`--env windows_powershell`); the matrix in
RESEARCH_PLAN.md is defined in those strings. This is the one place that
maps a pre-registered identifier to an implementation.

Unimplemented cells raise a clear error rather than silently doing nothing
— a benchmark that quietly skips a cell would corrupt the matrix.
"""

from __future__ import annotations

from .adapters.base import AgentAdapter
from .adapters.claude_code import ClaudeCodeAdapter
from .environments.base import EnvironmentAdapter
from .environments.powershell import PowerShellEnvironment

_ENVIRONMENTS: dict[str, type[EnvironmentAdapter]] = {
    PowerShellEnvironment.env_id: PowerShellEnvironment,
}

_AGENTS: dict[str, type[AgentAdapter]] = {
    ClaudeCodeAdapter.agent_id: ClaudeCodeAdapter,
}

# Pre-registered identifiers not yet implemented. Listed explicitly so the
# error message can distinguish "typo" from "not built yet".
# Kept in sync with the V1 confirmatory matrix in docs/VERSIONS.md.
# Notable history (do not re-add):
#   - "gemini" was REPLACED by "agy" per 2026-05-23 DECISIONS (Google's
#     Gemini CLI sunset; Antigravity CLI is the V1 Google-lineage agent).
#   - "cursor" was permanently DROPPED per 2026-05-18 DECISIONS (no
#     reproducible headless interface, harness over the same frontier
#     models the matrix already covers). Not "pre-registered but pending."
_PLANNED_ENVIRONMENTS = {"windows_pwsh7", "windows_wsl2", "linux_native", "macos_actions"}
_PLANNED_AGENTS = {"codex", "agy"}


def make_environment(env_id: str) -> EnvironmentAdapter:
    cls = _ENVIRONMENTS.get(env_id)
    if cls is not None:
        return cls()
    if env_id in _PLANNED_ENVIRONMENTS:
        raise NotImplementedError(
            f"environment {env_id!r} is pre-registered but not yet "
            f"implemented; implemented: {sorted(_ENVIRONMENTS)}"
        )
    raise KeyError(
        f"unknown environment {env_id!r}; "
        f"implemented: {sorted(_ENVIRONMENTS)}, "
        f"planned: {sorted(_PLANNED_ENVIRONMENTS)}"
    )


def make_agent(
    agent_id: str, model_id: str, max_budget_usd: float | None = None
) -> AgentAdapter:
    cls = _AGENTS.get(agent_id)
    if cls is not None:
        agent = cls(model_id)
        # Optional hard spend cap. The adapter appends --max-budget-usd only
        # when this attribute is set (see ClaudeCodeAdapter.build_invocation).
        if max_budget_usd is not None:
            agent.max_budget_usd = max_budget_usd  # type: ignore[attr-defined]
        return agent
    if agent_id in _PLANNED_AGENTS:
        raise NotImplementedError(
            f"agent {agent_id!r} is pre-registered but not yet implemented; "
            f"implemented: {sorted(_AGENTS)}"
        )
    raise KeyError(
        f"unknown agent {agent_id!r}; "
        f"implemented: {sorted(_AGENTS)}, planned: {sorted(_PLANNED_AGENTS)}"
    )
