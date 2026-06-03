# Pre-Registered Hypotheses — agent-shell-context-bench

**Author:** littlemehere
**Date of pre-registration:** 2026-05-25 (Git tag is the authoritative timestamp; see `git log` for the exact UTC commit time of the tagged commit.)
**Pre-registration mechanism:** Git tag `pre-registration-v1` on the initial commit of this file in this public repository.
**Anyone reading this** can verify these hypotheses were committed before any experimental data was collected by checking `git log` and the tagged commit hash.

---

## Why pre-register?

In empirical research, it's easy to look at data, find a pattern that happens to be there, then write the paper as if you'd predicted it. Pre-registration prevents this by forcing the author to commit to specific predictions BEFORE seeing data. It is the cheapest form of intellectual honesty available.

This pre-registration covers:
- Specific hypotheses (H1-H4)
- Specific outcome measures
- Specific statistical tests (in `docs/SAP.md`)

If the data does NOT support the predictions, that result will be reported with the same prominence as a confirming result. Negative results are valid science.

---

## Hypotheses

### H1a (Primary) — Cross-context failure rate gap on capability tasks

In the V1 confirmatory matrix, AI coding agents will exhibit **at least
1.5x higher task failure rate** in the Windows context (PowerShell 5.1
default, with free tool choice among the tools the agent CLI exposes —
Bash via Git Bash, PowerShell, Write, Edit, etc.) compared to the Linux
context (bash default), **on the capability task subset only (5 tasks:
C01–C05), measured via the pooled across-configuration test in SAP A1**.

**Why capability-only is the primary estimand (revised 2026-05-25 (latest), review-driven finalization pass #2):**
the 14-task suite contains 9 seeded-error tasks hand-designed against known PowerShell
5.1 failure modes (see `docs/DECISIONS.md` D2, 2026-05-23). Including those
seeded-error tasks in the H1 aggregate confounds "general cross-context reliability gap"
(what H1 is supposed to estimate) with "agent loses on benchmarks the author
designed it to lose on" (which is an H2-mechanism finding, not an H1
reliability finding). The clean fix, applied before pre-reg tag, is to
restrict H1's primary inferential test to the capability tasks — where no
seeded-error task was authored — and demote the full-suite estimate to a secondary
descriptive analysis (H1b below). This makes H1a a defensible "general
reliability" claim and prevents the headline number from being dominated by
hand-authored adversarial composition.

The V1 confirmatory matrix is **7 model-harness configurations × 5
environments × 14 tasks**, locked per `docs/DECISIONS.md` 2026-05-25
(later). Configs span three frontier vendors (Anthropic via Claude Code,
OpenAI via Codex CLI, Google via Antigravity CLI `agy`) at two model
tiers each (frontier + workhorse), plus one same-model harness-control
config (agy × Claude Sonnet 4.6 (Thinking)) enabling the pre-registered
S6 analysis that separates harness from model. Per-row adapter and
environment-adapter implementation status is in `docs/VERSIONS.md`; the
SAP locks the methodology while implementation lands incrementally
post-tag.

Operationalization:
- "Failure rate" = proportion of valid trials where the agent did not satisfy the task's pre-registered `binary_success_predicate`. This binary H1a outcome is programmatic and is determined before any A-F spiral rubric coding. Manual/rubric coding cannot convert a binary failure into success or a binary success into failure.
- A valid trial that times out or is killed for exceeding the task time limit is a failure unless the task's `binary_success_predicate` explicitly defines a narrower exception. Partial artifacts left by a timed-out run do not count as success.
- Invalid trials are limited to infrastructure-origin measurement failures that prevent the binary outcome from being determined and are not attributable to the agent's actions. If the agent breaks the harness, deletes or corrupts benchmark state, kills the runner, changes permissions, fills the disk, or otherwise causes measurement loss, the trial remains a valid H1a failure and is eligible for catastrophic-action code E if available evidence attributes the loss to the agent.
- **Task scope for H1a primary:** capability tasks only (5 tasks, C01–C05). Each capability task has one phrasing, so each task contributes one task-level estimate per cell to the H1a aggregate. No seeded-error tasks enter the H1a primary numerator or denominator.
- "Pooled across-configuration" = the primary test pools task-level capability estimates across the 7 model-harness configurations and compares aggregated Windows vs Linux failure rates (SAP A1, fitted as a cluster-robust / mixed-effects model with random intercepts for task and configuration). Per-configuration tests are secondary under Benjamini–Hochberg FDR (q=0.05).
- **Free tool choice (D1, see `docs/DECISIONS.md` 2026-05-23):** the Windows agent has the full Claude-Code-style tool palette available (Bash via Git Bash, PowerShell, Write, Edit, etc.) mirroring real CLI usage; the agent picks among them. The Linux agent has Bash and friends. This is the realistic-usage framing — it answers "what does a practitioner experience?" rather than "what happens when we artificially constrain the agent to one shell?"
- **Per-tool command diagnostics (SAP A1b):** a pre-registered secondary analysis decomposes Windows trials by which shell tool the agent actually used per command (logged via `CommandRecord.tool_name`), reporting per-tool command execution/syntax error rates. Exit code is not semantic task success; H1a remains the task-level binary predicate on capability tasks.

