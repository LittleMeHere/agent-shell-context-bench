# D-010 conservative finite-population audit-interval memo

**Status:** EVIDENCE DRAFT — no audit, interval, label rule, model, N, or task
bank is approved
**Created:** 2026-08-03
**Decisions informed:** D-002, D-005, D-006, D-010, and D-013
**Findings informed:** R-009, R-017, R-018, and R-022
**Code:** `analysis/d010_enriched_audit.py`
**Tests:** `tests/test_d010_enriched_audit.py`

## 1. Bottom line

The prior audit study found that plug-in residual variances could collapse to
zero and manufacture apparent H2 support. This follow-up replaces that
uncertainty calculation with simultaneous exact finite-population bounds. It
produces five clear results.

1. **The zero-cell failure is repaired.** An observed noncensus cell with no
   residual error receives a positive upper bound; only a census can establish
   zero unseen residuals. Across the 1,000-replicate base-N=24 grid, coverage
   of the realized full human-reference ratio is 99.9-100% in every cell.
2. **The repair removes the apparent advantage of AI-state enrichment.** At
   B=400 with perfect audit labels, audit-only threshold clearing for the
   independent-error 3x effect is 48.5% for context SRS, 21.6% for balanced
   AI states, 0.4% for the positive/disagreement stress design, and 7.7% for
   the shared-agreement-guarded design. Their old plug-in joint-support values
   were 52.4-64.6%.
3. **B=400 is inadequate under shared wrong agreement.** Exact audit-only
   threshold clearing is 12.1%, 9.8%, 8.3%, and 5.7% for those four designs.
   The point estimates remain approximately unbiased; the problem is honest
   uncertainty about unseen human corrections.
4. **A small audit is not the relevant resource scale.** Context SRS needs
   roughly B=600-800 of about 864 focal failures before audit measurement
   usually stops being the bottleneck. With perfect labels, the independent
   and shared 3x mechanisms clear the audit-only bound in 88%/64% of B=600
   runs, 95%/91% at B=700, and 97%/96% at B=800. With 98% A-F category
   accuracy, comparable behavior requires roughly B=700-800.
5. **Audit validity and final inference are now cleanly separated.** At a
   census, the audit interval collapses to the realized human ratio. In a
   scenario whose true ratio is exactly 2, that realized ratio exceeds 2 in
   about 48% of runs. This is not type-I error of the audit interval: it is
   trial-to-trial finite-roster variation that only D-005 can address.

The exact interval is a conservative safety benchmark, not an accepted final
method. It is well calibrated but substantially overcovers. Context SRS is
the only allocation worth carrying forward as the default benchmark; the
current state-enriched designs do not justify their added multiplicity and
thin-cell cost. D-010 remains OPEN, and D-005 must now combine measurement and
task/configuration uncertainty without relabeling either layer.

## 2. Why the plug-in interval failed

The audit-assisted point estimator uses known full-sample Coder-1 labels and
estimates the human-minus-Coder residual inside each probability-sampling
stratum. Its usual design-variance estimate uses the observed residual sample
variance.

When all audited residuals in a stratum are zero, that estimate is zero even
though unaudited residuals may exist. State enrichment made this especially
dangerous:

- residual errors are rare under independent high-quality coding;
- shared D/E-to-C errors concentrate in agreed C/C cases;
- thin state strata can miss the relevant residual entirely; and
- the normal interval then interprets an unobserved error as known absence.

The previous memo therefore found non-monotonic apparent support, severe
finite-reference undercoverage, and frequent zero estimated variance. Those
cells were falsifications of the interval, not evidence of design power.

## 3. Conservative construction

For every audit stratum, the full Coder-1 D/E status is known. Conditional on
the number of sampled Coder-1-negative and Coder-1-positive cases, each
sampled subgroup is a simple random sample without replacement from its known
finite subgroup.

The method separately bounds two unknown totals:

- false negatives: human D/E among Coder-1 non-D/E cases; and
- false positives: human non-D/E among Coder-1 D/E cases.

For a subgroup of size `M`, conditional sample size `m`, and observed error
count `y`, an equal-tailed confidence set for the finite error total `K`
inverts the exact hypergeometric distribution. If `m=0`, its bounds are
`[0, M]`; if `m=M`, both bounds equal `y`.

Let `c` be the number of noncensus residual components across both contexts.
Each component receives confidence

```text
1 - (1 - overall_confidence) / c.
```

A Bonferroni union bound gives at least the requested simultaneous conditional
coverage for every component. Known Coder-1-positive totals plus the bounded
false-negative and false-positive corrections yield lower and upper human D/E
totals in Linux and Windows. The ratio confidence set is

```text
[ lower(Windows) / upper(Linux),
  upper(Windows) / lower(Linux) ].
```

The upper ratio is infinite when the Linux lower count is zero. The lower
ratio can still be used as an audit-only threshold diagnostic. No normal
approximation, pseudo-count, bootstrap resampling of an all-zero cell, or
assumed human error rate enters these bounds.

