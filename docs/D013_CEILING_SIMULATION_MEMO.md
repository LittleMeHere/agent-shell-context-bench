# D-013 ceiling, construct-mismatch, and H2 simulation memo

**Status:** EVIDENCE BASIS — G2 ceiling gate and D-013C direction accepted 2026-08-09; N/analysis remain open
**Created:** 2026-08-01
**Decisions informed:** D-001 through D-005 and D-013
**Findings:** R-001, R-002, R-003, R-022
**Code:** `analysis/d013_ceiling_operating_characteristics.py`
**Tests:** `tests/test_d013_ceiling_operating_characteristics.py`

## 1. Bottom line

The simulation supports three conclusions.

1. A five-event/two-family blinded pilot rule is the leading ceiling/floor
   candidate among the three tested rules. A one-event rule is too permissive,
   while making cross-domain spread a hard gate can reject genuine
   domain-concentrated signal. Domain spread should be a diagnostic branch,
   not automatic evidence that the instrument is invalid.
2. The current five-probe design cannot estimate the proposed six-domain
   target without an untestable extrapolation. In exact counterexamples, a
   true five-point six-domain average is zero on the current roster when the
   effect lies in an omitted domain, and twelve points when it lies in the
   domain the current roster overweights. More repetitions cannot repair that
   construct mismatch.
3. The 12-family split-N design removes those specific coverage biases at
   approximately current full-matrix cost, but its precision is often
   insufficient for a decisive five-point interval at small N. H2 is even
   more fragile: under an optimistic analysis that ignores clustering, rater
   error, and model convergence, a true 3x D/E ratio has only about 16%, 36%,
   and 66% reference support at base N=6, 12, and 24 in the split-N design.

These findings narrow the viable options but do not approve D-013. The
synthetic rates are sensitivity scenarios, not predictions of benchmark
outcomes.

## 2. Reproducible run

The prospective grid used 20,000 Monte Carlo replicates per scenario and seed
`20260801`:

```powershell
python -m analysis.d013_ceiling_operating_characteristics `
  --sections pilot --replicates 20000 --seed 20260801

python -m analysis.d013_ceiling_operating_characteristics `
  --sections h1 --replicates 20000 --seed 20260801

python -m analysis.d013_ceiling_operating_characteristics `
  --sections h2 --replicates 20000 --seed 20260801
