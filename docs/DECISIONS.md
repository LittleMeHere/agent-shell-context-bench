# Decisions log — agent-shell-context-bench

This file is a dated record of the methodology development process for
`agent-shell-context-bench` in the period leading up to the
`pre-registration-v1` git tag. It captures decisions, alternatives
considered, supersessions, exploratory framings that the researcher later
refined, and same-day iterations.

**The authoritative locked methodology lives in `HYPOTHESIS.md`,
`docs/SAP.md`, and `RESEARCH_PLAN.md` at the `pre-registration-v1` tag
commit; this file documents how that methodology evolved.** Post-tag
methodology deviations are recorded in `DEVIATIONS.md`, not here — that
boundary is the discipline of pre-registration.

This is a **development-log** shape rather than a traditional Architecture
Decision Record (one-decision-per-entry, locked-once-accepted). It is
intentional: solo-researcher-plus-agents methodology work iterates rapidly
in the pre-tag period, and the iteration record itself is informative
about the research process. Reviewers should expect to see dated iteration
in the days leading up to the tag; some entries record analyses or
exploratory framings the researcher later refined rather than confirmed
decisions — those are flagged inline when surfaced, or noted in
subsequent superseding entries. The locked methodology is in the named
files above; this file is the iteration record.

This file is also the **extraction-safe subset** of the upstream decision
log. Documents inside `benchmark/` (SAP.md, HYPOTHESIS.md, VERSIONS.md,
RESEARCH_PLAN.md, harness source files) cite `docs/DECISIONS.md` relative
to the `benchmark/` root; that citation must resolve whether a reader is
browsing this folder inside the parent project or through a standalone
extracted repo. This file is the resolution target.

The authoritative super-set (which also includes project-strategy entries
unrelated to this benchmark) lives in the upstream working tree this file
is extracted from. Whenever an entry below is amended in the super-set,
this file is updated in lockstep. Original-dated entries are preserved
verbatim — never silently rewritten — so a reader inspecting the
`pre-registration-v1` tag sees what was committed when.

Entry format: each entry is dated. When a decision is reversed, add a
new entry — don't delete the old one.

---

## 2026-05-17 — PowerShell-tax: power-analysis fix (option a + d)

Context: the computed a-priori power analysis (`scripts/power_analysis.py`, results in `docs/SAP.md`) showed the originally pre-registered design — fixed 6 trials/cell, Bonferroni α=0.005 across 10 configs — is adequately powered only for large effects (Linux failure ≳0.30 with a true 1.5x gap) and badly underpowered for the small absolute gaps a 1.5x ratio implies at low base rates. Found BEFORE pre-registration, which is the point of doing it first.

Considered: (a) pooled-primary test + FDR instead of Bonferroni; (b) re-define H1's estimand to pooled absolute difference; (c) more trials/cell; (d) blinded pilot-then-expand as the primary sample-size mechanism.

Picked **(a) + (d)** because:
- (a) The real claim is "PowerShell agents fail more across the board," i.e. the pooled estimate — not 10 independent per-config verdicts. Making the pooled test primary matches the actual claim. Bonferroni at this N suppressed power so far a true effect would be missed; Benjamini–Hochberg FDR controls the false-discovery proportion across the (now secondary) per-config tests without crippling detection.
- (d) The required N depends on the true Linux base failure rate, which is unknown pre-data. Guessing N=6 is a gamble; a blinded pilot that reads only per-environment variance (never the cross-shell outcome) and then sizes the confirmatory run is legitimate pre-registered adaptive design, decided before any data. The SAP already half-allowed this as a contingency; this elevates it to the primary plan.
- (a)+(d) stack: (d) sizes the study to the real effect, (a) makes the success bar achievable at that size. Both are written down publicly before data; the original underpowered tables and the script stay in the repo unedited so the limitation is permanently auditable.

Rejected:
- (b): statistically cleanest but changes what H1 *means* publicly (headline becomes "X points more often" rather than "1.5x"). Not adopted now to keep H1's estimand stable through pre-registration; can be revisited only via a logged deviation if the pilot motivates it.
- (c): cost scales linearly in paid agent calls and buys the least power on the pooled test (the one that matters); the binding constraint is the $50/mo compute budget.

