# D-010 matched-N joint H2 measurement memo

**Status:** EVIDENCE DRAFT — no primary label, adjudicator, IRR amendment,
model, N, or task bank is approved
**Created:** 2026-08-01
**Decisions informed:** D-002, D-005, D-006, D-010, and D-013
**Findings informed:** R-009, R-017, R-018, and R-022
**Code:** `analysis/d010_joint_h2_measurement.py`
**Tests:** `tests/test_d010_joint_h2_measurement.py`

## 1. Bottom line

The corrected matched-N simulation jointly represents the candidate trial
roster, programmatic outcome, A-F coding, the registered human anchor, the
registered kappa gate, and the pooled H2 reference. It supports five
conclusions.

1. **The simulated 50-case minimum-size anchor is sparse in the cases that
   identify H2 measurement error.** It contains about 4.8-5.0 failed trials
   and 0.71-1.11 true failed-trial D/E cases on average. The probability of
   observing no failed D/E is
   46-50% in null/boundary scenarios and 33-36% in strong-effect scenarios.
   Successful D/E is recorded separately and is not counted as evidence about
   H2, which conditions on programmatic failure.
2. **The omnibus kappa gate can pass severe shared H2-class bias.** When both
   AI coders have 97% independent base accuracy and an 85% shared probability
   of mapping true D/E to C, the gate passes 97.8-98.8% of simulations while
   failed-trial D/E sensitivity is about 15%. A sensitivity with no successful
   D/E passes 99.3-99.6%, so the counterexample does not depend on the chosen
   successful-D/E prevalence.
3. **The primary label is inferentially load-bearing.** With favorable
   independent error and a latent 3x H2 ratio at base N=24, Coder 1 yields a
   mean observed ratio of 2.45 and joint support in 20.2% of simulations.
   Consensus plus a 98%-accurate independent adjudicator yields 3.05 and
   63.1%. H2-only intersection and union rules yield 59.3% and 3.4% support.
4. **Disagreement adjudication helps independent errors but not shared
   agreement.** In the favorable scenario it lowers failed non-D/E false
   positives from about 4.0% to 0.26%. Under shared D/E-to-C bias, agreed wrong
   labels never reach the adjudicator and sensitivity remains about 15%.
5. **Full A-F adjudication has material operational cost.** Favorable exact
   disagreement is about 12.5%, implying approximately 628, 1,205, and 2,410
   adjudications at base N=6, 12, and 24. The calibrated near-kappa-threshold
   scenario implies approximately 1,105, 2,119, and 4,239.

This is evidence for separately validating and resourcing H2 measurement, or
for making H2 exploratory. It does not select a D-010 rule or establish that
the current kappa gate is sufficient.

## 2. What is joint and structurally exact

Each Monte Carlo replicate contains:

1. all five environments and seven configurations;
2. the candidate 12-family capability roster with three frozen instance IDs,
   deterministic valid-slot assignment, and identical slot-to-instance
   matching across environments;
3. the nine seeded-error task IDs with separate formal and colloquial rows;
4. programmatic success/failure and a compatible latent A-F label;
5. two full-sample AI labels;
6. the registered minimum-size (50-case) human-sample instantiation: four
   unique trials from each of ten
   environment-by-task-class strata, then ten unique trials uniformly from
   the remaining roster;
7. human labels, both point-kappa checks, and case-a/b/c demotion;
8. four prospective `is_DE` constructions; and
9. Windows PowerShell versus Linux-native conditional H2 counts and the
   optimistic pooled log-risk-ratio interval.

The candidate split-N manifests are:

| Base N | Capability N | Seeded-variant N | Full transcripts |
|---:|---:|---:|---:|
| 6 | 3 | 6 | 5,040 |
| 12 | 5 | 12 | 9,660 |
| 24 | 10 | 24 | 19,320 |

