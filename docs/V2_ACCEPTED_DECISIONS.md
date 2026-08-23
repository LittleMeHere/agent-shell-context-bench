# V2 accepted methodology decisions

**Status:** ACCEPTED DIRECTION — implementation and evidence-dependent
parameters remain open until the V2 tag
**Accepted:** 2026-08-09, before pilot or confirmatory outcome access
**Authority:** researcher acceptance of the complete V2 slate
**Evidence package:** `V2_DECISION_PACKAGE.md` and the linked outcome-blind
simulation, construct-audit, resource, and runtime memos

## 1. Scope of this acceptance

This record resolves which scientific design the project is pursuing. It does
not pretend that unknown subscription capacity, unqualified task families,
unqualified coding backends, or an unverified analysis implementation are
already fixed. Final confirmation of the N=36 target against the provider cap
and the final runtime-matrix digest remain evidence-gated. The exact audit
parameters, D/E evidence boundary, and label-masking claim were accepted
pre-data on 2026-08-22. Coder identities were previously fixed pre-data in
`docs/D006_CODER_ASSIGNMENT.md`.

The existing five-capability-task V1 pilot is not an acceptable substitute
for the accepted V2 design. Paid pilot collection remains blocked until the
12-family bank is authored, qualified, frozen, and propagated through the
scheduler, blinding, sizing, and analysis paths.

## 2. Accepted slate

| ID | Accepted decision | Remaining parameter or evidence |
|---|---|---|
| D-001 | Primary H1 estimand is the finite-roster, task-weighted Windows-minus-Linux failure risk difference. The operational threshold is five percentage points. Report RR and both marginal rates as companions. | Plan-bound interval/fallback passed independent re-acceptance; N=36 target is accepted subject to the provider cap. |
| D-002 | H2 is exploratory. Report conditional D/E rates, denominators, audited uncertainty, coder sensitivities, and effect estimates without a support/reject threshold. | Measurement pipeline, coder qualification, and bounded human-audit design. |
| D-003 | Confirmatory N is selected prospectively from simulations and the accepted resource cap. Pilot outcomes validate the instrument and nuisance envelope; they do not resize N from the observed named effect. | N=36 target accepted 2026-08-22, conditional only on confirming the prospective 60/10/30 provider/calendar cap. |
| D-004 | Preserve the private 60% planned / 10% retry / 30% untouched provider-window envelope. Raw calls are not assumed to be equal quota units. | Numeric provider/calendar caps after representative paid shakedowns. |
| D-005 | Family B finite-roster fixed-block analysis is primary. Broader GLMM and task/configuration-superpopulation models are sensitivity analyses only. | Plan-bound CP-MOVER/fallback is independently accepted; N=36 target is cap-conditional and broad-sensitivity disposition remains. |
| D-006 | Coding and human review use a staged, probability-sampled, time-bounded design. Codex CLI 0.147.0 / GPT-5.6 Terra is population-wide Coder 1; Claude Code 2.1.231 / Sonnet 4.6 is probability-sampled Coder 2. Routine collection does not imply a 600–700-label human commitment. | Exact 50+150/cap-200 gate accepted 2026-08-22; production prompt/driver integration and golden qualification remain. |
| D-007 | E5 remains closed until real subscription CLIs authenticate and complete an analysis-excluded macOS runner shakedown with credential cleanup. | Real ephemeral-runner evidence. |
| D-008 | Publication remains closed until the deterministic redaction builder and audit report pass. | Sample publication build and final public-artifact inventory. |
| D-009 | Use role-preserving runtime eligibility, same-nominal-model S6, one global blocked round-robin order, four fixed 180-slot epochs, periodic runtime checks, and no decision-bearing analysis from an incomplete roster. | D-005 epoch-sensitivity interval, qualified hosts, and final matrix digest. |
| D-010 | The frozen Codex/Terra primary coder supplies the analysis label. No disagreement or adjudication branch may rewrite it. Claude/Sonnet and label-masked human labels are probability-sampled audit/sensitivity evidence. Missing/refused/malformed primary output remains missing. | Exact 50+150/cap-200 gates, D/E evidence boundary, and explicit-label-masking claim accepted 2026-08-22; production integration remains. |
| D-011 | Agy H1 uses the same observable outcome as every agent: valid, completed, not timed out, and executable predicate passed. Cwd/canary evidence is descriptive and supports A1d/H2, not an extra H1 gate. | VERIFIED across runner, writer, and independent analysis reconstruction after external falsification and repair of the combined incomplete-plus-measurement-loss edge case. |
| D-012 | H4 is the exploratory contrast between the exact registered formal and colloquial prompt sets, with prompt text and per-task heterogeneity shown. No generic colloquiality, permission, urgency, or syntax-cue mechanism claim is allowed. | Frozen coding/analysis implementation and reporting templates. |
| D-013 | Build and qualify a 12-family, six-domain capability bank with two independently authored families per domain, multiple instances, equal domain weighting, split N, and the symmetric five-failure/five-success two-family pilot gate. | Five-host oracles, all 36 instances, Q2, scheduling, and gate implementation are complete; fresh-human Q1, transcript Q2/Q3, N=36 cap confirmation, and final Q4 freeze remain. |

## 3. Human-review constraint

H2 and H4 are exploratory; therefore a human census or near-census is not a
default obligation. The routine design must have a small fixed label-masked anchor
and may have one bounded focal audit only when a pre-specified measurement-
informativeness gate passes. The gate may use frozen aggregate denominators,
known-probability audit diagnostics, refusal/malformed rates, and judge-error
evidence. It must not use whether a named environment effect looks exciting
or whether a preferred hypothesis would become significant.

If the primary judge is unusable, the default response is to report H2/H4 as
measurement-invalid or inconclusive, not to spend dozens of hours rescuing a
secondary claim. Any plan above the routine human-label cap requires a new
explicit researcher go/no-go decision. A 600–700-label audit belongs to a
separately justified follow-up or claim upgrade, not to the automatic cost of
this benchmark.

## 4. Rejected paths

- Running the five-task V1 pilot and generalizing a precise null to routine
  coding-agent work.
- Selecting N from the observed pilot context effect.
- Treating H2 as a powered threshold test under the current resource envelope.
- Letting consensus, adjudication, or selective human review replace the
  frozen primary label after seeing which result is favorable.
- Generic causal language about colloquiality from the compound prompt pairs.
- Agy-only unobservable “task-completing command” success requirements.
- Whole-cell scheduling that permits environment or configuration to align
  with quota week, host, or backend epoch.

## 5. Consequences for V1 and implementation

The V2 amendment must identify the exact V1 SAP/HYPOTHESIS/VERSIONS clauses
superseded by these decisions and add the corresponding `DEVIATIONS.md` entry
before a V2 tag is cut. Frozen V1 files remain historical evidence and are not
silently rewritten.

Implementation order is:

1. freeze the staged human-audit candidate and task-family qualification
   contracts;
2. author and independently qualify the 12-family bank;
3. generalize scheduler, trial identity, blinding, sizing, and analysis
   manifests to family/instance/slot identity and blocked rounds;
4. finish the finite-roster analysis and measurement pipelines with synthetic
   recovery;
5. qualify real hosts/backends and measure resource use;
6. confirm N=36 against the provider cap, freeze the runtime digest, V2 amendment, and pilot
   plan; and
7. begin paid pilot collection only after every earlier gate passes.
