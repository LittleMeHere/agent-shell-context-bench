# V2 statistical decision memo

**Status:** EVIDENCE BASIS — V2 direction accepted 2026-08-09; exact D-005 parameters remain open
**Created:** 2026-07-28
**Decision IDs:** D-001 through D-005, with D-009 implications, in
`docs/PRE_DATA_REMEDIATION.md`

## 1. Purpose

This memo records the alternatives and evidence considered before the
researcher accepted the V2 direction on 2026-08-09. The canonical decision
record is `V2_ACCEPTED_DECISIONS.md`. This memo does not itself modify or
supersede V1; remaining D-005 implementation choices still require the named
recovery and coverage evidence before the V2 amendment is frozen.

No pilot or confirmatory outcomes may be used to choose among these options.

## 2. Facts the decision must respect

1. The substantive project retains H1–H4, seven model-harness
   configurations, and five environments; the V2 capability roster is the
   accepted 12-family/six-domain design rather than the five-task V1 roster.
2. H1a and H3 use the qualified V2 capability-family bank.
3. H1b is descriptive over all fourteen tasks.
4. H2 is conditional on valid failed trials and reliable A–F coding.
5. H4 is exploratory and does not require a threshold-based support decision.
6. The confirmatory matrix has 805 cells and uses a common base N unless the
   pre-specified vendor-mini-pilot expansion rule raises a vendor's N.
7. The pilot is separate from confirmatory inference and must remain
   outcome-blind until N is locked.
8. The target estimand must determine the model and power procedure, not the
   other way around.

## 3. D-001 — H1a decision rule

### V1 problem

V1 uses a 1.5x ratio both as the effect used for ordinary
no-difference-versus-difference power and as the confidence-bound threshold
for supporting H1a. Those are different tests. A true effect on the threshold
cannot yield 80% probability that a 95% lower confidence bound clears that
same threshold.

### Option A — threshold-superiority claim

Define:

- null: `RR_Windows/Linux <= 1.5`;
- alternative: `RR_Windows/Linux > 1.5`;
- support: the pre-specified lower confidence bound is greater than 1.5;
- reject: the upper confidence bound is below or equal to 1.5;
- inconclusive: the interval crosses 1.5.

Power must be evaluated at one or more design alternatives strictly above
1.5. The design alternative cannot be chosen from pilot effect estimates.

**Advantages:**

- closest to the literal V1 headline;
- makes 1.5 a genuine minimum-effect threshold;
- produces honest three-way decisions.

**Costs and risks:**

- may require a very large N;
- requires a defensible reason for the design alternative above 1.5;
- "reject" and "inconclusive" become distinct, unlike some V1 wording.

### Option B — existence plus practical-magnitude claim

Define:

- statistical evidence: lower confidence bound greater than 1.0;
- practical magnitude: point estimate at least 1.5;
- support only when both hold;
- otherwise use pre-specified reject/inconclusive branches.

Power is simulated for the joint rule, not borrowed from a test of `RR=1`.
A design alternative above 1.5 is still needed to make the point-estimate
criterion exceed 1.5 with high probability.

**Advantages:**

- separates evidence that a gap exists from evidence about its magnitude;
- generally less demanding than requiring the full interval to clear 1.5;
- directly displays statistical and practical conclusions.

**Costs and risks:**

- is a more substantive change from V1;
- the point-estimate threshold can be unstable near 1.5;
- significance against `RR=1` plus a point estimate above 1.5 does not
  control the probability of falsely implying that the true magnitude
  exceeds 1.5; paper language would need to distinguish an observed
  magnitude from a confidence-bounded magnitude;
- needs exact branches when only one of the two criteria holds.

### Option C — estimation-first H1a

Remove the support threshold. Pre-register the task-weighted marginal risk
ratio, risk difference, and confidence intervals as the primary result.
Interpret 1.5 as a reference magnitude rather than a binary decision boundary.

**Advantages:**

- aligns the paper with effect estimation;
- avoids a brittle threshold;
- a null or modest effect remains straightforward to report.

**Costs and risks:**

- changes H1a from a threshold hypothesis to an estimation question;
- is least faithful to "all four hypotheses as planned."

