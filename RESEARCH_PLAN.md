# Research Plan — agent-shell-context-bench

**Author:** littlemehere
**Project status:** scaffolded, pre-research
**Start date:** 2026-05-10
**Target output:** public preprint / writeup + open benchmark code
**Estimated timeline:** 8–12 weeks
**Compute budget:** modest self-funded (small GCP instance; macOS via GitHub Actions on this public repo)

> This is the public, identity-clean copy of the research plan, maintained
> inside the benchmark repo so the repo is self-contained and citable.

## The question

**Do AI coding agents have measurably higher failure rates and qualitatively different failure modes when operating on Windows/PowerShell vs. macOS or Linux/bash — and if so, why, and how serious is it?**

## Working hypothesis (PRE-REGISTERED — do not change after data collection begins)

H1a (Primary): In the V1 confirmatory matrix, the measurement-qualified Claude Code reference configurations will have ≥1.5x higher task failure rates in the Windows context (PowerShell 5.1 default, agent has free tool choice across whatever the CLI exposes — Bash via Git Bash, PowerShell, Write, Edit, etc.) vs. the Linux context (bash default), **on the capability task subset only (5 tasks, C01–C05)**. Primary test pooled across the primary Claude Code model configurations; per-tool command execution/syntax diagnostics report which shell tool the agent actually used and how often commands returned execution errors (SAP A1 + A1b). The capability-only restriction was added 2026-05-25 (latest) per review-driven finalization pass #2 (see `docs/DECISIONS.md`): including the 9 seeded-error tasks in the primary aggregate confounds general reliability with hand-authored adversarial benchmark composition, so the seeded-error-inclusive estimate is demoted to H1b descriptive.

H1b (Secondary, descriptive): The same pooled Windows-vs-Linux comparison computed on the full 14-task suite (5 cap + 9 seeded-error, seeded-error phrasings averaged within task), reported with point estimate and 95% CI only (SAP A1c). No threshold; H1b shows whether direction is consistent when seeded-error tasks are included but is not interpreted as supporting or rejecting a confirmatory claim.

H2: Among valid trials that fail by the task's pre-registered binary success predicate, the Windows context will have at least 2x higher conditional D/E rate (spiral or catastrophic action) than the Linux context. This is a conditional failure-mode asymmetry claim, not a claim that D/E is the dominant Windows failure mode.

H3: WSL2 Ubuntu running on a Windows host will show a failure rate between the Windows context and the Linux context — closer to Linux but not identical to it.

H4: For seeded-error tasks (T01-T09), colloquial / permission-granting prompt phrasing will trigger D/E spiral patterns more often than formal imperative phrasing, within the same primary model-harness configuration and environment context. This is exploratory and reported with effect size plus confidence interval, not a binary accept/reject threshold.

Training-data imbalance — public command examples skewing Unix — is a plausible explanatory theory for any observed gap, but it is not directly tested by this protocol. Likewise, filesystem-boundary issues and tunnel complexity are plausible explanations for any observed WSL2-vs-Linux gap, but this protocol tests only the observational H3 rate ordering. These explanations belong in exploratory interpretation or future causal work unless a separate pre-registered mechanism study is added.

Per the 2026-05-25 (later) scope correction in `docs/DECISIONS.md`, Codex
CLI and Antigravity CLI (`agy`) are V1 primary configurations, alongside
Claude Code. The 2026-05-25 (earlier) narrowing to Claude-only V1 primary
was superseded the same day on the methodology-vs-implementation
discipline: pre-registration locks measurement intent before any data is
seen; it does not require every adapter to be implemented at tag time.
Adapter implementation status (CONFIRMED vs PIN-AT-START) for each of the
7 configurations is recorded in `docs/VERSIONS.md`. SAP S5 remains the
qualification gate for ANY future CLI added beyond V1 — not for the
already-pre-registered V1 configurations.

(Formal pre-registered statements: see `HYPOTHESIS.md`. Statistical plan: `docs/SAP.md`.)

## Why this matters