```

The program emits one JSON object per scenario/design row. The maximum Monte
Carlo standard error of a reported probability is approximately 0.35
percentage points. All inputs are synthetic and outcome-blind.

## 3. Pilot ceiling/floor gates

The candidate 12-family pilot exercises three frozen instances in two pilot
configurations and five environments:

```text
12 families x 3 instances x 2 configurations x 5 environments
= 360 capability trials
```

This is three target valid slots per family/configuration/environment cell,
with each frozen capability instance exercised exactly once—not two
repetitions of every family-instance cell. The seeded portion separately uses
two repetitions:

```text
18 seeded variants x 2 repetitions x 2 configurations x 5 environments
= 360 seeded trials
```

The two portions total the 720-valid-trial full-coverage pilot cost recorded
in the task-bank memo.

The three candidate gates were:

| Gate | Failure minimum | Success minimum | Spread minimum |
|---|---:|---:|---|
| G1 any information | 1 | 1 | one failing and successful family/domain |
| G2 five events/two families | 5 | 5 | two failing and successful families |
| G3 ten events/cross-domain | 10 | 10 | three families and two domains on each outcome side |

### 3.1 Diffuse failure scenarios

| True mean failure rate | Expected failures | G1 proceed | G2 proceed | G3 proceed |
|---:|---:|---:|---:|---:|
| 0.5% | 1.8 | 84% | 4% | 0% |
| 1.0% | 3.6 | 97% | 30% | 0% |
| 2.0% | 7.2 | ~100% | 85% | 19% |
| 5.0% | 18.0 | 100% | ~100% | 99% |
| 10.0% | 36.0 | 100% | 100% | 100% |

The floor behavior is symmetric at extreme high failure rates: at a 99%
failure rate, G1 proceeds 97%, G2 30%, and G3 approximately 0%.

G1 only detects a literal zero-event branch. It proceeds 84% of the time when
the expected number of failures is 1.8, which is too weak if the gate is meant
to establish nontrivial task-bank information rather than merely one event.
G3 makes a much stronger statement: it effectively requires roughly a 5%
diffuse failure rate in this pilot design.

### 3.2 Domain-concentrated scenarios

The concentrated scenarios put almost all failures in one domain while
holding the overall mean at 5% or 10%.

| Scenario | G2 proceed | G3 proceed | G3 concentrated branch |
|---|---:|---:|---:|
| one-domain mean 5% | 99.93% | 77.12% | 22.31% |
| one-domain mean 10% | 100% | 77.82% | 22.19% |

The G3 concentration branch is scientifically meaningful, but it should not
automatically send the instrument back to development. Concentration can be a
real result. The leading candidate is therefore:

- use G2 as the symmetric ceiling/floor sufficiency gate;
- compute the G3 family/domain-spread quantities as blinded diagnostics;
- route concentrated pilots to a pre-specified domain-heterogeneity review,
  without selecting tasks based on the named context-effect direction;
- require a fresh pilot only if that review changes the instrument.

This candidate still requires D-013 acceptance and sensitivity to other
family/domain heterogeneity patterns.

G2 is only a coarse instrument-development ceiling/floor gate. Passing it
does not establish per-context H1 estimability, H2's failed-trial denominator,
broad domain coverage, acceptable power, or criterion validity. Those are
separate D-001 through D-005 and D-013 gates.

## 4. Six-domain target versus five current probes

The target scenarios contain six domains, two families per domain, three
instances per family, and seven configurations. The broad estimator weights
instances within family, families within domain, and the six domains equally.

Equal domain weighting is a candidate estimand used to expose the construct
problem; the simulation does not establish that real workflows have equal
domain prevalence or that these are the correct decision weights. The exact
mismatch magnitudes below are conditional on that choice. More generally, an
unsampled domain with nonzero target weight remains unidentified from the
five-probe roster regardless of repeated-trial precision.

The current-probe synthetic estimator mirrors the documented roster:

- two families from filesystem/artifacts;
- two from data/config/text;
- one from repository/code change;
- no version-control, build/package, or runtime/system family.

The construct counterexamples set heterogeneity to zero so only domain
coverage changes the result.

| Scenario | True six-domain RD | True current-roster RD | Current mismatch | Broad split-N mismatch |
|---|---:|---:|---:|---:|
| effect only in omitted domain D | 5 pp | 0 pp | -5 pp | 0 pp |
| effect only in overweighted domain A | 5 pp | 12 pp | +7 pp | 0 pp |
| opposing +12/-12 pp domains | 0 pp | 4.8 pp | +4.8 pp | 0 pp |

The opposing-domain scenario also has a maximum absolute domain effect of 12
points even though the broad average is zero. A broad null therefore cannot
mean “no domain mechanism.” Registered domain and leave-one-domain-out
diagnostics remain necessary.

This is the load-bearing construct result: increasing N for C01-C05 can make
their exact-roster estimate precise, but it cannot identify the six-domain
average under these counterexamples.

## 5. Precision and breadth-versus-repetition

The table below gives Monte Carlo sampling standard deviations for a diffuse
five-point target. The intervals used for the accompanying decision
probabilities are oracle-normal references using the true Monte Carlo
sampling SD. They are not the D-005 confirmatory model.

| Base N | Current five SD | Broad common-N SD | Broad split-N SD |
|---:|---:|---:|---:|
| 6 | 2.92 pp | 1.99 pp | 2.83 pp |
| 12 | 2.09 pp | 1.42 pp | 2.31 pp |
| 24 | 1.46 pp | 1.00 pp | 1.57 pp |

At approximately matched full-matrix cost, split N has broadly similar
sampling error to the five-probe design while estimating the stated target.
Common N is substantially more precise and costs 30.4% more.

At a true five-point effect, approximately 95% of oracle 95% intervals are
inconclusive. That is expected: a rule requiring the interval to lie wholly
above or below five points should not usually decide at the boundary.

For more decision-relevant scenarios:

| Scenario | Base N | Current | Broad common N | Broad split N |
|---|---:|---:|---:|---:|
| true null: reference interval wholly below 5 pp | 6 | 46% | 76% | 47% |
| true null: reference interval wholly below 5 pp | 12 | 77% | 97% | 66% |
| true null: reference interval wholly below 5 pp | 24 | 96% | ~100% | 93% |
| true 10 pp: reference interval wholly above 5 pp | 6 | 25% | 64% | 38% |
| true 10 pp: reference interval wholly above 5 pp | 12 | 43% | 92% | 53% |
| true 10 pp: reference interval wholly above 5 pp | 24 | 73% | ~100% | 86% |

These are optimistic feasibility references. A real clustered/hierarchical
interval may be wider. They imply:

- split N is a serious resource-constrained candidate because it repairs
  content coverage without a large total-cost increase;
- base N=6 or 12 is unlikely to produce decisive five-point conclusions in
  many plausible scenarios;
- common N buys meaningful precision, so D-004 resource evidence is not a
  bookkeeping detail;
- no N should be approved until the exact D-005 analysis reproduces or
  improves on acceptable operating characteristics.

## 6. H2 failed-trial availability and optimistic reference power

H2 uses all capability and seeded tasks conditional on valid task failure.
The simulation preserves the registered pooled minimum of ten failed trials
per focal context and the per-configuration minimum of five. It varies
capability and seeded failure rates separately.

The reference interval is a pooled log-risk-ratio interval for the conditional
D/E proportion. It ignores task/configuration clustering, IRR
misclassification, adjudication, convergence failure, and the hard κ-based
demotion. It is an optimistic reference, not a formal upper bound and not the
D-005 analysis. The exact hierarchical model could behave differently; the
κ-based demotion can only reduce the probability of a confirmatory H2 status
relative to the same classified outcomes.

### 6.1 Sparse and low-failure scenarios at base N=6

| Scenario/design | Expected failures L/W | P(both pooled denominators >=10) | P(reference ratio estimable) |
|---|---:|---:|---:|
| sparse, current | 8.6 / 8.6 | 13% | 8% |
| sparse, broad common N | 10.1 / 10.1 | 30% | 21% |
| sparse, broad split N | 8.8 / 8.8 | 15% | 10% |
| low, current | 17.2 / 25.8 | 98% | 81% |
| low, broad common N | 20.2 / 30.2 | ~100% | 86% |
| low, broad split N | 17.6 / 26.5 | 98% | 81% |

At the exact true D/E ratio boundary of 2x, reference support is essentially
zero in the low-failure scenario and about 1.2% in the moderate-failure
scenario. That is not a defect: a 95% interval should rarely lie wholly above
the threshold when truth is exactly on the threshold.

### 6.2 True 3x D/E ratio under moderate failure rates

| Base N | Current reference support | Broad common-N support | Broad split-N support |
|---:|---:|---:|---:|
| 6 | 16% | 20% | 16% |
| 12 | 36% | 42% | 36% |
| 24 | 67% | 74% | 66% |

Even this optimistic reference does not reach conventional 80% power at the
largest tested N. The actual H2 procedure must additionally survive
clustering and the κ-based measurement gate.

The evidence therefore weighs against assuming that H1 sizing automatically
makes threshold-based H2 confirmatory. D-002 Option B (prospective
feasibility envelope) or Option C (explicitly exploratory H2) remains more
credible than separately powering H2 until measured failure and rater-error
inputs show otherwise.

## 7. Limitations and counterexamples not yet covered

- Domain, family, instance, configuration, and context probabilities are
  fixed synthetic finite-roster scenarios, not empirical estimates.
- Pilot results assume the 720-valid-trial full-instance pilot and no
  retry-cap failure.
- H1 oracle-normal intervals use the true Monte Carlo sampling SD. They do not
  model estimated standard errors, finite-cluster corrections, singular fits,
  or convergence branches.
- H2 uses a pooled reference interval and omits rater sensitivity,
  specificity, κ variability, adjudication, and hard demotion.
- The simulation does not yet model temporal drift, invalid-attempt caps,
  vendor-specific N, unequal domain weights, or criterion-holdout outcomes.
- The current-roster synthetic mapping is a construct counterexample, not an
  estimate of the actual C01-C05 effect.
- The scenarios establish that failures are possible; they do not estimate
  how likely each scenario is in collection.

## 8. Recommended decision state

**Subsequent evidence:** `docs/D005_FINITE_ROSTER_IRR_MEMO.md` implements
analytic finite-roster comparators and prospective IRR misclassification on
this exact candidate schedule. It confirms the small split-N estimability and
H2 feasibility concerns, shows that omnibus κ does not control rare-D/E
effect-scale attenuation, and still leaves the final D-005 model/bootstrap
and joint measurement model open.

`docs/D010_JOINT_H2_MEASUREMENT_MEMO.md` then implements that matched-N joint
measurement step with the registered minimum-size human-sampler
instantiation. It confirms that H2 remains measurement- and power-limited and
leaves every substantive D-010/D-005 choice open.

D-013 and the G2/split-N direction were accepted on 2026-08-09. R-022 remains
open for task authoring, qualification, and executable analysis. The next
implementation comparison is:

1. retain G2 as the leading pilot ceiling/floor candidate and treat domain
   concentration as a diagnostic branch;
2. retain the 12-family common-N and split-N banks for D-005 simulation;
3. reject the claim that the five-probe design can support a six-domain broad
   null, regardless of repeated-trial precision;
4. do not approve base N=6 as decision-adequate from this reference grid;
5. treat H2 as feasibility-limited unless exact-model and IRR simulations
   overturn the optimistic reference result;
6. next implement the accepted candidate estimator/model in simulation,
   including nested instance effects, finite-cluster behavior, invalid caps,
   and IRR misclassification.

No task, threshold, N, preregistration, scheduler, or collection plan is
changed by this memo.
