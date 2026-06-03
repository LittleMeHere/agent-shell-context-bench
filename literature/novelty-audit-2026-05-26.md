# Novelty audit — adversarial pre-registration review

**Date:** 2026-05-26
**Reviewer:** automated novelty-audit sub-agent (general-purpose), adversarial-stance instructions
**Scope:** verify the 5 novelty claims in `lit-review-2026-05-10.md` against literature published in the 15 days since; find anything a hostile reviewer would cite to argue "this is already done."

## Bottom line

**4 of 5 novelty claims hold. Claim 4 (training-corpus shell-language ratio) is partially scooped and needs softening to "supporting analysis" framing.** The bigger risk than scooping is **framing**: OpenAI's December 2025 GPT-5.2-Codex release notes and Anthropic's May 2026 Claude Code v2.1.149/150 release fixes are vendor-side admissions of the cross-OS reliability gap. They strengthen the motivation evidence — *and* a hostile reviewer can argue "the problem is already known and being fixed; what is the contribution?" Defended by: vendors are addressing some surface symptoms; no vendor has published the measurement framework or the cross-context controlled benchmark this study contributes.

## Per-claim verdict

| # | Claim | Verdict | Strongest counter-citation |
|---|---|---|---|
| 1 | No published controlled cross-OS coding-agent benchmark holding agent + task constant | **HOLDS** with insert-"agentic" caveat | IBM Vo/Paulovicks/Sheinin 2024 (arXiv:2405.06807) compares bash + PowerShell across 7 LLMs — but one-shot NL→code, not agentic, runs PowerShell on Linux containers, non-equivalent task sets across shells. Doesn't subsume an agentic apples-to-apples cross-OS study. |
| 2 | Spiral / runaway-execution chain not formally characterized with OS-conditional probability | **HOLDS** | Microsoft Apr 2025 taxonomy still OS-agnostic; Arize 591-incident corpus still not OS-stratified; *Capable but Unreliable* (arXiv:2602.19008) uses Linux-only Toolathlon. Clean gap. |
| 3 | Trap-task / seeded-error design for shell-using coding agents | **HOLDS** with one rename and one disambiguation | (a) **arXiv:2512.23128 already uses the acronym "TRAP"** for web-agent persuasion benchmarks — rename "trap tasks" → "seeded-error tasks" across this study before pre-reg tag. (b) AIShellJack arXiv:2509.22040 runs 314 MITRE-derived prompt-injection payloads on agentic coding editors; tests intentional malicious injection, not accidental recovery escalation. Distinguished in writeup. |
| 4 | bash:PowerShell training-corpus ratio quantified + correlated with downstream failure | **WEAKENED** — demote to "supporting analysis" | The Stack v2 publishes per-language byte counts in `language_stats.csv`; anyone can compute the ratio. IBM 2405.06807 implicitly correlates corpus prevalence with the bash/PowerShell success-rate gap (84% bash vs 64% PowerShell on GPT-4o, different tasks). The novelty claim must be rephrased as "first agentic-setting correlation" rather than "first corpus-ratio quantification." |
| 5 | Anthropic sandboxing (bubblewrap + seatbelt) is Linux/macOS only; native Windows is opt-in preview | **HOLDS — and reinforced** | Claude Code v2.1.149/150 (May 2026) explicitly fixed PowerShell tool exit-code-1 on winget/MS-Store installs and a `cd..`/`cd\`/`cd~`/`X:` permission bypass — concrete evidence of the OS-conditional risk surface this study theorizes about. Strengthens the claim's motivation. Update wording: PowerShell tool is opt-out (not opt-in) on Bedrock/Vertex/Foundry as of v2.1.150. |

## New prior work found (since 2026-05-10)

Not in the existing `lit-review-2026-05-10.md`:

### Direct cross-shell / cross-OS work (the threats)

- **IBM Vo, Paulovicks & Sheinin (2024) — *Execution-Based Evaluation of NL to Bash and PowerShell for Incident Remediation*** (arXiv:2405.06807, May 2024 / Dec 2024 revision). https://arxiv.org/abs/2405.06807. The hostile-reviewer's strongest "this is already done" citation. **Why this study still survives it:**
  1. IBM is one-shot NL→code, not agentic — the spiral / recovery-trajectory phenomenon is invisible to the design.
  2. IBM ran PowerShell on Linux podman containers (RedHat ubi-init), so host OS is held constant, not varied — the actual independent variable in the proposed study is held fixed in IBM's design.
  3. IBM's bash and PowerShell task sets are non-equivalent (50 + 50 vs 25 tasks); the reported gap conflates shell with task difficulty.
  4. This study holds tasks constant across shells and measures agent behavior over multi-turn execution, both of which IBM does not.
  IBM follow-up: arXiv:2506.11237 (LLM-as-a-Judge for NL2Bash refinement) — bash-only, less threatening.

### Adjacent failure-mode work

- **arXiv:2602.19008 — *Capable but Unreliable*.** Canonical path deviation framework for agent reliability failures; uses Linux Toolathlon trajectories only; doesn't condition on OS. Cite as adjacent prior framework; not a scoop.
- **arXiv:2509.25370 — *Where LLM Agents Fail (AgentDebug)*.** Memory / reflection / planning / action / system taxonomy; OS-agnostic.
- **arXiv:2508.11027 — *Hell or High Water*.** Agentic recovery from external failures; adjacent; not OS-stratified.
- **arXiv:2601.06112 — *ReliabilityBench*.** Production-like stress conditions across scheduling / travel / customer support / e-commerce. Not OS-conditional; not shell-using coding agents.

### Adversarial prompt / red-team work for shell-using agents

- **arXiv:2509.22040 — *Your AI, My Shell: Prompt-Injection Attacks on Agentic Coding Editors (AIShellJack)*.** 314 attack payloads, up to 84% attack success rate on Copilot / Cursor. Tests intentional malicious injection, not accidental escalation. Must be distinguished in writeup to forestall reviewer conflation.
- **arXiv:2512.23128 — *It's a TRAP!* (Task-Redirecting Agent Persuasion)** for *web* agents (Gmail, Calendar, LinkedIn, Amazon). Uses the acronym "TRAP." Forces the seeded-error rename in this study to avoid acronym collision.

### Vendor confessions of the cross-OS reliability gap

These are not novelty threats — they are motivation evidence:

- **OpenAI — *Introducing GPT-5.2-Codex* (Dec 18, 2025).** https://openai.com/index/introducing-gpt-5-2-codex/. Verbatim per third-party mirror: "targeted optimizations for native Windows agentic usage" + "improves general terminal reliability across Bash, PowerShell, and other shells when the model needs to run commands." A vendor stating the gap was real before December 2025.
- **Anthropic — Claude Code v2.1.149 / v2.1.150 (May 2026).** Fixed (a) PowerShell tool failing with exit code 1 on winget/MS-Store-installed pwsh, (b) a PowerShell permission bypass where `cd..` / `cd\` / `cd~` / `X:` built-in functions changed the working directory undetected, letting subsequent commands read outside the workspace. Both are concrete evidence of the OS-conditional risk surface this study studies.

### Training-corpus work

- **The Stack v2 `language_stats.csv`** (BigCode, HuggingFace). https://huggingface.co/datasets/bigcode/the-stack-v2/blob/main/language_stats.csv. Publishes per-language byte counts including Shell, Bash, PowerShell. **Researcher should pull this file and compute the bash:PowerShell byte ratio before publication** — defuses the strongest version of the Claim 4 critique.
- **arXiv:2601.06419 — PSSec / SecGenEval-PS.** PowerShell-specific LLM security benchmark; doesn't do cross-shell ratio analysis.
- **NDSS 2026 — *Local LLMs for NL2Bash: A Large-Scale Open-Source Study*.** https://www.ndss-symposium.org/wp-content/uploads/lastx2026-49.pdf. Bash-only.
- **NAACL 2025 — *LLM-Supported NL to Bash Translation* (arXiv:2502.06858).** Bash-only.

### Industry framing collision

- **The New Stack — *Avoiding the AI Agent Reliability Tax: A Developer's Guide*.** https://thenewstack.io/avoiding-the-ai-agent-reliability-tax-a-developers-guide/. Uses "reliability tax" framing in agent context. No conflict with this study's "PowerShell tax" framing but worth knowing for collisions.

## Required phrasing fixes before pre-registration tag

| Current phrasing in study docs | Problem | Suggested wording |
|---|---|---|
| "No one has published a controlled benchmark comparing AI coding agent reliability across OS/shell environments" | IBM 2405.06807 does benchmark across shells (one-shot, not agentic) | "No one has published a controlled **agentic** benchmark holding agent + task constant across OS/shell environments; IBM (arXiv:2405.06807) compares one-shot NL→code across bash and PowerShell but uses non-equivalent task sets and executes both on Linux." |
| "Trap-task design ... is not a published evaluation pattern for shell-using coding agents" | arXiv:2512.23128 owns the "TRAP" acronym for web-agent adversarial prompts; AIShellJack arXiv:2509.22040 runs adversarial prompts on coding editors but for intentional injection | **Rename "trap tasks" → "seeded-error tasks"** across `RESEARCH_PLAN.md`, `HYPOTHESIS.md`, `SAP.md`, `tasks/trap/T*.yaml` (rename dir to `tasks/seeded_error/` or keep dir, rename concept in docs), `DECISIONS.md`. Add explicit distinction: "Adversarial prompt benchmarks exist for prompt-injection in coding editors (AIShellJack, arXiv:2509.22040) and for persuasion-driven redirection in web agents (TRAP, arXiv:2512.23128); the seeded-error design here differs because the agent's failure is **accidental** (triggered by a deliberately-broken environment, not by malicious prompt content) and the measurement target is the **recovery trajectory**, not the initial breach." |
| "No published study quantifies the bash:PowerShell ratio in training corpora and correlates it with downstream shell-command failure rates" | The Stack v2 publishes per-language byte counts; IBM 2405.06807 implicitly correlates corpus prevalence with the bash/PowerShell gap | "While The Stack v2 publishes per-language byte counts, no peer-reviewed paper has computed the bash:PowerShell ratio and statistically tested its correlation with downstream **agentic** shell-command reliability. IBM 2405.06807 reports a ~20-point bash-PowerShell success-rate gap in one-shot NL→code, consistent with corpus prevalence, but does not establish causation or replicate in an agentic setting." |
| "Native Windows is opt-in preview" (Anthropic) | Strictly true at writing time, but Claude Code v2.1.150 flipped PowerShell tool to **opt-out** on Bedrock/Vertex/Foundry | "Native Windows PowerShell support is opt-out (not opt-in) as of Claude Code v2.1.150 on Bedrock/Vertex/Foundry; it shipped as opt-in preview prior to May 2026. Sandboxing (bubblewrap + seatbelt) remains Linux/macOS-only." |

## The single citation a hostile reviewer would lead with

**Vo, Paulovicks & Sheinin (2024), arXiv:2405.06807** — IBM, *Execution-Based Evaluation of Natural Language to Bash and PowerShell for Incident Remediation.*

A hostile review angle the authors should be ready to respond to:

> *"This work is largely subsumed by Vo, Paulovicks & Sheinin (2024), which already benchmarks LLM bash and PowerShell generation with execution-based evaluation across seven models. The 'spiral' framing is informal terminology for what Microsoft (2025) calls 'runaway execution' and Arize (2025) reports at 5.1% incidence. The seeded-error task pattern is adjacent to AIShellJack (2025), which already runs adversarial command prompts on agentic coding editors. The Windows reliability gap was acknowledged and addressed by OpenAI in GPT-5.2-Codex (Dec 2025) and by Anthropic's Claude Code v2.1.150 (May 2026), making this contribution descriptive of an already-solved problem."*

Defenses available (in priority order):

1. **IBM is one-shot, single-turn, no execution-feedback loop.** The paper benchmarks code *generation*, not agent *behavior under repeated failure*. The whole spiral phenomenon is invisible to that design.
2. **IBM ran PowerShell tasks on Linux podman containers** (RedHat ubi-init), not on Windows. The host OS context — the actual independent variable in this study — is held constant in IBM's design.
3. **IBM's bash and PowerShell task sets are different** (50 + 50 vs 25 tasks), so the reported success-rate gap conflates task difficulty with shell. This study holds tasks constant across shells.
4. **OpenAI and Anthropic announcements assert improvement without measuring the gap.** This study provides the missing measurement instrument — published vendor announcements specifically saying "we improved Windows reliability" presuppose a measurable gap; this benchmark is what would let one verify or refute such improvement claims.
5. **AIShellJack tests intentional malicious injection.** The seeded-error pattern here measures accidental escalation from environment friction. Different threat models, different mitigations.

## Limitations of this audit (the things the reviewer might find that I didn't)

- arXiv PDFs frequently 403'd to WebFetch; some abstract-only reads.
- OpenAI blog returned 403 on direct fetch — GPT-5.2-Codex quotes came via third-party mirror; researcher should re-verify the primary URL in a browser.
- The Stack v2 `language_stats.csv` returned 401 (HuggingFace auth required); researcher should pull this in browser/with auth and compute the bash:PowerShell ratio directly before publication.
- Non-English coverage was thin (three queries in JP/DE/ZH each); no Korean or French searches at all. A foreign-language paper that scoops a claim is possible but not surfaced.
- Paywalled venues (ACM Digital Library, IEEE Xplore, Springer) were not attempted; a 2026 ACM ICSE or FSE paper on cross-shell agent reliability could exist behind a paywall.
- OpenReview / workshop tracks were not searched directly — relied on arXiv preprints.
- Twitter / X / Hacker News practitioner discourse since 2026-05-10 was not searched.

## Recommended changes propagated from this audit (pre-tag work)

1. **Rename "trap tasks" → "seeded-error tasks"** across `RESEARCH_PLAN.md`, `HYPOTHESIS.md`, `SAP.md`, the `tasks/trap/*.yaml` directory (rename dir or keep dir name and rename concept in docs), `DECISIONS.md`, novelty audit. **Queued for next pre-tag pass — not done in 2026-05-26 session for scope.**
2. **Update Claim 1 phrasing** to insert "agentic": "no controlled **agentic** cross-OS coding-agent benchmark holding agent + task constant" + IBM citation acknowledging the one-shot prior.
3. **Demote Claim 4 framing** in `RESEARCH_PLAN.md` "Why this matters" and any writeup outline — corpus-ratio analysis becomes supporting analysis, not headline contribution.
4. **Update Claim 5 wording** to reflect Claude Code v2.1.150 opt-out-by-default on Bedrock/Vertex/Foundry.
5. **Pull The Stack v2 `language_stats.csv`** in browser with HuggingFace auth before publication; compute the bash:PowerShell ratio; add as supporting figure.
6. **Verify GPT-5.2-Codex quotes via primary OpenAI URL** in a browser; quote verbatim in TOS_COMPLIANCE.md and the writeup motivation section.
7. **Add explicit AIShellJack and TRAP distinctions** to the writeup's seeded-error design rationale (intentional injection vs accidental escalation; web agents vs shell coding agents).

## Cross-references

- Original lit review: [`lit-review-2026-05-10.md`](lit-review-2026-05-10.md)
- Operative pre-registration: `../benchmark/HYPOTHESIS.md` and `../benchmark/docs/SAP.md`
- Decision log entries for related scope choices: `../../../docs/DECISIONS.md` (2026-05-25 (later), 2026-05-25 (latest), 2026-05-26)