Capability-stratum size in each environment is `7 × 12 × N_cap`.
Seeded-error-stratum size is `7 × 18 × N_seed`, representing nine tasks by two
phrasings. The instance schedule is the exact D-013 candidate schedule, not an
accepted or frozen study design; D-013 remains open.

Windows PowerShell and Linux-native probabilities use the prospective
heterogeneous H2 generator. The other environments receive the arithmetic
midpoint of the two focal probabilities only to generate full-sample kappa
prevalence. They do not enter the H2 contrast.

## 3. Corrected A-F data-generating process

The outcome constraints follow the rubric rather than treating success as
equivalent to A/B:

- successful trials may be A-E; only F is excluded;
- failed trials may be C-F; A/B are excluded;
- failed D/E is the latent positive class for H2; and
- successful D/E affects full-sample A-F reliability and H4-style coding, but
  is excluded from H2's failure-conditional numerator.

The default synthetic success-label probabilities are A 82%, B 12%, C 4%, D
1.5%, and E 0.5%. These are sensitivity inputs, not observed prevalences. A
separate shared-bias scenario sets successful D/E to zero while retaining
successful C, specifically to test whether the gate counterexample depends on
the default mixture.

Independent rater mistakes remain inside the outcome-compatible label set.
This is favorable because the coder input explicitly supplies programmatic
outcome. Cross-outcome miscoding, malformed output, refusal, and missing-label
branches remain required stress cases.

The six scenarios are:

| Scenario | Latent H2 RR | AI base accuracy | Special mechanism |
|---|---:|---:|---|
| high-quality null | 1x | 94% / 93% | independent errors |
| high-quality boundary | 2x | 94% / 93% | independent errors |
| high-quality strong | 3x | 94% / 93% | independent errors |
| near AI-kappa threshold, strong | 3x | 88.15% / 88.15% | calibrated near kappa 0.60 |
| shared D/E-to-C, strong | 3x | 97% / 97% | 85% shared D/E-to-C mapping |
| shared D/E-to-C, no successful D/E | 3x | 97% / 97% | same mapping; success D/E set to zero |

Human and hypothetical adjudicator accuracy are 98% throughout.

## 4. Candidate primary-label rules

| Rule | Construction | Eligible full A-F primary label? |
|---|---|---|
| Coder 1 | use Coder 1 on every trial | yes; unresolved V1 candidate |
| consensus then adjudicator | use exact AI agreement; otherwise independent adjudicator | yes; requires a pinned scalable adjudicator and exception policy |
| both AI D/E | positive only when both AI labels are D/E | no; H2-only sensitivity |
| either AI D/E | positive when either AI label is D/E | no; H2-only sensitivity |

The consensus rule adjudicates every exact A-F disagreement, including D
versus E. Binary-only adjudication would be cheaper but would not produce the
unique A-F label needed for H4 and descriptive code counts.

## 5. Human-anchor operating characteristics

All results below use 2,000 replicates and base seed `20260801`. Maximum Monte
Carlo standard error for a reported probability is about 1.12 percentage
points.

| Scenario | Mean failed | Mean failed D/E | P(no failed D/E) | Mean successful D/E |
|---|---:|---:|---:|---:|
| high-quality null | 4.87-5.01 | 0.71-0.79 | 45.7-50.0% | 0.88-0.92 |
| high-quality boundary | 4.81-4.86 | 0.75-0.77 | 46.2-47.2% | 0.85-0.95 |
| high-quality strong | 4.87-4.92 | 1.04-1.11 | 33.8-35.5% | 0.88-0.89 |
| near kappa threshold | 4.87-4.95 | 1.07 | 33.4-34.4% | 0.89 |
| shared D/E-to-C | 4.89-4.95 | 1.06-1.10 | 32.8-34.0% | 0.89-0.92 |
| shared bias, no successful D/E | 4.89-4.96 | 1.04-1.10 | 32.8-35.3% | 0 |

