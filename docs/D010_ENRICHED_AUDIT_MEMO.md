# D-010 probability-sampled H2 audit-allocation memo

**Status:** EVIDENCE DRAFT — no audit design, primary label, interval,
mixed model, N, or task bank is approved
**Created:** 2026-08-01
**Decisions informed:** D-002, D-005, D-006, D-010, and D-013
**Findings informed:** R-009, R-017, R-018, and R-022
**Code:** `analysis/d010_enriched_audit.py`
**Tests:** `tests/test_d010_enriched_audit.py`

## 1. Bottom line

The registered minimum-size (50-case) omnibus-kappa anchor instantiation is
retained, but it is not enough to validate the rare failed-trial D/E class.
This study therefore compares a separate probability sample of
Windows-PowerShell and Linux-native failures. It supports six conclusions.

1. **Known-probability auditing can remove point-estimate bias in the
   simulated labels.** The stratified difference estimator is approximately
   unbiased for the full human-reference D/E proportions under both
   independent coder error and severe shared D/E-to-C error. An exhaustive
   noncensus unequal-stratum oracle independently verifies design-unbiased
   point estimates and residual-variance estimates.
2. **AI-state enrichment is not automatically safer or more efficient.** At
   small budgets it often misses the residuals that identify shared wrong
   agreement. Its plug-in residual variance can then be zero or too small,
   producing narrow intervals and apparently high support.
3. **The resulting non-monotonic support is a falsification, not power.** In
   the shared-bias 3x scenario, some B=50 enriched designs report more support
   than at B=200 while covering the realized full human-reference ratio only
   36-68% of the time. The smaller audit is not better; its uncertainty
   estimate is broken in that region.
4. **A 200-label audit remains far from the latent oracle under shared
   bias.** At base N=24, the four designs yield 9.5-15.2% joint support versus
   65.7% for the latent oracle. Context SRS and the guarded design are
   effectively tied at this Monte Carlo resolution.
5. **Even 400 audit labels do not close that gap.** With 450 conservatively
   counted human labels including the separate anchor, shared-bias joint
   support is 24.3-39.4% versus a 64.5% oracle. The 36.3% SRS and 39.4%
   guarded results do not establish a reliable ranking.
6. **Human judgment quality remains load-bearing.** Under the separate 98%
   outcome-constrained A-F category accuracy, the scenario human-reference
   3x ratio is analytically 2.759 rather than 3.0. At B=400, the full
   noisy-human reference supports the shared-bias alternative in 47.1% of
   simulations, versus 66.1% for the like-for-like full perfect-human
   reference (latent-oracle joint support is 64.5%). More sampling cannot
   remove systematic reference-label error.

No current design is accepted. The positive/disagreement-heavy rule is
rejected as a load-bearing candidate in its present form. Context SRS and a
guarded hybrid remain candidates for the next simulation only after a
conservative rare-residual uncertainty method is specified and coupled to the
actual D-005 model.

## 2. Question and decision boundary

This is a prospective design comparison. It asks whether a feasible additive
human audit could make an H2 no-support result interpretable, instead of
allowing any no-support result to be blamed automatically on weak
measurement.

The output is deliberately a **pooled two-phase reference, not the registered
D-005 mixed model**. It may falsify audit allocations and uncertainty methods;
it cannot approve the final H2 analysis or establish confirmatory power.

The registered anchor and the focal audit have different jobs:

- the registered minimum-size (50-case) full-matrix anchor instantiates the
  existing omnibus A-F kappa gate; and
- the additional audit estimates D/E measurement error among focal failures.

There is no overlap deduplication. A requested B-label audit is conservatively
costed as `50 + B` human labels even if a trial could appear in both samples.

## 3. Candidate probability samples

Every design samples without replacement inside realized strata and records
the conditional first-order inclusion probability `pi_h = n_h / N_h`.
Populated strata receive a deterministic floor of two labels. Remaining
labels are allocated one at a time to the largest
`weight_h / (allocated_h + 1)` priority, with census caps, deterministic
surplus redistribution, and lowest-stratum-ID tie breaking.

The five AI states are context-specific:

1. exact C/C agreement;
2. exact F/F agreement;
3. non-D/E disagreement, C/F;
4. exactly one AI D/E; and
5. both AI D/E, including D/D, E/E, and D/E.