### Option D — decision-relevant absolute-gap classification

Define the primary estimand as the finite-roster, task-weighted absolute risk
difference:

```text
RD = P(failure | Windows context) - P(failure | Linux context)
```

Before any pilot outcomes are inspected, select `delta_RD`, the smallest
absolute increase in failure probability that would change an intended
training, evaluation, or deployment decision. The justification must be tied
to that use, not reverse-engineered from an affordable N or an expected
effect. Report the risk ratio as a companion estimand rather than making it
the sole decision scale.

Using a confidence interval `[L_RD, U_RD]` whose coverage has been validated
for the selected finite-roster analysis:

- **decision-relevant gap:** `L_RD > delta_RD`;
- **bounded below the decision threshold:** `U_RD < delta_RD`;
- **inconclusive:** `L_RD < delta_RD <= U_RD`.

Direction relative to zero is reported as a qualifier rather than used to
replace these branches. For example, an interval entirely between zero and
`delta_RD` supports a positive but decision-small gap; an interval spanning
both zero and `delta_RD` is inconclusive about both existence and practical
magnitude.

**Advantages:**

- makes a sufficiently precise negative result informative for a stated
  decision;
- avoids treating a large relative change from a near-zero baseline as
  automatically operationally important;
- remains defined in many zero-event settings where the risk ratio is not;
- matches a claim about the exact registered task/configuration roster.

**Costs and risks:**

- changes V1's primary scale and requires a defensible decision use for
  `delta_RD`;
- different users may have different meaningful absolute thresholds;
- an absolute threshold can hide an important relative effect when the
  baseline is very low, so the risk ratio and both marginal rates must still
  be reported;
- interval construction near zero and under heterogeneous cells must pass
  coverage simulations rather than relying on a naive Wald approximation.

### Interpretability firewall common to all options

A result should be called **uninterpretable** only when a pre-specified
measurement-integrity gate fails. Before outcomes, V2 must name the exact
gates and their deterministic consequences. At minimum they should cover:

- plan, task, phase, and record provenance;
- binary-outcome construct validity and auditable timeout/agy handling;
- execution-context and model/version fidelity;
- cell completion, invalid-attempt attribution, and non-selective cap
  handling;
- temporal balance and the pre-specified backend-drift rule.

If all gates pass, the inferential result must remain one of the rule's
substantive states: support/decision-relevant, bounded-small/reject, or
inconclusive. A wide interval is **inconclusive**, not evidence of no effect.
A narrow interval below the threshold is evidence that the effect is bounded
on this finite benchmark roster. Low event rates, an uninteresting secondary
analysis, or disappointment with the result cannot be introduced after the
fact as reasons to relabel it "weak methods."

Ceiling/floor behavior and per-task heterogeneity must always be displayed as
scope diagnostics. They can narrow the paper's generalization, but they do
not invalidate a finite-roster estimate unless a pre-specified integrity gate
was actually breached. Conversely, passing these gates does not license a
claim about tasks, models, machines, or users outside the registered roster.

### D-013 dependency — what task population receives the threshold

D-001 cannot be approved independently of the capability-task population in
D-013. A five-point threshold applied to five purposively selected fixtures
does not have the same decision meaning as five points averaged across a
domain-stratified task bank. Increasing repeated trials can make the former
estimate precise but cannot create missing task-domain coverage.

An all-success result also has two separate interpretations. A sparse-safe
risk-difference interval may validly bound the context penalty on the exact
roster, while a blinded ceiling gate may still determine that the instrument
does not support the intended broader task-population decision. V2 must fix
the task-population scope and ceiling-response rule before attaching
support/bounded-small language to D-001. See
`docs/TASK_CONSTRUCT_AUDIT.md` and the costed alternatives in
`docs/TASK_BANK_DESIGN_OPTIONS.md`.

### Required evidence before D-001

For each viable option, simulate:

- type-I error or false-support probability at the relevant boundary;
- probability of every substantive state, including a correct bounded-small
  conclusion where the candidate rule permits one;