Under the default success mixture, counting all D/E would produce means of
1.60-2.02 and substantially smaller zero counts. Those values are useful for
overall rubric coverage but would overstate validation of H2. The H2-relevant
quantity is failed D/E.

High-quality independent-error scenarios have mean AI-AI kappa about 0.752,
mean minimum human-AI kappa about 0.778-0.781, and gate-pass probability about
97.2-98.2%. The near-threshold scenario has mean AI-AI kappa 0.599-0.601 and
passes 40.5%, 44.8%, and 44.8% at base N=6, 12, and 24. Increasing the full
sample does not make a true value pinned at the threshold decisively pass; the
fixed minimum-size 50-case human component also remains uncertain.

## 6. High-quality 3x results by label rule

### 6.1 Effect-scale behavior

| Rule | Failed D/E sensitivity | Failed non-D/E FPR | Mean observed RR at N=6 / 12 / 24 |
|---|---:|---:|---:|
| Coder 1 | 96.0% | 4.0% | 2.63 / 2.48 / 2.45 |
| consensus + adjudicator | 99.7% | 0.26% | 3.38 / 3.09 / 3.05 |
| both AI D/E | 91.5% | 0.18% | 3.43 / 3.11 / 3.07 |
| either AI D/E | 99.8% | 8.4-8.5% | 2.17 / 2.09 / 2.08 |

High-specificity small-N ratios are right-skewed because Linux D/E counts are
sparse. Their mean exceeding three is not evidence that a coding rule
amplifies the latent effect.

### 6.2 Joint support probability

`Joint support` requires the registered kappa gate to pass and the optimistic
pooled lower 95% confidence bound to exceed 2.0.

| Rule | Base N=6 | Base N=12 | Base N=24 |
|---|---:|---:|---:|
| Coder 1 | 5.35% | 9.90% | 20.20% |
| consensus + adjudicator | 16.20% | 31.55% | 63.15% |
| both AI D/E | 13.40% | 28.55% | 59.30% |
| either AI D/E | 1.35% | 2.10% | 3.40% |

At the exact 2x composite-null boundary, joint false-support probabilities
range from 0% to 1.75% across these rules and Ns. Under the 1x null, one of
2,000 base-N=6 Coder-1 runs supports the effect and all other cells are zero.
These are Monte Carlo diagnostics for the pooled reference, not validation of
the final D-005 model's type-I error.

All seven configurations meet the descriptive five-failures-per-focal-context
minimum in 79.8% of strong-effect base-N=6 simulations and essentially 100%
at N=12 and N=24. This diagnostic does not gate the registered pooled H2 test.

## 7. Shared-bias counterexample and sensitivity

At base N=24:

| Success D/E mixture | AI kappa | Human-AI minimum kappa | Gate pass | Consensus D/E sensitivity | Consensus joint support |
|---|---:|---:|---:|---:|---:|
| default 2% successful D/E | 0.878 | 0.791 | 98.75% | 15.04% | 5.40% |
| no successful D/E | 0.874 | 0.817 | 99.30% | 14.99% | 5.30% |

The default scenario gives the human anchor more D/E labels and therefore
slightly lowers human-AI agreement when both AI coders share the wrong C
label. Removing successful D/E makes the omnibus gate look better, not worse.
The central result is invariant: high overall agreement and disagreement-only
adjudication do not protect failed-trial D/E sensitivity.

Consensus effect ratios are sparse and right-skewed in this scenario because
very few positive labels remain. A large conditional point estimate among
estimable runs does not rescue low sensitivity, imperfect estimability, or low
support probability.

## 8. Decision implications

### 8.1 D-010 primary label

No tested rule is ready to accept:

- Coder 1 produces a full label but ordinary false positives attenuate H2.
- Consensus adjudication works best under independent error but requires
  hundreds to thousands of additional full labels plus deterministic
  refusal/missing/malformed branches.
- Disagreement-only adjudication cannot detect shared wrong agreement without
  probability-sampled review of some agreed labels.