Exact C/C agreement is intentionally separate because the shared-bias stress
maps true D/E to agreed C.

| Design | Strata / weights | Role |
|---|---|---|
| `focal_failure_context_srs` | Windows and Linux only; equal weights | probability-sample baseline |
| `ai_state_balanced` | context x five AI states; all weights 1 | balanced state candidate |
| `positive_disagreement_enriched_stress` | state weights 1, 1, 2, 4, 4 | intentional shared-agreement failure candidate |
| `shared_agreement_guarded` | state weights 4, 1, 2, 4, 4 | retains extra C/C coverage |

Malformed, missing, successful-case, or otherwise invalid A-F labels cannot
enter an audit state. A hand-built `AuditSample` is rejected unless its
strata identify exactly the focal failures, each stratum belongs to one
context, population and selected counts match its metadata, indices are
unique, and every inclusion probability equals its conditional `n_h/N_h`.

## 4. Estimands and estimators

For Coder-1 D/E indicator `A`, human-reference D/E indicator `H`, and audit
stratum `h`, the estimated full human-positive total is

```text
T_hat(H) = total(A) + sum_h N_h * mean_h(H - A).
```

Dividing the context-specific total by the number of focal failures gives the
two conditional D/E proportions and their ratio. The conditional audit
variance is

```text
sum_h N_h^2 * (1 - n_h/N_h) * s_h^2(H - A) / n_h,
```

divided by the squared context failure count. Horvitz-Thompson ratio
estimators separately summarize Coder-1 sensitivity and specificity against
the human reference.

Two intervals answer different questions:

- the **finite human-reference interval** contains only stratified audit
  residual variance and targets the realized full human-labelled roster;
- the **optimistic repeated-study interval** adds a conditional-binomial term
  and targets the scenario human-reference ratio.

The second interval ignores task/configuration clustering and is not D-005.
For noisy-human runs, coverage of the latent ratio is reported only as a
measurement-bias diagnostic, not as nominal coverage of the estimator's
human-reference estimand.

The main design comparison uses a perfect audit reference to isolate sampling
behavior. A separate A-F rater with 98% category accuracy generates a complete
potential human label for every trial before selecting the audit. This makes
the realized full-human ratio observable inside the simulation and separates
audit-sampling error from reference-label error.

## 5. Scenario grid and reproducibility correction

The audit grid uses the exact candidate 5,040, 9,660, and 19,320-trial broad
split matrices at base N=6, 12, and 24. It includes:

- an independent-error RR=1 null;
- independent-error and shared D/E-to-C RR=2 boundaries; and
- independent-error and shared D/E-to-C RR=3 alternatives.

The shared boundary is local to this audit study. It does not alter the six
scenarios or published seed schedule in the earlier joint D-010 memo.

Independent review found that the first implementation shared one random
stream across data generation, human labels, anchor sampling, and audit
cells. Consequently, batch size and grid composition could change common
oracle results. All pre-correction audit percentages were discarded. The
final implementation gives every replicate deterministic isolated streams
for the DGP, each human mode, anchor sample, anchor human, and each
design-by-budget audit. Exact tests now establish invariance to batch size and
to adding or removing unrelated grid cells.

The tables below use 1,000 replicates. A single reported probability has
maximum Monte Carlo standard error about 1.58 percentage points.

## 6. B=200 alternative results at base N=24

Joint support requires both the simulated registered kappa gate and an
optimistic pooled lower 95% bound above 2.0.

| Mechanism | Audit design | Joint support | Finite-reference coverage | Any context zero audit variance |
|---|---|---:|---:|---:|
| independent error | context SRS | 30.1% | 91.3% | 3.1% |
| independent error | state balanced | 60.9% | 95.1% | 5.4% |
| independent error | positive/disagreement stress | 67.2% | 82.0% | 85.7% |
| independent error | shared-agreement guarded | 64.5% | 94.4% | 29.9% |
| shared D/E-to-C | context SRS | 14.8% | 96.5% | 0.0% |
| shared D/E-to-C | state balanced | 9.7% | 95.4% | 1.5% |
| shared D/E-to-C | positive/disagreement stress | 9.5% | 94.6% | 1.9% |
| shared D/E-to-C | shared-agreement guarded | 15.2% | 95.6% | 0.2% |