Tradeoff: per-config claims are now explicitly secondary and weaker; the final trial count and total cost are unknown until the pilot completes (acceptable — it's the price of sizing honestly instead of guessing).

Propagated to: `docs/SAP.md` (A1, A2, Stopping rules, power conclusion marked RESOLVED) and `HYPOTHESIS.md` (sample-size/power paragraph). H1's estimand unchanged, so the H1 claim text was not edited.

---

## 2026-05-18 — PowerShell-tax: inter-rater reliability design (layered AI + human anchor)

Context: H2 (the "spiral" claim) rests on subjective A–F coding of failed transcripts. Sole-author coding is the central bias attack ("wrote the hypothesis, then graded the papers"). Original plan offered "Prolific ~$75 second coder OR single-coder + open data."

Considered: (1) Prolific crowd human coder ~$75; (2) single-coder + open data only; (3) one AI coder; (4) two different-lineage AI coders + human expert anchor (+ optional Deep Think audit).

Picked **(4)** because:
- Prolific rejected: a crowd worker can't reliably apply a technical shell-behavior rubric (noise → artificially low κ that would *weaken* H2), and a human coder cannot be re-run → not reproducible, which breaks the open-science spine.
- Reproducibility requires the bulk coder be API-scriptable with a pinned model + published prompt. **Deep Think (researcher's strong system-2 option) is web-only / no API**, so it cannot be the engine; demoted to an optional manual audit of ~20 hardest cases only.
- Two different-lineage AI coders give an AI–AI κ that is reproducible and cross-checks single-model bias; a pre-registered leniency check covers the "Google model goes easy on Gemini-CLI" concern.
- The researcher blind-coding ≥50 as a **human expert anchor** is the load-bearing addition: AI coders can agree with each other and be jointly wrong (shared training bias). Only a shell-literate human tether catches that. This role specifically requires domain expertise the researcher has and a crowd worker lacks — so the lack of a network peer is irrelevant (it had to be the researcher anyway).
- Interpretation rule pre-registered: high AI–AI κ alone is NOT sufficient; if human–AI κ < 0.6, A2 is flagged weakly-measured regardless of AI–AI agreement.

Tradeoff: more setup than a single coder; transcripts can't be perfectly blinded to shell (PowerShell vs bash errors are visually distinct) — disclosed as an explicit limitation with the behavioral-rubric + bias-check mitigation, not papered over. Cost ≈ API pennies, far under the $75 alternative, and fully reproducible.

Propagated to: `docs/SAP.md` S4 (full design + interpretation rule + blinding limitation). HYPOTHESIS.md unchanged (H2 estimand unaffected; this is a measurement-reliability plan, not a hypothesis change).

---

## 2026-05-18 — Agent roster locked: the three major-lab CLIs; Cursor + Antigravity out

Considered: keep all four pre-registered agents (Claude Code, Codex CLI, Gemini CLI, Cursor); include Antigravity (researcher's primary agentic IDE).

Picked **Claude Code + Codex CLI + Gemini CLI** (the CLI agents of the three major model labs — Anthropic, OpenAI, Google) because:
- Clean, defensible scoping: one frontier CLI per major lab; spans the three distinct model lineages that matter.
- **Cursor dropped** — `cursor-agent` headless CLI not installed, researcher uses Cursor minimally, and Cursor is a *harness over the same frontier models* (mostly tests its wrapper, not a distinct lineage). Marginal scientific value did not justify a full adapter + its own real-output parser verification + extra matrix cells/compute.
- **Antigravity excluded from the automated suite** despite being the researcher's primary agentic IDE: re-investigated thoroughly (2026-05-18). VS Code 1.107 Electron fork; its only agent entrypoint (`antigravity chat -m agent`) is GUI-window-bound, NO structured/headless output, cannot run on the headless envs (GitHub Actions macOS, GCP Linux). The agent command stream — load-bearing input to H2 — is never exposed. Architectural, not effort.

Tradeoff accepted:
- External validity: benchmark measures CLI agents, not GUI agentic IDEs (Antigravity/Cursor/Windsurf-class) — i.e. not the researcher's actual primary workflow. Stated as an explicit limitation and reframed as a meta-finding: **the most-used agentic tools are the least observable; reproducible measurement can currently only see CLI agents.**
- Antigravity handling RESOLVED 2026-05-18: v1 is scoped strictly to CLI agents. GUI agentic IDEs get NO v1 arm (not even a manual one) — v1 documents only the limitation + the observability meta-finding. A dedicated future study ("GUI agentic IDE reliability") is parked as RESEARCH_AGENDA Thread 10 (popular IDEs, separate harder methodology). Keeps v1 tight and reproducible.

---

## 2026-05-23 — PowerShell-tax: pre-registration finalization pass (5 coupled decisions)

Context: an independent code review identified 4 blocking + 6 important methodological-vs-implementation gaps (verified against the files). All trace to "claims and measurements aren't aligned yet" — exactly what pre-registration exists to catch. This entry captures the five coupled decisions in the single deliberate finalization pass deferred from 2026-05-18, plus the V1 implementation strategy. Also: CLI versions ticked since last verification (Claude Code 2.1.143→2.1.150, Codex 0.130.0→0.133.0, Gemini CLI 0.42.0→0.43.0); Google announced Gemini CLI is being retired within ~30 days in favor of the Antigravity CLI (`agy` v1.0.2, installed 2026-05-23, PATH-configured).

### D1 — H1 framing: (a + c) hybrid

Considered: (a) realistic-usage (free tool choice, reframe H1 as "Windows context vs Linux context"); (b) controlled-shell via `--disallowed-tools`; (c) per-tool-stratified (free choice, analyze per-shell); (a+c) hybrid.

Picked **(a + c) hybrid**: smoke test (2026-05-18) confirmed Claude Code on Windows has Bash, PowerShell, Write, Edit all available — the agent chose PowerShell but the choice was free. Linux cell would lack PowerShell. Original H1 ("Windows native PowerShell vs Linux native bash") therefore claimed a controlled shell comparison the harness doesn't deliver. (a) restores ecological validity and answers the practitioner question. (c) is collected as a free byproduct once the parser tags each command by tool — gives the academically-defensible per-shell decomposition without changing measurement. Hybrid pre-registers BOTH so neither is post-hoc-cherry-picked.

Rejected: (b) catastrophic ecological validity loss (no real user disables half their agent's tools, likely artificially inflates Windows failure rate); (a) alone loses mechanistic decomposition that lets H4 be investigated; (c) alone makes the headline too technical for practitioner audience and has small-stratum risk in some cells.

Tradeoff: ~1.2x analysis work for ~2x defensibility. SAP must precisely specify both analyses + how they interact.

Propagated to: HYPOTHESIS.md (H1 wording + falsification clause), SAP.md (A1 + new per-tool stratified secondary), RESEARCH_PLAN.md (both copies).

### D2 — Windows shell: PowerShell 5.1 only for V1

Considered: (i) PS 5.1; (ii) pwsh 7.5.5; (iii) both as separate cells.

Picked **(i) PS 5.1 only**: verified 2026-05-23 PS 5.1 present at `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` v5.1.26100.8457 on this Windows 11 Home machine. It ships with every Windows install; pwsh 7+ is opt-in. PS 5.1 IS the modal Windows experience. T01 traps as designed on PS 5.1 (no `&&` support); on pwsh 7.5.5 (which DOES support `&&` since v7.0) T01 fails to trap — reviewer correctly flagged. Pinning to PS 5.1 salvages T01 + most of the planned trap suite.

Rejected: (ii) tests power-user not modal-user, several traps need redesign; (iii) 25% scope expansion + doubles trap-audit work + expands IRR coding ~25%. Tempting but dilutes V1.

Tradeoff: V1 cannot make the "even with pwsh you're stuck" claim. The question "does upgrading to pwsh 7+ close the gap?" is genuinely interesting and parked in RESEARCH_AGENDA as a future-thread study.

Propagated to: RESEARCH_PLAN.md environments table, VERSIONS.md Windows shell PIN, `PowerShellEnvironment` (pin `powershell.exe` not `pwsh.exe`), T01 `trap_design_note` (remove pwsh-7 ambiguity).

### D3 — Model matrix: 6 configs (3 CLIs × 2 tiers); V1 data collection covers Claude only

Considered: 1/2/3 tiers per CLI; fully heterogeneous.

Picked **6 configs (2 tiers × 3 CLIs)**: catches the "best vs cheap" decision dimension users actually face; doesn't blow up the matrix.

V1-ready (adapter built, parser verified):
- **Claude Code 2.1.150:** `claude-opus-4-7` + `claude-sonnet-4-6`

V2 PIN-AT-START (adapter not yet built):
- **Codex 0.133.0:** `gpt-5.5` (frontier, xhigh default) + `gpt-5.4-mini` (cheap). Models verified from `~/.codex/models_cache.json` 2026-05-23.
- **Antigravity CLI 1.0.2 (`agy`):** models TBD when adapter work begins. `agy --help` confirms headless mode (`-p / --print`) + `--dangerously-skip-permissions`. Unverified: model pinning mechanism (no `--model` in top-level help), output format (stream-json availability), session persistence behavior. V2 adapter work blocks on these checks. If agy lacks stream-json, Gemini-lineage cell becomes a documented external-validity limitation rather than a deviation.

Tradeoff: V1 data collection is Claude-only because Codex and agy adapters don't exist yet — pre-reg locks the full matrix but only Claude cells are immediately runnable. Antigravity reproducibility risk (Gemini CLI sunset + agy's unverified gaps) is real and disclosed up front.

**Superseded 2026-05-25:** the V1 primary confirmatory matrix was narrowed
to Claude Code × two tiers only (`claude-opus-4-7`, `claude-sonnet-4-6`).
Codex and Antigravity were moved to SAP S5 extension-candidate status —
not V1 primary — because their adapters / parsers / harnesses are not
qualified for H2/H4 measurement. See the 2026-05-25 entry in
`VERSIONS.md` "Change log" for the propagation, and the
"Configuration eligibility" section in `docs/SAP.md`. The full 6-config
matrix remains the V2 ambition; V1 measurement is scoped to what is
actually measurable.

Propagated to: HYPOTHESIS.md (config count "10" → "6"), SAP.md (4 occurrences), scripts/power_analysis.py (comments), RESEARCH_PLAN.md agents table (Gemini CLI → Antigravity CLI with transitional-CLI note), VERSIONS.md PIN-AT-START rows.

### D4 — Capability-task hardening: (γ) harden some + document the rest

Considered: (α) harden all to frontier difficulty; (β) acknowledge H1 measured primarily on traps; (γ) mix.

Picked **(γ)**: C01 (5-deep dir tree) was trivially completed by Sonnet-4.6 in 21.9s in the smoke trial — most simple cap tasks will be 0/6 failure across all cells, making H1 ratio undefined (division by zero). Pure (β) leaves H1 entirely trap-driven; if some traps don't trap on PS 5.1, effective N shrinks dangerously. 3-4 genuinely-hard cap tasks (candidates: complex git rebase conflict, peer dep conflict, multi-file refactor with renames, platform-specific build/test) give H1 a non-zero denominator without abandoning the "common-workflow coverage" angle of the easier ones.

Tradeoff: more authoring work; writeup must distinguish "coverage-of-common-tasks" cap tasks from "designed-to-stress-the-frontier" hardened cap tasks so readers don't conflate the two.

Propagated to: tasks/capability/ — new YAMLs with explicit difficulty annotation in `notes`. RESEARCH_PLAN.md benchmark-suite section updated for two-tier cap-task structure.

### D5 — Escape detection: (I) canary sentinels

Considered: (I) canary sentinels at known external paths; (II) Docker/sandbox VM; (III) drop `--dangerously-skip-permissions`.

Picked **(I) canary sentinels**: reviewer correctly flagged that `FilesystemSnapshot.escaped_paths` is declared but never populated; `local_snapshot()` only walks `root.rglob('*')`. With `--dangerously-skip-permissions` the agent can write anywhere on the host and the snapshot is blind to it — making rubric code E (catastrophic) invisible exactly where it matters most. Canary sentinels are the cheapest fix that closes the blind spot WITHOUT changing what we measure: place known files at sandbox-parent + %USERPROFILE%\.canary_* + %TEMP%\canary_*; hash before, check after; populate `escaped_paths` from any diff.

Rejected: (II) heavy infrastructure that may change agent behavior + slows trials; (III) self-defeating — removes the agent's ability to take the destructive actions H2 is designed to measure.

Tradeoff: detects writes to canary paths only, not arbitrary paths — disclosed as residual limitation. Acceptable because (a) destructive actions tend to hit common paths, (b) most spirals cascade through known paths, (c) strict improvement over zero detection.

Propagated to: `EnvironmentAdapter` base contract gains `set_canaries()` / `check_canaries()`; `PowerShellEnvironment` implements concrete Windows canary paths; `fs.diff_snapshots()` already reads `escaped_paths` correctly (no change); new `tests/test_canary_detection.py`.

### V1 strategy (β): lock plan today, build incrementally

Considered: (α) build Linux/GCP env adapter (and optionally Codex adapter) BEFORE V1 tag; (β) tag full methodology today, build remaining adapters/environments incrementally, defer data collection until matched-pair env coverage exists.

Picked **(β)**: pre-registration is about locking methodology BEFORE data is seen, not about implementation completeness. The discipline matters more than data-start speed. Implementation is fluid post-tag — harness bugs can be fixed freely, new adapters/environments can be added, tests can be expanded, log schema can grow additively. Only methodology (hypotheses, SAP, task definitions, model pins, environment matrix, rubric, IRR design) is locked. Antigravity CLI's unverified gaps make Gemini-cell timing genuinely uncertain — (β) makes that natural (V2 work item) rather than forced (V1 dependency).

Rejected: (α) adds 4-8 hours of Linux env adapter work today; pushes tag by 1-2 days; mixes implementation pressure with the methodology-finalization pass.

Tradeoff: "first results" timeline gates on when matched-pair env coverage exists (likely 1-3 weeks). Pre-reg commits to scope (3 CLIs × 2 tiers × 4 envs × 19 tasks) that may not all be reached — honest scope-trimming via DEVIATIONS.md is allowed; silent abandonment is not.

**Superseded 2026-05-25:** the V1 pre-reg no longer commits to the
3-CLI primary matrix. The primary confirmatory scope is Claude Code × two
model tiers, with Codex and Antigravity retained only as SAP S5 extension
candidates until measurement-qualified. The 2026-05-23 text remains here
as audited history, not the current V1 scope.

Propagated to: tag scope statement enumerates "V1 implementation ready" vs "V2 implementation pending" cells explicitly. Post-tag harness work proceeds without methodological gating.

---

## 2026-05-25 — V1 primary matrix narrowed to Claude Code only

Context: pre-registration finalization review surfaced that Codex and Antigravity CLI cells (D3, 2026-05-23) had not yet been measurement-qualified — adapter not written, transcript parser not verified, headless output not characterised. Cutting `pre-registration-v1` with those rows still PIN-AT-START would lock a measurement promise for surfaces whose harness behaviour is unverified.

Considered: (α) defer the tag until all six configs are measurement-qualified; (β) tag now with Codex / Antigravity as **extension candidates** under SAP S5, primary inference scoped to qualified configs only.

Picked **(β)** because:
- The pre-reg's job is to lock methodology that is actually measurable. Promising H1-H4 inference for a config whose stdout/stderr surface has not been qualified is a measurement claim the harness cannot honour.
- Extension promotion is a clean, pre-registered mechanism: a future tag (`pre-registration-v1.1` or `v2`) can promote an extension cell to primary status once its adapter is built and qualified through SAP S5. This is the same discipline as DEVIATIONS.md — transparency about what changed and why.
- (α) would either compress adapter-qualification work into a multi-week pre-tag window, or push the tag indefinitely. Both compromise the discipline of "tag before any data is seen".

V1 primary confirmatory matrix:
- **Claude Code × `claude-opus-4-7`** — primary
- **Claude Code × `claude-sonnet-4-6`** — primary

V1 extension candidates (excluded from primary H1/H2/H3/H4 pooled inference):
- Codex CLI × `gpt-5.5`, Codex CLI × `gpt-5.4-mini`
- Antigravity CLI (`agy`) × any model

Tradeoff: pooled-primary H1/H2 inference is over a two-config matrix rather than the originally pre-registered six. Mixed-effects random intercepts for "configuration" still apply (the two configs are heterogeneous in cost and capability tier). The "cross-vendor" claim is weakened: V1 cannot make a vendor-comparison claim and explicitly does not. This is now consistent with HYPOTHESIS.md's "What this study does NOT claim" section.

Propagated to: SAP.md "Configuration eligibility" (new section), VERSIONS.md (Codex and Antigravity rows moved to "Extension candidates"), the per-config secondary count in SAP A1 (was 6, now 2).

---

## 2026-05-25 (later) — PowerShell-tax: pre-reg scope correction — methodology-locked vs implementation-pending

Context: an empirical CLI-qualification pass on 2026-05-25 (Claude Code, Codex, Antigravity) settled what each CLI can actually be measured for. Two findings forced a re-examination of the earlier same-day narrowing decision.

First: the earlier 2026-05-25 narrowing entry (in `docs/VERSIONS.md` change log) restricted the V1 primary matrix to Claude Code × {Opus 4.7, Sonnet 4.6} on the grounds that "Codex and Antigravity adapters don't exist yet." On reflection this conflates two distinct things — **methodology locked** vs **implementation pending** — that pre-registration discipline keeps separate. Pre-registration locks the *measurement intent* (hypotheses, outcomes, tests, scope) before any data is seen; it does NOT require the *implementation* (adapters, environment shims, data-collection scripts) to be complete at tag time. The 2026-05-23 D3 entry already had the correct framing: *"pre-reg locks the full matrix but only Claude cells are immediately runnable."* The 2026-05-25 narrowing was a step away from that discipline.

Second: an empirical re-verification of Antigravity (`agy 1.0.2`) on 2026-05-25 found that the persistent transcript at `~/.gemini/antigravity-cli/brain/<conv-id>/.system_generated/logs/transcript_full.jsonl` carries structured `PLANNER_RESPONSE.tool_calls[]` events with `CommandLine`, `Cwd`, and other args — i.e. agy IS measurement-qualifiable, contrary to the earlier "unqualified" assessment. The remaining engineering gaps (prose-encoded `RUN_COMMAND.content`; agent's default Cwd being `~/.gemini/antigravity-cli/scratch/` rather than the harness sandbox) are adapter-implementation work plus pre-registered handling rules, not unresolvable methodology unknowns.

Considered: (α) keep the 2026-05-25 narrowing (Claude-only V1 primary, Codex / agy as extension candidates); (β) restore the full V1 methodological matrix (3 vendors × 2 tiers × multiple envs), with adapter implementation explicitly disclosed as PIN-AT-START / post-tag; (γ) restore the full matrix AND add a same-model harness-control config (Sonnet via agy) to enable model-vs-harness causal attribution.

Picked **(γ)** because:

- **Pre-reg integrity:** Implementation status is *disclosed*, not *locked*. PIN-AT-START is a legitimate pre-reg state for V1 cells whose adapters land post-tag. Restricting pre-reg scope because of unwritten adapters is conflating two separate things and produces a pre-reg that under-claims what we'll actually study.
- **Durability:** Specific model versions (Opus 4.7, Sonnet 4.6, gpt-5.5, Gemini 3.1 Pro) will be deprecated within 12-24 months. What survives the model churn is (a) the failure-mode taxonomy, (b) the methodology, (c) the cross-environment + cross-vendor measurement framework. A 1-vendor V1 produces a much weaker artifact for audience 3 (future replication / AI-reliability research) than a 3-vendor V1 — even if some V1 cells get filled in over weeks rather than days.
- **Headline strength:** "Across three frontier vendors, agents fail Nx more often on Windows" is a meaningfully stronger claim than "Anthropic's models fail Nx more often on Windows." The audience (developers making $7-30K hardware/tooling decisions) needs the cross-vendor framing to draw a useful conclusion.
- **Same-model harness control (the (γ) addition over (β)):** including a single extra config — `agy × Claude Sonnet 4.6 (Thinking)` — enables a clean within-model comparison against `Claude Code × claude-sonnet-4-6`. Without it, the study can observe vendor-level differences but cannot separate *model* from *harness*; with it, the study can pre-register an analysis that attributes the cross-context gap to one or the other (or both, with effect-size shares). This is the kind of causal-attribution finding that turns the writeup from observation into evidence. The cost is one additional row in the matrix: 6→7 configs (+17% trial count); the agy adapter already handles arbitrary models via `settings.json` injection so there is no additional adapter work for the 7th config.

Rejected:
- (α) under-claims and discards the 2026-05-23 D3 reasoning that was correct.
- (β) gets the framing right but misses the cheap harness-vs-model attribution win that (γ) buys for one extra cell.

Tradeoff: more cells = more compute. Budget impact: 7×5×14×N vs the pre-narrowing 6×4×14×N is roughly 2.0x larger. Three responses pre-registered: (i) the blinded-pilot sizing already absorbs N variation; (ii) the existing "under-collected cell" stopping-rule language already covers budget-limited cells with disclosed power; (iii) the researcher may raise the compute cap as a logged DEVIATION if pilot N drives total cost above the published $50/mo. None of these break the pre-reg.

### V1 confirmatory matrix (LOCKED)

**7 model-harness configs × 5 environments × 14 tasks**

Configs (3 vendors × 2 tiers + 1 harness-control):
- Claude Code × `claude-opus-4-7`           (Anthropic frontier)         [adapter CONFIRMED]
- Claude Code × `claude-sonnet-4-6`         (Anthropic workhorse)        [adapter CONFIRMED]
- Codex × `gpt-5.5`                          (OpenAI frontier)            [PIN-AT-START — adapter pending]
- Codex × `gpt-5.4-mini`                     (OpenAI workhorse)           [PIN-AT-START — adapter pending]
- agy × `Gemini 3.1 Pro (High)`              (Google frontier)            [PIN-AT-START — adapter pending]
- agy × `Gemini 3.5 Flash (Medium)`          (Google workhorse)           [PIN-AT-START — adapter pending; label confirmed 2026-05-25 from agy settings UI]
- agy × `Claude Sonnet 4.6 (Thinking)`       (harness-vs-model control)   [PIN-AT-START — adapter pending; settings label CONFIRMED via prior smoke]

Environments (5):
- Windows 11 + PowerShell 5.1                [env adapter CONFIRMED]
- Windows 11 + pwsh 7.5.5                    [PIN-AT-START — subclass of PS env, ~2h implementation]
- Windows 11 + WSL2 Ubuntu 22.04             [PIN-AT-START — env adapter pending]
- Linux native (GCP Ubuntu 22.04)            [PIN-AT-START — env adapter pending]
- macOS (GitHub Actions runner)              [PIN-AT-START — env adapter pending]

Tasks (14): 5 capability + 9 trap, unchanged.

### agy-specific measurement rules (LOCKED with the matrix)

Because agy's default command Cwd is `~/.gemini/antigravity-cli/scratch/` rather than the harness-supplied sandbox, the harness applies the following pre-registered handling — replacing the earlier (incorrect) proposal to invalidate Cwd-non-compliant trials:

1. **Prompt-injected Cwd directive.** Every agy prompt is prepended with `"Use working directory `{sandbox_root}` for all shell and file operations."` This is the *attempt* at sandbox-binding, not the *measurement* of it.

2. **Per-command Cwd tagging.** From each `PLANNER_RESPONSE.tool_calls[i].args.Cwd`, classify the command into `cwd_in_sandbox` / `cwd_in_agy_scratch` / `cwd_elsewhere`. The per-trial compliance rate is reported in the writeup as a finding about agy's prompt-compliance.

3. **H1 binary outcome (agy).** A trial is H1-success only if `success_checks` on the sandbox snapshot pass AND at least the task-completing commands ran with `cwd_in_sandbox`. Commands run in scratch with no sandbox-visible effect = H1-failure (task not completed in the right place). Cwd non-compliance is NOT an "invalid" verdict — the SAP "invalid trial" definition is unchanged and applies only to infrastructure-origin measurement loss.

4. **H2 rubric coding (agy, and all agents).** The rubric is applied to the transcript. Destructive actions in the transcript are coded D/E regardless of WHERE they physically executed — `Remove-Item -Recurse -Force` is rubric code D/E whether it ran in sandbox, scratch, or anywhere else. The transcript carries the agent's intent; the snapshot only catches the consequences.

5. **Additional canary for agy trials.** `agy`-cell trials add `~/.gemini/antigravity-cli/scratch/.pstax_canary_agy_scratch` to the canary path set (in addition to the existing sandbox-sibling / USERPROFILE / TEMP sentinels). Destructive actions targeting scratch are detected via canary change, supplying code-E evidence even when the sandbox snapshot is silent.

### Why this matters

The earlier proposed rule ("Cwd non-compliance → invalid → re-run") would have **destroyed H2 evidence** in the exact cells most likely to produce it: an agy trial that spirals into `rm -rf .` from scratch would have been silently re-run instead of recorded as code E. The rules above preserve the transcript-as-evidence principle that the rest of the SAP already uses.

Propagated to: `docs/VERSIONS.md` (matrix tables, hard-gate language); `docs/SAP.md` (Configuration eligibility reverted to full-matrix; new S6 same-model harness-control subsection; agy-specific rules in the "Outcome construction" and "Invalid trial" definitions); `HYPOTHESIS.md` (config-count language restored); `RESEARCH_PLAN.md` (agents and environments tables).

Status of the 2026-05-25 earlier narrowing entry: superseded by this entry. The original entry is preserved in the VERSIONS.md change log as historical record (per the "never silently rewrite" rule); this entry is the operative scope.

---

## 2026-05-25 (latest) — PowerShell-tax: review-driven finalization pass #2 — H1 split into H1a (cap-only primary) + H1b (full-suite descriptive)

Context: an independent code-review agent ("opencalw") reviewed the
pre-registration drafts on 2026-05-25 and identified six methodological
gaps, of which two are pre-reg-blocking and were resolved in this pass.
This entry captures the H1 split; the four remaining items (H3
operationalization; explicit IRR collapse rule in public SAP; environmental
confounds language audit; canary-implementation status verification) are
each tracked separately or deferred to follow-up passes. Found BEFORE
pre-registration tag, which is the point of the review.

Considered: (α) keep H1 as a single hypothesis on the 14-task aggregate —
defend the trap composition as "principled, not arbitrary" via the existing
cheat-sheet language; (β) drop the trap tasks from H1 entirely and make H1
capability-only; (γ) split H1 into H1a (capability-only primary inferential)
+ H1b (full-suite secondary descriptive, no threshold), keeping the trap-
inclusive estimate reportable but not confirmatory.

Picked **(γ)** because:

- **Defensibility:** the reviewer's hostile-objection framing is correct.
  9 of 14 tasks were hand-authored to fail on PowerShell 5.1 (D2 2026-05-23).
  A pooled primary H1 test on the 14-task aggregate confounds "general
  cross-context reliability gap" (what H1 was claiming) with "agent loses
  on the traps the author designed for it" (which is an H2-mechanism
  finding, not an H1 reliability finding). The reviewer's exact language:
  *"A hostile reviewer will say the benchmark is dominated by hand-authored
  adversarial Windows traps, so of course Windows loses."* Cap-only-primary
  isolates the reliability claim from benchmark composition.

- **Honest match to where design energy lives:** the design record already
  treated H2 as the principal novel claim needing seeded-error depth, while
  H1 needed enough capability-task baseline to establish a non-zero
  denominator. That is incompatible with H1 being a confirmatory primary test
  on the seeded-error-loaded aggregate. The split aligns the inferential
  structure with that methodological distinction.

- **Preserves the trap-inclusive data:** (β) (drop traps from H1 entirely
  without a backup descriptive) would leave readers wanting the trap-
  inclusive number and unable to find it. (γ) keeps it as A1c descriptive
  alongside A1, in the same table, with point estimate and CI but no
  threshold-based "support/reject" decision.

- **Pre-reg integrity:** A1c being strictly descriptive (no threshold)
  forecloses the hostile-reviewer attack *"you renamed H1 to H1b and put it
  second, but you're still claiming the trap-aggregate as a confirmatory
  finding."* The hostile-reviewer test passes: there is no inferential
  threshold on A1c.

Rejected:
- (α) — leaves the contamination attack live. Defending "principled trap
  loading" against a hostile reviewer would consume pages and weaken the
  paper's headline claim. Cheaper to split now than defend later.
- (β) — over-corrects by hiding the trap-inclusive number entirely.
  Readers (and the paper's own H2 section) need the full-suite gap
  visible, even if it's descriptive only.

Tradeoff:
- The cap-only primary has a smaller denominator (5 tasks vs 14), so the
  pilot-sizing formula may derive a larger per-cell N to reach 80% power
  on the H1a-relevant cap-only base rate. The full confirmatory matrix
  still runs all 14 tasks at the same per-cell N (H1b, H2, H4 inherit
  the same N as a side effect). Compute impact is bounded by the existing
  budget-cap clamp in the pilot-sizing rule, and any binding cap is
  reported as "budget-limited" per existing SAP language.
- The headline number is now structurally smaller in magnitude (capability
  tasks are less Windows-hostile than the trap suite), which means H1a is
  *less likely* to support a ≥1.5x ratio than the pre-split H1 was. That
  is the right outcome: the prior likelihood reflected benchmark
  composition; the new likelihood reflects general reliability.
- One small executable change required pre-tag: `scripts/size_from_pilot.py`
  must accept a `--task-class capability` (or equivalent) filter so the
  pilot-sizing inputs (`p̂_pool`, ICC) come from cap-only trials. The SAP
  Stopping-rules text already specifies the cap-only restriction; the
  script update lands as a separate small commit before the
  `pre-registration-v1` tag.

Propagated to: `HYPOTHESIS.md` (H1 split into H1a/H1b; H2 scope clarified
to full-suite at trial level; H3 retargeted to H1a's averaging method;
sample-size/power paragraph updated); `docs/SAP.md` (A1 restricted to
cap-only with new explanatory paragraph; A1c added for H1b full-suite
descriptive; Outcome-construction task-weighting paragraph split into
H1a/H1b/H2 sections; A3 retargeted to H1a; option-(a) restatement
updated; Stopping-rules pilot-sizing inputs restricted to cap-only);
`RESEARCH_PLAN.md` (both copies, H1 statement updated).

Status of related review items (updated 2026-05-26 after a two-layer
pre-registration audit covering HYPOTHESIS / DEVIATIONS / SAP / VERSIONS /
DECISIONS / RESEARCH_PLAN, the 14 task YAMLs, the rubric, and the frozen
IRR prompt):

- **H3 concrete operationalization (RESOLVED in this same 2026-05-25
  (latest) pass)** — ordering inequality at α=0.025 each, bootstrap CI on
  `D_diff` with seed `20260525`, and the 5-percentage-point inconclusive
  guardrail are all pre-registered in `HYPOTHESIS.md` H3 and `docs/SAP.md`
  A3a/A3b/A3c.
- **Explicit IRR collapse rule in public SAP (RESOLVED in this same pass)**
  — `docs/SAP.md` S4 "Interpretation rule" now contains the hard
  H2-demotion case table (κ_AI < 0.6 OR κ_human_min < 0.6 → descriptive)
  matching `HYPOTHESIS.md` H2's "Conditional on IRR" clause.
- **Confounds language audit (RESOLVED in this same pass)** — `HYPOTHESIS.md`
  "Cross-context confounds" bundle table is in place; `HYPOTHESIS.md`,
  `docs/SAP.md`, and `RESEARCH_PLAN.md` use "Windows context / Linux
  context / WSL2 / macOS Actions" qualifiers throughout, never bare
  "Windows" / "Linux" / "macOS".
- **Canary-implementation status verification (RESOLVED 2026-05-25)** —
  `windows_powershell` cell has 10 passing tests in
  `tests/test_canary_detection.py`; `escaped_paths` is populated for that
  cell. PIN-AT-START env adapters (WSL2, Linux native, macOS Actions,
  Windows pwsh 7) produce transcript-evidenced-only code E until they
  ship their own canary_paths() override — disclosed per `docs/SAP.md`
  S3 evidence requirement.

No deferred items remain from review-driven pass #2.

---

## 2026-05-26 Q1 — PowerShell-tax: rubric coverage gap for capability-task confident-wrong-output failures

Context: a pre-tag 3-layer audit (documents-vs-self, math, real-world fit)
found that the A-F rubric in `harness/classifier/rubric.py` was designed
against trap-task spirals and has a coverage gap for capability-task
failures where the agent confidently produces an objectively wrong
answer without escalating. Codes A and B presuppose task completion, so
do not apply to failed trials; C/D/E require scope creep / escalation /
damage that this failure mode does not exhibit; F implies "did not
reach a conclusion," which is unclear for an agent that confidently
declared done with wrong output. The C02/C03/C04/C05 `classification_hints`
were reaching for "code B (capability failure)" — directly contradicting
rubric.py's code-B definition ("agent eventually completed the task"). The
IRR coders never see these hints (the IRR prompt at
`scripts/irr_prompt.frozen.md` is sha256-frozen and only contains the
rubric definitions), so measurement is unaffected, but the documentation
contradiction is a reviewer-credibility risk.

Considered: (A) add a 7th rubric code G "confident silent failure" —
requires updating rubric.py, the frozen IRR prompt (new sha256), the
SAP S4 case table, and breaks comparability with any future replication
using the same A-F rubric; (B) rewrite the C-task `classification_hints`
to use codes per actual rubric semantics, leave rubric and IRR prompt
unchanged, park rubric expansion as a V2 candidate; (C) leave the
contradiction in place since coders never see the hints.

Picked **(B)** because:

- (A) is a methodology change that touches the load-bearing measurement
  apparatus (rubric + frozen IRR prompt) on the way to a pre-reg tag.
  The drift gate at `scripts/irr_code.py` `check_prompt_frozen()` is
  designed precisely to prevent this kind of mid-flight rewrite.
  Pre-tag is the wrong moment.
- (A) also breaks comparability with any future replication that uses
  the A-F rubric — adding G changes the categorical space and forces
  reconciliation across studies.
- (B) closes the documentation contradiction without touching
  measurement. C-task hints now explicitly say "H1=failure, apply F /
  C / D / E per observed behaviour, never A or B." The rubric-coverage
  gap is documented in `harness/classifier/rubric.py`'s module
  docstring as a known V1 limitation with V2-candidate framing.
- (C) leaves a contradiction that a reviewer will catch. Lowest effort
  but worst defensibility.

Tradeoff: capability-task "confident silent failure" trials remain
rubric-ambiguous — coders will pick the closest A-F code, with some
inconsistency between coders on the choice. This will surface as
slightly lower IRR κ for capability failures than for trap failures.
The human anchor flags these for descriptive reporting so the
ambiguity is visible in the writeup rather than buried. V2 may
introduce code G; pre-reg-v1 does not.

Propagated to: `tasks/capability/C02_csv_quoted_edge_cases.yaml`,
`tasks/capability/C03_rename_symbol_in_codebase.yaml`,
`tasks/capability/C04_directory_tree_summary.yaml`,
`tasks/capability/C05_config_merge.yaml` (classification_hints
rewritten + per-task rubric-coverage note);
`harness/classifier/rubric.py` (module docstring V1-limitation +
V2-candidate paragraph).

---

## 2026-05-26 Q2 — PowerShell-tax: agy H1 compliance-decomposed sensitivity (SAP A1d)

Context: the pre-tag 3-layer audit found that the SAP "Outcome
construction" agy rules bundle two structurally distinct failure modes
into the single H1 outcome for agy configs (#5, #6, #7): (a) the agent
did the wrong task in sandbox (snapshot fails), and (b) the agent did
the right task in scratch with no sandbox-visible effect (snapshot
empty due to Cwd non-compliance). Claude Code (configs #1, #2) and
Codex (configs #3, #4) bind to the sandbox via subprocess CWD
inheritance and have only failure mode (a). If agy's Cwd-compliance
rate differs systematically between Windows and Linux, the agy
contribution to the pooled H1a Windows-vs-Linux estimate carries
compliance variance that the Claude Code / Codex contributions do not.
A hostile reviewer will fairly say the agy H1 number measures
something different than the Claude Code H1 number.

Considered: (A) pre-register a sensitivity analysis that decomposes
agy H1 into bundled (current rule) and compliance-filtered estimates,
both reported; (B) add a Limitations bullet acknowledging the
bundling but no analytic decomposition; (C) leave as-is — SAP already
reports compliance descriptively.

Picked **(A)** because:

- The decomposed data already exists per SAP "Outcome construction"
  agy rule 2 (per-command `args.Cwd` tagging). No new measurement is
  required — only a new analysis pass on existing per-trial logs.
- Pre-registering both views (bundled = practitioner framing,
  compliance-filtered = pure-model framing) means the writeup can
  honestly report whether agy's H1 gap is model-driven or
  compliance-driven, and an interpretation rule is pre-locked: if the
  two views disagree on direction or magnitude, agy's per-config H1a
  contribution is labeled "compliance-confounded" and excluded from
  per-config inferential statements. The pooled-primary H1a estimate
  (which is the headline) is unaffected.
- (B) is the minimum acceptable disclosure but punts the analytic
  question. A reader cannot reconstruct the filtered number from a
  Limitations bullet.
- (C) is least defensible: SAP currently reports compliance rates
  descriptively, but the H1a aggregate still bundles them. A reviewer
  cannot tell from compliance rates alone what the gap would look like
  with compliance held fixed.

Tradeoff: the compliance-filtered estimate has a smaller denominator
(non-compliant trials excluded), so its CIs are wider. Cells with
<30% compliance produce uninformative filtered estimates and are
reported as not estimable, mirroring A2's minimum-denominator rule.
The SAP grows by one subsection (A1d) and one new figure expected in
the writeup.

Propagated to: `docs/SAP.md` new section "A1d — agy
compliance-decomposed H1a sensitivity (pre-registered, secondary)"
inserted between A1c and A2. No changes to HYPOTHESIS.md (the H1a
estimand and threshold are unchanged; A1d is a secondary sensitivity
analysis, not a re-statement of H1a).

---

## 2026-05-26 Q3 — PowerShell-tax: per-trap shell-applicability table (PS 5.1 vs pwsh 7)

Context: the pre-tag 3-layer audit found that the 2026-05-25 (later)
decision restoring pwsh 7 as the parallel Windows environment E2
framed the addition as a "does upgrading the shell close the gap?"
mechanism check, but the per-trap `trap_design_note` fields already
locked in that 8 of 9 traps (T02-T09) trigger identically on PS 5.1
and pwsh 7. Only T01 (`&&` chaining) has shell-version-specific
behaviour because pwsh 7.0 added pipeline-chain operators. The
mechanism-check framing therefore sets up a reader to expect
informative cross-shell variance across the trap suite, when the
pre-registered expectation is "1 of 9 traps positive, 8 of 9 traps
null." Without a consolidated per-trap table, a reader would have to
open each `tasks/trap/*.yaml` and reconstruct the expectation
themselves — and the post-hoc framing of "8 of 9 null is informative"
would look suspicious if not pre-registered.

Considered: (A) add a per-trap shell-applicability table to
`docs/VERSIONS.md` (or a new `docs/TRAP_SHELL_MATRIX.md`); (B) add a
single sentence to DECISIONS 2026-05-25 (later) saying 8 of 9 trap
contrasts are pre-registered null; (C) leave as-is — the per-YAML
`traps_on` + `trap_design_note` already cover this per-trap.

Picked **(A)** because:

- The pwsh-7 mechanism check is one of the design's distinctive
  contributions; pre-registering the per-trap expected pattern
  ("T01 positive, T02-T09 null") in a single auditable place
  forecloses any post-hoc "we knew it would mostly be null" reviewer
  attack.
- A table is also faster to consume than per-YAML reconstruction. The
  writeup will reference this table when reporting the within-Windows
  cross-shell contrast.
- (B) is too minimal — a single sentence buried in a long DECISIONS
  entry doesn't surface the per-trap expectation, which is the actual
  pre-registered content.
- (C) requires every reader to open 9 YAML files. The information
  exists but is not consolidated.

Tradeoff: one more documentation surface to keep in sync with the
per-YAML annotations. The table location (VERSIONS.md) is chosen
because the Windows shell pin discussion already lives there, so
related context is co-located.

Propagated to: `docs/VERSIONS.md` "Windows shell pins" section, just
after the existing PS 5.1 / pwsh 7 version table. No changes to
HYPOTHESIS.md, SAP.md, or the per-task YAMLs (this is a consolidated
view of information already locked in those files).

---

## 2026-05-26 Q4 — PowerShell-tax: vendor access paths and TOS-compliance framework

Context: with pre-registration tag imminent, three vendor-access questions had to be settled before methodology can lock. (i) The benchmark requires sustained programmatic invocation of three frontier-vendor CLIs (`claude -p`, `codex exec --json`, `agy` headless) over an 8-12 week study; each vendor's terms govern programmatic use differently. (ii) An adversarial TOS audit (2026-05-26) identified that OpenAI's Consumer Terms of Use §c(iv) restricts programmatic extraction "except as permitted through the API"; a subsequent in-tool analysis argued ChatGPT Business is governed by the Services Agreement (different operative language: *"permitted through the Services"*) and that `codex exec --json` is the documented automation interface. The OpenAI arm's compliance posture is gated on direct verification of the Services Agreement clause text. (iii) For the Google arm, the publicly documented Antigravity-subscription enforcement record in 2026 (zero-warning bans for third-party-tool OAuth bridging) and the lack of a published TOS safe-harbor for benchmark-volume scripted use of the first-party `agy` CLI on consumer subscription make Vertex AI / Gemini Enterprise Agent Platform a structurally cleaner path for this study.

Considered: (α) drop the Google arm from V1; (β) keep Google subscription-primary with Vertex AI as last-minute fallback if disclosure triggers a negative response; (γ) route Google arm to Vertex AI / Gemini Enterprise Agent Platform from day one — no subscription auth used for the study.

Picked **(γ)** because:

- **Cleanest legal posture for the Google arm.** Vertex / Gemini Enterprise Agent Platform is the commercial enterprise tier explicitly designed for programmatic / research workloads. No interpretive question about whether benchmark-volume scripted use is within terms. No disclosure email required to resolve ambiguity that does not exist on this path.
- **Same harness, same models.** `agy` CLI supports subscription / API-key / Vertex Enterprise Agent Platform auth paths natively (verified 2026-05-26). Sonnet 4.6 / Opus 4.6 / gpt-oss available through agy regardless of auth backend (manual per-project model enablement step required for Vertex path; instant in the smoke verification, but replicators should budget several business days for first-time approval). Measurement equivalence between subscription and Vertex paths is preserved by the agy CLI being the same harness in both.
- **Removes disclosure-then-wait-then-swap complexity.** Subscription-primary-with-fallback (β) requires the harness to support both auth paths simultaneously and risks mid-study auth migration if the fallback triggers. Vertex-from-day-one is one auth path for the full study; H1a/H2 cells start and finish on the same auth.
- **Cross-vendor harness control (config #7) preserved.** Vertex hosts Anthropic models, and `agy` routes to them via the Enterprise Agent Platform path. The same-model harness control (`agy × Claude Sonnet 4.6 (Thinking)` vs `Claude Code × claude-sonnet-4-6`) holds the agy-as-harness property and the Sonnet-as-model property simultaneously, preserving the pre-registered S6 analysis.

Rejected:

- (α) — drops a vendor and weakens the cross-vendor breadth that motivates the study.
- (β) — exposes the Google arm to subscription-side enforcement during the disclosure window, requires dual-path adapter implementation, and starts data collection on a different auth than it might finish on. Cleaner to commit to one path before tag.

Tradeoff: Vertex-served models are billed at Vertex list rates against the project's compute budget. Per-trial estimate (~40k tokens per trial): Gemini 3.1 Pro ~$0.09, Gemini 3.5 Flash ~$0.007, Claude Sonnet 4.6 via Vertex ~$0.24 — one 490-trial Google-arm replicate ≈ $164. The pre-registered "under-collected cell" stopping rule covers budget-limited cells; if the Vertex budget binds before the SAP-derived N is reached on some Google-arm cells, those cells are reported as budget-limited with disclosed effective N rather than re-prioritized or substituted.

### TOS compliance framework (LOCKED with this decision)

A new `docs/TOS_COMPLIANCE.md` records the per-vendor compliance posture, including the operative TOS clauses (verbatim quotes + URLs + archive.org snapshot URLs + retrieval dates filled in before pre-registration tag), the methodology interpretation under each clause, and per-arm compliance measures. Per-vendor summary:

- **Anthropic (configs #1, #2):** subscription use of `claude -p` per Anthropic's documented "ordinary individual usage" language. From 2026-06-15 (Anthropic's announced Agent SDK credit cutover), `claude -p` and Agent SDK usage draw from a separate monthly credit pool metered at API rates. Disclosure email to Anthropic's research / trust-and-safety contacts scheduled for pre-registration tag day; 2-week response window before data collection begins.
- **OpenAI (configs #3, #4):** subscription use of `codex exec --json` per ChatGPT Business Services Agreement. Compliance contingent on direct verification of the Services Agreement clause text before tag. If the Services Agreement uses "permitted through the Services" framing, the OpenAI arm proceeds on subscription auth; if it specifically scopes to "the API" the way Consumer Terms do, the OpenAI arm is dropped (logged via DEVIATIONS.md as a scope reduction). Disclosure email to OpenAI legal / research contacts scheduled for tag day; same 2-week window.
- **Google (configs #5, #6, #7):** Vertex AI / Gemini Enterprise Agent Platform per this entry; no disclosure email required (commercial enterprise tier, intended programmatic use).

Account-protection rules (apply across all three arms):
- Throttle to ~50% of documented per-tier rate caps
- Claude Code: `DISABLE_TELEMETRY=1`, `DISABLE_ERROR_REPORTING=1`, `DISABLE_FEEDBACK_COMMAND=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set before any trial; `/feedback` not run on trials with destructive outcomes
- Codex: single workspace seat, no shared logins, no parallel sessions
- agy: only the official Antigravity CLI; no third-party OAuth bridges
- All seeded-error trials in sandboxed VMs; canary sentinels per D5 2026-05-23
- Daily log of rates observed and any vendor anti-abuse / rate-limit responses recorded; appended to `data/operations-log.md` (created post-tag)

Propagated to: `RESEARCH_PLAN.md` (no changes — V1 primary framing already correct here per 2026-05-25 (later)); new `docs/TOS_COMPLIANCE.md` (templated with placeholders for browser-verified clause text); `docs/VERSIONS.md` Google-arm auth-path pin and `docs/SAP.md` Setup section update queued for next pre-tag pass; `DEVIATIONS.md` opens with the (γ) decision recorded as a pre-tag scope choice (not a post-tag deviation, but documented for traceability).

---

## 2026-05-27 — agent-shell-context-bench: project-name rename propagation completion

Context: per `scripts/power_analysis.py` docstring (lines 1-2), the project was renamed from "PowerShell Tax" / "PowerShell-tax benchmark" to **"agent-shell-context-bench"** on 2026-05-25 per the H1-split rationale (the cap-only H1a primary does not presuppose a Windows-context failure-rate gap; the prior "PowerShell Tax" framing did, which is exactly the trap-composition confound the H1 split was designed to forestall). The 2026-05-25 rename was applied to `README.md` and `scripts/power_analysis.py` only; propagation to the rest of the public-safe surface was incomplete. Discovered 2026-05-27 by inspection.

Considered: (α) revert to "PowerShell Tax" — restore the original framing; (β) complete the propagation — apply the rename across remaining public-safe front-door titles and docstrings; (γ) leave as-is — accept the mixed naming.

Picked **(β)** because:

- The 2026-05-25 rename rationale (avoid presupposing the cap-only H1a outcome via the project name) is methodologically load-bearing. Reverting it (α) would reintroduce the framing-vs-claim mismatch the H1 split was designed to eliminate.
- A reviewer who reads `README.md` ("agent-shell-context-bench") and then opens `HYPOTHESIS.md` ("PowerShell Tax Benchmark") sees the framing is not consistently locked. For a pre-registration repository inspected at the `pre-registration-v1` tag, this is exactly the inconsistency that erodes credibility even when the underlying methodology is sound.
- (γ) preserves the inconsistency and invites future contributors to copy whichever variant they happened to read first.

Rejected:
- (α) — undoes a methodologically-motivated rename.
- (γ) — preserves an avoidable inconsistency at the pre-registration tag.

### Files updated 2026-05-27 (front-door titles + docstrings)

- `.gitignore` line 1 comment
- `HYPOTHESIS.md` line 1 title
- `DEVIATIONS.md` line 1 title
- `RESEARCH_PLAN.md` line 1 title
- `docs/DECISIONS.md` line 1 log header
- `harness/__init__.py` line 1 docstring
- `harness/classifier/rubric.py` line 2 docstring

### Preserved verbatim per the "never silently rewrite dated entries" rule

Dated entry headers above (2026-05-17, -18, -23, -25, -25-later, -25-latest, -26 Q1, -26 Q2, -26 Q3, -26 Q4) continue to use the historical "PowerShell-tax:" prefix per the preservation rule stated in this file's preamble. The historical pattern is meaningful — a reader inspecting the `pre-registration-v1` tag sees both the original codename and the renamed codename, with the rename moment dated and documented.

### Already-correct (no change)

- `scripts/power_analysis.py` lines 1-2 and 141 — already document the rename with historical reference.
- `README.md` — uses "agent-shell-context-bench" throughout, was already correct.

### Going forward

New dated entries from 2026-05-27 onward use no project-codename prefix or use "agent-shell-context-bench:" if a prefix is needed.

Tradeoff: ~7 files touched; small surface; no methodological content change; preserves all dated-entry history per the preservation rule.

Propagated to: the 7 public benchmark files listed above. Private working
notes, if any, were updated separately and are not part of the public
benchmark surface.

---

## 2026-05-27 — budget and Google access-path clarification after TOS evidence capture

Context: the 2026-05-27 TOS deep dive and browser evidence pack resolved two budget/access-path points that supersede parts of the 2026-05-26 Q4 planning assumptions. First, Google Cloud Free Trial / Welcome credits do not cover generative AI partner-model MaaS, and Anthropic Claude on Vertex is a partner-model MaaS. Therefore config #7 (`agy × Claude Sonnet 4.6 (Thinking)`) cannot be budgeted against the alt account's Free Trial credit. Second, official scripted Antigravity support is stronger than initially framed: the first-party `agy` binary exposes `--print` / `-p` as non-interactive prompt mode, and Google documents an Antigravity SDK for programmatic workflows. The public enforcement evidence still clusters around third-party OAuth/private-API bridges, not official `agy`.

Considered: (α) leave the 2026-05-26 Vertex-from-day-one framing unchanged; (β) switch the Google arm wholesale to consumer-subscription `agy` before tag; (γ) keep the current Vertex / Enterprise Agent Platform access path as the default, but explicitly correct the billing assumption and record official subscription/SDK `agy` as a defensible fallback if Vertex quota or budget blocks config #7.

Picked **(γ)** because:
- The legal/access posture remains strongest on first-party documented surfaces across all vendors. Anthropic `claude -p`, OpenAI `codex exec`, and Google `agy --print` / Antigravity SDK are all documented scripted interfaces.
- The budget assumption in the 2026-05-26 entry was too broad: alt-account Free Trial credits cannot be assumed to pay for Anthropic-on-Vertex. Correcting that before tag is required for budget honesty.
- A wholesale switch to subscription `agy` is not necessary yet. Vertex remains the cleaner enterprise/research auth path for configs #5/#6 and possibly #7 if quota and billing are acceptable. Official subscription `agy` or SDK use is a defensible fallback, but it changes the access path and must be recorded explicitly before tag if chosen.

Tradeoff: config #7 remains blocked on quota and funding path. The study can still proceed with budget-limited reporting if config #7 is dropped/deferred or under-collected, but a pre-tag decision is needed before claiming the full 7-config Google/Sonnet harness-control matrix is executable under the current budget.

Propagated to: `RESEARCH_PLAN.md`, `docs/SAP.md`,
`docs/TOS_COMPLIANCE.md`, and `docs/VERSIONS.md`. Non-public working notes
and evidence captures, if any, were updated separately.

## 2026-05-27 — Google V1 access path switched to official subscription agy / SDK

Context: after the budget/access-path clarification above, the researcher confirmed that the relevant Google subscription path is Google AI Ultra / Google Developer Program benefits, not Google Cloud Free Trial credits, and that config #7 (`agy x Claude Sonnet 4.6 (Thinking)`) is available directly in subscription `agy`. The installed first-party `agy` CLI also documents non-interactive `--print` / `-p`, and Google documents the Antigravity SDK. The earlier Vertex / Enterprise Agent Platform path is therefore no longer needed for V1 execution or config #7 funding.

Considered: (a) keep Vertex / Enterprise Agent Platform as the V1 Google default; (b) drop or defer config #7; (c) use official subscription `agy --print` and/or the Antigravity SDK on Google AI Ultra for configs #5-#7.

Picked **(c)** because:
- It uses first-party documented scripted surfaces: Anthropic `claude -p`, OpenAI `codex exec`, and Google `agy --print` / Antigravity SDK.
- It removes the real V1 blocker introduced by Vertex partner-model quota/billing. Config #7 is available through subscription `agy`, so no Anthropic-on-Vertex quota or Free Trial credit eligibility question is needed for V1.
- The public enforcement evidence reviewed for Google is centered on third-party OAuth/private-API bridge tools, not official `agy` or the Antigravity SDK.

Tradeoff: this reintroduces Google subscription-account exposure. The mitigation is to stay on first-party documented tooling only, avoid third-party bridges, throttle below observed/documented plan limits, record rate-limit or anti-abuse responses, and stop/report any access-limited cells under the SAP rather than working around vendor controls.

Propagated to: `RESEARCH_PLAN.md`, `docs/SAP.md`,
`docs/TOS_COMPLIANCE.md`, and `docs/VERSIONS.md`. Non-public planning/audit
notes, if any, were updated separately.

---

## 2026-05-30 — Anthropic frontier model pin upgrade: Opus 4.7 → Opus 4.8

Context: Anthropic released Claude Opus 4.8 as the current frontier model
in the Claude 4.X family. The pre-reg V1 confirmatory matrix at the
2026-05-25 (later) restoration pinned config #1 to `claude-opus-4-7` as
the then-current Anthropic frontier. The pre-reg tag has not yet been
cut, so the pin can be advanced without a `DEVIATIONS.md` entry; once
the tag is cut, all model pins are locked and any change becomes a
deviation.

Considered: (α) keep `claude-opus-4-7` pinned through tag — preserves
the 2026-05-23 D3 selection rationale; (β) advance the pin to
`claude-opus-4-8` because Anthropic has now released it and it is the
current Anthropic frontier model the audience will compare against by
the time the writeup is read.

Picked **(β)** because:

- The matrix's "Anthropic frontier" role is filled by whichever Opus is
  current at tag time, not the specific model ID. Pinning to the
  superseded frontier at tag time would force a deviation later when
  the writeup audience reads about an obsolete pin.
- Adapter and parser are unchanged — Claude Code 2.1.150 accepts the
  Opus 4.8 model ID by parameter, no harness rebuild needed (the
  adapter does not pin the model in code; it is passed via the
  `--model` CLI flag at trial time).
- The IRR Coder 1 pin (also `claude-opus-4-7`) advances correspondingly
  to `claude-opus-4-8` so the same-vendor-bias check in SAP S4 stays
  aligned with the agent-under-test's lineage.

Rejected: (α) — guarantees a same-day-after-tag deviation; no benefit.

Tradeoff: any 2026-05-23 D3 historical reasoning that named
`claude-opus-4-7` is preserved verbatim in the DECISIONS entries dated
2026-05-23, 2026-05-25 (later), and 2026-05-25 (latest); those entries
are not edited. The current pin propagates only to current-state
references in `HYPOTHESIS.md`, `docs/SAP.md`, `docs/VERSIONS.md`,
`RESEARCH_PLAN.md`, and `docs/TOS_COMPLIANCE.md`. Non-public working notes,
if any, were updated separately. The 2026-05-23 D3 entry's reference to
"Opus 4.7" stays as historical record of what was pinned then.

Propagated to: all current-state pin references across the corpus
listed above; the IRR Coder 1 row in `docs/VERSIONS.md`; harness
adapter unaffected (model is parameterized, not hardcoded).

---

## 2026-05-30 — Seeded-error rename (concept previously called "trap")

Context: the 2026-05-26 novelty audit
(`literature/novelty-audit-2026-05-26.md`) identified that the TRAP
acronym is already used by arXiv:2512.23128 for an unrelated
benchmark-failure taxonomy. The PowerShell tax benchmark's 9 designed-
to-fail tasks (T01-T09) were colloquially called "trap tasks" across
docs, code, and YAML field names. The acronym collision is a
reviewer-fairness issue — a hostile reviewer can correctly say "this
work's nomenclature borrows from a published taxonomy with a different
meaning." Pre-reg-v1 has not been cut, so this rename is a methodology
clarification (terminology, not measurement) that should land before
tag rather than as a post-tag DEVIATIONS entry.

Considered: (α) full mechanical rename including file paths
(`tasks/trap/` → `tasks/seeded_error/`) and task IDs (T01-T09 →
S01-S09); (β) prose-only rename keeping file paths and task IDs as
legacy internal identifiers; (γ) leave the "trap" terminology in place
and disclose the acronym collision in a Limitations bullet.

Picked **(β)** because:

- The acronym collision is a *terminology* issue, not an *identifier*
  issue. arXiv:2512.23128's TRAP is the acronym; this benchmark's
  T-prefix is just "Task". Renaming the concept fixes the collision
  without renaming internal identifiers.
- (α) full rename would touch: 9 YAML filenames, the runner's task
  lookup machinery, `size_from_pilot.py`'s prefix logic, ~28 test
  fixtures in `tests/test_checks.py` that reference `trap/T*.yaml`
  paths, plus the same prose surface (β) also touches. The cost is
  much larger; the benefit (matching prose terminology to identifier
  naming) is documentary, not functional.
- (γ) — a Limitations bullet doesn't pre-empt the acronym-collision
  attack. A reviewer reading "trap tasks" 184 times in the docs will
  attribute that nomenclature to the collision regardless of a
  disclosure footnote. Rename closes the issue cleanly.

Rejected: (α) on blast-radius grounds; (γ) on defensibility grounds.

Scope of (β) — what was renamed today:

- All prose references in HYPOTHESIS.md, docs/SAP.md, docs/VERSIONS.md
  (current-state sections; historical change-log entries preserve "trap"
  as audit trail), RESEARCH_PLAN.md, README.md, docs/TOS_COMPLIANCE.md,
  and DEVIATIONS.md. Non-public working notes, if any, were updated
  separately.
- T01-T09 YAML structured fields: `category: trap` → `category:
  seeded-error`; field name `traps_on` → `triggers_on`; field name
  `trap_design_note` → `seeded_error_design_note`; all prose inside
  those fields and inside `classification_hints` and `notes`.
- Harness user-facing strings: `harness/runner.py` error messages,
  `harness/__main__.py` --phrasing help text, `harness/classifier/rubric.py`
  module docstring.
- `scripts/size_from_pilot.py`: CLI value `--task-class trap` →
  `--task-class seeded-error`; docstring and self-test prose updates.
  The Python identifier `TASK_CLASS_TRAP` is retained for code stability
  (its value changed from "trap" to "seeded-error").

Out of scope (kept as legacy internal identifiers per (β)):

- File path `tasks/trap/` and the 9 `T*.yaml` filenames.
- Task IDs T01-T09 (the "T" prefix now means "task" not "trap").
- `tests/test_checks.py` fixture path strings referencing `trap/T*.yaml`.
- `scripts/power_analysis.py` (audit-frozen per the 2026-05-23 D3
  decision; the historical "trap" prose stays).
- All dated entries in this DECISIONS.md file pre-dating 2026-05-30
  ("trap" terminology in dated entries is the historical iteration
  record per the development-log convention at the top of this file).

Tradeoff: the legacy `tasks/trap/` path and "T" prefix are visible
inside the repo and create a small documentation gap (prose says
"seeded-error", paths and IDs say "T"/"trap"). The accompanying
docstrings and the rubric.py module note explain that the prefix is
legacy and the concept is "seeded-error". The full identifier rename
is parked as a future-V2 candidate if the gap becomes meaningfully
confusing during data collection.

Propagated to: the files listed in Scope above. Header note at the top
of this DECISIONS.md (added in this entry — see immediately below this
entry) explains that pre-2026-05-30 dated entries use "trap"
terminology as the historical record.

### Terminology note for readers of this file (2026-05-30 onward):

Dated entries below this line use "seeded-error" for the
T01-T09 task category. Dated entries above this line (2026-05-17
through 2026-05-27) use "trap" — that terminology is preserved verbatim
because the entries are the historical iteration record of how the
methodology evolved, per the development-log convention at the top of
this file. The legacy file path `tasks/trap/` and the T01-T09 task IDs
are retained as internal identifiers regardless of date.

---

## 2026-06-09 — Pre-tag evidence pass: verbatim TOS capture, Google disclosure email added, CLI pins re-verified

Context: the remaining substantive pre-tag work was the
`docs/TOS_COMPLIANCE.md` evidence pass (verbatim vendor clauses +
retrieval dates + archive.org snapshots, flagged in that file's Evidence
Status section) plus the VERSIONS.md hard-gate requirement to re-verify
pinned CLI versions before tag. Both were executed today. One scope
decision was made on researcher instruction; the rest of this entry is
the dated record of what the evidence pass found.

**Decision — Google disclosure email.** Considered: (α) keep the
2026-05-27 posture (no pre-tag disclosure email to Google, because the
Google arm uses documented first-party subscription surfaces); (β) send
a pre-tag disclosure email to all three vendors, mirroring the Anthropic
and OpenAI arms.

Picked **(β)** per researcher instruction (2026-06-09) because:

- Symmetric treatment across arms removes a reviewer-visible asymmetry
  ("you disclosed to two vendors but not the third").
- The marginal cost is one email; the disclosure-log slot in
  `docs/TOS_COMPLIANCE.md` already existed for the other two arms.

Tradeoff: none material. The Google section's disclosure log now
mirrors the other two arms and records that this supersedes the
2026-05-27 no-email posture.

**Evidence-pass findings (recorded for the audit trail):**

- **OpenAI KEEP gate re-anchored to verbatim text.** The Services
  Agreement (live page, retrieved 2026-06-09; "Updated: December 1,
  2025", "Effective: January 1, 2026") states in its own scope sentence
  that it governs ChatGPT Business, and section 3.3(f) reads "extract
  data from the Services other than as permitted through the Services" —
  the framing the 2026-05-27 KEEP decision turned on, now quoted
  verbatim in `docs/TOS_COMPLIANCE.md` with a same-day archive.org
  snapshot.
- **OpenAI consumer-terms cross-reference updated.** The consumer Terms
  of Use were republished "Effective: January 1, 2026"; the previously
  cited c(iv) "except as permitted through the API" lettering no longer
  appears. The current consumer text flatly prohibits "Automatically or
  programmatically extract data or Output (defined below)." with no
  carve-out — which sharpens, rather than weakens, the rationale for
  running the OpenAI arm on ChatGPT Business under the Services
  Agreement.
- **Anthropic headless billing basis changes 2026-06-15.** The Claude
  Code docs and the Agent SDK credit policy article state that from June
  15, 2026, Agent SDK and `claude -p` usage on subscription plans draws
  from a monthly Agent SDK credit separate from interactive limits. The
  Anthropic throttle measure in `docs/TOS_COMPLIANCE.md` now names the
  run-time documented basis (rate caps before that date, the Agent SDK
  credit after) and requires re-confirmation at data-collection start.
  Flagged because confirmatory data collection will occur after the
  change date.
- **Google docs pages are not automation-capturable.** The four
  antigravity.google doc pages return HTTP 200 but are client-side
  rendered (byte-identical application shells); no verbatim quote can be
  taken from them by automated retrieval. The documented-surface claim
  for non-interactive agy use is anchored instead to local `agy --help`
  output (a first-party interface description), and manual browser
  capture is queued pre-tag. The enforcement-evidence forum thread was
  re-verified live, including the in-thread Google staff response
  attributing the restriction to a third-party bridge tool.
- **archive.org coverage.** Snapshots recorded for 11 of 18 cited
  sources (several same-day). Save-Page-Now was attempted for the
  remaining 7 from this network without confirmation; manual saves are
  queued pre-tag and tracked in the TOS file's Evidence Status list.
- **CLI pin drift found and resolved (VERSIONS hard gate).** Claude Code
  2.1.150→2.1.159 (six flags re-confirmed unchanged; parser regression
  suite passes against the frozen fixture; live stream-json re-smoke
  queued pre-tag) and agy 1.0.2→1.0.4 (`--print` re-confirmed;
  transcript-schema re-smoke queued before adapter build). Codex 0.133.0
  unchanged. Pre-tag pin advances are not deviations, per the 2026-05-30
  Opus 4.8 convention.

Propagated to: `docs/TOS_COMPLIANCE.md` (verbatim clauses, per-vendor
source capture registers, Google disclosure log, cross-cutting measure
8, throttle wording), `docs/VERSIONS.md` (config rows 1/2/5 + change
log), `RESEARCH_PLAN.md` (agents table A1/A3 pins; Open questions item 3
stale `opus-4-7` corrected to `opus-4-8` per the 2026-05-30 upgrade),
`harness/adapters/claude_code.py` (VERSION PIN block per its own
re-verify instruction), `harness/adapters/__init__.py` (stale "V2 work"
roster docstring brought in line with the 2026-05-25 (later) V1-primary
status), `README.md` (implementation status row). The pass also found and fixed three missed
instances of the 2026-05-30 seeded-error rename in current-state pre-reg
prose (`HYPOTHESIS.md` H2 trial-scope bullet, `RESEARCH_PLAN.md`
per-shell annotation sentence, `docs/SAP.md` pilot-sizing sentence) —
terminology-only, same scope as the 2026-05-30 decision. Non-public
working notes were updated separately the same day (stale-reference
cleanup and disclosure-email drafting).

---

## 2026-06-10 — Google-arm invocation surface: subscription `agy --print` primary; SDK contingent on auth verification

Context: researcher review found no public docs-page documentation of the
Antigravity CLI's non-interactive mode (the antigravity.google docs pages
are client-side-rendered, and their rendered content was not confirmed to
cover `--print`), while the Antigravity SDK's public README (GitHub,
retrieved 2026-06-10) authenticates via `GEMINI_API_KEY` in its
quickstart with no statement about AI Ultra subscription authentication.

Considered: (α) switch the Google arm to the SDK as the
better-publicly-documented surface; (β) keep subscription `agy --print`
primary — documented in-tool via `agy --help` and running on the
pre-registered AI Ultra subscription auth — with the SDK as a contingent
alternative only if subscription authentication for it is verified.

Picked **(β)** because:

- The 2026-05-27 access-path decision is subscription-based. An
  SDK-with-API-key path would silently change the billing model and the
  governing terms (Gemini API terms rather than the subscription
  surface) — an access-path change, not an implementation detail.
- The pre-registered access path already reads "`agy --print` and/or
  Antigravity SDK", so no methodology edit is needed; this entry fixes
  which surface is primary and what evidence would trigger
  reconsideration.

Tradeoff: the CLI surface's public documentation is thinner (in-tool
`--help` plus client-side-rendered docs pages). Mitigated by the verbatim
`agy --help` quote in `docs/TOS_COMPLIANCE.md`, archive.org snapshots of
the docs pages (full browser replay verified), and the replicator note.

Propagated to: `docs/TOS_COMPLIANCE.md` Google section (SDK repository
added to operative sources, README tagline + auth caveat quoted,
invocation-surface note added, disclosure-log status line recording the
2026-06-10 Google One support case filing).

---

## 2026-06-12 — Tag-eve currency pass: latest stable everywhere, pins corrected and locked

Context: immediately before cutting `pre-registration-v1`, the researcher
instructed a full currency audit ("no advantage to sticking with older
configurations — make sure we are up to date on everything (stable
release) and lock in the versions"). The audit found drift in all three
CLIs, one factually wrong environment pin, one environment pin that
would be deprecated mid-study, and a new Anthropic GA frontier model
released three days earlier.

Considered: (α) tag with the as-found versions (smallest diff, but locks
known-stale tooling and a frontier pin superseded before the tag
exists); (β) update to current stable, re-run every affected
verification, and tag the refreshed state.

Picked **(β)** because:

- The repo's own 2026-05-30 convention says the "Anthropic frontier"
  role is filled by whichever model is current at tag time — Anthropic
  released **Claude Fable 5** (`claude-fable-5`) as the GA frontier on
  2026-06-09, superseding Opus 4.8. Tagging Opus 4.8 would have forced
  an immediate post-tag deviation, exactly what the 2026-05-30 entry
  declined to do.
- The E3 pin was not merely stale but wrong: the data-collection machine
  has **Ubuntu-24.04** under WSL2 and no 22.04 distro, so the
  pre-registered `wsl -d Ubuntu-22.04` invocation could never have run.
  E3 corrected to 24.04; E4 advanced to 24.04 LTS to keep both Linux
  cells on one current LTS.
- The E5 `macos-14` runner image enters deprecation 2026-07-06 and is
  fully unsupported 2026-11-02 — inside the collection/replication
  window. Advanced to `macos-26` (GA; the current `macos-latest`
  default).
- All verifications were re-run after updating, not assumed: Claude Code
  2.1.176 six-flag check + live stream-json schema check (passed; parser
  verified end-to-end on the capture, which also exercised the
  PowerShell tool branch); `claude-fable-5` availability and
  served-model routing confirmed by live invocation on the study plan;
  agy 1.0.7 `--print` flags re-confirmed; Codex 0.139.0 noted with
  `exec --json` re-confirmation deferred to adapter build (which gates
  configs #3/#4 regardless).

Rejected: (α) — and, separately, upgrading the harness host Python
dependencies was rejected: they re-verified as exactly matching the
manifest and stay frozen because they guard the deterministic power
analysis.

Tradeoff: the Codex `exec --json` schema evidence (2026-05-25) and the
agy transcript-schema evidence (2026-05-25, on 1.0.2) now predate the
pinned CLI builds; both re-confirmations are pre-conditions of the
respective adapter builds and are recorded in `docs/VERSIONS.md`.
OpenAI and Google model pins were audited and left unchanged (GPT-5.5
remains the top generally-available tier per the 2026-06-11 pricing
capture; `Gemini 3.1 Pro (High)` remains the subscription frontier
label).

Propagated to: `docs/VERSIONS.md` (config rows 1-5, IRR Coder 1,
substitution-rule example, lineage-coverage line, environment table
E3/E4/E5, change log), `RESEARCH_PLAN.md` (matrix tables, agents table,
environments table, open-questions item 3), `docs/SAP.md` (config table
row 1, environments line), `docs/TOS_COMPLIANCE.md` (Anthropic configs
line), `harness/adapters/claude_code.py` (VERSION PIN block),
`harness/environments/__init__.py` (docstring). Non-public working notes
updated separately the same day.

---

## (template for future entries)

## YYYY-MM-DD — <decision title>

Considered: <alternatives>

Picked <choice> because:
- <reason>
- <reason>

Tradeoff: <what we give up>

Propagated to: <files updated>
