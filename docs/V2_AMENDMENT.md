# Pre-data V2 methodology amendment — freeze candidate

**Status:** FREEZE CANDIDATE — not operative until reviewed and tagged
**Prepared:** 2026-08-16
**Data status:** no blinded-pilot or confirmatory outcomes have been collected
**Supersedes when frozen:** only the V1 clauses identified below; all other V1
rules remain in force

## Reading rule

The immutable `pre-registration-v1` tag remains the historical record. This
document states the intended V2 replacement wording without editing the
frozen files. Bracketed `OPEN` items are not methodology and prevent a V2 tag.
The final review must remove every bracketed item, add the corresponding
`DEVIATIONS.md` entry, and bind this amendment to the frozen runtime, task,
analysis, and collection-plan digests.

## V1 → V2 wording diff

| Topic | V1 wording/behavior | V2 replacement wording |
|---|---|---|
| H1a task scope | Five capability tasks, C01-C05; broader reliability language | The exact qualified 12-family, 36-instance, six-domain capability roster only. It is a finite benchmark screening decision, not an estimate for all coding tasks, machines, or users. |
| H1a scale and decision | Windows/Linux risk ratio of at least 1.5, with the interval required not to cross 1.5 | Primary estimand is the equally weighted Windows-minus-Linux failure risk difference. `L_RD > 0.05` is **decision-relevant gap**; `U_RD < 0.05` is **bounded below the decision threshold**; otherwise **inconclusive**. Both marginal rates and RR are mandatory companions. |
| H1a weighting | Pooled mixed/clustered model across task and configuration | Average repeated trials within instance; weight instances equally within family, families equally within domain, domains equally, and the seven registered configurations equally. The exact finite roster is fixed; a missing or extra leaf/configuration is not silently reweighted. |
| H1a uncertainty | Cluster-robust/mixed-effects primary, with an incompletely matched sizing formula | Family-B fixed-roster analysis is primary. The independently re-accepted interval is CP-MOVER with a simultaneous Clopper-Pearson/Bonferroni fallback below three observations in any registered leaf. The estimator requires the fully validated schedule plan and rejects incomplete, excess, swapped, or foreign identities. Base N=36 is the accepted target subject only to the prospective provider cap. `[OPEN: provider-cap confirmation and broad-sensitivity freeze]` Broader GLMM/superpopulation fits are sensitivities only. |
| Pilot and N | A 460-trial, Claude-only blinded pilot estimates a pooled rate/ICC and sets confirmatory N through the frozen V1 formula | N is selected prospectively from outcome-blind operating-characteristic simulation and the accepted resource envelope. Base N=36 is the accepted target if and only if the prospective 60/10/30 provider cap supports it; pilot outcomes cannot change that choice. The exact 540-cell/720-slot V2 pilot validates roster execution, ceiling/floor behavior, and the nuisance envelope; it does not resize N from an observed named context effect. Fewer than five capability failures is `CEILING`, fewer than five successes is `FLOOR`, and either outcome confined to one family is `CONCENTRATED`; each stops confirmation. A task change requires an amendment, new digest, and fresh pilot. Domain concentration across at least two families is diagnostic only. `[OPEN: numeric provider/calendar caps]` |
| H2 status | Confirmatory conditional D/E ratio threshold of 2.0, demoted only when IRR fails | H2 is exploratory. Report conditional D/E rates, denominators, effect estimates, design-aware uncertainty, and coder/audit sensitivities; make no support/reject claim at 2.0. Sparse and measurement-invalid branches remain explicit. |
| Primary H2/H4 label | Two AI coders plus human anchor and κ rules, without a complete rule selecting the analysis label | Codex CLI 0.147.0 / GPT-5.6 Terra is frozen Coder 1 and the sole primary label source. Claude Code 2.1.231 / Sonnet 4.6 is Coder 2. Coder 2 and human labels are probability-sampled audits/sensitivities. Disagreement or adjudication never rewrites the primary label. Refused, malformed, missing, or substituted Coder-1 output remains missing. The accepted audit is a fixed 50-label anchor plus exactly 150 focal failed-trial labels when the gate passes, capped at 200 with no automatic third stage. Zero AI-reported C/D/E does not itself stop the focal audit. |
| A-F evidence and masking | Coder sees prompt/outcome/transcript, while code-E and capability-failure rules also depend on filesystem/canary evidence; the human was described as blinded | The exact coder packet and a frozen deterministic post-coder evidence join preserve raw code, canary coverage, confirmed escape evidence, transcript-only evidence, and invalid/missing states under the accepted D/E boundary. Human packets mask explicit identities and normalize non-evidential vendor wrappers, but do not claim full blinding because evidential commands can reveal environment. `[OPEN: R-018 production integration and golden-case acceptance]` |
| H3 population/time | C01-C05 with V1 model machinery | Same qualified finite capability roster and fixed four-epoch contract as H1a. WSL2 claims are limited to the registered host/context bundle. An executable A3 candidate exists, but independent review found its multiplicity, binding, interval/reporting, and epoch checks insufficient; `[OPEN: repair and independently accept A3]`. |
| H4 construct | “Colloquial / permission-granting phrasing” mechanism language | Exploratory contrast between these exact nine registered formal and colloquial prompt pairs. Show prompt text and per-task heterogeneity. Do not claim a generic effect of colloquiality, permission, urgency, specificity, or syntax cues. |
| agy H1 | Success additionally depended on undefined “task-completing” commands and Cwd compliance | Agy uses the same observable H1 outcome as every agent: valid, completed, not timed out, and executable predicate passed. Transcript/Cwd evidence is separate A1d/H2 evidence and can make a trace-dependent measurement unavailable; it is not an extra H1 success gate. |
| Collection order | No complete prospective temporal-balance contract | Use the digest-bound 720-slot blocked-round order, four fixed 180-slot epochs, host partitions, periodic routing/version checks, and fail-closed incomplete-roster handling. No decision-bearing estimate may silently use an incomplete crossing. |
| Runtime identity | V1 version table with several pin-at-start paths | Every production plan and trial binds the accepted runtime-matrix digest. Fixed pins are enforced where installable; agy's day-one exact version/hash/archive/re-smoke contract governs its self-updating channel. `[OPEN: final matrix digest and day-one agy evidence]` |
| Publication | Manual redaction policy | Public release stays closed until a separate deterministic staging builder, automated high-risk scans, and signed human spot-audit pass. This is a publication gate, not a pilot-start gate. |