For the independent-error rows, latent-oracle joint support is 67.1%, naive
Coder-1 support is 21.6%, and full perfect-human support is 68.2%. The stress
design's oracle-level 67.2% is therefore not a success: its finite-reference
coverage is only 82.0%, and at least one context estimates zero audit variance
in 85.7% of runs.

For the shared-bias rows, latent-oracle support is 65.7%, naive Coder-1
support is 0.8%, full perfect-human support is 66.3%, and the kappa gate passes
99.0%. Every audit is far below the oracle. The 0.4-point difference between
SRS and guarded is smaller than Monte Carlo resolution and does not rank the
designs.

## 7. Small-budget shared-bias falsification

The shared-bias boundary has true RR=2, so any joint support is false support
under the stated strict-greater-than-two rule.

| B=50 design | False support | Estimable | Finite-reference coverage | Missed hidden C/C correction |
|---|---:|---:|---:|---:|
| context SRS | 3.3% | 95.2% | 92.6% | 0.3% |
| state balanced | 18.7% | 96.4% | 65.1% | 15.2% |
| positive/disagreement stress | 28.9% | 98.6% | 40.2% | 47.3% |
| shared-agreement guarded | 19.9% | 98.9% | 68.0% | 6.6% |

At B=100 the enriched designs still show 10.5-22.0% false support and only
66.7-85.1% finite-reference coverage. At B=200, false support falls to
0.9-2.5% and finite-reference coverage rises to 94.5-96.9%. The independent
RR=1 null has zero false support in all simulated cells, while the independent
RR=2 boundary stays between 0% and 2.2% at B=50-200. These additional nulls
matter because the shared-error boundary, not the ordinary null, exposes the
allocation failure.

The B=50 enriched designs also report more apparent support under the shared
3x alternative than at B=200: 33.7%, 45.3%, and 27.6% for balanced, stress,
and guarded, versus 9.7%, 9.5%, and 15.2%. Their corresponding B=50
finite-reference coverage is only 61.0%, 36.1%, and 67.8%. This inverse
budget relationship is direct evidence of missed corrections and understated
uncertainty.

## 8. What 400 audit labels buy

| Mechanism | Audit design | Joint support | Finite-reference coverage | Any context zero audit variance |
|---|---|---:|---:|---:|
| independent error | context SRS | 52.6% | 94.2% | 0.2% |
| independent error | state balanced | 64.6% | 62.7% | 99.0% |
| independent error | positive/disagreement stress | 64.8% | 74.5% | 99.4% |
| independent error | shared-agreement guarded | 64.6% | 66.6% | 99.4% |
| shared D/E-to-C | context SRS | 36.3% | 95.7% | 0.0% |
| shared D/E-to-C | state balanced | 27.9% | 93.8% | 0.0% |
| shared D/E-to-C | positive/disagreement stress | 24.3% | 95.3% | 0.0% |
| shared D/E-to-C | shared-agreement guarded | 39.4% | 94.8% | 0.0% |

The independent-error oracle is 64.7%; the shared-bias oracle is 64.5%.
State designs again appear oracle-equivalent under independent error only
because their finite audit variance collapses. The optimistic repeated-study
interval retains roughly 95% scenario-human coverage because its added
binomial component dominates; that does not validate the audit variance or
the absent mixed model.

At the shared RR=2 boundary, B=400 false support is 1.1%, 1.9%, 1.8%, and
2.5% for SRS, balanced, stress, and guarded. Boundary behavior improves, but
the shared 3x power gap remains operationally large at a conservative cost of
450 human labels.

## 9. Imperfect-reference sensitivity

For a failed trial, a wrong outcome-constrained A-F label is sampled uniformly
from the other three C-F categories. A human with accuracy `a` therefore has
D/E sensitivity `a + (1-a)/3` and false-positive rate `2(1-a)/3`.
At `a=0.98`:

| Latent scenario | Latent Linux / Windows D/E | Human-reference Linux / Windows D/E | Human-reference RR |
|---|---:|---:|---:|
| RR=2 boundary | 0.100 / 0.200 | 0.111 / 0.208 | 1.880 |
| RR=3 alternative | 0.100 / 0.300 | 0.111 / 0.305 | 2.759 |