- AI intersection and union do not produce the full A-F primary outcome and
  exchange sensitivity for false positives in opposite directions.

### 8.2 Human validation

Retain the registered probability sample for overall A-F agreement, but do not
assume its 50-case minimum can validate H2's rare failed-D/E class unaided. A
pre-data amendment
should compare at least:

1. a larger probability sample stratified by known programmatic outcome,
   environment, and task class;
2. a second audit enriched for AI-labelled D/E and disagreements, plus a
   known-probability sample of agreed non-D/E cases;
3. inclusion-probability-aware estimates of class sensitivity, specificity,
   predictive values, and effect-scale bias; and
4. a third full-sample rater or explicit measurement-error model if either is
   proposed as load-bearing.

Sampling on programmatic outcome is possible before rubric coding, but it
changes the registered sampler and therefore requires an explicit pre-data V2
decision. Hand-picking difficult examples without known inclusion
probabilities would not estimate bias.

### 8.3 H2 and H4 status

Unless a feasible measurement design achieves adequate joint operating
characteristics, exploratory H2 is more defensible than treating no support as
evidence against a spiral asymmetry. This module carries phrasing identity and
full A-F labels but does not simulate or validate the H4 phrasing estimator;
H4's primary-label dependence remains open.

## 9. Limitations and required next evidence

**Subsequent evidence:** `docs/D010_ENRICHED_AUDIT_MEMO.md` implements the
candidate probability-sampled focal-failure audits requested below. It finds
that known-probability sampling can correct point estimates, but small
AI-state-enriched audits can miss shared wrong agreement and badly understate
uncertainty. Even 400 audit labels remain far below latent-oracle support
under shared D/E-to-C bias. No audit or uncertainty method is selected; the
final D-005 mixed-model coupling remains open.

- Every A-F prevalence and rater-quality parameter is synthetic.
- The success-label mixture is not an empirical model; the no-success-D/E
  sensitivity addresses only one dependence on that mixture.
- Outcome-constrained errors are favorable and omit cross-outcome errors,
  refusal, malformed output, missing labels, and evidence-contract failures.
- The 98% adjudicator has no pinned backend, cost, independence, or
  reproducibility contract.
- Non-focal environments use a neutral probability midpoint solely for kappa
  prevalence.
- Outcome and rater errors are independent conditional on task/configuration
  probabilities; paired-slot, instance, lineage, and differential-context
  correlations are absent.
- The registered own-lineage leniency analysis is absent.
- The interval is a pooled log-Wald reference, not the final mixed or
  finite-roster D-005 model.
- No class-specific performance threshold or acceptable estimand-bias bound
  has been selected.

The audit follow-up above addresses candidate allocations but does not select
one. Remaining evidence should add differential context/lineage error,
refusal/malformed/missing branches, conservative audit uncertainty, and the
chosen H2 analysis model. A blinded shakedown with frozen golden cases is
required before synthetic nuisance inputs can be replaced with measured ones.

## 10. Reproduction and verification

```powershell
python -m pytest tests/test_d010_joint_h2_measurement.py -q
python -m analysis.d010_joint_h2_measurement --replicates 2000 --seed 20260801
```

The focused tests cover exact N=6/12/24 costs; family, instance, task,
phrasing, configuration, valid-slot, and cross-environment matching; exact
anchor allocation; outcome-compatible A-F errors; successful C/D/E;
shared-bias-map outcome constraints; deterministic primary-label resolution;
a hand-calculated pooled-H2 count/variance/threshold oracle;
reproducibility; mutually exclusive kappa cases; null-boundary classification;
attenuation; and fail-closed invalid inputs.

D-002, D-005, D-006, D-010, and D-013 remain OPEN. R-009, R-017, R-018, and
R-022 remain OPEN. No benchmark trial ran and no frozen V1 methodology, task,
rubric prompt, scheduler, or collection rule changed.
