# D-005 finite-roster and H2 measurement simulation memo

**Status:** EVIDENCE DRAFT — no estimator, model, label rule, N, or task bank
is approved
**Created:** 2026-08-01
**Decisions informed:** D-001, D-002, D-003, D-005, D-010, and D-013
**Findings informed:** R-001 through R-004, R-017, R-018, and R-022
**Code:** `analysis/d005_finite_roster_irr.py`
**Tests:** `tests/test_d005_finite_roster_irr.py`

## 1. Bottom line

This audit changes the working diagnosis in four ways.

1. The budget-matched 12-family split-N design does not support the ordinary
   within-instance variance estimator at base N=6 or N=12. Its exact candidate
   assignment gives at least one instance only one observation in each
   family/configuration cell, so that estimator is undefined. A
   Jeffreys-stabilized analytic candidate remains computable but is strongly
   conservative and often inconclusive. It is not ready to approve as the
   D-005 confirmatory interval.
2. A valid H1 null can be informative in principle, but not reliably at every
   candidate N/procedure. Under a diffuse 10% null, the stabilized split-N
   candidate declares the effect bounded below five points in only 16%, 35%,
   and 84% of simulations at base N=6, 12, and 24. The rest are valid but
   inconclusive. Under the near-zero stress test, the same rates are 0%, 0.6%,
   and 100%. A null estimate from the small split design therefore cannot
   automatically answer the intended prioritization question.
3. The registered omnibus six-category κ gate does not bound H2's
   measurement bias. In a rare-D/E scenario, it passes both registered
   thresholds in 100% of 5,000 simulations. The mean omnibus κ values are
   0.835 AI-AI and 0.861 for the weaker human-AI pairing, while the
   prevalence-sensitive D/E-specific values are 0.392 and 0.368. The latter
   does not prove poor classification: Coder 1 still has about 95.2%
   sensitivity and 2.4% false positives. But that small false-positive rate
   attenuates a latent 2x D/E ratio to about 1.79. Omnibus κ therefore cannot
   by itself establish that H2's effect-scale bias is acceptably small.
4. H2 remains feasibility-limited after adding even favorable rater error.
   With 94%/93% per-coder six-class accuracy, a latent 2x D/E ratio is
   attenuated to about 1.79. A latent 3x ratio becomes about 2.59, yet the
   optimistic pooled reference supports a lower confidence bound above 2 in
   only 8.9% of base-N=6 split designs and 34.5% at base N=24. A no-support H2
   result would therefore not distinguish absence of asymmetry from ordinary
   sampling imprecision and measurement attenuation under these scenarios.

The evidence supports neither “the benchmark cannot work” nor “the analysis
is ready.” It rejects specific easy implementations and identifies the
measurement/design changes needed before a null could carry the intended
decision meaning.

## 2. Scope and non-decisions

All inputs are synthetic, outcome-blind, and fixed before any benchmark data.
No function reads trial outcomes. The module does not modify the frozen V1
tasks, methodology, scheduler, rubric prompt, or collection plan.

The intended R implementations for D-005 Family A (`glmmTMB` or `lme4`) are
not installed in the current environment. Substituting a different Python
model and calling it the same crossed frequentist binomial GLMM would be
misleading. This audit therefore evaluates transparent finite-roster Family B
candidates and leaves the required Family A/B comparison OPEN.

The H2 overlay assumes Coder 1 is the primary label only to expose the
consequences of a concrete candidate. R-017/D-010 remain OPEN; the simulation
does not silently select Coder 1 for the study.

## 3. Exact finite-roster design represented

The H1 data-generating roster is the D-013 candidate:

```text
6 content domains
x 2 task families per domain
x 3 frozen instances per family
x 7 configurations
x 2 focal contexts
```

Domains, families within domains, instances within families, and
configurations are equally weighted. The exact deterministic instance
schedule from `analysis/d013_task_bank_design.py` allocates each
family/configuration repetition count as follows:

| Base N | Broad common-N instance counts | Broad split-N | Split instance counts |
|---:|---:|---:|---:|
| 6 | 2/2/2 | 3 | 1/1/1 |
| 12 | 4/4/4 | 5 | 2/2/1 |
| 24 | 8/8/8 | 10 | 4/3/3 |

The simulation generates fixed heterogeneous Bernoulli probabilities at the
domain, family, instance, configuration, and context-interaction levels. It
then estimates the equally weighted finite-roster risk difference and the
companion marginal risk ratio.

Three risk-difference intervals are compared:

- `oracle_normal_reference`: uses the true generating probabilities for the
  standard error. It is a validation reference and cannot be fit to real data.
