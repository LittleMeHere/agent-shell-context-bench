"""Agent adapters: one per coding-agent CLI under test.

Pre-registered configurations live in RESEARCH_PLAN.md / docs/VERSIONS.md
(7 model-harness configs = 3 vendors × 2 model tiers + 1 same-model
harness-control, per docs/DECISIONS.md 2026-05-25 (later) — supersedes
the earlier "6 configs" framing from D3 2026-05-23). An adapter is the
harness-side knowledge of how to drive ONE CLI non-interactively and how
to recover a transcript + command list from its output. agy serves
configs #5, #6, and #7 (three model pins through the same adapter).

  claude_code.py   Claude Code CLI            -> reference implementation (V1)
  codex.py         OpenAI Codex CLI           -> (V2 work; model pins locked, parser unverified)
  agy.py           Google Antigravity CLI     -> (V2 work; replaces planned Gemini CLI per D3 — Google announced Gemini CLI sunset within ~30 days of 2026-05-23; agy is the official replacement. Headless mode confirmed; structured output / model pinning / session persistence UNVERIFIED, adapter blocks on those checks)

Only `claude_code.py` is implemented so far — it is the reference example
for the base contract. Cursor was dropped per docs/DECISIONS.md 2026-05-18
(no headless `cursor-agent`; harness-over-same-frontier-models).
"""
