# `data/pre-registration/` — NOT ANALYSIS DATA

Anything under this subtree is **NOT** experimental data for H1/H2/H3/H4
inference. Analysis scripts and the IRR coder MUST exclude
`data/pre-registration/**` when globbing for trial JSONs.

## What's here

### `smoke_trials/`

Trials run **before** the `pre-registration-v1` tag for the purpose of
verifying the harness end-to-end (parser, environment probe, success
checks, immutable logging) against a real paid agent call. These trials:

- Are real Claude Code stream-json captures, so they're useful as parser
  fixtures and for harness debugging.
- Were run when the harness, task definitions, environment pins, or other
  pre-registered methodology was still in flux — they're **not** committed
  to under any pre-registered hypothesis.
- Must be excluded from any inferential analysis even if their schema
  matches the post-pre-reg trial logs.

The C01 smoke trial here (2026-05-18, CLI 2.1.143, pwsh 7.5.5) is the
trial that caught the PowerShell-tool parser bug. The frozen, redacted
parser fixture lives separately under `tests/fixtures/` — the trial here
is preserved for additional harness-debugging context, not as a fixture.

## Why move them out of `data/<env>/`?

If analysis scripts naively glob `data/**/trial_*.json`, smoke trials get
mixed into the analysis dataset. That's a methodological breach for free:
trials run under a different shell pin, a different model pin, or a
different task definition would be tabulated alongside confirmatory runs
without any flag distinguishing them.

The directory separation here is the cheapest enforceable rule. The
pre-push privacy grep gate also runs on this directory to catch any
accidental PII leaks in raw smoke-trial outputs.

## Adding new pre-registration smoke trials

After the `pre-registration-v1` tag, any further smoke trials run for
harness validation (e.g., when wiring up a new EnvironmentAdapter or
AgentAdapter) should go here with a timestamped subfolder and a brief
note in this README.

- `2026-07-04T04-11-01Z-agy-resmoke/` — agy pre-data re-smoke (PASS),
  VERSIONS.md hard-gate discharge. Ran on installed agy 1.0.9; pin
  re-pinned 1.0.7 → 1.0.9 (DEVIATIONS.md 2026-07-05).
- `2026-07-05T21-49-03Z-codex-resmoke/` — codex pre-data re-smoke (PASS)
  on pinned 0.139.0, run inside a disposable GCP VM per TOS_COMPLIANCE;
  VERSIONS.md hard-gate discharge.
- `2026-07-05-codex-e2e-shakedown/` — full `run_cell()` end-to-end
  shakedown (PASS): real codex 0.139.0 × `gpt-5.4-mini` on C01 via
  `linux_native` (self-SSH transport) on a disposable GCP VM — sandbox,
  probe, agent, snapshot, hardened checks, trial record all wired.
  Same session: `gpt-5.5` (config #3 model) availability confirmed live.
