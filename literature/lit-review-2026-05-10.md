# Literature Review — Agent Reliability Across OS Environments
**Date:** 2026-05-10
**Reviewer:** automated lit review agent, scope-bounded (20-call WebSearch/WebFetch budget)

## Bottom line for the researcher

**No one has published a controlled benchmark comparing AI coding agent reliability across OS/shell environments (Windows/PowerShell vs macOS/zsh vs Linux/bash).** The major agent benchmarks — SWE-bench, Terminal-Bench, AgentBench, METR's HCAST, RE-Bench, TheAgentCompany — all run inside Linux Docker containers and explicitly use bash. Windows Agent Arena exists, but it benchmarks GUI/desktop multimodal agents on Windows in isolation; it does not run the same task suite on multiple OSes for comparison. The "spiral" failure mode (syntax error → fix attempt → broaden → catastrophic action) is recognized informally — it appears in vendor incident reports (Gemini CLI July 2025, Replit July 2025, Claude Code rm -rf bug) and in Microsoft's April 2025 *Taxonomy of Failure Modes in Agentic AI* whitepaper as "runaway execution" / "cascading errors" — but no peer-reviewed work decomposes the OS-conditional probability of these escalations. This is a clear, defensible gap.

## Tier 1 findings

### Existing OS-comparison benchmarks