- `jeffreys_plugin_normal_candidate`: uses Beta(1/2, 1/2) cell pseudo-counts
  only for the variance estimate while retaining the raw standardized risk
  difference as the point estimate.
- `unbiased_cell_normal_candidate`: uses the ordinary unbiased within-cell
  Bernoulli variance. It fails closed if any instance count is below two.

The latter two are analytic Family B probes. They are not the parametric or
stratified bootstrap proposed in the D-005 decision memo, and neither is
approved as a fallback.

## 4. Finite-roster results

Each entry below uses 5,000 replicates and seed `20260801`; the maximum Monte
Carlo standard error for a probability is approximately 0.71 percentage
points.

### 4.1 Budget-matched broad split-N design

The table reports stabilized-candidate coverage, the probability of an
informative threshold decision, and the ordinary estimator's status.

| Scenario | Base N | Stabilized coverage | Relevant/bounded decision | Ordinary estimator |
|---|---:|---:|---:|---|
| diffuse 10% null, RD=0 | 6 | 99.7% | 16.2% bounded-small | unestimable |
| diffuse 10% null, RD=0 | 12 | 99.4% | 35.0% bounded-small | unestimable |
| diffuse 10% null, RD=0 | 24 | 98.7% | 83.5% bounded-small | 95.1% coverage |
| diffuse threshold, RD=5 pp | 6 | 99.3% | 99.3% inconclusive | unestimable |
| diffuse threshold, RD=5 pp | 24 | 98.1% | 98.1% inconclusive | 94.8% coverage |
| diffuse strong, RD=10 pp | 6 | 98.9% | 19.4% relevant | unestimable |
| diffuse strong, RD=10 pp | 12 | 98.7% | 35.0% relevant | unestimable |
| diffuse strong, RD=10 pp | 24 | 97.4% | 77.9% relevant | 95.1% coverage; 85.4% relevant |
| near-zero null, 0.1% each | 6 | 100.0% | 0.0% bounded-small | unestimable |
| near-zero null, 0.1% each | 12 | 100.0% | 0.6% bounded-small | unestimable |
| near-zero null, 0.1% each | 24 | 100.0% | 100.0% bounded-small | 79.6% coverage |

At the diffuse threshold itself, a calibrated 95% interval should usually be
inconclusive. The oracle reference does so about 95% of the time; the
stabilized candidate does so 98-99% of the time, confirming its conservatism.

Every simulated dataset has at least one boundary instance cell at these
small cell counts. That does not mean every global model is completely
separated, but it means a saturated fixed-instance implementation must have a
pre-specified boundary/separation strategy. In the near-zero split design,
at least one focal context has zero total failures in about 94.8%, 87.9%, and
68.0% of simulations at base N=6, 12, and 24.

The near-one mirror likewise records whether either context has all events,
rather than treating a zero-event check as sufficient coverage of complete
separation. At base-N=6 split, this is about 95% in the dedicated stress run.

### 4.2 Broad common-N comparison

Common N makes the ordinary estimator computable and materially increases
precision:

| Scenario/method | Base N=6 | Base N=12 | Base N=24 |
|---|---:|---:|---:|
| diffuse null, ordinary bounded-small | 78.2% | 97.1% | 100.0% |
| diffuse null, stabilized bounded-small | 52.4% | 92.3% | 99.9% |
| diffuse strong, ordinary relevant | 66.1% | 91.7% | 99.9% |
| diffuse strong, stabilized relevant | 50.3% | 87.3% | 99.7% |
| near-zero null, ordinary coverage | 64.7% | 84.7% | 94.1% |
| near-zero null, stabilized coverage | 100.0% | 100.0% | 100.0% |

The ordinary method's apparently excellent decisions near zero are not
trustworthy when its coverage is 65-85%. The stabilized method avoids that
failure by becoming conservative. This is exactly why the final estimator
must be selected using coverage and decision error, not whichever produces
the narrowest interval.

### 4.3 What this establishes for D-005

- Reject the ordinary within-instance variance estimator as a universal
  primary/fallback: it is undefined at the smaller split Ns and undercovers
  badly in sparse scenarios even when it becomes computable.
- Retain the stabilized analytic interval only as a comparator. Its coverage
  is safe in these scenarios, but its conservatism can make an affordable
  valid null uninformative.
- Do not approve base N=6 for the broad split design as capable of resolving a
  five-point H1 decision. The exact selected procedure and scenario envelope
  must demonstrate that capability.
- The 30.4% common-N cost increase buys scientifically material precision; it
  is not merely redundant replication.