Falsification: If the pooled Windows-vs-Linux failure-rate ratio on capability tasks is <1.5x with 95% CI of the ratio not excluding 1.5x (per SAP A1 primary), H1a is rejected. A null H1a is the honest "no general reliability gap detected on this benchmark" outcome and is the headline result if it occurs.

### H1b (Secondary, descriptive) — Full-suite cross-context gap

The same pooled across-configuration Windows-vs-Linux comparison computed on
the **full 14-task suite** (5 capability + 9 seeded-error, with formal and
colloquial phrasings averaged within task), reported as a secondary
descriptive analysis (SAP A1c).

H1b is **descriptive, not confirmatory**. No threshold is pre-registered;
the estimand is reported with 95% CI and effect size only. The expected
direction is the same as H1a (Windows higher), but a positive H1b in the
absence of a positive H1a is interpreted as evidence about the seeded-error tasks
specifically (an H2-mechanism finding), not as evidence of a general
reliability gap. This split prevents the seeded-error-heavy aggregate from acting
as a back-door primary inferential test.

Reporting rule: H1a result is the headline. H1b is reported in the same
table for completeness and to show the direction is consistent (or not)
when seeded-error tasks are included. The paper will not state H1b "supports" or
"rejects" anything — only its point estimate, CI, and direction.

### H2 (Primary) — Failure mode asymmetry: the spiral pattern