- Practitioner relevance: the researcher is a Windows user evaluating whether to switch to macOS for AI-assisted development. The investigation is genuinely open — not a post-hoc justification of a purchase.
- Practical: developers and small teams make real $7K–$30K hardware/tooling decisions partly on this question, and public data is mostly anecdotal.
- Safety/alignment: agent reliability across environments is a legitimate empirical alignment question. A failure-mode taxonomy is a contribution even if H1 is rejected.

## Methodology (draft — refined after literature review)

### Environments

| ID | Environment | Source |
|---|---|---|
| E1 | Windows 11 native, **PowerShell 5.1** (default Windows shell) | researcher's Windows workstation |
| E2 | Windows 11 native, **pwsh 7.6.2** (modern PowerShell, becoming default for developer-Windows; pin ticked from 7.5.5 at the 2026-06-12 tag-time re-verification) | same machine |
| E3 | Windows 11 + WSL2 Ubuntu 24.04 (the distro actually installed on the data-collection machine; pin corrected from 22.04 at the 2026-06-12 tag-eve verification) | same machine |
| E4 | Linux native (Ubuntu 24.04 LTS on a small GCP instance, matching E3) | ~$10/mo |
| E5 | macOS (GitHub Actions runner) | free via this public repo |

Per the 2026-05-25 (later) scope correction in `docs/DECISIONS.md`, V1
measures across **both Windows shells in parallel** (E1 and E2). The
within-Windows PS-5.1-vs-pwsh-7 comparison is a built-in mechanism check
("does upgrading the shell close the cross-context gap?") and is
publishable in its own right. The original D2 (2026-05-23) pinned PS 5.1
alone as "the modal Windows experience"; that framing under-claimed for
the writeup's reading window (pwsh-7 adoption is expected to grow
materially over the 12-24 months the writeup will be read). Seeded-error tasks
are annotated per-shell: some trigger on both (T04 `chmod`, T08
`2>/dev/null`, T09 `$(date +%F)`), some only on PS 5.1 (T01 `&&`, fixed
in pwsh 7.0). The no-trigger result on pwsh 7 is itself an informative
finding.

### Agents