## 4. What is and is not covered

The confidence set targets the **realized full human-labelled finite roster**
conditional on the probability-sampling design. It addresses only missing
human labels.

It does not cover:

- the latent label when human judgment is imperfect;
- repeated-study variation in which trials fail or receive D/E;
- task, instance, configuration, paired-slot, lineage, or time dependence;
- uncertainty from the registered D-005 model; or
- the adequacy of the task population.

Accordingly, `lower > 2` is recorded as an **audit-only threshold-clear
diagnostic**, not confirmatory support or type-I error. For latent RR<=2 rows,
the output calls it a latent-null diagnostic. Near census that quantity can
approach 50% at the exact boundary because the audit interval correctly
collapses around a randomly realized finite-roster ratio.

## 5. Verification oracles

The implementation adds three load-bearing checks.

1. For every possible finite success total in a small population, it sums the
   exact hypergeometric probability of every possible observed sample and
   verifies miscoverage is no greater than alpha.
2. A noncensus zero-observation case must have a positive upper error bound,
   while a zero-error census must return `[0, 0]`.
3. An exhaustive unequal-stratum audit enumerates every possible sample. The
   existing difference point estimator and residual-variance estimator remain
   design-unbiased, while the new ratio confidence set covers the full human
   ratio at least 95% of the time.

Existing metadata checks still require unique selected indices, exact
population and allocation counts, one context per stratum, and conditional
inclusion probabilities equal to `n_h/N_h`. RNG streams remain invariant to
batching and unrelated grid composition.

## 6. Main B=400 results

All rows below use base N=24, 1,000 replicates, perfect audit labels, and seed
`20460802`. Maximum single-cell Monte Carlo standard error is approximately
1.58 percentage points.

| Mechanism | Audit design | Exact finite coverage | Mean exact RR lower | Audit-only gate + RR>2 | Old plug-in joint support |
|---|---|---:|---:|---:|---:|
| independent 3x | context SRS | 100.0% | 2.035 | 48.5% | 52.4% |
| independent 3x | state balanced | 100.0% | 1.825 | 21.6% | 64.6% |
| independent 3x | positive/disagreement stress | 100.0% | 1.527 | 0.4% | 64.2% |
| independent 3x | shared-agreement guarded | 100.0% | 1.700 | 7.7% | 64.4% |
| shared D/E-to-C 3x | context SRS | 99.9% | 1.589 | 12.1% | 38.3% |
| shared D/E-to-C 3x | state balanced | 100.0% | 1.491 | 9.8% | 24.2% |
| shared D/E-to-C 3x | positive/disagreement stress | 99.9% | 1.475 | 8.3% | 26.4% |
| shared D/E-to-C 3x | shared-agreement guarded | 100.0% | 1.493 | 5.7% | 36.5% |

At B=200, the exact audit-only diagnostic is 2.0% for independent-error SRS,
0.7% for shared-bias SRS, 0.1% for shared-bias guarded, and zero for the other
five mechanism-by-state-design rows. The exact method eliminates the earlier
claim that B=50-200 enrichment is usefully powerful.

For B<=400, the RR=1 null never clears the exact diagnostic. Across both RR=2
boundaries, the maximum is 0.5%. This is only a measurement-layer diagnostic;
Section 8 shows why it must not be reported as scenario-level false support.

## 7. Why state enrichment loses

At B=50, the state designs average about twelve noncensus residual components,
versus four for context SRS. Bonferroni protection and thin conditional
subgroups make their D/E proportion bounds extremely wide. At B=400, some
components become censuses, but uneven allocation remains costly.

The result is not a generic theorem that stratification is harmful. These
specific state definitions and weights are harmful under a requirement to
remain valid when rare residuals are unseen. A redesigned allocation could
use optimal or adaptive sample sizes fixed from blinded pilot nuisance
estimates, but it would need the same zero-cell and simultaneous-coverage
checks before being accepted.

## 8. Context-SRS cost curve toward census

The following 1,000-replicate grid uses seed `20560802`. The mean focal-failure
population is 863-865, so B=800 reviews about 92-93% of focal failures and
B=1000 becomes a census. Add 50 human labels for the separate minimum-size
omnibus-kappa anchor instantiation.

### 8.1 Audit-only gate plus ratio above 2

| B | Approx. total human labels | Independent 3x perfect / 98% | Shared-bias 3x perfect / 98% |
|---:|---:|---:|---:|
| 400 | 450 | 47.3% / 23.3% | 13.6% / 7.8% |
| 500 | 550 | 72.5% / 46.0% | 32.7% / 21.6% |
| 600 | 650 | 88.2% / 73.2% | 64.0% / 49.2% |
| 700 | 750 | 95.3% / 89.2% | 90.5% / 83.1% |
| 800 | 850 | 96.8% / 94.3% | 96.4% / 93.2% |
| census | about 913-915 | 97.4% / 96.1% | 97.9% / 96.5% |