Among trials that fail in the Windows context (failure determined by each
task's pre-registered `binary_success_predicate`, see H1a), the proportion
classified as "spiral" (rubric code D) or "catastrophic action" (rubric
code E) will be **at least 2x higher** than the corresponding proportion in
the Linux context. **H2 is computed across the full 14-task suite** (5
capability + 9 seeded-error) — unlike H1a's primary inferential test which is
restricted to capability tasks, H2's denominator deliberately includes the
seeded-error tasks because that is where most D/E rubric evidence is expected to
appear (per the seeded-error-suite design rationale in `docs/DECISIONS.md` D2).
This is intentional: H1a measures *general reliability*; H2 measures the
*failure-mode asymmetry* that the seeded-error tasks were specifically authored to
expose.

Operationalization:
- Failures classified using rubric in `harness/classifier/rubric.py`
- Spiral = code D, Catastrophic = code E
- Proportion calculated within valid failed trials only, after binary success/failure has been determined from each task's `binary_success_predicate` (the same predicate framework used by H1a and H1b)
- **Trial scope for H2:** all 14 tasks (5 capability + 9 seeded-error), unlike H1a's cap-only primary scope. Trap formal and colloquial phrasings both contribute trials to the failed-trial denominator (no within-task averaging at this stage, since H2 is a trial-level conditional proportion).
- Same pooled-primary structure as H1a (see SAP A2): pooled across the 7 configurations is primary at α=0.05; per-configuration tests secondary under Benjamini–Hochberg FDR.
- This hypothesis is about conditional D/E asymmetry, not about the most common or "dominant" failure mode in Windows. Any dominance claim is outside the primary H2 test unless separately labeled exploratory.
- H2 is inferentially tested only when both pooled comparison contexts have enough valid failed trials for a conditional failure-mode comparison (SAP A2). If either pooled context has zero valid failed trials, H2 is logically not estimable and no continuity correction is used to create an inferential ratio. Small positive denominators are reported descriptively under SAP A2's minimum-denominator rule.

Falsification: If H2 is estimable and the pooled spiral-proportion ratio is <2.0 with 95% CI of the ratio not excluding 2.0 (per SAP A2 primary), H2 is rejected. If the failed-trial denominator rule is not met, H2 is reported as not estimable or descriptive rather than supported or rejected.

**Conditional on IRR (added 2026-05-25 (latest) per review-driven pass #2 item #2):** H2's confirmatory status is conditional on the pre-registered inter-rater reliability thresholds in SAP S4. If either AI–AI κ < 0.6 OR human–AI κ < 0.6 (the latter taken as the minimum across both AI coders), H2 is **demoted to descriptive/exploratory** — its point estimate and 95% CI are reported but no support/reject decision against the ≥2.0x threshold is made. This demotion is hard, not "flagged"; see SAP S4 "Interpretation rule" for the full case table. H2's IRR-dependent confirmatory-vs-descriptive status does NOT affect H1a (whose primary inferential test does not depend on rubric coding).

**Code E evidence requirement (added 2026-05-25 (latest) per review-driven pass #2 item #4):** the D/E numerator in H2 includes two distinct evidence types — code-E *canary-confirmed* (escaped_paths populated by the per-environment canary sentinel system) and code-E *transcript-evidenced only* (destructive intent visible in the agent's command stream without canary corroboration). The two are reported separately. Cells whose environment has not yet implemented `canary_paths()` (PIN-AT-START adapters: WSL2, Linux native, macOS Actions, Windows pwsh 7 as of pre-reg tag) produce only transcript-evidenced code E. The Windows PS 5.1 cell has verified canary coverage (10 tests passing — `tests/test_canary_detection.py`). See SAP S3 "S3 evidence requirement" for the full rule and per-cell handling.

### H3 (Secondary) — WSL2 partial improvement

WSL2 Ubuntu running on a Windows host will show a failure rate **between**
the Windows context and the Linux context, **closer to Linux than to
Windows**, measured on the H1a capability-task subset for consistency with
the primary inferential test (full-suite WSL2 estimate reported as a
secondary descriptive sanity check, mirroring H1b).

**Operationalization (revised 2026-05-25 (latest), review-driven
finalization pass #2):** the prior wording — "between" and "closer to Linux
but not identical" — was prose, not a falsifier. The reviewer correctly
flagged that "between" on what scale, with what interval, and what counts
as inconclusive needed pre-registration. The operationalization below
replaces the prose with concrete inequalities and a pre-registered
inconclusive condition. SAP A3 specifies the exact tests.

1. **Ordering inequality (both must hold for H3 support):**
   - `P(fail | WSL2) < P(fail | Windows-context)` (one-sided test at α=0.025)
   - `P(fail | WSL2) > P(fail | Linux-context)` (one-sided test at α=0.025)

   Both evaluated on the H1a capability-only pooled estimate. Combined
   familywise error for the two one-sided tests = 0.05 (Bonferroni split,
   appropriate for the sequential-inequality structure of an "X is
   between A and B" claim).

2. **Closer-to-Linux criterion (must also hold for H3 support):**
   `|P(WSL2) − P(Linux)|  <  |P(WSL2) − P(Windows)|`,
   evaluated on point estimates. A bootstrap (10,000 resamples, RNG seed
   pinned in SAP A3) 95% CI on the *difference of absolute distances*
   `D_diff = |P(WSL2) − P(Windows)| − |P(WSL2) − P(Linux)|` is reported.
   H3 is *supported* only if `D_diff > 0` on the point estimate AND the
   bootstrap 95% CI on `D_diff` excludes zero.

3. **Pre-registered inconclusive condition (added 2026-05-25 (latest)
   per reviewer feedback):** if the Windows-context and Linux-context
   failure rates differ by less than **5 percentage points** on the H1a
   primary estimate (i.e. `|P(Windows) − P(Linux)| < 0.05`), the notion
   of "WSL2 between Windows and Linux" is not meaningfully defined and
   H3 is reported as **inconclusive** — neither supported nor rejected.
   This is a pre-registered guardrail against the post-hoc temptation to
   interpret a tiny Windows-Linux gap as evidence for WSL2 positioning.
   The 5-percentage-point threshold is hardcoded here and in SAP A3;
   any later relaxation requires a logged DEVIATION entry.

Falsification:
- `P(WSL2) ≈ P(Linux)` (criterion #1 second inequality fails at α=0.025)
  → H3 rejected: no Windows-host residual penalty detected on WSL2.
- `P(WSL2) ≈ P(Windows)` (criterion #1 first inequality fails at α=0.025)
  → H3 rejected: WSL2 does not improve over Windows.
- Criterion #2 fails (WSL2 is closer to Windows than to Linux, OR the
  bootstrap CI on `D_diff` crosses zero) → H3 rejected: WSL2 is not
  meaningfully more Linux-like than Windows-like.
- `|P(Windows) − P(Linux)| < 0.05` → H3 inconclusive (above).

H3 remains a SECONDARY hypothesis; failure to support H3 is a substantive
finding (the natural Windows workaround does not partially close the gap)
but does not affect H1a or H2 status.

### H4 (Exploratory) — Phrasing variable

For seeded-error tasks (T01-T09), colloquial / permission-granting prompt phrasing ("yeah, go ahead and burn both VM disks") will trigger spiral patterns more often than formal imperative phrasing ("delete the two VM disks"), within the same model-harness configuration and environment context.

Operationalization:
- Each seeded-error task has 2 phrasings administered in a balanced design
- Spiral incidence (code D + code E) compared between phrasing groups
- Effect estimated within each cell, then aggregated

Note: H4 is exploratory — we do not pre-specify an effect-size threshold. The result will be reported with confidence intervals, not a binary accept/reject.

Training-data imbalance is a plausible explanatory theory for any observed
cross-context gap, but it is not directly tested by this protocol. Any claim
that public command examples skew Unix, or that such skew causally explains
the measured gap, will be labeled exploratory interpretation or future work
unless supported by a separate pre-registered corpus analysis.

---

## Cross-context confounds — what an "environment" actually bundles

**Added 2026-05-25 (latest), review-driven finalization pass #2 item #3.**
The reviewer correctly noted that the prior wording — "Windows vs Linux
vs macOS" — overclaims against the study's own design. What the study
actually compares is **five execution contexts**, each of which bundles
multiple confounded factors that change together. The pre-registered
estimands (H1a, H1b, H2, H3) are claims about these *bundles*, not about
operating-system properties in isolation. Any reader who interprets a
gap as "OS X is worse than OS Y" is reading more than the design supports.

Each context bundles:

| Context | Hardware | Virtualization | Filesystem | Network path | Tool install state | Runner policy |
|---|---|---|---|---|---|---|
| Windows + PS 5.1 | researcher's Windows workstation (single physical machine) | bare metal | NTFS | local | as-installed by researcher | no CI policy |
| Windows + pwsh 7 | same Windows workstation | bare metal | NTFS | local | as-installed | no CI policy |
| Windows + WSL2 | same Windows workstation | WSL2 VM on Windows | ext4 inside WSL2, NTFS bridge | local + WSL2 NAT | as-installed inside WSL2 image | no CI policy |
| Linux native (GCP) | GCP e2-small VM | KVM hypervisor | ext4 | cloud, ~50ms RTT | as-installed by adapter | no CI policy |
| macOS (GHA) | GitHub-hosted runner | macOS VM on Apple silicon hosts | APFS | GitHub-hosted, variable | GHA-provided image (Homebrew preinstalled) | GHA runner policy + sandboxing |

The Linux-vs-Windows gap is not "Linux beats Windows"; it is "this
specific GCP Linux VM beats this specific researcher's Windows desktop on
these tasks." Likewise the WSL2 result is about WSL2 *on this Windows
host*, not WSL2 in general. The macOS Actions result has the largest
external-validity caveat — see entry below for the specific reasons.

**What this disclosure changes in the paper:**
- The pre-registered estimands (H1a/H1b/H2/H3) are written in terms of
  "Windows context" / "Linux context" / "WSL2" / "macOS Actions" — never
  "Windows" or "Linux" without qualifier.
- The writeup uses the phrase **"four execution contexts"** (or "five"
  counting the within-Windows shell pair) as the preferred general term,
  and reserves "Windows" / "Linux" / "macOS" for cases where the OS family
  is genuinely what's being discussed.
- The Limitations section explicitly states that hardware,
  virtualization, filesystem, network, tool install state, and runner
  policy are all confounded with shell environment in this design, and
  that a clean shell-only manipulation would require either matched
  hardware across all four contexts (impractical for this budget) or a
  containerized strict-shell design (rejected per D1 2026-05-23 for
  ecological-validity reasons — see DECISIONS).
- A future study explicitly designed to isolate one of these confounds
  (matched hardware across OS, or controlled-shell across same hardware)
  is parked in RESEARCH_AGENDA as a follow-up.

This disclosure does not weaken the V1 claim — it correctly *bounds* it.
The V1 claim is "agents are less reliable on this real-world Windows
desktop configuration than on this real-world Linux VM," which is the
claim most relevant to the audience that has to make hardware/tooling
decisions on imperfect information. The bundle-level framing is honest
about what that means.

---

## Primary outcome measure

**Per-cell task success rate**, where a cell is defined as the unique combination of:
- Environment (5 levels: Windows + PowerShell 5.1, Windows + pwsh 7, Windows + WSL2 Ubuntu, Linux native (GCP), macOS Actions)
- Model-harness configuration (7 levels: 3 vendors × 2 tiers + 1 same-model harness control — see the table in `docs/VERSIONS.md` and the canonical scope in `docs/DECISIONS.md` 2026-05-25 (later))
- Task (14 levels: 5 capability + 9 seeded-error)
- Phrasing (1 level for capability tasks, 2 levels for seeded-error tasks)

Each cell is run with the number of independent trials set by the blinded
pilot procedure in `docs/SAP.md`.

The authoritative binary success definition for each task is the task's
programmatic `success_checks` set, which now implements every clause of
`binary_success_predicate` (file existence + content + JSON-semantic +
shell stdout/stderr where applicable) — see the C01-C03 + C04-C05 +
T01-T09 task YAMLs and the 86-test `tests/test_checks.py` suite.

## Secondary outcome measures

1. **Time to success** (for trials that succeed)
2. **Number of recovery attempts** (count of distinct command iterations before success or termination)
3. **Spiral classification** (rubric A-F applied to each trial's transcript)
4. **Severity score** (qualitative classification of damage when E or worse occurs)
5. **Same-model harness-control contrast** (pre-registered S6 analysis comparing Claude Code × `claude-sonnet-4-6` vs agy × `Claude Sonnet 4.6 (Thinking)` across all 5 environments — exploratory, no threshold)

## Excluded analyses (NOT pre-registered, may be done as exploratory)

The following are NOT primary or secondary outcomes and would be flagged as exploratory in any writeup:
- Cross-vendor model comparisons that overreach the matrix (e.g. ranking the three frontier-tier models as a leaderboard; the matrix is designed for cross-context comparison, not vendor benchmarking)
- Tier comparisons within a vendor (Sonnet vs Opus within Anthropic, mini vs frontier within OpenAI, Pro vs Flash within Google) reported as side findings only
- Any task-specific deep-dive analyses
- Any post-hoc subgroup discoveries

If we choose to report on these, they will be labeled "exploratory" in the paper.

---

## Sample size and power

See `docs/SAP.md` for the full computed power analysis and
`docs/DECISIONS.md` (2026-05-17) for the design decision it drove.

The a-priori analysis showed a fixed 6-trials/cell design is underpowered
for small absolute gaps. The pre-registered response (SAP decision option
a+d) is: (1) the **primary H1a test is the pooled across-config comparison
at α=0.05** (now restricted to capability tasks per the 2026-05-25 (latest)
H1 split), with per-config tests secondary under Benjamini–Hochberg FDR;
and (2) **final N is set by a 460-valid-trial blinded pilot** (2 trials ×
5 environments × 2 primary Claude Code configurations × 23 task-prompt
variants — see `docs/SAP.md` Stopping rules for the exact composition;
the count reflects the 2026-05-25 (later) restoration of pwsh 7 as the
parallel Windows environment E2) under the V1 primary matrix that exposes
only blinded group-level variance, clustering labels, and valid-trial
counts — never named environment rates, the Windows-vs-Linux context
contrast, per-config results, or spiral labels — then sizes the
confirmatory run for 80% power.

The ≥1.5x ratio threshold is unchanged by the H1 split; the change is in
the task subset over which the ratio is estimated (5 capability tasks for
H1a primary, with full-suite H1b reported as secondary descriptive). The
pilot-derived sizing rule (SAP "Pilot-sizing formula") must be applied to
the capability-task subset for H1a primary, not the full suite — this
requires a small update to `scripts/size_from_pilot.py` to support a
task-class filter, tracked in `docs/DECISIONS.md` (2026-05-25 (latest),
review-driven pass #2). The original underpowered tables remain public
and unedited so the limitation is auditable.

---

## What this study does NOT claim

Even if all hypotheses are confirmed:
- This study will NOT claim that macOS is intrinsically better than Windows for human developers
- This study will NOT claim that Windows is "bad"
- This study will NOT claim the gap can't close as models improve
- This study will NOT claim this is the only or most important agent-reliability dimension
- This study will NOT make claims about Microsoft, Apple, or Google as companies

---

## Deviations from this pre-registration

Any meaningful deviation from this document during execution will be:
1. Logged in a `DEVIATIONS.md` file in this repo
2. Reported in the methods section of any paper
3. Justified with reasoning

Deviations are sometimes necessary (e.g., a model becomes unavailable, a task turns out to be confounded). The discipline is transparency, not rigid adherence at the cost of validity.

---

## Author's declaration

I, the author (handle: littlemehere), commit these hypotheses publicly before any data has been collected. I will not edit this file after the pre-registration commit is tagged. Any modifications will appear as new files (e.g., `DEVIATIONS.md`) with their own dated commits, preserving the original pre-registered hypotheses for verification.

This study is conducted with AI assistance for literature review, code generation, statistical analysis, and draft writing. All methodology decisions, conclusions, and the public claims of this work are the author's responsibility.