- D-005 still requires a bootstrap or other finite-roster interval with
  validated sparse-cell behavior, a marginal risk-ratio interval, the Family
  A comparison, convergence/fallback branches, and an independent
  implementation oracle.

## 5. IRR data-generating process

The registered A-F rubric is simulated as six nominal categories. Both AI
coders label a 5,040-trial full sample, matching the base-N=6 broad split
matrix. The human anchor contains 50 labels, five from each of ten equal
environment-by-task-class strata. This exactly represents the registered
minimum under equal stratum sizes; real unequal manifest counts and the
proportional remainder remain to be simulated.

Independent rater errors are symmetric across the five wrong labels. The
shared-bias scenario additionally forces both AI coders to map true D/E cases
to C with probability 0.85. The registered rule is applied exactly to point
estimates:

```text
confirmatory only if kappa_AI >= 0.60
and min(kappa_human_vs_AI1, kappa_human_vs_AI2) >= 0.60
```

For diagnosis, the same κ calculations are repeated after collapsing the
labels to the binary H2 outcome D/E versus not-D/E. The binary result is not a
registered or proposed gate; it exposes how class prevalence changes the
agreement statistic for the outcome H2 actually uses.

## 6. IRR results

| Scenario | Mean omnibus κ AI / human-min | Confirmatory | Main diagnosis |
|---|---:|---:|---|
| high-quality balanced | 0.849 / 0.873 | 100.0% | gate behaves as intended |
| near AI threshold | 0.594 / 0.710 | 21.3% | 78.1% demoted for AI-AI disagreement |
| shared D/E→C bias | 0.945 / 0.549 | 23.8% | 76.2% case-b demotion; n=50 human threshold is variable |
| rare D/E, high overall accuracy | 0.835 / 0.861 | 100.0% | passes despite prevalence-sensitive binary κ and material ratio attenuation |

In the rare-D/E scenario, mean binary D/E κ is 0.392 AI-AI and 0.368 for the
weaker human-AI pair. A hypothetical binary κ gate passes 0% while the
registered omnibus gate passes 100%. This is largely a prevalence-paradox
example, not evidence that 0.60 should become a binary-κ gate. The useful
counterexample is that neither high omnibus κ nor high raw accuracy limits the
effect-scale bias from false positives when D/E is uncommon. Class-specific
sensitivity, specificity, predictive values, prevalence, and propagated
estimand bias must be reported and used in the D-010 decision.

The shared-bias case also validates why the human anchor is necessary. AI-AI
κ remains 0.945 even while Coder 1's D/E sensitivity falls to about 0.146.
However, 23.8% of runs still clear both registered point thresholds because
the simulated minimum-size human anchor contains only 50 cases. This
probability is conditional on
the synthetic class mix and error mechanism; it is not a forecast of real
coder quality.

## 7. H2 measurement-error overlay

For an explicit sensitivity analysis, Coder 1's simulated D/E sensitivity and
false-positive rate transform each latent conditional D/E probability as:

```text
q_observed = sensitivity * q_true
           + false_positive_rate * (1 - q_true)
```

The transformed probabilities are passed to the existing optimistic pooled
H2 log-Wald reference for the broad split-N bank. This overlay still ignores
clustering, model convergence, differential error by context, and uncertainty
in the confusion rates. The reported combined probability multiplies the IRR
pass rate by the H2 support rate and therefore assumes independent IRR and H2
sampling. It also holds the IRR full-sample reference at 5,040 when comparing
larger-N H2 designs; a matched-N joint simulation could change κ threshold
crossing near 0.60. It is a stress-test reference, not D-005.

Under the high-quality balanced rater scenario:

| Latent D/E RR | Observed candidate RR | Support at base N=6 | Support at base N=24 |
|---:|---:|---:|---:|
| 1.0 | 1.00 | 0.0% | 0.0% |
| 2.0 | 1.79 | 0.5% | 0.6% |
| 3.0 | 2.59 | 8.9% | 34.5% |

The exact-threshold 2x row is not a conventional power target: requiring the
lower 95% bound to exceed 2 should rarely succeed when the latent truth is
exactly 2, and nondifferential false positives attenuate the observed ratio
below 2. The 3x row is more consequential. Even at four times the base N, the
optimistic reference misses support in about two thirds of simulations.

Under shared D/E→C bias, the latent 3x ratio becomes about 2.06; combined IRR
and pooled-reference support is approximately 0% at base N=6 and 0.4% at base
N=24. Under the near-threshold AI scenario, the corresponding values are
about 0.3% and 0.5%.

## 8. Null interpretability