- interval coverage;
- bias and RMSE of risk-ratio and risk-difference estimators;
- behavior at low Linux failure rates and zero-event cells;
- sensitivity to task/configuration heterogeneity;
- probability that a true decision-relevant effect is incorrectly declared
  bounded-small, and vice versa;
- N and total trial count required over a pre-specified parameter grid.

For Option D, repeat the operating-characteristic grid over multiple
prospective `delta_RD` values. The grid is evidence about feasibility and
tradeoffs; it must not be used to choose whichever threshold makes an
observed result look decisive.

## 4. D-002 — H2 rule and power

### V1 problem

H2 repeats the H1 boundary issue with a 2.0x D/E ratio, but its denominator is
itself random: only valid failed trials enter. H1 sizing does not guarantee
enough failures or enough D/E events to estimate H2. IRR can also demote H2
after collection.

### Option A — separately powered threshold H2

Retain a threshold-superiority rule at 2.0 and size the full experiment to
meet both H1 and H2 targets, subject to the pre-committed resource cap.

Simulation must jointly vary:

- Windows and Linux task-failure rates;
- conditional D/E rates;
- task/configuration heterogeneity;
- invalid-trial rates;
- IRR misclassification rates.

Use the maximum N required by H1 and H2.

**Advantage:** gives H2 a real prospect of confirmatory interpretation.

**Risk:** conditional event scarcity may make the required N infeasible.

### Option B — confirmatory rule with prospective feasibility envelope

Retain H2's support rule and minimum denominators, but explicitly state that
the experiment is powered for H1 and only characterized prospectively for H2.
Before collection, publish the probability that H2 is estimable and its power
over a scenario grid. If the resource cap cannot support H2, that limitation
is known before data rather than discovered afterward.

**Advantage:** preserves H2 without allowing it to determine an unbounded N.

**Risk:** "confirmatory" can be misleading if most plausible scenarios are
underpowered. A minimum acceptable estimability probability should therefore
be pre-specified.

### Option C — make H2 explicitly exploratory

Retain the estimand, rubric, IRR, and reporting but remove the
support/reject threshold.

**Advantage:** scientifically honest if event counts cannot support the
threshold claim.

**Risk:** changes the status of one of the four planned hypotheses.

### Required evidence before D-002

- A simulation table of H2 estimability and decision probabilities over
  plausible H1 failure and conditional D/E rates.
- Misclassification sensitivity at κ values around the 0.6 demotion
  threshold.
- Trial and AI-coding cost under each option.
- An explicit rule for whether H2 can increase N beyond the H1 requirement.

The first prospective denominator and optimistic pooled-reference grid is in
`docs/D013_CEILING_SIMULATION_MEMO.md`. It finds that H2 can remain weak even
when its pooled failed-trial minimum is satisfied. Exact-model clustering and
IRR-misclassification simulations remain required; the reference does not
resolve D-002.

## 5. D-003 — power and blinded nuisance re-estimation

### V1 problem

The current closed form does not match the proposed confirmatory analysis.
It uses the five-environment pooled rate as a comparison-arm baseline and
does not use `blinded_group`. The implemented ICC construction does not match
the SAP's mixed-model description.

### Proposed common foundation

Regardless of D-001/D-002, replace the closed form with a versioned Monte
Carlo operating-characteristic simulation that:

1. generates the exact 805-cell design;
2. generates cell outcomes under the candidate analysis model;
3. reproduces the complete decision rule, including zero-event and
   convergence branches;
4. runs the exact analysis implementation intended for confirmatory data;
5. records Monte Carlo uncertainty;
6. checks both null and alternative scenarios;
7. is independently cross-checked on reduced analytic cases.

Simulation-based power is standard when no tractable analytic solution
matches a GLMM. Relevant starting points include:

- Kumle, Võ, and Draschkow, *Estimating power in (generalized) linear mixed
  models: An open introduction and tutorial in R*:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8613146/
- Green and MacLeod, *SIMR: an R package for power analysis of generalized
  linear mixed models by simulation*:
  https://doi.org/10.1111/2041-210X.12504

### Candidate blinded re-estimation methods

#### Method 1 — blinded nuisance distribution, worst-case target baseline

