# agent-shell-context-bench

A controlled benchmark measuring AI coding agent reliability across five OS-shell execution contexts. Headline question: *do AI coding agents have measurably higher failure rates and qualitatively different failure modes when operating on Windows/PowerShell vs. Linux/bash, and if so, why?*

> **Status:** methodology locked for `pre-registration-v1`. When the
> pre-registration commit + git tag exists, this README will say so
> explicitly with the tag's commit SHA and UTC timestamp.

## What this is

A controlled cross-context benchmark for AI coding agents. The V1
confirmatory matrix is **7 model-harness configurations × 5 execution
contexts × 14 tasks** (5 capability + 9 seeded-error, with seeded-error tasks running
both formal and colloquial phrasings — 23 task-prompt variants total).
Configurations span three frontier vendors (Anthropic via Claude Code,
OpenAI via Codex CLI, Google via Antigravity CLI `agy`) at two model
tiers each, plus a same-nominal-model harness control pair.

Outcomes measured: task-weighted binary failure rate (H1a / H1b) and
qualitative failure-escalation patterns ("the spiral", H2). The full
formal pre-registration is in [`HYPOTHESIS.md`](HYPOTHESIS.md) and
[`docs/SAP.md`](docs/SAP.md); informal summaries below.

## Hypotheses (formal versions in HYPOTHESIS.md)

- **H1a (primary inferential):** On the 5 capability tasks, pooled across the 7 configurations, the Windows-context (PowerShell 5.1 default, free tool choice) failure rate ratio over the Linux-context rate is ≥1.5×.
- **H1b (secondary descriptive):** The same comparison on the full 14-task suite (cap + seeded-error), reported with point estimate and 95% CI but no threshold-based support/reject decision.
- **H2 (primary qualitative):** Among valid failed trials across all 14 tasks, the Windows context shows at least 2× higher conditional rate of code-D (spiral) or code-E (catastrophic action) than the Linux context. Confirmatory status is conditional on inter-rater reliability per SAP S4; demoted to descriptive if κ-thresholds aren't met.
- **H3 (secondary inferential):** WSL2 failure rate sits between Windows and Linux, closer to Linux. Tested via two one-sided ordering inequalities (α=0.025 each) plus a bootstrap distance criterion, with a pre-registered inconclusive guardrail when the Windows-Linux gap is under 5 percentage points.
- **H4 (exploratory):** Colloquial / permission-granting seeded-error-task phrasings may trigger more D/E spiral patterns than formal phrasings. Reported with effect size + CI, no binary accept/reject.

The 5 execution contexts: Windows + PowerShell 5.1, Windows + pwsh 7.6.2, Windows + WSL2 Ubuntu, Linux native (GCP), macOS (GitHub Actions runner). Per the cross-context confounds disclosure in HYPOTHESIS.md, each context bundles hardware/virtualization/filesystem/network/tool-install-state/runner-policy — claims are about context bundles, not OS-in-isolation.

## Why this matters

No published controlled **agentic** cross-OS coding-agent benchmark currently compares reliability across shell environments while holding the agent and task constant. Major suites (SWE-bench, Terminal-Bench, AgentBench, METR HCAST/RE-Bench, TheAgentCompany) all run in Linux Docker containers on bash by design. Windows Agent Arena is Windows-only desktop-GUI work, not a comparison. The closest prior work, Vo, Paulovicks & Sheinin 2024 (arXiv:2405.06807, IBM), compares one-shot NL-to-bash and NL-to-PowerShell code generation across 7 LLMs but is not agentic, runs both shells on Linux containers, and uses non-equivalent task sets across shells. This benchmark occupies a clean methodological gap — agentic, multi-turn, host-OS-as-the-independent-variable — and produces evidence relevant to developers and small teams making real hardware/tooling decisions on imperfect anecdotal data.

## Repository structure