The proposed use is:

> If the average Windows-context penalty is credibly greater than five
> points, prioritize a targeted mechanism/mitigation study; if credibly below
> five points, do not prioritize a broad context-gap investigation based on
> this benchmark.

That use requires different conclusions for H1 and H2.

### H1

A null H1 result is interpretable only if the selected, validated interval is
wholly below five points. A point estimate near zero is not enough. At small
split N, most diffuse-null simulations remain inconclusive under the only
currently computable stabilized candidate. That is weak precision, not an
instrument-validity failure—but it also cannot support “do not prioritize.”

The null is additionally bounded to the accepted task population. A precise
six-domain average near zero can coexist with large opposing domain effects;
the D-013 domain and leave-one-domain-out diagnostics remain necessary.

### H2

Under the simulated resource envelope, failure to support H2 is not evidence
that spiral asymmetry is absent. It can arise when:

- a real 3x latent effect is attenuated by plausible nondifferential label
  error;
- overall κ passes while effect-scale attenuation remains material;
- the simulated 50-case minimum-size human anchor randomly misses or weakly
  samples the load-bearing
  class;
- or the failed-trial denominator yields a wide conditional-ratio interval.

Unless later simulations overturn this result, H2 should either receive a
separately powered and outcome-valid measurement design or be made explicitly
exploratory. Calling a no-support result a substantive null under the present
design would blame the phenomenon for a test that has little chance to detect
it.

## 9. Required next decisions and evidence

**Subsequent evidence:** `docs/D010_JOINT_H2_MEASUREMENT_MEMO.md` implements
the matched-N joint simulation requested below, including the exact registered
four-per-stratum-plus-proportional anchor and concrete primary-label rules. It
confirms the effect-attenuation concern and shows that the 50-case minimum-size
anchor is
too sparse in failed-trial D/E to catch severe shared H2-class bias reliably.
At that stage, the final mixed model, enriched audit, label-exception
branches, and D-010 choice remained open.

`docs/D010_ENRICHED_AUDIT_MEMO.md` subsequently implements the proposed
known-probability focal-failure audits. The audit-assisted point estimator is
design-unbiased in an exhaustive noncensus oracle, but small AI-state-enriched
audits can miss shared wrong agreement and severely understate residual
variance. Even B=400 reaches only 24.3-39.4% shared-bias joint support versus
a 64.5% latent oracle. This is still a pooled two-phase reference: the
conservative rare-residual interval and final D-005 mixed-model coupling
remain OPEN.

`docs/D010_CONSERVATIVE_AUDIT_INTERVAL_MEMO.md` then supplies simultaneous
exact finite-population residual bounds. They repair zero-cell undercoverage
but show that robust audit measurement may require reviewing 600-800 of about
864 focal failures. A census still clears an audit-only RR>2 diagnostic in
about half of exact-boundary scenarios because audit certainty is not
trial-sampling certainty. The next D-005 comparison must therefore keep the
measurement confidence set and crossed-model uncertainty distinct.

1. **D-010/R-017:** specify the primary per-trial label and every disagreement,
   missing-output, refusal, adjudication, and sensitivity-analysis branch.
2. **H2-specific validity evidence:** do not rely on omnibus κ alone or replace
   it mechanically with another prevalence-sensitive κ cutoff. Pre-specify a
   D/E confusion matrix, class-specific performance quantities, and an
   acceptable effect-scale bias/sensitivity criterion. Consider a second,
   probability-sampled human audit enriched for AI-labelled D/E and
   disagreements, with inclusion probabilities retained for unbiased
   estimation; do not simply hand-pick hard cases. The subsequent D-010 audit
   memo tests four such allocations but does not accept one.
3. **Human-anchor sizing:** simulate real unequal strata, D/E prevalence,
   lineage effects, and the selected class-specific criterion over candidate
   anchor sizes. Fifty is a floor, not evidence of adequate precision.
4. **D-005 Family B:** implement and test a principled finite-roster
   bootstrap/randomization-aware interval that preserves equal domain,
   family, instance, and configuration weights and handles singleton and
   boundary cells without hidden pooling.
5. **D-005 Family A:** run the intended crossed binomial GLMM in a pinned R
   analysis environment and compare it against Family B on exactly the same
   scenarios. Few-level variance behavior and convergence must be reported,
   not assumed.
6. **Joint H2 simulation:** replace the mean-error/product overlay with one
   simulation that generates failures, six-category labels, the exact
   manifest-level human sample, primary-label resolution, κ/demotion, and the
   final conditional model together.