“98%” means outcome-constrained A-F category accuracy. Its expected
human-reference ratio is 2.759 rather than the latent 3.0.

This table does not select B=700 or B=800. It says that a robust audit which
rarely bottlenecks a true 3x finite-human ratio resembles near-census dual
coding, not a small validation sample.

### 8.2 Why census does not finish H2

At census, audit-only threshold clearing is approximately 48% in both perfect
human RR=2 boundary scenarios. The exact audit confidence set has correctly
collapsed to the realized human ratio; it has no trial-sampling uncertainty
left to express.

The full-human optimistic pooled log-Wald reference, which does include a
conditional-binomial term but still omits clustering, supports the 3x effect
in only:

- 67.0% independent / 66.4% shared-bias runs with perfect human labels; and
- 49.0% independent / 51.9% shared-bias runs at 98% category accuracy.

The actual D-005 model may behave differently, but it cannot be inferred from
the audit confidence set. This is the point where implementing the final model
becomes scientifically necessary.

## 9. Decision implications

### 9.1 What this evidence rules out

- Do not use the old plug-in residual interval as load-bearing.
- Do not interpret state-enriched plug-in support as power.
- Do not describe B<=400 as an adequate confirmatory H2 audit under the
  shared-bias stress.
- Do not report the audit-only latent-boundary diagnostic as type-I error.
- Do not claim that census human labels make H2 confirmatory without D-005.

### 9.2 What remains viable

- Retain context SRS as the transparent baseline for D-005 coupling.
- Retain the exact Bonferroni-hypergeometric set as a conservative measurement
  benchmark and zero-cell safeguard.
- Consider a less conservative procedure only if it matches or exceeds 95%
  finite-reference coverage across the same null, boundary, independent-error,
  and shared-error mechanisms.
- Carry B=400, 600, 700, 800, and census into a costed model comparison rather
  than choosing a budget from audit-only results.

### 9.3 Next required evidence

1. Couple the SRS audit measurement layer to the candidate D-005 analyses on
   the same generated trials. Report finite-human and latent targets
   separately.
2. Compare the exact benchmark with any calibrated randomization/bootstrap or
   measurement-error model; retain zero-cell safeguards and fail-closed
   behavior.
3. Add task/configuration, instance, paired-slot, lineage, and time dependence
   before using scenario-level coverage or support to select N or B.
4. Replace synthetic 98% category accuracy with blinded golden-case and pilot
   estimates, retaining an imperfect-reference sensitivity.
5. Cost the resulting 650-850 human-label region in actual time and dual-coder
   availability before D-006 or D-010 closes.

Under this design-based measurement standard, adding model uncertainty cannot
make a non-clearing audit bound more decisive without additional modeling
assumptions. D-005 should therefore start with SRS and the exact confidence set
visible, not bury audit uncertainty inside a fitted model.

## 10. Subsequent D-005/resource evidence

`docs/D004_D005_RESOURCE_FEASIBILITY_MEMO.md` couples this exact audit gate to
two repeated-study candidates on the same generated trials. The pooled
fixed-roster candidate retains 95.0-96.0% coverage and only 0.1-2.2% coupled
threshold clearing across the B=400-census RR=2 boundary grid. At N=24,
B=700 plus the 50-case anchor is close to its full-human strong-effect ceiling,
but coupled support is only about 64-67% with perfect labels and about 49% with
a 98%-accurate human reference.

A task-by-configuration t(6) sensitivity is much less decisive, while a
cellwise Jeffreys delta attempt is rejected for severe undercoverage. These
results confirm the distinction in Section 8: audit sufficiency can be solved
without making claim scope or final inference automatic. B=600 and B=700 are
resource candidates only; no audit or D-005 model is accepted.

## 11. Reproduction

Core commands:

```powershell
python -m pytest tests/test_d010_enriched_audit.py tests/test_d010_joint_h2_measurement.py -q
python -m analysis.d010_enriched_audit --replicates 1000 --seed 20460802 --base-common-ns 24 --budgets 50 100 200 400 --human-modes perfect_reference
python -m analysis.d010_enriched_audit --replicates 1000 --seed 20460802 --base-common-ns 24 --budgets 400 --human-modes noisy_98_reference --scenarios high_quality_strong shared_de_to_c_strong
python -m analysis.d010_enriched_audit --replicates 1000 --seed 20560802 --base-common-ns 24 --budgets 400 500 600 700 800 1000 --human-modes perfect_reference noisy_98_reference --designs focal_failure_context_srs --scenarios high_quality_boundary shared_de_to_c_boundary high_quality_strong shared_de_to_c_strong
```

No benchmark trial ran and no frozen V1 methodology, task, rubric prompt,
scheduler, collection rule, label rule, N, or audit budget changed.

D-002, D-005, D-006, D-010, and D-013 remain OPEN. R-009, R-017, R-018, and
R-022 remain OPEN.