- [SWE-bench / SWE-bench Verified](https://www.swebench.com/) — HIGH confidence
  - Real GitHub issues, model produces a patch, evaluated in containerized environments. Verified subset = 500 human-validated instances co-developed with OpenAI.
  - Does NOT vary OS/shell. Everything runs in Linux Docker; results are not stratified by host OS or shell.
- [Terminal-Bench 2.0 (tbench.ai)](https://www.tbench.ai/) and [arXiv:2601.11868](https://arxiv.org/abs/2601.11868) — HIGH confidence
  - 89 hard, interactive terminal tasks; agents call a "headless terminal" tool and complete tasks "using only Bash commands." Docker-based.
  - Does NOT include PowerShell, cmd.exe, or Windows-native tasks. Single shell by design.
- [AgentBench (THUDM, ICLR'24, arXiv:2308.03688)](https://arxiv.org/abs/2308.03688) — HIGH confidence
  - 8 environments incl. an OS environment; OS environment is Linux/bash.
  - No Windows/PowerShell variant.
- [METR public-tasks + HCAST + RE-Bench](https://metr.org/hcast.pdf) and [GitHub METR/public-tasks](https://github.com/METR/public-tasks) — HIGH confidence
  - Tasks are pre-built Docker images; agent gets bash access; 6 independent runs per task. Used in METR's "time horizons" measurements of frontier models.
  - All Linux. METR has not published an OS-comparison study.
- [TheAgentCompany (arXiv:2412.14161)](https://arxiv.org/html/2412.14161v2) — MED confidence
  - Simulates a software company workflow. Linux-based sandbox.
  - No OS comparison.
- [Windows Agent Arena (Microsoft, arXiv:2409.08264)](https://arxiv.org/abs/2409.08264) — HIGH confidence
  - 154 tasks across browser, docs, video, coding, Windows apps. Best agent: 19.5% vs human 74.5%.
  - Crucially: Windows-only. Built as a sibling of OSWorld but does NOT run the same task set on multiple OSes. Closest neighbor to our research, but doesn't answer the comparison question.
- [OSWorld](https://leaderboard.steel.dev/registry/benchmarks/osworld) — MED confidence
  - 369 desktop tasks across Ubuntu, Windows, macOS. This is the most multi-OS benchmark in print.
  - But: it tests GUI multimodal agents on desktop apps, not coding-agent-in-shell reliability. Tasks differ across OSes; not an apples-to-apples shell comparison.

**Gap our research could fill:** an apples-to-apples coding-agent task suite executed on Windows/PowerShell, Windows/Git Bash, WSL2, macOS/zsh, and Linux/bash, with identical prompts and identical expected behavior, measuring not just success rate but the *qualitative escalation pattern* on failure.

### Failure mode taxonomies

- [Microsoft Security — *Taxonomy of Failure Mode in Agentic AI Systems* (April 2025 whitepaper)](https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Taxonomy-of-Failure-Mode-in-Agentic-AI-Systems-Whitepaper.pdf) and [blog summary](https://www.microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents/) — HIGH confidence
  - Categorizes "novel failure modes unique to agentic AI" including cross-agent communication failures.
  - Does NOT condition failure modes on OS or shell. Treats agents as OS-agnostic.
- [Arize — *Why AI Agents Break: A Field Analysis of Production Failures*](https://arize.com/blog/common-ai-agent-failures/) and [Clyro — *5 AI Agent Failure Modes*](https://clyro.dev/blog/the-5-ai-agent-failure-modes-why-they-fail-in-production/) — MED confidence (industry, not peer-reviewed)
  - Five-mode taxonomy across 591 documented incidents (2023–2026): Context Blindness 31.6%, Rogue Actions 30.3%, Silent Degradation 24.9%, Memory Corruption 8.1%, **Runaway Execution 5.1%**.
  - Runaway Execution = closest published label for the "spiral" pattern. Field notes that it is rare but disproportionately expensive.
  - Does NOT publish OS breakdown of the 591 incidents.
- [Concentrix — *12 Failure Patterns of Agentic AI Systems*](https://www.concentrix.com/insights/blog/12-failure-patterns-of-agentic-ai-systems/) and [NimbleBrain](https://nimblebrain.ai/why-ai-fails/agent-governance/agent-failure-modes/), [MindStudio — *6 Ways Agents Fail*](https://www.mindstudio.ai/blog/ai-agent-failure-pattern-recognition), [Galileo — *7 Failure Modes*](https://galileo.ai/blog/agent-failure-modes-guide) — LOW–MED confidence
  - Industry-blog taxonomies. Mention "retry spiral" / "logic spiral" — agent generates "hundreds of migration approaches targeting the same unsolvable problem." No quantitative analysis.
- [Anthropic — *Agentic Misalignment*](https://www.anthropic.com/research/agentic-misalignment) and [arXiv:2510.05179](https://arxiv.org/abs/2510.05179), [GitHub anthropic-experimental/agentic-misalignment](https://github.com/anthropic-experimental/agentic-misalignment) — HIGH confidence
  - Studies *intentional* misalignment (blackmail, sabotage) under goal conflict, across 16 frontier models.
  - Orthogonal to our concern: this is about deliberate scheming, not unintentional escalation from shell error.

**Gap:** "spiral" / "runaway execution" pattern is observed but not formally characterized. Conditioning it on shell environment is unexplored.

### Training data composition

- [BigCode — The Stack v1/v2](https://huggingface.co/datasets/bigcode/the-stack) — HIGH confidence on existence, LOW on the breakdown
  - Includes both `shell` (bash family) and `powershell` as language tags. Search did not surface the actual file/byte counts per language. **Action item for the researcher: pull these stats directly from the BigCode dataset cards or the StarCoder/StarCoder2 papers.**
  - One paper noted sampling 100k PowerShell scripts from "an original pool of 520k" in The Stack — useful as a rough order-of-magnitude anchor but not a direct ratio.
- [2025 Stack Overflow Developer Survey](https://survey.stackoverflow.co/2025/) and [Technology page](https://survey.stackoverflow.co/2025/technology) — HIGH confidence
  - 49% of developers use Bash/Shell scripting in 2025 (up ~15 pts from 2024); ranked 5th among all languages. Specific PowerShell percentage not surfaced in the search snippets — pull directly from the survey.
  - Indirect support: macOS = 31.8% personal / 33.2% professional dev usage (2024). zsh shipped default since macOS Catalina (2019), so a large fraction of dev shell traffic is bash + zsh.
- [Tiniaco Leyba — *From Corpus to LLM*](https://tiniacoleyba.com/blog/from-corpus-to-llm-how-training-data-shapes-ai-language-models/) — LOW confidence (general)
  - Generic discussion of corpus-shapes-behavior, no PowerShell-specific quantification.

**Gap:** No published study directly quantifies the bash:PowerShell ratio in training corpora and correlates it with agent shell-command accuracy. **This would be a high-value supporting analysis for our paper.**

### Vendor statements (Anthropic / OpenAI / Google on supported envs)

- [Claude Code Advanced Setup](https://code.claude.com/docs/en/setup) and [Sandboxing docs](https://code.claude.com/docs/en/sandboxing) and [Anthropic engineering — Claude Code Sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) — HIGH confidence
  - Sandboxing relies on **Linux bubblewrap and macOS seatbelt**. **Windows is conspicuously absent from the sandboxing implementation.**
  - Native Windows install supports both Git Bash and an opt-in PowerShell tool gated by `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`.
  - Anthropic's own docs implicitly treat Windows as a second-class environment for safe agent execution.
- [GitHub Issue #26006 — Windows can silently use WSL instead of Git Bash](https://github.com/anthropics/claude-code/issues/26006) — HIGH confidence (primary source)
  - Documents the exact failure pattern relevant to our hypothesis: agent mixes WSL and PowerShell+Windows commands across calls, gets confused by inconsistent state. Concrete example: a .NET Framework 4.8 build that Claude could not solve "because it kept trying to install on the wrong platform, or install on the right platform and then check for successful install on the wrong platform."
  - Closed as duplicate — meaning this has been reported multiple times.
- [GitHub Issue #14902 — Native PowerShell install of Claude Code is not viable](https://github.com/anthropics/claude-code/issues/14902) — HIGH confidence
  - Installer reports success but `claude.exe` is never downloaded on PowerShell variant; CMD installer works.
  - Dec 2025; no public Anthropic resolution at time of fetch.
- [GitHub Issue #5723 — Feature Request: Native Support for Windows Terminal/PowerShell](https://github.com/anthropics/claude-code/issues/5723) — MED confidence (didn't fetch but title is diagnostic)
  - Existence of the feature request is itself evidence that native Windows is not first-class.

**Pattern:** Anthropic's product surface, sandboxing, and bug surface all indicate Linux/macOS is the supported happy path; Windows is supported via WSL2 or Git Bash, with native PowerShell as opt-in preview. OpenAI Codex and Gemini CLI vendor statements were not deeply explored — flagging as a follow-up.

## Tier 2 findings

- **WSL2 vs native Windows:** Multiple practitioner write-ups ([claudelab.net](https://claudelab.net/en/articles/claude-code/claude-code-windows-native-wsl2-complete-guide), [Delphi-PRAXiS thread](https://en.delphipraxis.net/topic/14894-claude-code-running-in-wsl2-vs-windows-native/), [DEV Community guide](https://dev.to/xujfcn/claude-code-installation-guide-for-windows-git-path-environment-variables-powershell-wsl-and-1lag), [Morph](https://www.morphllm.com/claude-code-windows)) consistently report "running Claude Code on WSL, the difference from Mac is barely noticeable" and 5–10x perf improvement on file ops when projects live in the Linux FS. None of these are controlled studies, but the convergent qualitative signal is strong. The previously-cited Issue #26006 is the cleanest documented failure mode for the cross-environment confusion case.
- **Shell-safety / containment research:** Anthropic's [sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) (Linux bubblewrap + macOS seatbelt) is the most relevant production safety primitive; reduces permission prompts by 84% in internal use. [Prompt Injection Attacks on Agentic Coding Assistants (arXiv:2601.17548)](https://arxiv.org/html/2601.17548v1) is adjacent — systematic vulnerability analysis of skills/tools/protocol layers but not OS-conditional.
- **Shell-LLM academic adjacency:** [ARACNE (arXiv:2502.18528)](https://arxiv.org/abs/2502.18528), [RapidPen (arXiv:2502.16730)](https://arxiv.org/abs/2502.16730), [Guardrails for an LLM-Powered Natural Language Shell (arXiv:2506.13028)](https://arxiv.org/pdf/2506.13028) all evaluate LLMs as shell operators but exclusively in Linux/bash penetration-testing contexts. None compare shells.
- **Practitioner discourse:** Search did not surface a clean, citable Theo / swyx / Karpathy quote on Mac-vs-Windows for AI coding agents. Karpathy's December 2025 "coding agents basically didn't work before December" tweet ([x.com/karpathy](https://x.com/karpathy/status/2026731645169185220)) is widely cited but environment-agnostic. **Gap: more targeted social-media archaeology needed.**

## Tier 3 findings

- **Hardware (Mac vs NVIDIA for local LLM):** Apple Silicon's unified memory wins for >24 GB models (M3 Max 96 GB runs 70B Q4 at 8–12 tok/s); NVIDIA RTX 4090 wins 2–3x throughput for ≤24 GB models. See [SitePoint Mac vs PC 2026](https://www.sitepoint.com/local-llm-hardware-requirements-mac-vs-pc-2026/) and [Julien Simon — What to Buy for Local LLMs (April 2026)](https://julsimon.medium.com/what-to-buy-for-local-llms-april-2026-a4946a381a6a). Useful "should I switch to a Mac" framing but tangential to the reliability hypothesis.
- **"AI deletes my repo" incidents:**
  - [Gemini CLI file deletion (July 2025)](https://incidentdatabase.ai/cite/1178/) and [Winbuzzer coverage](https://winbuzzer.com/2025/07/26/googles-gemini-cli-deletes-user-files-confesses-catastrophic-failure-xcxwbn/) — **occurred on Windows/PowerShell.** Failure pattern: hallucinated successful `mkdir`, then cascaded `move` operations that overwrote files. Agent confessed: "I have failed you completely and catastrophically." Strongest single anecdote supporting the hypothesis that the spiral pattern is OS-conditional.
  - [Replit AI agent dropped production DB (July 2025)](https://incidentdatabase.ai/cite/1152/) — environment was Replit's hosted Linux container; counterexample showing the spiral is *not exclusively* Windows.
  - [Claude Code rm -rf home directory bug (byteiota)](https://byteiota.com/claude-codes-rm-rf-bug-deleted-my-home-directory/) — bug-driven, not spiral-driven.
  - [Amazon March 2026 outage](https://towardsdatascience.com/the-reality-of-vibe-coding-ai-agents-and-the-security-debt-crisis/) — referenced in industry coverage as AI-assisted deployment causing 6-hour Amazon.com outage. **Could not verify primary source in this review.**

## What's new about our proposed research

Based on this review, the literature has established:
1. AI agents have well-documented failure modes (Microsoft taxonomy, Arize 591-incident field study).
2. AI agents have catastrophic-action incidents (Gemini CLI, Replit, Claude Code rm -rf).
3. There is informal practitioner consensus that WSL2/Mac/Linux is more reliable than native Windows for Claude Code.
4. Vendor sandboxing (Anthropic) is implemented for Linux + macOS but not Windows.

The literature has NOT established:
1. **A controlled benchmark holding the agent and task constant while varying the host execution context.**
2. **A quantified link between training-corpus shell-language imbalance and downstream shell-command failure rates.**
3. **A formal characterization of the syntax-error → broaden → catastrophic-action escalation chain ("spiral") and whether its trigger probability differs across OSes.**
4. **An OS-stratified breakdown of the major incident corpora (e.g., the Arize 591 incidents).**

Our novel contribution is the controlled cross-context benchmark + spiral-pattern characterization.

## Recommended primary sources to read in full

1. **Microsoft — *Taxonomy of Failure Mode in Agentic AI Systems* (April 2025 whitepaper)** — closest published taxonomy. Adopt its vocabulary so our spiral pattern slots in cleanly. https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Taxonomy-of-Failure-Mode-in-Agentic-AI-Systems-Whitepaper.pdf
2. **METR HCAST paper** — methodology template for measuring agent capability with statistical rigor. https://metr.org/hcast.pdf
3. **Terminal-Bench 2.0 (arXiv:2601.11868)** — protocol most analogous to what we need; we extend by varying the shell. https://arxiv.org/abs/2601.11868
4. **Windows Agent Arena (arXiv:2409.08264)** — only published Windows-specific agent benchmark; closest neighbor. https://arxiv.org/abs/2409.08264
5. **SWE-bench Verified writeup (OpenAI)** — methodology for human-validated subset selection. https://openai.com/index/introducing-swe-bench-verified/
6. **Anthropic — Claude Code Sandboxing engineering blog** — documents that the safety boundary itself is Linux/macOS-only. https://www.anthropic.com/engineering/claude-code-sandboxing
7. **GitHub Issue anthropics/claude-code#26006** — the cleanest existing primary-source description of the failure mode our research will quantify. https://github.com/anthropics/claude-code/issues/26006
8. **Arize — *Why AI Agents Break: A Field Analysis of Production Failures*** — 591-incident corpus; useful context and a possible target for re-analysis with OS stratification. https://arize.com/blog/common-ai-agent-failures/
9. **Anthropic — *Agentic Misalignment* (arXiv:2510.05179)** — methodology template for stress-testing agents with controlled scenarios. https://arxiv.org/abs/2510.05179
10. **2025 Stack Overflow Developer Survey** — primary source for shell-usage demographics. https://survey.stackoverflow.co/2025/

## Methodological precedents to consider

- **Terminal-Bench's Terminus 2 scaffold:** single tool, headless terminal, agent issues commands. We can fork this scaffold to swap bash → PowerShell as the only changed variable. This is the cleanest experimental design path.
- **METR's "6 independent runs per task":** addresses stochasticity; an analogous repeat-trial convention is adopted in the SAP.
- **SWE-bench Verified's human-validation pipeline:** for our task suite, every task should be human-verified to be solvable on every shell we test, otherwise success-rate comparisons are confounded.
- **Anthropic Agentic Misalignment's controlled-scenario harness:** for measuring spiral escalation, we likely need pre-seeded "trap" tasks where a syntax error is inevitable, and we score what the agent does next.
- **Windows Agent Arena's Docker + Azure VM scaling:** model for running a multi-OS benchmark at reasonable throughput.
- **Arize incident-corpus framing:** complement the controlled benchmark with a meta-analysis of public incidents stratified by OS.

## Limitations of this review

- 20-call budget; spent 14 search/fetch calls + 1 directory-prep + 1 write. Did not deeply explore OpenAI Codex docs, Gemini CLI docs, or any X/Twitter primary sources.
- BigCode "The Stack" actual byte/file counts for `shell` vs `powershell` were not pulled directly — only inferred from one paper's sampling note (100k of 520k PowerShell). The researcher should query the dataset card directly.
- 2025 Stack Overflow Survey PowerShell-specific percentage not extracted in search snippets; the underlying survey page should be loaded.
- Did not verify the Amazon March 2026 outage primary source; it appeared in one industry blog and warrants confirmation before being cited in the paper.
- Did not search for content behind paywalls (no Nature, Science, ACM Digital Library hits attempted).
- No X/Twitter primary sources retrieved (skipped the 402 fallback because budget was tight and the formal-source signal was already strong).
- Search snippets sometimes summarize without quoting; quotations attributed above are from the snippet text returned by WebSearch and were not all independently fetched and verified at primary URLs. Treat the 4 WebFetched sources (Issues #26006, #14902; Anthropic sandboxing blog; Gemini incident DB) as the highest-confidence primary citations.
- Did not look for German/Chinese/Japanese-language coverage which sometimes contains practitioner detail missing from English sources.