## Explicitly retained V1 boundaries

- H1 outcomes are programmatic and fixed before A-F coding.
- Valid timed-out or incomplete trials are failures; infrastructure-invalid
  attempts do not consume valid slots and remain auditable.
- Invalid attempts, plan identity, source bytes, and analysis membership are
  immutable and digest-bound.
- H1b remains descriptive, but its exact V2 population/weighting text must be
  reconciled with the instance-expanded capability bank before freeze.
- H3 remains secondary and H4 remains exploratory.
- Environment effects describe the registered execution-context bundles, not
  intrinsic operating-system causation.

## Freeze blockers visible in this amendment

1. provider-cap confirmation of the accepted N=36 target and broad-sensitivity freeze for the re-accepted D-005 estimator;
2. independent acceptance of the executable A2-A4/reporting candidate after
   repairing exact design binding, H1 coherence, multiplicity, scarcity,
   provenance/evidence-transition, epoch, and reporting-firewall gaps;
3. provider/calendar resource caps using the completed human-timing evidence;
4. exact V2 H1b population/weighting wording;
5. final runtime-matrix, analysis-version, plan, and task-bank digests;
6. the day-one agy capture and final outcome-blind host dry runs; and
7. reviewer approval plus a matching `DEVIATIONS.md` entry and V2 tag.

## Proposed paper-language firewall

Positive, bounded-small, null, sparse, and measurement-invalid results must
all be reportable without changing this plan. The paper may say “on this
registered finite benchmark and these execution-context bundles.” It may not
say Windows intrinsically causes failures, the roster estimates all coding
work, H2 is a powered mechanism test, or H4 isolates colloquiality.

No finite N can force a decisive result when the true risk difference lies
at the five-point decision boundary. A threshold-adjacent `inconclusive`
result is therefore calibrated behavior, not a post-hoc sample-size excuse.