| ID | Agent | CLI | Notes |
|---|---|---|---|
| A1 | Claude Code | `claude` 2.1.176 (updated + re-verified 2026-06-12; six flags re-confirmed; live stream-json schema check passed same day) | **V1 primary**; adapter built + parser fixture frozen + 12 regression tests passing |
| A2 | Codex CLI | `codex` 0.139.0 (updated 2026-06-12; `exec --json` schema characterised on 0.133.0 via the 2026-05-25 smoke — re-confirm at adapter build) | **V1 primary**; `--json` schema characterised (cleaner than Claude Code's), adapter ~6h post-tag work |
| A3 | Antigravity CLI | `agy` 1.0.7 (updated 2026-06-12; `--print`/`-p` re-confirmed via `agy --help`; transcript-schema smoke 2026-05-25 ran on 1.0.2 — re-smoke before adapter build) | **V1 primary**; **auth path is official subscription `agy` / Antigravity SDK on Google AI Ultra** per `docs/DECISIONS.md` 2026-05-27 (superseding the 2026-05-26 Vertex-on-alt-GCP plan for V1 data collection); structured `tool_calls` in transcript_full + model pin via `settings.json` write; agy-specific Cwd handling pre-registered in SAP "Outcome construction"; adapter ~12-20h post-tag work |

Per the 2026-05-25 (later) scope correction in `docs/DECISIONS.md`, V1
primary inference is **across all three vendors at two model tiers each
plus a same-model harness control (7 configs total)**. The matrix is:

| # | Vendor | Config | Role |
|---|---|---|---|
| 1 | Anthropic | Claude Code × `claude-opus-4-8` | Anthropic frontier (subscription-available for the full collection window; see `docs/DECISIONS.md` 2026-06-12 (later) on Fable 5) |
| 2 | Anthropic | Claude Code × `claude-sonnet-4-6` | Anthropic workhorse |
| 3 | OpenAI | Codex × `gpt-5.5` | OpenAI frontier |
| 4 | OpenAI | Codex × `gpt-5.4-mini` | OpenAI workhorse |
| 5 | Google | agy × `Gemini 3.1 Pro (High)` | Google frontier |
| 6 | Google | agy × `Gemini 3.5 Flash (Medium)` | Google workhorse |
| 7 | cross-vendor | agy × `Claude Sonnet 4.6 (Thinking)` | same-model harness control vs #2 (SAP S6) |

Per `docs/VERSIONS.md`, only #1 and #2 have CONFIRMED adapters at tag
time; configs #3-#7 are PIN-AT-START (methodology locked, adapter post-tag).
This is a legitimate pre-reg state — pre-registration locks methodology,
not implementation completeness. See the DECISIONS.md entry for the
methodology-vs-implementation discipline.

Cursor was dropped (no headless `cursor-agent`; harness-over-same-frontier-models).
GUI agentic IDEs (Cursor desktop, Windsurf-class, the Antigravity desktop
IDE — distinct from `agy` the CLI, which IS V1 primary) cannot be
automated reproducibly and are an explicit external-validity limitation,
not part of the matrix.

**CLI-transition note (Antigravity):** Google's Gemini CLI is being
retired in favor of Antigravity CLI (`agy`). The 2026-05-25 smoke trial
confirmed agy IS measurement-qualifiable through the persistent
`transcript_full.jsonl` at `~/.gemini/antigravity-cli/brain/<conv-id>/`
(structured `PLANNER_RESPONSE.tool_calls[]` events with `CommandLine`,
`Cwd`, args); the earlier "no structured transcript" assessment was
based on inspection of the working-dir `.antigravitycli/` only. See
`docs/VERSIONS.md` for the full smoke evidence and `docs/SAP.md`
"Outcome construction" for the agy-specific measurement rules
(prompt-injected Cwd directive + per-command Cwd tagging + scratch
canary + transcript-based rubric coding).

**Auth path note (Google arm):** V1 data collection uses official
subscription Antigravity CLI / SDK on Google AI Ultra. The first-party
`agy` binary documents `--print` as non-interactive prompt mode, and
Google documents Antigravity SDK as a programmatic surface using the same
agent harness. Config #7 (`agy × Claude Sonnet 4.6 (Thinking)`) is
available directly through the subscription `agy` model label; no separate
cloud quota, billing, or credit path is needed for V1. Controls:
official Google tooling only, no third-party OAuth/private-API bridges,
no credential sharing, throttling below plan limits, and sandboxed
seeded-error trials.

### Primary model matrix (3 vendors × 2 tiers + 1 harness control = 7 configurations)

| CLI | Frontier tier | Workhorse tier |
|---|---|---|
| Claude Code | `claude-opus-4-8` | `claude-sonnet-4-6` |
| Codex | `gpt-5.5` (xhigh) | `gpt-5.4-mini` |
| agy (Antigravity) | `Gemini 3.1 Pro (High)` | `Gemini 3.5 Flash (Medium)` |
| **Cross-vendor control** | — | **agy × `Claude Sonnet 4.6 (Thinking)`** (settings label CONFIRMED) |

Three vendors × two tiers catches the "best vs cheap" dimension within
each lineage. The 7th cell — a same-nominal-model harness control
(Sonnet 4.6 running under both Claude Code and agy) — enables the
pre-registered S6 analysis to separate harness-architecture effects from
model-lineage effects (with explicit acknowledgement that this is *not* a
clean model-controlled causal isolation; the harnesses differ in system
prompts, hidden tools, helper models, permissions). agy's settings.json
`model` field accepts the verified-label `Claude Sonnet 4.6 (Thinking)`
to propagate Sonnet; lowercase falls back to Gemini.

### Benchmark suite

A standardized set of common dev tasks. Each must be:
- Specific enough that success/failure is unambiguous
- Common enough that real developers do it
- Touchable: requires actual command execution, not just code generation
- Repeatable: same starting state every trial

Candidate task categories:
1. **File operations**: create, move, delete, rename across nested directories
2. **Git operations**: clone, branch, commit, push, resolve simple merge conflict
3. **Dependency install**: install Node/Python deps, handle peer dep conflicts
4. **Run tests**: detect test framework, run, parse output
5. **Build & deploy**: build a small project, deploy to a stub target
6. **Search & refactor**: find all usages of a symbol, rename across files
7. **Browser/headless**: launch headless Chrome, navigate, screenshot
8. **Cleanup/destructive**: remove a dependency, undo a commit (where the spiral risk lives)

### Trial protocol

- Trials per cell set by a blinded pilot (see `docs/SAP.md`); fixed before the confirmatory run.
- Fresh sandbox each trial (no carryover state).
- Identical prompt or pre-registered phrasing variant across all environments per task.
- Log: full transcript, exit status, time elapsed, file system diff, recovery attempts, scope drift.
- Binary task success is determined only from each task's pre-registered
  `binary_success_predicate`. Rubric coding is applied after binary
  success/failure is fixed and is used only for H2/H4 failure-mode analysis.
- Timeouts are valid task failures unless a task explicitly pre-registers a
  narrower exception. Invalid trials are limited to measurement failures
  that prevent binary outcome determination and are not attributable to the
  agent's actions; they are excluded, re-run, and reported separately.
  Agent-induced harness damage or measurement loss remains a valid H1
  failure and may be coded E if attributable to the agent.

### Outcome measures

- **Primary:** task-weighted failure rate per environment × primary model-harness configuration, derived from valid trials and each task's `binary_success_predicate`. For seeded-error tasks, formal and colloquial phrasings are averaged within task before the 14-task aggregate.
- **Secondary:** time to success, number of recovery attempts, scope drift score (qualitative classification), severity of failures
- **Failure mode taxonomy:** classify each failure into categories (syntax, path, permission, scope drift, catastrophic action, hang, etc.)

### Statistical analysis

See `docs/SAP.md` for the pre-registered analysis plan, multiple-comparison handling, and the computed power analysis. Pre-registration locks the plan before data collection to prevent p-hacking.

## Methodology glossary

Reference for what these terms mean and why they matter. Any reader can use this without prior context.

**Cohen's kappa.** A number between -1 and 1 measuring how much two independent raters agree when classifying things into categories — *after correcting for chance agreement*. Two coin-flippers will randomly agree ~50% of the time on binary categories; kappa subtracts that baseline out. Interpretation: 0.81–1.00 = almost perfect, 0.61–0.80 = substantial (publishable), 0.41–0.60 = moderate (concerning), <0.40 = poor. Needed for the spiral classification rubric (codes A–F) — without inter-rater reliability, the codes are one person's interpretation, which a critic can fairly attack as subjective.

**Statistical analysis plan (SAP).** A document written *before* running experiments that locks in: primary outcome, secondary outcomes, specific test for each, significance threshold, multiple-comparison correction, subgroup analyses planned, assumption-violation handling, stopping rules. Pre-registered = published with timestamp before experiments begin. Without an SAP, a researcher can run many tests, report the one that "worked," and look like they predicted it. That's p-hacking and it's why a lot of published research doesn't replicate.

**Pre-registration.** Publishing your hypothesis and SAP somewhere with a verifiable timestamp BEFORE running experiments. Cheapest sufficient method: commit the plan to public git, create a tag (a permanent timestamped pointer to that commit). Anyone can verify the methodology was decided before data was seen.

**Power analysis.** A calculation done before the experiment that answers "given my sample size and significance threshold, what's the smallest effect I can reliably detect?" Without it, you can design a study that literally can't detect the effect you're looking for. (Computed: `scripts/power_analysis.py`.)

**Inter-rater reliability.** When data includes judgment calls (the spiral codes), at least two independent raters apply the rubric to a sample, then agreement is measured (kappa). Standard for qualitative coding in published research.

**Cell.** One specific combination of all variables in the experiment matrix — e.g., "Claude Code, Sonnet 4.6, Linux native, task T1, formal phrasing." Each cell needs N trials.

**Trial.** One run of one cell.

**N (per cell).** How many independent trials per cell. More N = tighter confidence interval on the cell's true success rate.

**Confidence interval (CI).** The range the true value probably falls in, given the sample. Smaller samples → wider intervals. Always report CIs alongside point estimates.

**Native macOS vs Actions runners.** "Native macOS" = real macOS on Apple hardware. "Actions runners" = macOS images in GitHub's CI/CD environment. They differ in file system semantics, permissions, GUI access, sandboxing, default shell config, and permission prompts. Findings from Actions don't fully transfer to native — hedged in the writeup.

**Replication.** Another team independently running the study to verify results. Built-in replication = publishing methodology + code so others CAN re-run. This repo is structured for that.

**Single-researcher caveat.** One person doing everything has blind spots, motivated reasoning, and uncorrected errors. Mitigations used here: a layered inter-rater reliability design (see `docs/SAP.md` S4), staged publication, and explicitly flagging the limitation.

---

## What this research will NOT claim

- That macOS is intrinsically better than Windows for human developers
- That Windows is "bad"
- That the gap can't close as models improve
- That this is the only or most important agent-reliability dimension
- Anything about Microsoft, Apple, or Google as companies

## Honest limitations to surface in any writeup

- **Cross-context confounds (added 2026-05-25 (latest)):** the five
  execution contexts each bundle hardware, virtualization, filesystem,
  network path, tool install state, and runner policy. The pre-registered
  estimands compare context bundles, NOT operating systems in isolation.
  A clean shell-only mechanism study would require either matched hardware
  across all contexts (impractical for this budget) or a containerized
  strict-shell design (rejected per D1 2026-05-23 for ecological-validity
  reasons). The writeup uses "Windows context" / "Linux context" / "macOS
  Actions" consistently — never "Windows" / "Linux" / "macOS" without
  qualifier. See `HYPOTHESIS.md` "Cross-context confounds" for the full
  bundle table.
- Single researcher, single Windows machine — not a distributed study
- Models update; findings are time-stamped (model versions pinned at run time)
- Benchmark suite is finite; real-world tasks are messier
- Prompt sensitivity not exhaustively explored (limited variation, not adversarial)
- macOS via GitHub Actions ≠ native macOS user experience — this is the
  *largest* external-validity caveat among the five contexts and adds GHA
  runner policy on top of the general bundle-level confounds above.

## Outputs (this repo)

- `tasks/` — benchmark task definitions
- `harness/` — runner, environment/agent adapters, classifier rubric
- `data/` — raw experiment logs, transcripts, classifications (large; see repo data policy)
- `analysis/` — notebooks, statistical tests, figures
- `docs/` — SAP, methodology, contributing
- writeup/preprint — linked from the README when available

## Open questions

1. **Primary agents to test — LOCKED.** Per the 2026-05-25 (later) scope correction, V1 primary is the full 7-configuration matrix across all three frontier-vendor CLIs (Claude Code, Codex, agy) at two model tiers each plus one same-model harness-control config (agy × Claude Sonnet 4.6 (Thinking)). Adapter implementation status per row is recorded in `docs/VERSIONS.md`; only Claude Code is CONFIRMED at tag time, with Codex and agy as PIN-AT-START — a legitimate pre-reg state because pre-registration locks methodology, not implementation completeness. SAP S5 is the qualification gate for any FUTURE CLI added beyond this V1 matrix. Cursor and GUI agentic IDEs are out (not reproducibly automatable).
2. **Benchmark task selection.** Task list refined after lit review; capability tasks include a mix of common-workflow coverage and hardened frontier-difficulty tasks (D4 2026-05-23) so H1 has a non-zero denominator.
3. **Model versions.** All seven V1 configurations have CONFIRMED model pins (see `docs/VERSIONS.md`): Claude `opus-4-8` + `sonnet-4-6`, Codex `gpt-5.5` + `gpt-5.4-mini`, agy `Gemini 3.1 Pro (High)` + `Gemini 3.5 Flash (Medium)` + `Claude Sonnet 4.6 (Thinking)`. Fable 5 (released 2026-06-09) was evaluated and not pinned: its subscription inclusion ends 2026-06-22, before the confirmatory collection window (`docs/DECISIONS.md` 2026-06-12 (later)). Adapter implementation for Codex and agy is PIN-AT-START per `docs/VERSIONS.md`.
4. **Publication venue for the writeup.** preprint server and/or relevant research forums; decided before release.

## Pre-registration

Before running ANY experiments, the hypotheses (`HYPOTHESIS.md`) and analysis plan (`docs/SAP.md`) are timestamped and committed to public git history with a tag. That discipline is what distinguishes research from anecdote.