```
agent-shell-context-bench/
  HYPOTHESIS.md              Pre-registered hypotheses (H1a, H1b, H2, H3, H4)
  RESEARCH_PLAN.md           Full research plan + methodology glossary
  DEVIATIONS.md              Methodology deviations from the pre-reg tag (empty at tag)
  docs/
    SAP.md                   Pre-registered Statistical Analysis Plan
    VERSIONS.md              Pinned tool/model versions + V1 matrix + IRR coder pins
    DECISIONS.md             Dated rationale log for each load-bearing decision
  tasks/
    capability/              C01-C05: baseline reliability tasks
    trap/                    T01-T09: seeded-error tasks (legacy folder name; concept renamed to "seeded-error tasks" per 2026-05-30 DECISIONS — tasks designed to trigger known failure modes)
  harness/
    runner.py                Trial orchestration
    adapters/                Per-agent adapters (Claude Code implemented; Codex / agy adapter pending)
    environments/            Per-environment adapters (Windows PS 5.1 implemented; pwsh 7 / WSL2 / Linux / macOS pending)
    classifier/rubric.py     Spiral classification rubric (A-F codes)
    logging/                 Per-trial immutable log writer
  scripts/
    irr_code.py              IRR coder driver with frozen-prompt drift gate
    irr_prompt.frozen.md     The verbatim grading prompt (sha256-tied to rubric.py)
    size_from_pilot.py       Pilot-data → confirmatory N (cap-only-aware)
    make_parser_fixture.py   PII-redacting fixture builder
    power_analysis.py        A-priori power tables (audit-frozen)
  tests/                     Regression tests for canary, checks, parser
  data/                      Trial logs (gitignored; only the data-hygiene README is tracked)
  analysis/                  IRR + statistical outputs (populated post-tag)
```

## Implementation status at pre-registration-v1

Per the methodology-vs-implementation discipline in DECISIONS, pre-registration locks **methodology**, not implementation completeness. PIN-AT-START is a legitimate pre-reg state for V1 cells whose adapters land post-tag.

| Component | Status |
|---|---|
| Claude Code adapter (configs #1, #2) | Implemented + parser-verified against real CLI output (current CLI/model pins and the full verification history live in `docs/VERSIONS.md` — the single aggregated record) |
| Windows PS 5.1 environment | Implemented + canary-confirmed escape detection |
| Codex adapter (configs #3, #4) | PIN-AT-START — schema characterized via 2026-05-25 smoke; adapter ~6h post-tag |
| agy adapter (configs #5, #6, #7) | PIN-AT-START — transcript schema characterized; adapter ~12-20h post-tag with agy-specific Cwd handling |
| Windows pwsh 7 env (E2) | PIN-AT-START — `PowerShellEnvironment` subclass, ~2h post-tag |
| Windows WSL2 env (E3) | PIN-AT-START — `wsl -d` wrapper, ~3h post-tag |
| Linux native env (E4) | PIN-AT-START — SSH wrapper, ~4h post-tag |
| macOS env (E5) | PIN-AT-START — GitHub Actions YAML + harness self-invocation, ~4h post-tag |

Per-CLI / per-environment qualification gate for any future additions: SAP S5.

## Running the benchmark

For an implemented cell (Claude Code × Windows PS 5.1):

```bash
python -m harness run \
  --task tasks/capability/C01_nested_directory.yaml \
  --agent claude_code \
  --model claude-sonnet-4-6 \
  --env windows_powershell \
  --trials <pilot-derived-N> \
  --output data/
```

For PIN-AT-START cells the runner will raise `NotImplementedError` with a clear message naming the unbuilt adapter — see `harness/registry.py`.

## Reproducibility

Every methodology decision and every code path is in this repo. To reproduce:

1. Clone, install dependencies: `python -m pip install -r requirements.txt`.
2. Verify the frozen IRR prompt hasn't drifted: `python scripts/irr_code.py --check-prompt`.
3. Run the test suites: `python tests/test_checks.py && python tests/test_canary_detection.py && python tests/test_claude_code_parser.py`.
4. Run any implemented cell with the harness invocation above.
5. Coded transcripts + per-trial logs publish under `data/` after each run (PII-redaction reviewed before commit — see `data/pre-registration/README.md` for the data-hygiene policy).

Replication welcome — please open an issue with your environment fingerprint + results.

## Author

Maintained by [littlemehere](https://github.com/littlemehere). Independent research project.

## License

MIT — see [`LICENSE`](LICENSE).

## Citation

Preprint pending; this README will list the DOI / arXiv ID when available. For now, please cite the repository directly using the `pre-registration-v1` tag.

## Contact

GitHub issues preferred for methodology questions, replication results, and CLI/environment qualification proposals.