Fit nuisance heterogeneity using blinded group labels, treat each blinded
group in turn as the possible Linux baseline, and select the largest N over
the pre-specified possibilities. Do not expose the per-group values.

**Property:** preserves researcher blinding without pretending the overall
five-group rate is the Linux rate.

**Risk:** may be conservative and unstable with only two trials per pilot
cell.

#### Method 2 — sealed deterministic contrast service

An independently specified program has access to the sealed mapping, computes
only approved nuisance parameters, and emits N plus an audit proof/digest. The
researcher sees neither named rates nor intermediate group effects.

**Property:** can estimate nuisance quantities targeted to Windows/Linux.

**Risk:** operational secrecy is weak when the researcher ultimately controls
the machine; the credibility rests on immutable code, sealed artifacts, and
no intermediate output.

#### Method 3 — fixed N from prospective scenarios; pilot is operational only

Select N before the pilot using a conservative scenario grid. Retain the
460-trial pilot only for infrastructure, invalid-rate, and variance-model
validation, without changing N.

**Property:** simplest inferential story.

**Risk:** materially changes the V1 adaptive design and may waste pilot calls.

#### Method 4 — validated blinded binary-outcome recalculation method

Adapt a published blinded binary-outcome sample-size re-estimation procedure,
then evaluate it inside the full hierarchical simulation.

Starting references:

- Baumann, Pilz, and Kieser, *blindrecalc — An R Package for Blinded Sample
  Size Recalculation*:
  https://journal.r-project.org/articles/RJ-2022-001
- Shih and Zhao, *Design for sample size re-estimation with interim data for
  double-blind clinical trials with binary outcomes*:
  https://pubmed.ncbi.nlm.nih.gov/9304763/

These methods were not written for this five-environment crossed benchmark.
They are evidence sources, not drop-in validation. The selected method must
still pass benchmark-specific simulations.

### Required evidence before D-003

- For each candidate, distributions of selected N, achieved power, false
  support, and cap-binding frequency.
- Behavior under unequal non-target environment rates.
- Behavior under pilot/configuration variance mismatch.
- Confirmation that the output reveals no prohibited named effects.
- A precise statement about whether pilot data are discarded or reused;
  V1 currently discards them from confirmatory inference.

`docs/D013_CEILING_SIMULATION_MEMO.md` adds prospective 12-family common-N and
split-N precision references plus exact construct counterexamples. Its
oracle-normal intervals are deliberately not a substitute for the selected
D-005 implementation.

## 6. D-004 — resource cap

The cap must be a number or deterministic per-vendor rule fixed before pilot
outcomes. "Subscription limits" alone is not a reproducible cap.

The minimum collection burden is:

- 460 valid pilot trials;
- `805 * N` valid confirmatory trials;
- at `N=6`, 5,290 valid collection trials total;
- invalid attempts are additional;
- optional Codex and `agy` mini-pilots add 460 and 690 valid trials,
  respectively.

Under the current full-transcript IRR design, two AI coders add
`2 * 805 * N` grading calls. At `N=6`, that is 9,660 calls, plus a human
anchor of at least 50 transcripts.

Before D-004, the project needs measured distributions from non-analysis
shakedowns for:

- wall time per agent/configuration/task class;
- tokens or usage units per call;
- transcript bytes per trial;
- invalid-attempt rate;
- vendor rate-limit and reset behavior;
- AI-rater input/output tokens;
- E4 VM and E5 Actions resource consumption.

The accepted decision must fix:

- `N_max`;
- total collection-attempt or usage envelope;
- per-vendor overage behavior;
- maximum calendar collection window;
- whether vendor mini-pilots are affordable;
- plan-limit handling that does not selectively stop unfavorable cells.

## 7. D-005 — confirmatory model and software

### The estimand question comes first

The five capability tasks and seven configurations are deliberately selected,
not random samples from well-defined populations. Treating task and
configuration as random effects implies a superpopulation interpretation that
may be stronger than the actual benchmark supports. Conversely, treating
them as fixed blocking factors limits the claim to the registered roster but
avoids estimating variance distributions from only five and seven levels.