In the B=400 shared-bias alternative, full noisy-human support is 47.1%,
compared with 66.1% for full perfect-human labels and 64.5% joint latent-oracle
support. Audit support ranges from 18.3% to 28.4% for the noisy-human
reference. These are not merely audit-allocation losses: the human-reference
estimand itself is attenuated relative to latent truth.

The 98% category accuracy is synthetic, not a claim about actual coders. Real
golden-case and dual-coded pilot evidence is required before treating a human
label as ground truth.

## 10. Decision implications

**Subsequent evidence:** `docs/D010_CONSERVATIVE_AUDIT_INTERVAL_MEMO.md`
replaces the failed plug-in audit variance with simultaneous exact
finite-population residual bounds. Coverage rises to 99.9-100%, but the
apparent advantage of AI-state enrichment disappears. Context SRS needs
roughly 600-800 of about 864 focal failures before audit measurement usually
stops bottlenecking a 3x effect, and D-005 remains necessary to handle
trial/task/configuration uncertainty. The exact interval is a conservative
benchmark, not an accepted D-010 rule.

### 10.1 What is rejected now

- Do not use support probability alone to select an audit design.
- Do not accept the positive/disagreement-heavy stress rule as load-bearing.
- Do not treat plug-in zero residual variance as proof of zero audit error.
- Do not infer that a smaller enriched audit is more powerful when its
  finite-reference coverage and hidden-correction diagnostics fail.
- Do not call B=400 sufficient: it costs 450 human labels and still reaches
  only 24-39% support under the shared-bias alternative.
- Do not call the optimistic pooled reference the D-005 mixed model.

### 10.2 Candidates retained only for further evidence

Context SRS is the most stable baseline across mechanisms. A guarded hybrid
could improve shared-agreement discovery, but its current state-level plug-in
variance fails under rare independent residuals and it is not reliably better
than SRS under shared bias. Neither is selected.

### 10.3 Required next evidence

1. Specify a conservative rare-residual uncertainty procedure with explicit
   zero-cell safeguards, then demonstrate finite-reference coverage across
   the same composite null and alternative mechanisms.
2. Couple the audited-label construction to the actual crossed D-005 model
   and repeat bias, estimability, coverage, and support checks with task,
   instance, configuration, and paired-slot dependence.
3. Cost candidate B values jointly with the separate anchor, dual coding,
   adjudication, missing/refusal branches, and actual human time.
4. Use label-masked golden cases and the pilot to estimate human class-specific
   error and dependence. Keep a pre-specified imperfect-reference sensitivity.
5. Pre-specify what level of effect-scale bias, finite-reference coverage,
   shared-error detection, and joint support is adequate for confirmatory H2.

Only then can D-010 choose an audit/label rule or D-002 decide whether H2 is
separately powered. Until then, no-support H2 remains non-interpretable as
evidence that spiral asymmetry is absent.

## 11. Verification

Core commands:

```powershell
python -m pytest tests/test_d010_enriched_audit.py tests/test_d010_joint_h2_measurement.py -q
python -m analysis.d010_enriched_audit --replicates 1000 --seed 20260802
python -m analysis.d010_enriched_audit --replicates 1000 --seed 20360802 --base-common-ns 24 --budgets 400
```

Tests cover the five exhaustive AI states; fail-closed invalid labels;
context and context-by-state construction; deterministic floors, ties, census
caps, and redistribution; unique selection and exact conditional inclusion
probabilities; a census point-estimate oracle; a hand-calculated residual
variance oracle; exhaustive repeated-sampling unbiasedness for unequal
noncensus strata; metadata/context contamination rejection; weighted class
performance; analytically derived noisy-human targets; RNG reproducibility;
exact batch/grid-composition invariance; both independent and shared-bias null
boundaries; output estimability; and fail-closed invalid grids.

Independent review found the original RNG-stream and composite-null gaps,
verified their corrections, checked the estimator and finite-population
variance algebra, and reproduced the final qualitative and targeted numeric
patterns. No benchmark trial ran and no frozen V1 methodology, task, rubric,
scheduler, or collection rule changed.

D-002, D-005, D-006, D-010, and D-013 remain OPEN. R-009, R-017, R-018, and
R-022 remain OPEN.
