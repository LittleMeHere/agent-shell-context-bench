# D-005 H1 dependence, drift, and attrition recovery envelope

**Status:** PLAN-BOUND IMPLEMENTATION INDEPENDENTLY ACCEPTED; N=36 target
accepted subject to provider cap
**Created:** 2026-08-15
**Code:** `analysis/d005_h1_recovery_envelope.py`
**Tests:** `tests/test_d005_h1_recovery_envelope.py`

## Result

The leading Clopper-Pearson-MOVER fixed-roster interval passed all 32
prospectively defined recovery cells at base N=24 under the current split-N
capability design. The grid crosses four outcome structures with eight
nuisance/dependence mechanisms and uses 5,000 replicates per cell.

Across all 32 cells:

- minimum coverage was 95.52%;
- maximum wrong five-point threshold declaration probability was 0.70%;
- maximum absolute point-estimate bias was 0.063 percentage points; and
- all intervals remained estimable.

The estimator is now bound directly to a fully validated schedule plan. An
independent adversarial re-review accepted its configuration, instance, leaf,
count, plan-digest, and count-preserving identity-swap boundaries after the
repair. Exact N, the broad-model sensitivity disposition, and researcher
methodology acceptance remain pre-data requirements.

## N=36 precision extension (2026-08-22)

The same full 32-cell, 5,000-replicate envelope was rerun prospectively with
15 repetitions per family/configuration, corresponding to base N=36. All 32
coverage/bias/wrong-declaration screens passed. For the diffuse null,
bounded-small classifications ranged from 84.76% to 93.92%; for the diffuse
10-point gap, decision-relevant classifications ranged from 80.82% to 93.06%.
At the five-point boundary, 96.92% to 99.82% remained inconclusive, as a
calibrated interval should.

The opposing-domain null is deliberately harder: bounded-small decisions
ranged from 72.86% to 86.60%. Thus N=36 supports an 80% decisiveness target
for the registered diffuse clear-null/strong-effect envelope, but not a claim
that every heterogeneous null will be decisive. It raises the full
confirmatory matrix from 19,320 to 28,980 agent trials (+50%), including
12,420 `agy` trials, so it is a freeze candidate only if the final provider
and calendar cap can support it.

## Prospective screen

The screen was fixed in the evidence code before the full grid was run:

- coverage at least 94%, allowing Monte Carlo tolerance around a nominal 95%
  interval;
- wrong threshold declarations no more than 1%; and
- absolute risk-difference point bias no more than 0.5 percentage points.

The target in each replicate is the equally weighted average of the actual
slot-level generating probabilities. This avoids pretending trials are
identically distributed when a simulated calendar wave or provider state
changes the probability within a fixed leaf.

## Recovery mechanisms

Each mechanism preserves the exact 252 configuration/family/instance leaves
per focal context and 1,680 total focal trials at split N=10.

| Mechanism | Stress represented | Minimum coverage over four outcome structures |
|---|---|---:|
| Independent reference | Original prospective independent-binomial case | 96.62% |
| Balanced common calendar drift | Four ordered logit shifts shared by contexts | 97.08% |
| Balanced differential calendar drift | Additional ordered Windows-context shift | 97.20% |
| Shared domain/configuration state | Replicate-specific shared logit shock, SD 0.75 | 97.62% |
| Context-specific domain/configuration state | Independent context shocks, SD 0.40 | 97.20% |
| Positive matched-slot dependence | Gaussian-copula association +0.40 | 98.28% |
| Negative matched-slot falsification | Gaussian-copula association -0.40 | 95.52% |
| Combined operational stress | Drift, shared/differential state, and +0.25 dependence | 97.68% |

The deliberately adverse negative-dependence arm produced the minimum
coverage. It still cleared the prospective screen, so the result is not an
artifact of testing only variance-reducing positive matching.

## Outcome-structure summary

| Generating structure | Minimum coverage | Maximum wrong declaration | Maximum absolute point bias |
|---|---:|---:|---:|
| Diffuse null, RD=0 | 99.44% | 0.00% | 0.024 pp |
| Diffuse threshold, RD near 5 pp | 98.90% | 0.70% | 0.042 pp |
| Diffuse strong, RD near 10 pp | 98.38% | 0.00% | 0.053 pp |
| Opposing domain mechanisms, average RD=0 | 95.52% | 0.04% | 0.063 pp |

The diffuse-null bounded-small decision rate ranged from 60.64% to 75.26%.
The exact-threshold grid was inconclusive in 97.48% to 99.86% of replicates.
The strong-effect decision-relevant rate ranged from 63.32% to 73.44%.
These are operating characteristics of this candidate and scenario envelope,
not promises about benchmark outcomes.

## Attrition and retry interpretation

D-009 already prohibits a decision-bearing complete-case analysis. An
infrastructure-invalid attempt retries the same valid slot; if a retry cap is
exhausted, the roster is incomplete and A1 has no decision. Therefore
attrition is an availability problem, not a missing-data estimator branch.

For a 720-slot roster under independent invalid attempts, the probability of
completing every slot illustrates why the final cap must use measured invalid
rates rather than a convenient small integer:

| Invalid probability per attempt | 2 attempts/slot | 3 attempts/slot | 4 attempts/slot |
|---:|---:|---:|---:|
| 1% | 93.05% | 99.93% | >99.99% |
| 5% | 16.49% | 91.39% | 99.55% |
| 10% | 0.07% | 48.66% | 93.05% |

These are analytic availability probes, not forecasts and not cap choices.
The D-004 cap must be frozen from authenticated measurements and the accepted
60/10/30 resource envelope.

## Boundaries and remaining evidence

- The four simulated waves are balanced stress waves, not a claim that the
  eventual confirmatory plan already has an accepted epoch layout. The
  accepted 180-slot D-009 epochs currently bind the V2 pilot plan.
- Outcome-dependent or selective deletion is not analyzed because it is
  forbidden: any missing registered valid slot produces no primary decision.
- The Gaussian copula is a dependence stress model, not a claim about the
  actual joint distribution of agent failures.
- This module does not substitute a Python approximation for the unavailable
  R Family-A GLMM. The finite-roster Family-B primary direction remains
  accepted; the exact broad-model sensitivity and software disposition still
  require freeze.
- H2 measurement error and audit uncertainty remain in the D-010 evidence
  chain and do not become resolved by this H1 recovery grid.

## Reproduction

```powershell
python -m pytest tests/test_d005_h1_recovery_envelope.py -q
python -m analysis.d005_h1_recovery_envelope --replicates 5000 --seed 20260815
python -m analysis.d005_h1_recovery_envelope --replicates 5000 --seed 20260822 --repetitions-per-family-config 15
```

No benchmark outcomes, private artifacts, task bytes, or frozen V1
methodology are read or changed by these commands.