The decision must explicitly choose the target:

1. **Finite-roster estimand:** average effect over these five tasks and seven
   configurations.
2. **Superpopulation estimand:** generalization to a wider task and
   model-harness population.

The README and H1 language currently sound closer to a finite-roster claim
than a random sample of all possible tasks/models.

Research on few random-effect levels does not supply a universal cutoff, but
it does warn that variance estimates can be unstable and singular fits more
common:

- Gomes, *Should I use fixed effects or random effects when I have fewer than
  five levels of a grouping factor in a mixed-effects model?*:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8784019/

### Candidate analysis families

#### Family A — frequentist GLMM matching V1

Binary GLMM with context fixed effect and crossed task/configuration random
intercepts, marginalizing predicted probabilities to the pre-specified
task-weighted risk ratio.

Candidate implementation: R `glmmTMB` or `lme4`, with a separately tested
marginal-effects/bootstrap layer.

Relevant implementation reference:

- Brooks et al., *glmmTMB Balances Speed and Flexibility Among Packages for
  Zero-inflated Generalized Linear Mixed Modeling*:
  https://journal.r-project.org/articles/RJ-2017-066/

**Risk:** only five capability-task levels and seven configuration levels;
convergence and variance-component behavior must be simulated.

#### Family B — finite-roster fixed-block model

Treat task and configuration as fixed blocking factors, construct the
pre-specified equal-task-weighted marginal probabilities, and obtain
uncertainty from a pre-specified parametric or stratified bootstrap that
respects repeated trials within cells.

**Advantage:** matches a claim about the exact benchmark roster.

**Risk:** does not justify generalization beyond these tasks/configurations
and still needs a principled heterogeneity/interaction treatment.

#### Family C — hierarchical Bayesian model

Fit task/configuration variation hierarchically and report posterior
probabilities/intervals for the marginal ratios.

**Advantage:** handles sparse binary cells and partial pooling naturally.

**Risk:** largest departure from V1's frequentist thresholds and requires
prior-sensitivity decisions.

### Required evidence before D-005

For Families A and B at minimum:

- convergence/failure frequency;
- interval coverage and decision error;
- bias in task-weighted marginal risk ratios;
- zero-event and complete-separation behavior;
- sensitivity to task-by-context and configuration-by-context
  heterogeneity;
- leave-one-capability-task-out sensitivity, reported as a robustness
  diagnostic rather than an alternate primary result;
- exact fallback behavior when the primary model cannot be estimated;
- independent implementation check on simple cases.

The final choice must be one primary model fixed before data, not a
post-outcome contest among packages.

### Prospective finite-roster and IRR evidence (2026-08-01)

`docs/D005_FINITE_ROSTER_IRR_MEMO.md` evaluates analytic Family B comparators
on the exact candidate 12-family/3-instance schedule and simulates the H2
reliability gate. The ordinary within-instance variance estimator is
unestimable at base-N=6 and base-N=12 split designs and undercovers sparse
outcomes when it becomes estimable. A Jeffreys-stabilized comparator avoids
that failure but is conservative and often inconclusive. Neither is approved.

The same evidence establishes that omnibus six-category κ can pass while a
small D/E false-positive rate materially attenuates H2 when D/E is rare. Low
binary κ in that counterexample is itself partly a prevalence effect, so it is
not a drop-in replacement gate. D-010 must instead pre-specify class-specific
error and acceptable effect-scale bias; omnibus κ alone does not control
either. The intended R GLMM toolchain is not available in the current
environment, so the required Family A/B comparison, final bootstrap, and
joint H2 measurement/model simulation remain OPEN.

`docs/D010_JOINT_H2_MEASUREMENT_MEMO.md` subsequently replaces the fixed-N
IRR and equal-stratum approximations with the exact matched-N full matrices
and registered four-per-stratum-plus-proportional human sampler. The 50-case
minimum-size instantiation averages only about five failed and roughly
0.7-1.1 failed D/E
transcripts. It can
therefore pass omnibus κ under severe shared D/E-to-C bias, and the candidate
primary-label rules produce materially different H2 bias, support, and
adjudication burden. This narrowed D-010 but did not select a rule; at that
stage, an outcome-specific probability audit and the final D-005 model
remained OPEN.

