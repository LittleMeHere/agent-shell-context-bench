"""Agent adapters: one per coding-agent CLI under test.

Pre-registered configurations live in RESEARCH_PLAN.md / docs/VERSIONS.md
(7 model-harness configs = 3 vendors × 2 model tiers + 1 same-model
harness-control, per docs/DECISIONS.md 2026-05-25 (later) — supersedes
the earlier "6 configs" framing from D3 2026-05-23). An adapter is the
harness-side knowledge of how to drive ONE CLI non-interactively and how
to recover a transcript + command list from its output. agy serves
configs #5, #6, and #7 (three model pins through the same adapter).

  claude_code.py   Claude Code CLI            -> reference implementation (configs #1, #2)
  codex.py         OpenAI Codex CLI           -> V1 primary, PIN-AT-START (configs #3, #4) — `codex exec --json` schema characterised via 2026-05-25 smoke (structured `item.completed` fields); adapter is ~6h post-tag work
  agy.py           Google Antigravity CLI     -> V1 primary, PIN-AT-START (configs #5, #6, #7) — 2026-05-25 smoke confirmed structured tool_calls in brain transcript_full.jsonl + model pin via settings.json; replaces sunset Gemini CLI; adapter ~12-20h post-tag work with agy-specific Cwd handling (see SAP "Outcome construction")

Only `claude_code.py` is implemented so far — it is the reference example
for the base contract. Cursor was dropped per docs/DECISIONS.md 2026-05-18
(no headless `cursor-agent`; harness-over-same-frontier-models).
"""