7. **Remaining D-005 envelope:** add invalid-attempt caps, differential rater
   error by environment/lineage, calendar drift, backend changes, and the
   accepted D-009 schedule.

## 10. Subsequent joint inference/resource evidence

`docs/D004_D005_RESOURCE_FEASIBILITY_MEMO.md` implements the requested joint
screen on the same D-010 trials. Three results change the D-005 frontier:

- a cellwise Jeffreys delta repair is rejected for 66-70% coverage and
  11-19% threshold clearing at RR=2;
- a pooled two-phase fixed-roster candidate, when required to pass both the
  exact finite-human audit bound and IRR gate, achieves 95.0-96.0% coverage
  and only 0.1-2.2% coupled threshold clearing across the RR=2 B=400-census
  grid; and
- a task-by-configuration t(6) sensitivity is calibrated but much less
  decisive because seven purposively selected configurations do not support
  a precise wider configuration-population claim through repeated trials.

At N=24, B=700 plus the 50-case anchor is close to the pooled candidate's
full-human ceiling, but supports a synthetic 3x effect only about 64-67% with
perfect labels and about 49% with a 98%-accurate reference. B=600 and B=700
are retained for empirical costing, not selected. The intended Family A GLMM,
time/lineage dependence, and final finite-versus-superpopulation decision
remain open.

## 11. Reproduction and current evidence state

Core commands:

```powershell
python -m pytest tests/test_d005_finite_roster_irr.py -q
python -m analysis.d005_finite_roster_irr --sections irr --replicates 5000 --seed 20260801
python -m analysis.d005_finite_roster_irr --sections finite --replicates 5000 --seed 20260801
```

The focused D-005/IRR suite passes 13 tests. The implementation tests exact
scheduler counts, deterministic replication, exclusive result states,
singleton fail-closed behavior, oracle coverage, zero- and complete-event
diagnostics, an independent heterogeneous unequal-count variance check,
analytic κ reference cases, fail-closed invalid labels, shared AI-bias
demotion, the rare-D/E omnibus-κ counterexample, and explicit overlay
assumptions.

An additional D-013 regression confirms that a pooled sample with all failed
trials labelled D/E remains ratio-estimable. Directly affected evidence is 27
passed; full local evidence is 373 passed with 3 infrastructure-gated skips.
Python compilation, end-to-end CLI JSON serialization, and `git diff --check`
also pass.

D-001, D-002, D-003, D-005, D-010, and D-013 remain OPEN. R-017, R-018, and
R-022 remain OPEN. No benchmark trial was run and no frozen V1 methodology or
task file was changed.

## 12. 2026-08-15 executable fixed-roster interval candidate

`analysis/v2_finite_roster.py` now implements the accepted hierarchical point
weights as an executable interval candidate. It uses the MOVER construction
for a linear combination of independent binomial proportions described by
Zou, Huang, and Zhang (2009, DOI
[`10.1016/j.csda.2008.09.033`](https://doi.org/10.1016/j.csda.2008.09.033)).
Every context/configuration/family/instance leaf remains explicit; no sparse
cell is pooled into another family or domain.

Prospective recovery rejected the narrower Wilson-component version. In the
N=24 broad split-N opposing-domain stress, its 95% interval covered only
92.1% of 5,000 simulations. The retained leading candidate instead uses
equal-tail Clopper-Pearson component limits inside MOVER. Across the current
N=24 split-N grid it covered 97.0-100% of simulations; the largest wrong
five-point threshold declaration rate was 0.5%. Under the diffuse null it
made a bounded-small decision 71.2% of the time, and under the diffuse
10-point alternative it made a decision-relevant declaration 64.1% of the
time. These are calibrated-candidate results, not proof over an unrestricted
data-generating class.

The executable branch requires at least three observations in every fixed
leaf. If that requirement fails, it uses a simultaneous
Clopper-Pearson/Bonferroni linear envelope. The fallback is intentionally
capable of returning a very wide, inconclusive interval; it cannot silently
borrow information or manufacture precision from singleton cells. Companion
marginal rates and a boundary-safe RR envelope are emitted with the accepted
three-way D-001 classification.

Twenty-six focused tests pass, including an independent MOVER calculation,
permutation invariance, exact singleton/boundary fallback, hierarchical
weight recovery, and a deterministic regression that preserves both the
Wilson falsification and the Clopper-Pearson-MOVER repair.

D-005 is not yet accepted. Before freeze, the candidate still requires the
full differential-error/attrition/epoch scenario envelope, Family A and
multiway sensitivity comparison on the same draws, a second implementation
review, and researcher acceptance of the exact interval and fallback.