`docs/D010_ENRICHED_AUDIT_MEMO.md` then compares four known-probability
focal-failure audits. It shows that the difference estimator can recover the
full human-reference point estimand, but sparse AI-state strata can miss
shared wrong agreement and report zero or too little residual variance.
Small enriched audits consequently produce non-monotonic apparent support and
severe undercoverage. At base N=24/B=400, shared-bias support remains only
24.3-39.4% versus a 64.5% latent oracle at a conservative cost of 450 human
labels. No allocation or interval is selected; conservative rare-residual
uncertainty and coupling to the final D-005 model remain OPEN.

`docs/D010_CONSERVATIVE_AUDIT_INTERVAL_MEMO.md` subsequently replaces the
failed plug-in residual variance with simultaneous exact finite-population
hypergeometric bounds. The repair achieves 99.9-100% finite-human coverage
and removes the apparent advantage of AI-state enrichment. Context SRS needs
roughly 600-800 labels from about 864 focal failures before audit measurement
usually stops bottlenecking a 3x effect. At census, however, an RR=2 scenario
still yields a realized finite-human ratio above 2 in about half of runs,
showing that D-005 must separately handle trial/task/configuration variation.
No audit, interval, N, or model is selected.

`docs/D004_D005_RESOURCE_FEASIBILITY_MEMO.md` performs that first joint
screen. A pooled two-phase fixed-roster candidate maintains 95.0-96.0%
coverage and 0.1-2.2% coupled threshold clearing across the perfect-reference
RR=2 B=400-census grid. B=700 plus the anchor is close to its N=24 full-human
ceiling, but coupled support for a synthetic 3x effect is only about 64-67%
with perfect labels and about 49% with a 98%-accurate reference. A broader
task-by-configuration t(6) sensitivity is much less decisive, while a
cellwise Jeffreys delta attempt is rejected for severe undercoverage. The
evidence narrows the resource frontier to B=600-700 but does not select a
claim scope, D-005 family, H2 status, or budget.

### D-009 interaction — time, order, and backend drift

Power and coverage simulations must not assume every trial in a cell is
exchangeable across an arbitrarily long collection window without checking
that assumption. At least two drift scenarios should be included:

1. a monotonic calendar-time change in failure probability shared by a
   vendor; and
2. a discrete backend/routing change partway through collection.

Compare whole-cell batching with a pre-generated blocked or round-robin
schedule. Report balance by environment, configuration, task class, and
phrasing over fixed collection epochs and host-specific subsequences. The
selected schedule must remain outcome-blind and resumable.

The confirmatory analysis should have one pre-specified epoch/drift
sensitivity path. It must not add or remove time adjustment after viewing
which version produces the preferred result.

## 8. Preliminary recommendation for simulation work

This is a recommendation about what to prototype, not an approved V2
decision:

1. Prototype D-001 Option A, Option B, and Option D.
2. Prototype D-002 Option A and Option B.
3. Compare D-005 Family A against Family B under the same finite-roster data
   generators.
4. Evaluate D-003 Method 1 and Method 4; retain Method 2 only if neither can
   achieve acceptable operating characteristics.
5. Do not select a design alternative, nuisance grid, or N cap until D-004
   shakedown evidence is available.

The prototype should output a compact operating-characteristics table, not
only a single "power" number. At minimum each scenario reports:

- true parameters;
- selected N distribution;
- support/reject/inconclusive probabilities;
- type-I error or false-support probability;
- coverage;
- estimator bias/RMSE;
- convergence/fallback rate;
- resource-cap binding rate;
- Monte Carlo standard error.

## 9. Initial reference-simulation smoke

An outcome-blind scaffold now exists at
`analysis/d001_operating_characteristics.py`, with focused tests at
`tests/test_d001_operating_characteristics.py`. It simulates the exact H1a
finite roster of 5 capability tasks × 7 configurations × 2 focal contexts
with a common N. Fixed task, configuration, and context-interaction
heterogeneity is applied on the logit scale, then calibrated to the requested
finite-roster marginal rates.

This is **not** the D-003/D-005 confirmatory implementation. It uses an
equal-weighted finite-roster estimator, a non-degenerate Newcombe score
interval for the risk difference, and a log-delta risk-ratio interval with
an auditable within-cell binomial variance estimate. Its purpose is to
falsify bad candidate rules and identify design regions requiring better
methods. The tests include an independent homogeneous-binomial RMSE oracle,
threshold-boundary cases, a low-event risk-ratio counterexample, and seed
reproducibility.

The following smoke grid used 20,000 replicates per scenario, fixed
`delta_RD=0.05`, the default heterogeneity values in the scaffold, and seeds
20260730–20260737 and 20260810–20260813. It is reproduced by:

```text
python -m analysis.d001_operating_characteristics --linux-rates 0.05,0.20 --target-rds 0,0.05 --n-per-cell 6,24 --delta-rd 0.05 --replicates 20000 --seed 20260730
python -m analysis.d001_operating_characteristics --linux-rates 0.05,0.20 --target-rds 0.10 --n-per-cell 6,24 --delta-rd 0.05 --replicates 20000 --seed 20260810
```

"Full trials" is `805 * N` confirmatory valid trials; it excludes the
460-trial pilot and invalid attempts.

| Linux rate | True RD | N | Full trials | D relevant | D bounded-small | D inconclusive | RD coverage |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.05 | 0.00 | 6 | 4,830 | 0.00% | 61.47% | 38.53% | 95.57% |
| 0.05 | 0.00 | 24 | 19,320 | 0.00% | 99.68% | 0.33% | 95.37% |
| 0.20 | 0.00 | 6 | 4,830 | 0.06% | 23.79% | 76.16% | 95.76% |
| 0.20 | 0.00 | 24 | 19,320 | 0.00% | 73.51% | 26.49% | 95.88% |
| 0.05 | 0.10 | 6 | 4,830 | 39.51% | 0.00% | 60.49% | 95.89% |
| 0.05 | 0.10 | 24 | 19,320 | 94.63% | 0.00% | 5.37% | 95.82% |
| 0.20 | 0.10 | 6 | 4,830 | 20.50% | 0.04% | 79.46% | 96.30% |
| 0.20 | 0.10 | 24 | 19,320 | 67.16% | 0.00% | 32.85% | 96.03% |

Monte Carlo standard errors for the displayed decision probabilities were at
most 0.36 percentage points. At the exact Option D boundary
`true_RD=delta_RD=0.05`, approximately 95% of runs were inconclusive and each
decisive tail occurred about 2%–3% of the time. That is the expected behavior
of a coherent interval-threshold rule and independently demonstrates why
80% "support" cannot be claimed at a design truth equal to the boundary.

The smoke also exposed two important rule consequences:

- Under Option A, at Linux 0.05 and Windows 0.10 (`RR=2.0`), support was only
  9.63% at N=6 and 35.23% at N=24.
- Under Option B, at Linux 0.20 and Windows 0.25 (`RR=1.25`, below the 1.5
  magnitude threshold), the joint rule still returned "support" in 15.68%
  of N=6 simulations. This confirms that the point-estimate magnitude
  condition does not control false magnitude claims.

These results do not approve Option D or a five-point threshold. They show
that:

1. the current N=6 floor does not guarantee either an informative null or
   adequate power for a five-point decision threshold;
2. operating characteristics vary substantially with the baseline rate even
   on the risk-difference scale;
3. the V2 decision must jointly fix the decision use, threshold, resource
   envelope, interval method, and scenario grid; and
4. Option B as currently written needs different claim language or a stronger
   interval requirement before it is a viable magnitude rule.

R-001 remains OPEN. This smoke is only the first evidence artifact; sparse,
zero-event, stronger-interaction, drift, attrition, and candidate-analysis
family grids remain required.

## 10. Approval record

No decision has been approved yet.

When a decision is accepted, append:

```text
Decision ID:
Date:
Selected option:
Modifications:
Evidence artifact:
Researcher approval:
Consequences for V1:
Required implementation:
```
