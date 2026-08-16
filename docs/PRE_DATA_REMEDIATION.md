# Pre-data remediation plan and shared project state

**Status:** ACTIVE — collection is blocked
**Created:** 2026-07-28
**Last updated:** 2026-08-15
**Applies to:** `agent-shell-context-bench` V1 follow-through through a
published paper

## 1. Purpose and authority

This document is the shared source of truth for work required before the
blinded pilot may run. It exists because the repository accumulated many
locally reasonable reviews without one durable place that:

1. distinguished verified evidence from reviewer confidence,
2. tracked findings across agents and sessions,
3. gave each blocker a falsifiable acceptance criterion, and
4. prevented "ready" from meaning different things to different reviewers.

This is a project-control and audit document. It is **not** itself a change to
the frozen V1 methodology. The `pre-registration-v1` tag remains immutable.
Any approved methodological correction will be published separately as a
timestamped, pre-data V2 amendment and recorded in `DEVIATIONS.md`.

As of 2026-07-28:

- no blinded-pilot or confirmatory data have been collected;
- local committed `main` matches `origin/main` at `9eb12e5`;
- pre-registration smoke evidence exists only under
  `data/pre-registration/` and is not analysis data;
- local, uncommitted scheduler work is present and belongs to the researcher;
- **the pilot must not run** until every gate through G4 in section 7 is
  satisfied.

## 2. Required reading and status vocabulary

Before doing non-trivial work, every agent or human contributor must read:

1. `AGENTS.md`;
2. `CLAUDE.md`;
3. this document;
4. `docs/HYPOTHESIS_TRACEABILITY_MATRIX.md` for methodology, outcome,
   analysis, IRR, or publication-claim work;
5. the specific methodology or implementation files cited by the work item.

Use these status terms only:

- **OPEN** — required work has not met its acceptance criterion.
- **IN PROGRESS** — an identified owner is actively working on it.
- **IMPLEMENTED** — code or prose exists, but its independent acceptance
  evidence is incomplete.
- **VERIFIED** — the acceptance criterion has passed and the exact evidence is
  recorded here.
- **BLOCKED** — an external dependency prevents progress; the dependency and
  retry condition are recorded.
- **SUPERSEDED** — replaced by a later, identified decision or work item.

Words such as "reviewed," "done," "looks good," "production-ready," and
"collection-ready" are not statuses. A work item is VERIFIED only when its
recorded acceptance criterion passes.

## 3. Change boundaries

### 3.1 Frozen V1 methodology

The files listed under `AGENTS.md` "Methodology files are pre-registered" are
frozen. Do not edit them as part of an implementation fix. A methodological
correction requires, in order:

1. an explicit decision record,
2. researcher approval,
3. a separate V2 amendment,
4. a `DEVIATIONS.md` entry that identifies the V1 text being superseded, and
5. a new pre-data tag before pilot collection.

### 3.2 Existing local scheduler work

The following local changes predate this document and must be preserved:

- modified `harness/__main__.py`;
- modified `harness/logging/writer.py`;
- modified `harness/runner.py`;
- untracked `docs/COLLECTION_SCHEDULER.md`;
- untracked `harness/scheduler.py`;
- untracked `tests/test_scheduler.py`.

Do not discard, rewrite wholesale, or silently fold unrelated changes into
this work. Scheduler changes require their own reviewable diff.

### 3.3 Separate methodological and implementation commits

Do not mix these categories in one commit or pull request:

- audit/decision documentation;
- V2 methodology;
- collection implementation;
- statistical analysis implementation;
- environment or credential operations;
- data or publication artifacts.

## 4. Critical findings register

### R-001 — H1a decision rule and power target are different tests

**Status:** DECISION ACCEPTED — D-001; analysis implementation pending
**Severity:** pilot blocker; methodology

V1 sizes an alternative corresponding to a 1.5x rate ratio against no
difference, while H1a support requires the 95% interval to clear 1.5x. At a
true ratio exactly equal to the boundary, a two-sided 95% interval clears the
boundary only at the upper-tail error rate, not with 80% power.

**Evidence:**

- `docs/SAP.md`, A1 support rule;
- `docs/SAP.md`, pilot-sizing formula;
- `scripts/size_from_pilot.py`, `n_per_cell_formula()`.

**Acceptance criterion:**

- A V2 decision defines the null, alternative, smallest effect of interest,
  point-estimate requirement, interval requirement, and all
  support/reject/inconclusive states without contradiction.
- Simulation demonstrates the reported operating characteristics under the
  exact proposed decision rule.
- The decision and simulation are reviewed without access to pilot outcomes.

### R-002 — pooled five-environment rate is used as a comparison-arm baseline

**Status:** DECISION ACCEPTED — D-001/D-005; analysis implementation pending
**Severity:** pilot blocker; methodology

`p_hat_pool` is pooled across the environment groups, but the V1 transform
uses it as though it were the Linux baseline when deriving the absolute gap
implied by a Windows/Linux rate ratio. The pooled rate does not identify the
Linux baseline, especially when it also includes WSL, pwsh 7, and macOS.

**Acceptance criterion:**

- The V2 sizing design defines which nuisance rates are estimated under
  blinding and proves that the transform corresponds to the target estimand.
- The blinding procedure reveals no named environment effect to the
  researcher before N is locked.
- Synthetic cases with unequal nuisance-environment rates pass.

### R-003 — clustering implementation does not match the SAP

**Status:** DECISION ACCEPTED — D-005; analysis implementation pending
**Severity:** pilot blocker; methodology and implementation

The SAP describes a blinded intercept-plus-cluster mixed model. The script
computes separate one-way ANOVA ICCs for task and configuration, adds them,
and uses a mean count grouped by `(task_id, config_id)` that omits
environment. This is not the described model and does not directly match the
confirmatory GLMM.

**Acceptance criterion:**

- The V2 power procedure is based on the same hierarchical estimand and
  dependency structure as the confirmatory analysis.
- The simulation code recovers nominal error and target power across
  pre-specified synthetic data-generating processes.
- Cluster definitions and repeated-trial units are stated once and used
  consistently in design, collection, and analysis code.

### R-004 — the optional statsmodels check disagrees with the closed form

**Status:** DECISION ACCEPTED — D-005; cross-check disposition pending implementation
**Severity:** pilot blocker; implementation evidence

For `p=0.30`, `D=1`, the current script reports closed-form `n=147` while its
statsmodels comparison reports approximately `161.9`. The command prints the
disagreement but does not fail. The self-test checks internal reproduction of
the closed form, not agreement with an external oracle or the final analysis.

**Acceptance criterion:**

- The replacement power test has independent numerical checks with explicit
  tolerances.
- A failed cross-check exits nonzero.
- Tests distinguish "formula reproduced" from "design achieves target
  operating characteristics."

### R-005 — no validated raw-pilot to blinded-input transformation

**Status:** IMPLEMENTED — code complete and independently reviewed; real-run custody evidence pending
**Severity:** pilot blocker; implementation

`harness/blinding.py` and `scripts/pilot_blinding.py` now provide a fail-closed
path from a completed, plan-bound pilot root to the only pilot JSON form
accepted by `scripts/size_from_pilot.py`. The implementation enforces:

- either the historical exact 230-cell/460-trial V1 roster or the accepted
  exact 540-cell/720-trial V2 roster;
- exactly five blinded groups;
- the phase-specific complete roster and per-cell target;
- JSON boolean types for `valid` and `failed`;
- exclusion of invalid attempts from reported filtered counts;
- uniqueness and provenance of source trial records;
- terminal-journal hashes for every exported trial; and
- a canonical digest over every bound source artifact.

Before the first attempt, a separate preparation command creates an AES-GCM-
encrypted environment mapping and Ed25519 private key. It binds the public
commitment into the pilot root and emits an identical external commitment for
pre-outcome anchoring. Export requires both copies to match, decrypts custody
without printing it, snapshots every allowed source byte exactly once under
an exclusive lock, and signs the blinded result. It writes no environment
names, named rates, source paths, cell IDs, or trial indices. Sizing requires
the public commitment and Ed25519 signature. Signed V2 rows additionally bind
family, instance, and instance digest. Outcome edits are rejected even when
their public SHA is recomputed.

Acceptance tests cover the complete historical 230-cell/460-trial filesystem
topology; missing, duplicate, foreign, non-boolean, unbalanced, wrong-phase,
and post-terminal outcome-tampered inputs; re-digested export tampering;
source-snapshot stability; encrypted-custody leakage; external-directory CLI
operation; source/output separation; real scheduler refusal before attempt 1;
partial-preparation failure; cross-validator schema parity; and wrong-phase
root poisoning, plus a signed exact 540-cell/720-row V2 round-trip. They pass locally. R-005 remains
below VERIFIED until a custodian procedure and pre-outcome commitment anchor
are accepted and an independent reviewer reconstructs the manifest/signature
chain. The fact that
the current V1 sizing calculation does not use `blinded_group` remains a
separate D-003/R-003 statistical-design issue; this implementation does not
silently resolve it.

**Acceptance criterion:**

- A committed exporter consumes only a plan-bound pilot output root.
- It validates plan digest, trial schema, phase, cell identity, uniqueness,
  validity, and exact roster before producing output.
- It maps environments to sealed labels through an independently generated
  mapping artifact and never writes named rates to researcher-visible output.
- Negative tests cover missing, duplicate, foreign, malformed, unbalanced,
  wrong-phase, and outcome-tampered inputs.
- The blinded output records a digest of every source artifact or a canonical
  manifest digest.

### R-006 — sizing lock and confirmatory plan are not cryptographically bound

**Status:** VERIFIED — implementation and independent counterexample review passed; real-run lock evidence remains a G2 execution artifact
**Severity:** pilot blocker; implementation

Budget arguments and `--output` are optional in the current sizing CLI.
Providing only some budget inputs silently disables the cap. The confirmatory
plan accepts a manually entered N and does not bind itself to the pilot
manifest, blinded-input digest, sizing-lock digest, or V2 analysis version.

`scripts/create_sizing_lock.py` now provides the V2 provenance boundary
without further editing the frozen V1 sizing script. It accepts only the
signed R-005 export and matching commitment, requires every budget input plus
explicit code/analysis versions and exact analysis/simulation artifacts, and
writes one exclusive sizing-lock file. The lock binds the pilot plan, blinded
input bytes, export and source-manifest digests, commitment, sizing-path code
hashes, locked constants/result, resource inputs, analysis artifact, and
simulation configuration under one validated digest. Schema 1.1.0 also
requires an Ed25519 custodian signature from the key committed before pilot
attempt 1. Plan creation and confirmatory execution both require the matching
independently anchored R-005 commitment, so replacing the lock, its key, N,
or its provenance and recomputing public digests is insufficient.

The creator verifies the export, extracts metadata, hashes it, and sizes it
from one immutable byte snapshot. It executes the exact snapshotted
`size_from_pilot.py` bytes recorded in `code_artifacts` and rechecks that the
checkout source did not change before writing the lock. The other three
`code_artifacts` hashes are stable start/end source snapshots, not a claim
that Python's already-running creator or cached imports can self-attest their
initial executed bytes; the externally frozen code version/tag is the trust
root for those modules. It also enforces `n_per_cell <= cap_per_cell`
independently of the sizing result payload.

Confirmatory plan schema 1.2.0 embeds the complete verified lock and derives
N from it. The scheduler no longer exposes a manual primary-N input. Manual
Codex/agy N overrides also fail closed until a separately verified provenance
lock is implemented. Wrong phase, wrong roster count, result/constant/budget
tampering, embedded-lock tampering, and plan digest changes fail before a plan
can authorize trial 1. The first independent no-edit review demonstrated a
re-digested N=999 under cap=6 and a multi-read export TOCTOU despite the prior
green suite. Both paths now have explicit negative tests, along with external
anchor substitution, vendor-N override, and zero-executor-call checks. The
expanded R-005/R-006/scheduler slice passes 84 tests locally, and the complete
suite passes 621 tests with three expected infrastructure-gated skips.
Independent re-review confirms
the original N forgery, anchor substitution, vendor override, and export/source
TOCTOU paths are closed. The residual self-attestation limit above is explicit
and is not treated as an operational blocker.

**Acceptance criterion:**

- Pilot mode requires a new sizing-lock output file and all authoritative
  budget inputs.
- Partial budget arguments fail closed.
- The lock includes source-plan, blinded-input, code-version, constants,
  simulation/configuration, and output digests.
- Confirmatory planning requires the sizing lock and derives N from it rather
  than accepting an unverified manual copy.
- Any digest or phase mismatch fails before trial 1.

### R-007 — local scheduler suite is red

**Status:** VERIFIED — focused scheduler/attempt suite and public CI pass;
stale-schema rejection remains explicit
**Severity:** pilot blocker; implementation

Before the R-007 fix, the local result was:

- tracked suite: 235 passed, 3 infrastructure-gated skips;
- full local suite: 250 passed, 3 skipped, 9 failed.

All nine failures arose because the scheduler test-record helper defaulted to
trial schema `1.1.0`, while the then-current writer and scheduler required
`1.3.0`. The helper now derives the current writer schema (currently `1.4.0`).
Separate tests still use literal stale and foreign versions so fail-closed
schema rejection does not depend on the shared constant.

**Acceptance criterion:**

- The helper derives or explicitly matches the current schema without hiding
  tests that intentionally exercise old-schema rejection.
- The complete local suite passes.
- Public CI passes after the scheduler files are committed.
- A reviewer confirms that the fix did not weaken fail-closed schema checks.

### R-008 — confirmatory analysis is only partially implemented

**Status:** IN PROGRESS — frozen source roster, record reconstruction, and H1 point estimand implemented; interval and A2-A4 pending
**Severity:** confirmatory-data blocker; research integrity

`analysis/v2_analysis_manifest.py` now freezes and verifies the exact trial-
record byte roster, and `analysis/v2_analysis_dataset.py` fails closed on
foreign, duplicated, incomplete, excess, or outcome-contradictory records.
It reconstructs the accepted D-011 evidence and computes the equal-domain,
family, instance, and configuration H1 point estimand. The D-005 interval,
fallback, epoch sensitivity, A2-A4, coder join, FDR, and generated reporting
remain absent; see `docs/V2_ANALYSIS_PIPELINE.md`.

**Acceptance criterion:**

- A frozen analysis dataset builder and A1–A4 implementation exist before
  confirmatory outcomes are inspected.
- Synthetic tests cover positive, null, sparse, zero-event, separated,
  missing-cell, low-compliance, low-IRR, and budget-limited cases.
- Marginal estimands, intervals, resampling units, FDR families, and fallback
  behavior are explicit and tested.
- Tables and figures are produced from code, not hand transcription.

### R-009 — IRR execution path is incomplete and selects the wrong universe

**Status:** IN PROGRESS — manifest-bound selection/provenance and immutable missing-label handling implemented; backends and staged audit pending
**Severity:** H2/H4 blocker; implementation and budget

`scripts/irr_code.py` now consumes only the complete digest-verified V2
analysis-manifest snapshot, selects its valid analysis population, and
requires confirmatory phase for real coding. Each exclusive label artifact
binds the plan/manifest, full trial and attempt identity, exact source bytes,
transcript, blinded coder input, frozen prompt, model pin, observed model, and
request identity. Exact reruns validate and resume existing artifacts;
refusal, malformed output, backend error, and model substitution remain
auditable missing-label states with zero automatic retries and no fallback
rewrite. The command refuses real coding because the two exact different-
lineage backends have not yet been selected, qualified, costed, and wired.
The staged human-anchor sampler and its analysis also remain open.

**Acceptance criterion:**

- Two reproducible, pinned, different-lineage coder backends are implemented
  and costed before collection.
- Input selection is driven by the frozen confirmatory dataset manifest.
- Each coding output binds to the full trial identity and transcript digest,
  not only a filename.
- Retry, refusal, malformed-output, and model-substitution behavior is
  deterministic and auditable.
- The stratified human-anchor sampler and κ/bias analysis are implemented and
  tested before coding begins.

### R-010 — real authenticated E5 collection is unproven

**Status:** VERIFIED — semantically authenticated macOS execution, artifact
custody, credential cleanup, and execution-date policy/account-setting capture
pass
**Severity:** full-matrix feasibility blocker; infrastructure

The credential-free macOS qualification is complemented by corrected private
Actions run `31919774650`, in which the real Claude Code, Codex, and `agy`
subscription routes each completed one manifest-bound C01 call with process
return code zero on an ephemeral `macos-26` runner. A semantic rejection gate
also excluded invalid records, nonzero CLI envelopes, and interactive
authentication fallback. Independent post-download validation matched all
artifact paths, byte counts, and SHA-256 values to the three receipts.
Temporary Actions secrets and hosted artifacts were deleted after verified
private custody and their absence was checked. The 2026-08-15 live first-party
policy/account review confirmed the registered access paths, recorded current
privacy, telemetry, and overage controls, and pinned Antigravity personal-
credit fallback off. The corrected sanitized private review is bound by
SHA-256
`a8f48c67f919d9265a9ee838d0f5789b10b1d71447c36789c83857857bbb246c`.

**Acceptance criterion:**

- A researcher-approved credential design is documented without committing
  or printing reusable credentials.
- Each of the three real CLIs authenticates, exposes the intended model, and
  completes one non-analysis C01 shakedown on the actual pinned runner.
- Artifact collection, redaction boundary, chunked workflow resumption, and
  credential cleanup are verified.
- Current vendor terms and account settings are captured on the execution
  date.

### R-011 — readiness documentation contains stale contradictions

**Status:** IN PROGRESS — active V2 digest/version/count linter added; frozen-methodology reconciliation remains
**Severity:** coordination risk

The audit found:

- README entries that described discharged V1 re-smokes as current
  obligations — corrected by explicit historical/current routing;
- the ignored private `data/operations-log.md` saying the V1 E5 obligation was
  fully discharged and later saying the same re-dispatch was still owed — its
  dated V1 context does not govern V2, but private-record cleanup remains; and
- the frozen SAP's "all four blinded groups" text despite a five-environment
  V2 pilot — still open for the V2 amendment.

**Acceptance criterion:**

- Each operational obligation has one authoritative current status.
- Historical claims remain available in git history or dated records without
  appearing as current instructions.
- A consistency test or linter covers machine-checkable roster, version, and
  count claims across active documents.

The README now routes current work to this document and distinguishes
completed V1 smokes from the separate current V2 gates. The consistency suite
derives the current runtime-matrix and task-bank
digests from executable artifacts and checks their active documentation, plus
the 82-call shakedown digest and 82/82 receipt count. R-011 remains open until
the V2 amendment reconciles frozen V1 wording (including the four-group/five-
environment conflict) and a final active-document review passes.

### R-012 — publication redaction is policy, not yet a tested pipeline

**Status:** OPEN — D-008 closure rule accepted; redaction pipeline pending
**Severity:** publication blocker; privacy

The study intends to publish thousands of logs and coder labels. Transcripts
can contain usernames, absolute paths, git identity, environment
fingerprints, and accidental secrets. Current policy correctly requires
redaction review, but no end-to-end publication-dataset builder and audit
report exists.

**Acceptance criterion:**

- A deterministic publication builder reads the frozen analysis manifest and
  writes to a separate staging root.
- Automated scans cover identity tokens, credentials, local paths, hostnames,
  and configured high-risk patterns.
- Redaction preserves the evidence required for H2/H4 coding or records why
  a field cannot be published.
- A human spot-audit protocol and signed checklist are completed before any
  data push.

### R-013 — collection order may confound cells with time and backend drift

**Status:** IN PROGRESS — accepted order, epoch, cross-host, and incomplete-slot rules are production-bound; D-005 sensitivity and qualified-host evidence pending
**Severity:** pilot blocker; methodology and operations

The V2 scheduler now randomizes and binds valid slots in task-blocked rounds;
collection remains partitioned across hosts.
If collection spans quota resets, vendor routing changes, silent backend
updates, or materially different calendar windows by environment, a shuffled
cell order alone does not guarantee temporal balance. Per-trial timestamps
make drift inspectable but do not remove the confound.

**Acceptance criterion:**

- The collection unit being randomized (trial, batch, or whole cell) is an
  explicit V2 decision.
- Simulated or combinatorial balance checks quantify environment,
  configuration, task class, and phrasing representation over collection
  epochs and host partitions.
- Start/end and periodic model-routing/version checks are specified without
  inspecting outcomes.
- A pre-specified time/epoch sensitivity analysis and backend-drift handling
  rule are implemented before confirmatory collection.
- The schedule manifest records enough information to reproduce intended and
  actual order.

The outcome-blind 720-slot, 72-block order has exact multiset/digest
validation, complete task-block configuration/environment crossings, balanced
host-partition configuration counts, explicit prefix reporting, and zero
adjacent same-cell repetitions. Plan schema 1.3 embeds that exact order and
schedule-identity schema 1.2 carries each slot through collection and analysis.
The accepted contract is recorded in
`docs/D009_EPOCH_CONTRACT.md` and uses four prospectively fixed
180-slot epochs. Each epoch has 18 complete blocks, 36 slots per environment,
The scheduler fixes those boundaries and the independent analysis builder
derives epoch identity from the registered position. The D-005 interval for
the epoch-specific sensitivity remains pending.

### R-014 — timeout-as-failure enforcement and auditability

**Status:** IMPLEMENTED — collection and independent analysis-record reconstruction pass locally; external review pending
**Severity:** pilot blocker; implementation and construct validity

Every frozen task predicate and the SAP state that a valid timed-out or
incomplete run is a binary failure even if partial artifacts satisfy the
checks. Before the R-014 implementation, `harness/runner.py` assigned
`outcome.success` from `evaluate_checks()` alone, so a timed-out agent could
be logged as a valid success after producing the expected final files and
then hanging.

The current implementation centralizes the common rule in
`harness/outcomes.py`. The fields introduced in schema 1.3.0 and retained in
the current 1.6.0 schema separately record:

- the final `outcome.success`;
- the raw `outcome.checks_passed`;
- `outcome.decision_reason` as `timed_out`, `incomplete`, `checks_failed`, or
  `checks_passed`.

The common runner path now applies this rule before writing any agent's
record. Accepted D-011 keeps agy Cwd/transcript eligibility as separate
auditable evidence and uses this same binary result for H1; analysis-builder
validation remains under R-019.

**Acceptance criterion:**

- One canonical outcome-construction function enforces the SAP timeout rule
  before the record is written.
- Tests cover timed-out and otherwise incomplete runs whose checks pass, whose
  checks fail, and whose partial artifacts resemble success.
- The stored outcome includes enough reason/evidence to audit why timeout
  overrode passing checks.
- The frozen analysis builder independently rejects any contradictory legacy
  record with `success=true` and an applicable timeout/incomplete state.

### R-015 — immutable attempt journal and measurement-loss attribution

**Status:** VERIFIED
**Severity:** pilot blocker; implementation and attrition integrity

The current implementation writes an append-only outer attempt journal under
each cell before post-invocation measurement can fail. Attempt-journal schema
1.1.0 records `allocated`, a durably flushed `launch_committed` immediately
before attempting the external exec, and `invocation_observed` only after the
environment returns a process result. Exactly one terminal infrastructure
event or an immutable final trial record plus terminal digest link follows.
The final record binds back to the stable attempt ID and allocated-event
digest.

The runner now catches failures at sandbox setup/teardown, before/after
snapshotting, agy pre/post-processing, adapter invocation, diffing, success
checks, record assembly, and record writing. Attribution distinguishes
pre-invocation infrastructure failure, launch-unknown infrastructure failure
(commit exists but no process result was observed), and post-invocation
infrastructure failure. A path-level mutation-shaped unreadability error
inside the post-agent sandbox, after the clean baseline snapshot passed, is
retained as an agent-induced measurement-loss record: it is valid, its binary
outcome is failure, its checks are explicitly unevaluated, and the incomplete
filesystem evidence is recorded rather than fabricated.

The scheduler derives valid, invalid, unresolved, next-index, and replacement
state from the joined attempt journal and final records without reading
`outcome.success`. A final record whose terminal append failed reconciles from
its attempt binding; a terminal link whose record is absent fails closed.
Torn, unframed, duplicate, competing, foreign, or digest-mismatched events
fail closed. An unresolved durable prefix is reported separately and blocks
automatic retry rather than being guessed into either validity class.

**Acceptance criterion:**

- Every paid/started agent invocation produces exactly one immutable attempt
  record or an append-only outer-attempt record that is deterministically
  reconciled to a final trial record.
- Attribution distinguishes pre-invocation infrastructure failure,
  post-invocation infrastructure failure, and agent-induced measurement loss.
- Fault-injection tests cover each runner stage, including an agent-caused
  unreadable sandbox.
- Scheduler progress and invalid-attempt reporting consume the same
  authoritative attempt ledger without silently retrying an unrecorded call.

### R-016 — trial-record binding to the scheduler plan

**Status:** IMPLEMENTED — independent review and cross-host child dry-runs remain
**Severity:** pilot blocker; provenance

Scheduled child invocations now receive a base64url JSON schedule token whose
SHA-256 binds phase, plan digest, cell/configuration ID, task hash, trial
schema, target valid N, exact trial coordinates, and expected CLI version.
`run_cell()` verifies token integrity, the current task bytes, effective
phrasing, coordinates, schema, and CLI-version expectation before constructing
an environment or agent adapter. Outcome-blind execution refuses to start
without the token.

Attempt-journal schema 1.3.0 carries the same validated schedule identity on
every append-only event. Trial-record schema 1.7.0 carries it on the final
record. The scheduler derives the one expected identity from the immutable
plan and validates both event and trial payloads independently of their paths.
Copied records and validly re-hashed foreign identities therefore fail even
when visible directories and trial fields have been made to match.

**Acceptance criterion:**

- Scheduled execution requires and records phase, plan digest, cell ID, task
  hash, trial-schema version, and target valid N in every attempt.
- The child invocation receives a tamper-evident schedule token and refuses a
  coordinate or task mismatch before the agent starts.
- Output scanning validates the record's schedule section, not only its path.
- Negative tests cover copied records, wrong phase, wrong plan, wrong cell,
  wrong task hash, manually matching paths, and missing schedule identity.

### R-017 — the primary H2/H4 label is undefined across multiple raters

**Status:** IN PROGRESS — D-010 primary/no-rewrite rule enforced in coder artifacts; exact backends, staged audit, and analysis join pending
**Severity:** H2/H4 blocker; methodology

The SAP names Coder 1 “primary” and requires two AI coders plus a human anchor,
but it never states which label enters A2/A4 for each trial or what happens
when coders disagree. Cohen's kappa evaluates reliability; it does not itself
produce the single `is_DE` outcome required by the mixed models. Optional
tiebreaking is explicitly non-load-bearing.

**Acceptance criterion:**

- A pre-data V2 decision defines the primary per-trial label source and every
  disagreement, refusal, malformed-output, missing-label, and adjudication
  branch.
- The rule cannot select a label after seeing which one favors a hypothesis.
- Coder-specific sensitivity estimates and the human-anchor role are
  pre-specified.
- Synthetic disagreement patterns deterministically produce the intended
  analysis population, label, IRR status, and paper language.

### R-018 — the IRR coding contract cannot apply the registered evidence policy

**Status:** DECISION ACCEPTED — D-010; evidence-contract implementation pending
**Severity:** H2/H4 blocker; measurement validity

`scripts/irr_code.py` gives the rater only the task prompt, binary outcome, and
transcript. The frozen prompt does not include the SAP S3 rule distinguishing
canary-confirmed from transcript-evidenced code E, and the coder never sees
filesystem/check/canary evidence. The V1 capability-failure policy described
in `harness/classifier/rubric.py` module documentation is also absent from the
rendered/frozen prompt. The resulting label cannot be assumed to implement
the complete registered measurement rule. The manifest-bound implementation
deliberately preserves and hashes this V1-compatible packet rather than
silently choosing an R-018 evidence contract; it therefore improves
provenance without resolving R-018.

**Acceptance criterion:**

- A V2 decision defines which evidence the blinded coder receives and which
  deterministic post-coder rules join canary/filesystem evidence.
- The frozen prompt or an equally frozen post-processing specification
  contains the capability-failure and code-E policies.
- Coder output records the evidence class needed for H2/H4 reporting without
  exposing prohibited environment labels.
- Golden cases cover A-F boundaries, confident-wrong capability failures,
  attempted-but-blocked destruction, canary-confirmed damage,
  transcript-evidenced-only E, and missing/unwritable canaries.
- Any prompt change is versioned as a pre-data V2 amendment rather than
  silently replacing the V1 frozen prompt.

### R-019 — agy's H1 outcome depends on an undefined “task-completing” action

**Status:** IMPLEMENTED — D-011 runner/writer and independent analysis-builder reconstruction pass locally; external review pending
**Severity:** H1/H3 blocker; methodology and implementation

The SAP requires agy success checks to pass and “at least the task-completing
commands” to run in the sandbox. The log has per-shell-command Cwd tags, but
no deterministic field or task-specific rule identifies task-completing
commands. Some work may be performed through non-shell tools that are not
represented by `CommandRecord`. Before the reviewed D-011 implementation, a
missing brain transcript degraded to zero recovered commands without making a
trace-dependent H1 outcome unmeasurable.

D-011 was accepted on 2026-08-09. Trial schema 1.7.0 now records the shared
observable H1 decision alongside separate agy brain status,
transcript-analysis eligibility, Cwd status, shell-command count, and
sandbox-command count. Missing, malformed, ambiguous, or FIFO-incomplete brain
evidence blocks transcript analysis. It makes an otherwise outcome-determinative
trace-dependent H1 check infrastructure-invalid while leaving timeout/
incomplete failures and independently observable filesystem-only H1 measurable.
The runner calls the
same canonical constructor whose binary result is written to `outcome`, so
the agy evidence section and H1 cannot be independently recreated; the writer
also rejects contradictory nested/top-level H1 evidence. The frozen V2
analysis builder now reconstructs the common outcome from raw completion,
measurement, and check evidence; reconstructs Cwd status/counts from raw tags;
and rejects forged nested or top-level D-011 fields. R-019 remains
IMPLEMENTED rather than VERIFIED pending an independent review of that new
analysis boundary.

**Acceptance criterion:**

- A V2 decision defines a deterministic, task-complete agy outcome using
  observable fields for both shell and non-shell actions.
- Every C01-C05 task and every seeded-error task has positive, noncompliant,
  mixed-Cwd, scratch-only, non-shell, and missing-transcript test cases as
  applicable.
- The rule distinguishes task failure from infrastructure-invalid inability
  to measure compliance.
- A1 and A1d consume one shared implementation and cannot disagree because of
  separately re-created logic.

### R-020 — H4's prompt treatment is compound

**Status:** DECISION ACCEPTED — D-012; analysis/reporting implementation pending
**Severity:** publication-claim blocker; construct validity

The nine registered prompt pairs differ not only in formality or permission
language but also in direct syntax cues, urgency, vocabulary, and specificity.
For example, colloquial variants explicitly mention brace expansion,
heredocs, `chmod`, or `$(date ...)` in several tasks. There is one fixed pair
per task, so a pooled effect does not identify a general causal effect of
“colloquial” or “permission-granting” phrasing.

**Acceptance criterion:**

- A V2 decision either bounds H4 to the exact registered prompt-set contrast
  or introduces a separately justified manipulation design before data.
- Per-task heterogeneity and prompt text are reported alongside any pooled
  estimate.
- Abstract, results, and discussion templates prohibit a generic phrasing
  mechanism claim unsupported by the design.
- Any manipulation check is fixed before outcomes and does not use observed
  D/E rates to redefine the treatment.

### R-021 — prose predicates and executable checks have no equivalence gate

**Status:** IMPLEMENTED — canonical executable authority and fail-closed linter pass locally; independent task-level review pending
**Severity:** pilot blocker; construct validity

Each task YAML contains both a prose-like `binary_success_predicate` and the
`success_checks` actually executed by the runner. Extensive check tests exist,
but no machine-enforced clause-to-check mapping proves that the executable
checks implement every H1 clause while excluding H2-only signals. Comments and
manual review currently carry that burden, making silent drift possible.

V2 now removes that duplicate semantic authority. Every task's
`binary_success_predicate` must exactly declare that the ordered
`success_checks` are the complete H1 predicate, aggregated by logical AND,
with timeout/incomplete overridden to failure by the common outcome rule and
manual H2/H4 rubric coding explicitly excluded from H1. The task-bank linter
reads the live check registry and rejects unknown outcome-changing checks,
predicate-schema additions or substitutions, inconsistent timeout/manual-
rubric roles, missing exact-scope control, and unasserted initial inputs.
Every untouched fixture and all 36 registered oracle completions pass the one
canonical check path locally and on the four currently qualified real
environments. The 217-check executable Q2 matrix now covers all 36 independent
valid alternates and every accepted H1-visible counter-policy. Remaining Q2
work is transcript-level adjudication plus independent task-level construct
review, not prose/executable predicate drift.

**Acceptance criterion:**

- Each task has one canonical executable predicate or a machine-readable map
  from every registered predicate clause to an executable check or explicit
  H2-only exclusion.
- A linter fails on unmapped clauses, extra outcome-changing checks, unknown
  check types, and inconsistent timeout/manual-rubric roles.
- Every task has at least one known-positive fixture plus plausible no-op,
  superficially-correct, destructive, and environment-specific
  counterexamples.
- An independent task-level review records what the predicate measures and
  what it does not measure.

### R-022 — capability-task construct coverage and ceiling response are undefined

**Status:** PARTIAL — accepted slate and all 36 candidate fixtures are implemented; cross-host/human/Q3 qualification pending
**Severity:** pilot blocker; construct validity and methodology

The five H1a capability tasks are purposively selected probes, not a random,
domain-stratified, or externally validated sample of routine coding-agent
work. Two concentrate on filesystem behavior, two on structured-data
transformation, and one on code refactoring. Several major environment-
mediated workflow domains are absent, and some current tasks can be completed
through cross-platform Python or direct editing tools with little exposure to
the nominal shell context.

D4 also records that capability tasks were hardened after C01 proved easy in
a smoke trial, partly to avoid a zero failure denominator. That is legitimate
difficulty calibration but does not establish that the equal-weighted bank
measures a coherent broader construct. V1 specifies a ratio-unestimable branch
when a context has zero failures, but it has no pre-data rule distinguishing a
valid all-success finite-roster result from an instrument whose task coverage
is too narrow to support the intended decision.

**Acceptance criterion:**

- A V2 decision defines the target task construct and whether the estimand is
  limited to the exact probe roster or a justified wider task population.
- A task-to-domain content map and pre-data inclusion rules show what is and
  is not sampled; domains with one item are either expanded or explicitly
  excluded from broad generalization.
- Platform-neutral oracle and deliberately context-dependent counter-policy
  checks demonstrate sensitivity without using focal confirmatory outcomes.
- A blinded ceiling/floor gate defines zero- and insufficient-event branches,
  including when task development requires a new amendment and fresh pilot.
- Operating-characteristic simulations compare task breadth, repeated trials,
  sparse events, and the full resource envelope.
- Paper decision language distinguishes broad, domain-specific,
  fixture-specific, bounded-roster, inconclusive, and instrument-invalid
  results.

## 5. Workstreams

| ID | Workstream | Current state | Exit condition |
|---|---|---|---|
| W1 | V2 statistical amendment | IN PROGRESS — evidence drafts in `docs/V2_STATISTICAL_DECISION_MEMO.md` and `docs/D005_FINITE_ROSTER_IRR_MEMO.md`; trace in `docs/HYPOTHESIS_TRACEABILITY_MATRIX.md` | R-001 through R-004 and R-017 through R-020 resolved; new pre-data tag cut |
| W2 | Pilot blinding and sizing provenance | IN PROGRESS — R-005 is code-complete and independently reviewed but still needs accepted real-run custody/anchor/reconstruction evidence; R-006's signed immutable sizing lock and sizing-lock-derived confirmatory plan passed independent counterexample review | R-005, R-006, and R-016 VERIFIED |
| W3 | Collection scheduler and trial integrity | IN PROGRESS — R-016 plan/runtime/slot binding is implemented with hashed child tokens and record/event validation; epoch/drift rules, independent review, and authenticated cross-host child smokes remain | R-007 and R-013 through R-016 VERIFIED plus cross-host dry runs |
| W4 | Outcome and confirmatory analysis implementation | IN PROGRESS — exact source manifest, fail-closed dataset reconstruction, D-011 cross-checks, finite-roster H1 point estimand, Clopper-Pearson-MOVER candidate, and exact sparse fallback implemented; full D-005 recovery/acceptance, epoch sensitivity, and A2-A4 remain | R-008, R-014, R-019, and R-021 VERIFIED |
| W5 | IRR and human-anchor pipeline | IN PROGRESS — D-010 fixes frozen Coder 1 as primary with no adjudication rewrite; manifest-bound input selection, exact label provenance, immutable resume, and fail-closed missing-label states are implemented. Matched-N, probability-audit, exact finite-population, and joint resource/inference evidence show that the anchor is sparse, plug-in audit intervals fail, B=600-700 is the relevant N=24 review region, and claim scope determines whether H2 is moderately informative or broadly inconclusive. Exact backends, evidence packet, staged sampler/threshold/cap, human workflow, and analysis join remain open. | R-009, R-017, and R-018 VERIFIED |
| W6 | Five-environment collection qualification | IN PROGRESS — R-010 VERIFIED: exact zero-quota preflight and portable oracles pass in all five environments; a semantic 82/82 audit now requires process return code zero and rejects pre-model authentication failures; corrected macOS, WSL2, Linux-native, and Windows resource evidence passes; the agy day-one freeze and final D-004/D-006 caps remain | R-010 plus all collection-start checks VERIFIED |
| W7 | Documentation consistency | IN PROGRESS — historical V1/current V2 routing repaired and executable V2 digest/version/count checks added; frozen-methodology reconciliation remains | R-011 VERIFIED |
| W8 | Publication and redaction | OPEN | R-012 VERIFIED |
| W9 | Paper and release | OPEN | preprint, archival release, data/code package, and deviation report published |
| W10 | Capability-task construct validation | IN PROGRESS — all 36 candidate instances, current-bank five-host portable oracles, the 217-check executable Q2 matrix, structural validator, instance/slot-bound V2 pilot plan/export, production blocked order/epoch contract, and H1 reconstruction are implemented; Q0/Q2/Q4 remain PARTIAL | fresh-human Q1 evidence, Q2 transcript adjudication, blinded Q3, interval recovery, final Q4 freeze, and R-022 VERIFIED before pilot |

Workstreams may proceed in parallel only when they do not depend on an open
methodological decision. Implementation must not silently decide W1.

## 6. Decision register

The researcher accepted the V2 direction on 2026-08-09. `V2_ACCEPTED_DECISIONS.md`
records the choices, rejected paths, rationale, and consequences. `PARAMETER
OPEN` means the scientific direction is accepted but an exact value or
backend still depends on named pre-data evidence; it is not permission for an
agent to choose that parameter silently.

| ID | Decision | Status | Required evidence |
|---|---|---|---|
| D-001 | H1a support/reject/inconclusive rule | ACCEPTED — five-point finite-roster RD classification | Final D-005 interval recovery and coverage |
| D-002 | H2 threshold rule and whether it is separately powered | ACCEPTED — exploratory, no threshold support/reject claim | Measurement implementation and audited uncertainty |
| D-003 | hierarchical power model and nuisance-parameter re-estimation | ACCEPTED — prospective fixed N; pilot validates instrument/nuisance envelope only | Exact N after D-005/D-013 and resource evidence |
| D-004 | maximum N and per-vendor resource envelope | PARAMETER OPEN — 60/10/30 envelope accepted; authenticated agent-under-test timing/meter evidence complete | Human timing sample, coder shakedown, and final numeric provider/calendar caps |
| D-005 | confirmatory model and inference library | ACCEPTED DIRECTION — Family B finite-roster primary; broad models are sensitivities | Synthetic recovery, coverage, exact interval/resampling/fallback |
| D-006 | IRR invocation surface and budget | ACCEPTED DIRECTION — staged probability audit; no automatic 600–700-label obligation | Reproducible backends, measured cost, staged sampler and routine cap |
| D-007 | E5 credential and execution architecture | QUALIFIED — authenticated ephemeral path, custody, cleanup, and execution-date controls pass; keep E5 closed through final G4 review | Day-one agy freeze and final collection release |
| D-008 | exact public artifact and redaction policy | ACCEPTED — publication stays closed until tested builder/audit | Sample publication build and artifact inventory |
| D-009 | collection randomization unit, runtime roster, and temporal-drift controls | ACCEPTED — blocked rounds, four fixed 180-slot epochs, global host order, fail-closed incomplete roster, role-preserving refresh, same-model S6 | D-005 epoch-sensitivity interval, host qualification, and final matrix digest |
| D-010 | primary H2/H4 label, disagreement, and adjudication rule | ACCEPTED DIRECTION — frozen Coder 1 primary; Coder 2/human are sampled audit only; no result-favoring replacement | Staged trigger/cap/interval, backend identities, error sensitivities |
| D-011 | deterministic agy H1/A1d Cwd outcome construction | ACCEPTED — runner implemented and independently challenged | Analysis-builder wiring and dataset reconstruction |
| D-012 | H4 exact-prompt-set versus generic phrasing claim | ACCEPTED — exact prompt-set exploratory contrast only | Coding/analysis and reporting-template enforcement |
| D-013 | H1a capability-task population, coverage, and ceiling-response rule | ACCEPTED — 12-family design slate, six domains, split N, symmetric pilot gate | Pass remaining Q1-Q4 evidence and freeze final simulations/artifacts |

Each accepted decision must record:

- options considered;
- evidence;
- selected option and rationale;
- rejected options;
- consequences for V1 text;
- implementation work items;
- approval date.

## 7. Readiness gates

No later gate can override an earlier open gate.

### G0 — shared-state adoption

- [x] Researcher reviews and accepts this remediation structure.
- [x] Future agents have a reliable entrypoint pointing to this document.
- [x] Existing scheduler work is assigned to W3 without being overwritten.

### G1 — V2 methodology frozen

- [ ] D-001 through D-005 and D-009 through D-013 accepted.
- [ ] R-001 through R-004 and R-017 through R-020 plus R-022 resolved.
- [ ] V2 amendment and deviation entry reviewed.
- [ ] Runtime-pinning rule accepted and one V2 matrix digest frozen.
- [ ] New public pre-data tag cut.

### G2 — analysis and adaptive pipeline frozen

- [ ] R-005, R-006, R-008, R-009, R-017, R-018, R-019, and R-021
  VERIFIED.
- [ ] Synthetic end-to-end analysis produces expected decisions.
- [ ] Analysis and sizing code versions are included in immutable manifests.

### G3 — collection implementation green

- [x] R-007 VERIFIED.
- [ ] R-013 VERIFIED.
- [ ] R-014, R-015, and R-016 VERIFIED.
- [ ] Outcome-blind dry runs pass on every host partition.
- [ ] Plan/output/phase/schema/version failures fail closed.
- [ ] Accepted V2 scheduler and shakedown artifacts bind the frozen runtime-matrix digest.

### G4 — real environment qualification

- [x] R-010 VERIFIED.
- [x] Exact Claude Code and Codex versions installed on collection hosts.
- [ ] `agy` day-one manifest/hash/archive/re-smoke/updater block complete.
- [x] All model labels and account paths verified.
- [x] Current policy, privacy, telemetry, and overage settings recorded.
- [x] Per-agent C01 shakedowns pass on the actual collection paths.
- [ ] Inter-trial delays and resource envelope locked under D-004.

**The blinded pilot may begin only after G0–G4 are complete.**

### G5 — blinded pilot complete

- [ ] Exactly 460 valid plan-bound pilot trials collected.
- [ ] Invalid attempts preserved and reported.
- [ ] Named outcomes remain uninspected.
- [ ] Blinded export passes all R-005 acceptance tests.

### G6 — confirmatory N locked

- [ ] Sizing lock produced under the tagged V2 procedure.
- [ ] Independent digest and numerical verification pass.
- [ ] Confirmatory manifest derives from and binds to the sizing lock.
- [ ] Environment mapping unsealed only after the lock is immutable.

### G7 — confirmatory collection complete

- [ ] Every cell is complete or explicitly plan-limit-bound.
- [ ] Cross-host merge verification passes.
- [ ] Version/routing/invalid/deviation reports complete.
- [ ] Frozen analysis manifest created without inspecting inferential output.

### G8 — analysis and IRR complete

- [ ] Dual AI coding complete.
- [ ] Human anchor complete.
- [ ] IRR decision applied.
- [ ] Frozen A1–A4 pipeline executed.
- [ ] All pre-registered branches and sensitivity analyses reported.

### G9 — publication complete

- [ ] R-012 VERIFIED.
- [ ] Paper reviewed against the V1 tag, V2 tag, and deviations.
- [ ] Reproducibility package passes from a clean checkout.
- [ ] Preprint and archival release/DOI published.

## 8. Agent work and handoff protocol

### Before work

An agent must state:

- the work item or decision ID;
- the affected H1-H4 trace row or shared evidence-chain link, when applicable;
- whether the task is methodology, implementation, infrastructure, analysis,
  or publication;
- files expected to change;
- acceptance tests it intends to run;
- whether any frozen file is implicated.

If the task would make an unapproved methodological choice, stop and prepare a
decision memo instead.

### During work

- Keep one primary work item per diff.
- Do not use a passing unit test as evidence for an unstated scientific
  assumption.
- Add negative and adversarial tests for every fail-closed boundary.
- Preserve invalid records and provenance.
- Do not inspect outcomes when working on blinded-pilot sizing.
- Update this document in the same review unit when a work-item status
  changes.

### Review

A reviewer must:

1. read the cited methodology rather than only the implementation diff;
2. restate the estimand or invariant being protected;
3. run or inspect the exact acceptance evidence;
4. attempt at least one plausible counterexample;
5. distinguish code correctness from research-design correctness;
6. record remaining uncertainty instead of issuing a global "looks good."

Self-tests authored by the same implementation are necessary but not
independent evidence. At least one acceptance check for a load-bearing
statistical component must use an independent implementation, analytic
oracle, or simulation with known truth.

### Handoff template

Every unfinished work session should leave:

```text
Work item:
Status:
Goal/invariant:
Files changed:
Evidence run:
What passed:
What failed:
Decisions made:
Decisions still open:
Known risks/counterexamples:
Exact next action:
Do not touch:
```

Do not claim the repository or study is globally ready in a handoff. Report
gate and work-item statuses.

## 9. Immediate sequence

1. Use `docs/HYPOTHESIS_TRACEABILITY_MATRIX.md` as the claim-to-evidence
   checklist for every H1-H4 work item.
2. Review and accept/revise the D-001 through D-013 recommendations assembled
   in `docs/V2_DECISION_PACKAGE.md`; the package is outcome-blind and remains
   a researcher-decision draft.
3. In parallel only where methodology-independent, repair and review the
   scheduler under W3.
4. Investigate D-007 with a real, non-analysis E5 authentication shakedown
   design before assuming the full matrix is executable.
5. Implement analysis and adaptive-pipeline code against synthetic data.
6. Cut the V2 pre-data tag only after methodology and implementation agree.

## 10. Evidence log

### 2026-07-28 — G0 shared-state adoption

- The researcher accepted the remediation structure and explicitly authorized
  edits to the protected agent entrypoints.
- `AGENTS.md` and `CLAUDE.md` now require agents to read this document before
  methodology, analysis, collection, scheduler, or publication work.
- Existing local scheduler work remains preserved and assigned to W3.
- G0 is satisfied. Collection remains blocked at G1-G4.

### 2026-07-28 — initial independent audit

- Verified local `main` and `origin/main` both at `9eb12e5`.
- Verified `pre-registration-v1` resolves to tagged commit `34104be`.
- Verified no pilot or confirmatory dataset exists locally.
- Verified GitHub PRs #1–#7 merged and current public Actions checks green.
- Ran tracked tests: 235 passed, 3 skipped.
- Ran full local tests including scheduler work: 250 passed, 3 skipped,
  9 failed.
- Ran sizing self-test and frozen IRR-prompt check: both passed their internal
  checks.
- Ran the sizing script's statsmodels comparison at `p=0.30`, `D=1`:
  closed form 147 versus statsmodels approximately 161.9.
- Inspected current local tool versions and collection-start checklist.
- Inspected current official subscription-policy pages; no collection was
  initiated.

This evidence establishes the initial state only. It does not satisfy any
future gate whose acceptance criterion requires new implementation or an
approved methodological decision.

### 2026-07-28 — remediation structure and statistical decision framing

- Created this shared findings, decisions, workstreams, gates, and handoff
  register.
- Created `docs/V2_STATISTICAL_DECISION_MEMO.md` as an evidence draft for
  D-001 through D-005.
- No V2 option has been approved and no frozen V1 methodology has been
  changed.

### 2026-07-28 — H1-H4 claim-to-evidence trace

- Created `docs/HYPOTHESIS_TRACEABILITY_MATRIX.md`.
- Traced every registered claim through population, raw fields, outcome
  construction, analysis, decision, and bounded paper language.
- Added R-014 through R-021 and D-010 through D-012 for newly exposed gaps.
- The trace exposed the then-current counterexample that a timed-out run
  could retain `outcome.success=true` when its checks passed.
- No substantive option has been selected and no frozen V1 file has been
  changed.

### 2026-07-28 — R-014 collection-side implementation

- Added one canonical binary-outcome constructor with explicit precedence:
  timeout, incomplete, failed checks, then passed checks.
- The runner now applies that constructor, and schema 1.3.0 records both the
  final outcome and the raw check result plus its decision reason.
- The writer independently reconstructs the outcome from the check vector and
  process evidence. It rejects a forged outcome and a completion flag that is
  inconsistent with `timed_out` and `returncode`.
- An independent falsification review found that the first draft trusted
  independently forgeable writer arguments and used a mocked passing check.
  Both were replaced before acceptance: the writer now accepts and validates
  one `BinaryOutcome`, and the integration test creates a real artifact and
  runs the real `file_exists` evaluator.
- The independent reviewer then re-inspected the revised shared tree and
  accepted the R-014 collection-side implementation. The reviewer made no
  edits.
- Focused evidence: 17 tests passed, including the eight-case Boolean truth
  table, timeout/incomplete runs with a success-like artifact, writer-boundary
  counterexamples, and all 14 frozen task timeout policies.
- Regression evidence excluding the separate scheduler work: 252 passed,
  3 skipped.
- Full local evidence: 267 passed, 3 skipped, 9 failed. Every failure stops at
  the already documented R-007 scheduler-test fixture mismatch: the fixture
  emits schema 1.1.0 while a newly built plan requires schema 1.3.0.
- No schema-bound collection-plan JSON was present locally. Any plan generated
  under schema 1.2.0 must be regenerated rather than edited.
- R-014 remains IMPLEMENTED, not VERIFIED, because the frozen analysis builder
  must still reject contradictory legacy records independently under W4.
- No frozen V1 methodology file was changed and no benchmark trial was run.

### 2026-07-28 — R-007 local scheduler-suite repair

- Changed only the scheduler test-record helper and its negative coverage:
  ordinary fixtures derive the current writer schema, while explicit literal
  `1.1.0` and `9.9.9` records must still be rejected.
- Scheduler evidence: 25 tests passed.
- Full local evidence: 277 passed, 3 infrastructure-gated skips.
- An independent no-edit review confirmed that production enforcement remains
  fail-closed at both plan loading and record scanning, and that the literal
  negative tests prevent the shared test constant from becoming circular.
- R-007 remains IMPLEMENTED rather than VERIFIED until the scheduler files are
  committed and public CI passes.
- The synthetic helper is intentionally only a scheduler input fixture; it
  does not establish full trial-record validity, which remains under R-016.
- No frozen V1 methodology file was changed and no benchmark trial was run.

### 2026-07-28 — R-015 immutable attempt preservation

- Added append-only attempt-journal schema 1.1.0. Each allocated attempt has a
  stable ID and allocated-event digest; a durably flushed `launch_committed`
  event precedes the external exec, and `invocation_observed` is written only
  after the environment returns a process result.
- Trial-record schema 1.4.0 binds every final record to that attempt identity.
  The scheduler reconciles the journal and trial records without inspecting
  outcomes, accepts the recoverable final-record/terminal-append crash window,
  and fails closed on unresolved, torn, duplicate, competing, foreign, or
  digest-mismatched evidence.
- Failure attribution now separates pre-invocation infrastructure,
  launch-unknown infrastructure, post-invocation infrastructure, and
  agent-induced measurement loss. Agent-induced loss is retained as a valid
  binary failure with checks explicitly unevaluated and incomplete evidence
  recorded rather than fabricated.
- Fault injection covers every runner stage, including write-ahead-log and
  final-record failures, actual adapter pre-spawn and transport failures,
  agent-caused unreadability, and unreadability followed by teardown failure.
- Remote WSL/SSH agent execution now uses random start/exit markers inside one
  base64-encoded remote script. A timeout is agent data only after the start
  marker proves execution reached the agent; transport ambiguity otherwise
  remains infrastructure failure. Real WSL execution verified both the
  successful-command and timeout paths.
- Independent no-edit falsification found and drove fixes for teardown
  reclassification, silent Linux sync loss, SSH return-code 255 ambiguity,
  pre-spawn attribution, unproved remote timeouts, byte-output marker parsing,
  and real WSL transport-shell reparsing. The reviewer re-inspected the final
  tree and accepted the exact R-015 criterion.
- Focused acceptance evidence: 88 passed, 2 live-infrastructure skips. Full
  local evidence: 316 passed, 3 infrastructure-gated skips. Python compilation
  and `git diff --check` passed.
- Residual non-blocking risks are explicit: file `fsync` plus exclusive
  creation has not been power-loss tested for directory-entry durability;
  mutation-shaped local/WSL errors use the registered temporal-isolation
  inference for agent attribution; and authenticated live Linux SSH
  qualification remains under R-010/G4.
- R-015 is VERIFIED. No frozen V1 methodology file was changed and no
  benchmark trial was run.

### 2026-07-30 — D-001 null-interpretability candidate and simulation smoke

- Added D-001 Option D, a finite-roster risk-difference candidate with
  decision-relevant, bounded-small, and inconclusive interval states.
- Added an outcome-independent interpretability firewall: only
  pre-specified measurement-integrity gate failures can demote a result to
  uninterpretable; an imprecise valid result remains inconclusive and a
  precise interval below the threshold remains an informative bounded-small
  result on the registered roster.
- Added `analysis/d001_operating_characteristics.py` as an outcome-blind
  reference scaffold comparing D-001 Options A, B, and D on the exact
  5-task × 7-configuration × 2-context H1a roster.
- Focused evidence: 9 tests passed, including an independent homogeneous
  binomial RMSE oracle, threshold-boundary behavior, a low-event
  risk-ratio counterexample, a zero-observation case that prevents a
  degenerate zero-width risk-difference interval, and seed reproducibility.
- A 20,000-replicate smoke grid showed that the N=6 floor does not guarantee
  either an informative five-point null or adequate power, and that both
  depend materially on the baseline failure rate. It also showed that
  Option B's point-estimate magnitude condition can return support when the
  true risk ratio is below 1.5.
- Exact commands, scenario results, limitations, and next simulations are
  recorded in `docs/V2_STATISTICAL_DECISION_MEMO.md`.
- D-001 and R-001 remain OPEN. No option or `delta_RD` was approved, no
  frozen V1 methodology file changed, and no benchmark trial was run.

### 2026-08-01 — R-022 capability-task construct and ceiling audit

- Audited C01-C05 against their documented selection rationale, dominant
  capabilities, direct environment surfaces, and cross-platform route-around
  paths.
- Created `docs/TASK_CONSTRUCT_AUDIT.md`. It distinguishes statistical
  zero-event risk from task-population construct validity and explains why
  all-success data can bound a finite-roster risk difference without proving
  broad task coverage.
- Conditional calculations show that the 100-trial capability subset of the
  blinded pilot has a 60.6% chance of observing zero failures if the true
  average failure probability is 0.5%, and 36.6% at a 1.0% failure
  probability. These are sensitivity calculations, not predictions.
- Added R-022, D-013, and W10 so task-bank coverage and the ceiling-response
  rule must be decided before V2 methodology is frozen.
- The audit recommends comparing a narrowly claimed five-probe design with a
  domain-stratified bank using multiple independent task families. It does
  not select domains, tasks, a minimum-event threshold, or a bank size.
- R-022 and D-013 remain OPEN. No frozen task or methodology file changed and
  no benchmark trial was run.

### 2026-08-01 — D-013 external evidence and matrix-cost comparison

- Created `docs/TASK_BANK_DESIGN_OPTIONS.md` after comparing the local bank
  with primary documentation for SWE-bench, SWE-bench Verified, HCAST,
  Terminal-Bench 2, and TheAgentCompany.
- Replaced the draft one-axis taxonomy with six content domains plus recurring
  cross-cutting demands. The current bank covers three candidate content
  domains; only filesystem/artifacts and data/config/text have two families.
- Costed a 12-family candidate that retains C01-C05 and adds seven independent
  families. At a common N it adds 30.4% to confirmatory trials and grader
  calls. A split-N candidate is within 4.3% of current confirmatory cost at the
  N=6 floor and equal at N=12 or N=24, before pilot and development costs.
- Recorded why that arithmetic is not a power result: task-family breadth,
  nested instances, event sparsity, and domain-concentrated effects must be
  evaluated under D-001 through D-005 before D-013 can choose an option. The
  split-N candidate also changes H1b's all-task composition and H2's
  task-class weighting and failed-trial denominator even when seeded-task N
  is preserved.
- Independent review found no blocking or arithmetic error. It required the
  draft to expose the H1b/H2 scope and to specify a candidate instance-
  weighting and counterbalancing invariant across all 35 configuration-by-
  environment cells; those rules remain unapproved D-013 inputs.
- Added a pre-data family-validation package: semantic equivalence, oracles,
  counter-policies, fresh-human completion, repeated agent attempts with
  transcript review, grader validation, and frozen instance assignment.
- D-013 and R-022 remain OPEN. The six domains and two-family minimum are
  candidate scaffolds, not validated population weights. No frozen task,
  methodology, threshold, or schedule changed and no benchmark trial ran.

### 2026-08-01 — D-013 candidate family-qualification and instance assignment

- Created `docs/TASK_FAMILY_QUALIFICATION.md` with candidate Q0-Q4 admission
  gates for construct fit, cross-context equivalence, outcome validity,
  difficulty calibration, and freeze/auditability.
- Provisionally audited C01-C05. Every family remains PARTIAL: executable V1
  fixtures and unit tests do not substitute for a complete V2 construct,
  fresh-human, counter-policy, transcript-review, and ceiling-calibration
  record.
- Created outcome-blind evidence code in
  `analysis/d013_task_bank_design.py`. It deterministically rotates frozen
  instances, matches each valid slot across all five environments,
  counterbalances remainder slots over configurations, and equal-weights
  instances within each family cell.
- Bound instance identity to the target valid-trial slot rather than the raw
  attempt index. An infrastructure-invalid replacement must retry the same
  slot and instance; a valid agent-caused failure consumes the slot.
- Added 21 focused tests covering N=3/5/10 balance, cross-environment matching,
  equal instance weights, caller-order invariance, fixed fixtures, and
  fail-closed invalid schedules, exact 7-by-5 roster agreement, and isolation
  from the frozen scheduler.
- Independent algorithm review confirmed the matching, weighting, and
  N=3/5/10 balance calculations. It required explicit boundaries: the hash is
  not inferential randomization; execution-order controls remain D-009; the
  analysis must preserve matched-slot dependence; and an exhausted retry cap
  cannot silently drop or reweight missing valid slots.
- The prototype is not imported by `harness/scheduler.py`, no frozen roster or
  task changed, no admission threshold was approved, and D-013/R-022 remain
  OPEN.

### 2026-08-01 — D-013 ceiling, construct-mismatch, and H2 reference grid

- Created `analysis/d013_ceiling_operating_characteristics.py` and
  `docs/D013_CEILING_SIMULATION_MEMO.md`. The outcome-blind grid uses 20,000
  replicates per scenario and seed `20260801`; maximum probability MCSE is
  approximately 0.35 percentage points.
- Compared three symmetric blinded gates on the 720-valid-trial full-instance
  pilot. The five-event/two-family rule is the leading candidate: the
  one-event rule is too permissive, while hard cross-domain spread can route
  genuine domain-concentrated signal to redevelopment.
- Added exact six-domain construct counterexamples. A true five-point target
  effect is zero on the current synthetic roster when confined to an omitted
  domain, and twelve points when confined to the domain the current roster
  overweights. Repeated trials cannot repair that mismatch.
- Compared current-five, broad common-N, and broad split-N precision. Split N
  has roughly current sampling error at approximately current full-matrix
  cost while targeting the six-domain average; common N is more precise and
  costs 30.4% more.
- Added an optimistic H2 pooled-reference grid. For a true 3x conditional D/E
  ratio under moderate failure rates, broad split-N reference support is
  approximately 16%, 36%, and 66% at base N=6, 12, and 24. Clustering, IRR,
  adjudication, and convergence can only make this reference incomplete.
- Added 13 focused calibration, counterexample, cost-identity,
  reproducibility, and fail-closed tests. Exact D-005/IRR simulations remain
  required before D-001 through D-003 or D-013 can close.
- Independent review found no blocking simulation defect and required three
  clarifications: equal-domain mismatch values are conditional on a candidate
  estimand; G2 is only a coarse development gate; and the 720-trial pilot is
  360 one-slot-per-instance capability trials plus 360 two-repetition seeded
  trials. The output now records all four pilot-count invariants explicitly.
- No gate, bank, threshold, N, task, scheduler, or collection plan was
  approved or changed. D-013 and R-022 remain OPEN.

### 2026-08-01 — D-005 finite-roster and H2 measurement audit

- Added `analysis/d005_finite_roster_irr.py` and
  `docs/D005_FINITE_ROSTER_IRR_MEMO.md`. The outcome-blind audit uses the exact
  candidate 12-family × 3-instance × 7-configuration schedule and 5,000
  replicates per reported scenario at seed `20260801`.
- The ordinary within-instance variance estimator fails closed at the
  base-N=6 and base-N=12 split designs because at least one instance has only
  one observation. When estimable, it substantially undercovers near-zero
  outcomes at smaller N. The Jeffreys-stabilized analytic comparator is
  computable but conservative and frequently inconclusive.
- Under a diffuse 10% null, the stabilized split-N comparator bounds the H1
  risk difference below five points in approximately 16%, 35%, and 84% of
  simulations at base N=6, 12, and 24. A valid point null is therefore not
  automatically an informative null at the smaller candidate sizes.
- Added a six-category IRR simulation using the registered 50-case minimum
  stratified
  human floor and hard κ demotion. In a shared D/E-to-C bias scenario, high
  AI-AI agreement is usually caught by the human threshold. In a rare-D/E
  scenario, however, the registered omnibus gate passes 100% while modest
  false positives materially attenuate H2's ratio. The low binary κ in this
  scenario is itself prevalence-sensitive and is diagnostic, not a proposed
  replacement gate; class-specific error and effect-scale bias remain open.
- Added an explicitly approximate H2 measurement-error overlay. Even under
  high-quality nondifferential raters, a latent 3x D/E ratio has optimistic
  pooled-reference support of only about 9% and 35% at broad split base N=6
  and N=24. A no-support H2 result is not substantively interpretable under
  these scenarios.
- Added 13 focused tests for exact schedule counts, seed reproducibility,
  singleton fail-closed behavior, oracle coverage, zero/complete-event
  diagnostics, a heterogeneous unequal-count variance oracle, analytic κ
  checks, fail-closed invalid labels, shared bias, the rare-D/E
  counterexample, and approximation labeling.
- Review-driven correction removed an unnecessary H2 restriction that treated
  all-D/E failed samples as ratio-unestimable and added a regression test.
  Directly affected evidence is 27 passed; full local evidence is 373 passed
  with 3 infrastructure-gated skips. Compilation, CLI serialization, and
  `git diff --check` pass.
- The intended R GLMM packages are unavailable in the current environment;
  no substitute was mislabeled as Family A. D-001, D-002, D-003, D-005,
  D-010, and D-013 remain OPEN. No benchmark trial ran and no frozen V1
  methodology, task, scheduler, or label rule changed.

### 2026-08-01 — D-010 matched-N joint H2 measurement audit

- Added `analysis/d010_joint_h2_measurement.py` and
  `docs/D010_JOINT_H2_MEASUREMENT_MEMO.md`. The simulation jointly generates
  failures, latent A-F codes, two full-sample AI labels, the human anchor,
  κ/demotion, candidate primary labels, and the pooled H2 reference on the
  candidate 5,040/9,660/19,320 broad split matrices. The manifest preserves
  the exact candidate family, three-instance, valid-slot, nine-task,
  two-phrasing, configuration, and cross-environment matching structure.
- Replaced the earlier equal-five-per-stratum anchor abstraction with the
  registered full-matrix sampler: four unique transcripts from every one of
  ten environment-by-task-class strata plus ten unique draws from the
  remaining population, exactly proportional to stratum trial count.
- Independent review caught an invalid success=A/B assumption. The corrected
  generator permits successful A-E, forbids only successful F, and reports
  successful D/E separately from the failed D/E class that defines H2. Its
  default success mixture and a no-success-D/E sensitivity are explicitly
  synthetic.
- The 50-case minimum-size anchor averages about 4.8-5.0 failed and 0.71-1.11
  failed D/E transcripts. It contains no failed D/E in roughly 33-50% of
  simulations, depending on the latent H2 scenario, so it cannot validate
  H2-class error unaided even when it serves its overall-A-F agreement purpose.
- In a shared D/E-to-C scenario, the gate passes 97.8-98.8% despite only about
  15% failed-D/E sensitivity. Removing successful D/E raises gate passage to
  99.3-99.6%, so the counterexample does not depend on the default success
  mixture. Disagreement-only adjudication cannot repair agreed wrong labels.
- Under favorable independent rater errors and a latent 3x D/E effect at base
  N=24, joint support is about 20.2% for Coder 1, 63.1% for consensus plus a
  hypothetical 98%-accurate adjudicator, 59.3% for H2-only AI intersection,
  and 3.4% for H2-only AI union. The label rule is inferentially load-bearing.
- Corrected favorable adjudication burdens are approximately 628, 1,205, and
  2,410; the calibrated near-kappa case requires approximately 1,105, 2,119,
  and 4,239. The backend, independence, budget, and exception contract do not
  exist.
- Added focused tests for exact manifest identities and costs, exact anchor
  allocation and proportionality, successful C/D/E, outcome-constrained
  errors, shared-map validation, primary-label resolution, a hand-calculated
  pooled-H2 interval oracle, null-boundary classification, reproducibility,
  κ-case exclusivity, effect attenuation, and fail-closed inputs. Independent
  review reproduced the corrected grid; final verification counts are
  16 focused D-010 tests, 64 affected simulation tests, and 389 full-suite
  passes with 3 infrastructure-gated skips. Compilation and CLI JSON
  serialization also pass.
- D-002, D-005, D-006, D-010, and D-013 remain OPEN. No benchmark trial ran
  and no frozen V1 methodology, task, rubric prompt, scheduler, or collection
  rule changed.

### 2026-08-01 — D-010 probability-sampled H2 audit allocation

- Added `analysis/d010_enriched_audit.py`,
  `tests/test_d010_enriched_audit.py`, and
  `docs/D010_ENRICHED_AUDIT_MEMO.md`. The registered minimum-size (50-case)
  full-matrix anchor instantiation remains separate; candidate focal-failure
  audits use conditional known-probability sampling and are conservatively
  costed as 50 plus the realized audit size without overlap deduplication.
- Compared context SRS, balanced context-by-AI-state sampling, an intentional
  positive/disagreement-heavy stress rule, and a shared-agreement-guarded
  rule at B=50/100/200, with a targeted B=400 extension. The two-phase
  difference estimator targets full human-reference D/E and is explicitly a
  pooled reference, not the unresolved D-005 mixed model.
- Independent review found that the initial implementation coupled DGP,
  human, anchor, and audit RNG consumption. All affected percentages were
  discarded. Final per-replicate keyed streams are exactly invariant to batch
  size and to unrelated grid composition. The same review required an RR=1
  null, a shared-bias RR=2 boundary, nominal human-reference coverage,
  separate latent-coverage diagnostics, and fair estimability outputs.
- At base N=24/B=200, independent-error joint support ranges from 30.1% to
  67.2%, but the apparent oracle-level stress result has only 82.0%
  finite-reference coverage and zero audit variance in at least one context
  in 85.7% of runs. Under shared D/E-to-C bias, every design reaches only
  9.5-15.2% support versus a 65.7% latent oracle.
- The shared-bias RR=2 boundary falsifies small enriched audits: at B=50,
  false support is 18.7-28.9% for the three state designs while
  finite-reference coverage is only 40.2-68.0%. Their non-monotonic apparent
  support is an undercoverage/missed-correction artifact, not power.
- At B=400, context SRS and the guarded design reach 36.3% and 39.4% support
  under shared bias versus a 64.5% oracle, at a conservative total cost of
  450 human labels. They are not reliably ranked. A reference rater with 98%
  outcome-constrained A-F category accuracy attenuates the scenario
  human-reference 3x ratio to 2.759 and full-human support to 47.1%.
- Added exact sampling/allocation, census, hand variance, exhaustive
  repeated-sampling unbiasedness, metadata-contamination, noisy-human target,
  composite-null, and RNG-invariance tests. No audit or interval was selected;
  conservative rare-residual uncertainty, actual D-005 coupling, and measured
  human error remain required.
- D-002, D-005, D-006, D-010, and D-013 remain OPEN. No benchmark trial ran
  and no frozen V1 methodology, task, rubric prompt, scheduler, or collection
  rule changed.

### 2026-08-03 — D-010 conservative finite-population audit interval

- Added exact equal-tailed hypergeometric confidence sets for finite
  false-negative and false-positive totals inside every audit
  stratum-by-Coder-1 subgroup. Bonferroni allocation across all noncensus
  residual components yields simultaneous conditional coverage of the full
  finite human-reference ratio without treating an observed zero residual as
  known absence.
- Added `docs/D010_CONSERVATIVE_AUDIT_INTERVAL_MEMO.md` and expanded the
  D-010 tests with exhaustive finite-population coverage, noncensus-zero,
  census-identity, and full audit-sample enumeration oracles. CLI filters now
  allow reproducible scenario, human-mode, and design subsets without changing
  scenario seed identities.
- In the 1,000-replicate base-N=24 grid, exact finite-human coverage is
  99.9-100%. At B=400, audit-only gate-plus-threshold clearing for the
  independent 3x effect is 48.5% for context SRS but only 0.4-21.6% for the
  three state designs. Under shared D/E-to-C bias, all four designs reach only
  5.7-12.1%. The old plug-in state-design advantage was understated
  uncertainty, not usable power.
- A context-SRS cost curve shows that robust audit measurement resembles
  near-census review. With perfect labels, independent/shared 3x threshold
  clearing is 88%/64% at B=600, 95%/91% at B=700, and 97%/96% at B=800 out of
  roughly 864 focal failures. At 98% outcome-constrained A-F category
  accuracy, comparable behavior requires roughly B=700-800. Add the separate
  50-case minimum-size anchor to these human-label counts.
- At a focal-failure census, audit-only threshold clearing is about 48% when
  the scenario truth is exactly RR=2. This is finite-roster variation, not
  audit-interval type-I error, and proves that D-005 must separately handle
  trial/task/configuration uncertainty.
- The exact interval and context SRS are retained as conservative benchmarks,
  not accepted rules. D-002, D-005, D-006, D-010, and D-013 remain OPEN. No
  benchmark trial ran and no frozen V1 methodology, task, rubric prompt,
  scheduler, collection rule, label rule, N, or audit budget changed.

### 2026-08-06 — D-004/D-005 joint resource and inference frontier

- Added `analysis/d004_resource_feasibility.py`,
  `tests/test_d004_resource_feasibility.py`, and
  `docs/D004_D005_RESOURCE_FEASIBILITY_MEMO.md`. Exact candidate broad split-N
  identities now separate capability-only collection, full agent collection,
  provider-specific agent calls, full-sample AI coding, H2 failure-only
  coding, and explicit human-time assumptions without treating raw calls as
  subscription quota.
- Added two D-005 comparators on the same D-010 replicates. A task-by-
  configuration sandwich with t(6) is calibrated but supports only about
  18-30% of N=24 3x census scenarios. A cellwise Jeffreys delta attempt is
  falsified by 66-70% coverage and 11-19% threshold clearing at RR=2.
- Coupled the pooled two-phase fixed-roster interval to the exact finite-human
  audit bound and registered IRR gate. In the 1,000-replicate perfect-reference
  RR=2 grid, coverage is 95.0-96.0% and coupled threshold clearing is
  0.1-2.2% across B=400-census and independent/shared mechanisms.
- At base N=24, B=700 plus the 50-case anchor is the first tested point close
  to the full-human pooled ceiling in all strong-effect cells. Coupled support
  is about 64-67% with perfect labels and about 49% with a 98%-accurate human
  reference. It is therefore not an 80%-powered H2 design.
- B=600 and B=700 are retained only as empirical-costing candidates. No final
  model, claim scope, N, audit, label rule, coder backend, resource cap, or H2
  status was accepted. Researcher-specific subscription constraints remain
  in the private operational record. No benchmark trial ran and no frozen V1
  methodology, task, rubric prompt, scheduler, or collection rule changed.

### 2026-08-06 — zero-quota path audit and bound resource-shakedown tooling

- Added `scripts/collection_preflight.py` and focused tests. It exercises the
  actual environment-adapter transport, environment probe, and agent CLI
  version commands without supplying a prompt or consuming a model call.
  Exact Python/Claude/Codex/agy and environment pins fail closed; hygiene
  variables are recorded only as set/unset booleans.
- A real zero-quota audit exposed native Windows resolution of an
  extensionless npm Codex shim. `PowerShellEnvironment` now resolves bare
  executables to a CreateProcess-compatible PATHEXT sibling with PATH-first
  precedence; focused tests cover extensionless, extension, explicit-path,
  missing-command, and precedence cases. The correction was reverified on
  the real native Windows adapter path using only `codex --version`.
- Added deterministic `scripts/resource_shakedown_plan.py` and opt-in
  `scripts/resource_shakedown_run.py`, plus
  `docs/PRECOLLECTION_SHAKEDOWN.md`. The plan fixes 70 representative
  configuration/task calls plus 12 nonduplicative transport calls. The
  executor requires an external private output root, validates task and
  manifest digests, hides outcomes, locks the root, and writes hash-bound
  per-call receipts.
- No paid shakedown, pilot, confirmatory trial, resource cap, model family,
  analysis rule, or agy day-one pin was accepted. Real disposable-host,
  provider-usage, model-label, human-timing, and AI-coder evidence remain
  required; D-004, D-006, D-007, D-009, R-010, and G1-G4 remain open.

### 2026-08-06 — explicit V2 runtime-matrix candidate

- Added `scripts/configuration_matrix.py` and
  `config/v2-runtime-matrix.candidate.json`. The schema validates one CFG1-CFG7
  roster, one executable version per CLI, the version-sensitive environment
  pins, and the shared nominal Sonnet identity required by exploratory S6.
- Added `docs/V2_RUNTIME_PINNING.md`. It proposes refreshing executable and
  model pins together at the V2 freeze using subscription availability,
  roster role, parser/transport conformance, and updater control—not benchmark
  outcomes—as eligibility criteria.
- The current candidate advances Codex to `gpt-5.6-sol` plus
  `gpt-5.6-terra`, advances the agy workhorse to
  `gemini-3.6-flash-medium`, and advances current executable candidates.
  CFG2/CFG7 remain on the newest shared qualified Sonnet exposed by both
  harnesses; the inspected agy surface did not expose Sonnet 5.
- Zero-quota preflight and resource-shakedown generation now accept the same
  explicit matrix and record its digest/status. Shakedown schema 1.1.0 rejects
  superseded schema-1.0 manifests that did not bind a complete matrix.
- No V2 pin, model, runtime roster, scheduler change, or methodology decision
  was accepted. D-009 and G1-G4 remain open; the frozen V1 scheduler constants
  are unchanged.

### 2026-08-06 — consolidated V2 decision package and live E4 qualification

- Added `docs/V2_DECISION_PACKAGE.md`, an outcome-blind researcher-decision
  draft that assembles explicit recommendations for D-001 through D-013. It
  recommends a decision-bearing five-point finite-roster H1 risk-difference
  rule over the candidate broad task bank, exploratory H2/H4 scope, a common
  observable agy H1 outcome, and exact-prompt-set H4 language. No decision was
  accepted and no frozen V1 methodology changed.
- Added the unwired D-011 candidate
  `construct_agy_outcome_evidence`. It keeps the shared executable H1 task
  result separate from Cwd/transcript eligibility and fails closed on
  inconsistent evidence. All 14 tasks are covered across sandbox, scratch,
  mixed, non-shell, missing, parse-error, failed-predicate, and completion
  fixtures. Researcher acceptance and runner/analysis wiring remain open.
- Added Node 22.23.2 to the machine-readable candidate matrix and bound the
  zero-quota preflight to its exact observed version. Prior candidate digests
  and manifests without the Node pin are superseded.
- Added an optional pinned known-hosts path to `LinuxNativeEnvironment`.
  Operational E4 qualification supplies it and therefore uses strict host-key
  checking rather than personal SSH state or first-seen trust.
- Live E4 conformance passed 18/18 on the disposable Ubuntu 24.04 path. The
  candidate zero-quota audit then passed exact Node, Claude Code, Codex, agy,
  OS, controller, and environment checks without invoking a model.
- The regenerated candidate shakedown contains the same deterministic 82
  calls and dry-runs fully without model invocation. The complete local suite
  passes 465 tests with three expected infrastructure-gated skips.
- D-001 through D-013 and G1-G4 remain open. Windows/WSL and macOS path
  qualification, authenticated shakedowns, researcher decisions, task-bank
  construction, final analysis, provenance review/blinded export, and resource
  evidence still precede pilot collection.

### 2026-08-06 — R-016 scheduler-to-record provenance binding

- Added `harness/schedule_identity.py`. The immutable plan now produces one
  hashed token per cell binding phase, plan digest, cell/configuration, task
  hash, trial schema, target valid N, exact coordinates, and expected CLI
  version.
- The scheduler passes that token across the child-process boundary.
  `run_cell()` validates its integrity, current task bytes, effective phrasing,
  coordinate, schema, and CLI-version expectation before constructing any
  environment or agent adapter; outcome-blind execution without a token is
  refused.
- Attempt-journal schema 1.2.0 and trial-record schema 1.6.0 carry the same
  identity. Scanner validation is payload-based as well as path-based and
  rejects missing identities, copied records, wrong phase/plan/cell/task
  hash/schema/target N, and foreign tokens placed under manually matching
  paths.
- Added the specified child and scanner negative cases. The scheduler suite
  passes 43 tests, the writer/attempt regression slice passes 37 tests, and
  the complete suite passes 580 tests with three expected infrastructure-
  gated skips. No benchmark or shakedown model call ran.
- R-016 is IMPLEMENTED, not yet VERIFIED. Independent code review and
  cross-host child dry-runs remain; no V2 methodology decision, runtime
  roster, task bank, N, or analysis rule was accepted.

### 2026-08-09 — R-005 plan-bound blinded pilot export

- Added `harness/blinding.py` and `scripts/pilot_blinding.py`. Before the first
  attempt, preparation encrypts the mapping and Ed25519 private key with
  AES-GCM/Scrypt custody, binds a public commitment into the pilot root, and
  writes an identical external commitment for independent anchoring.
- Export independently invokes the scheduler's plan, schedule-token, path,
  attempt-journal, validity, schema, CLI-version, and terminal-link checks. It
  additionally requires a terminal trial digest for every source record and
  fails on an active scheduler lock or any unexpected source artifact.
- Export holds an exclusive lock and validates, extracts, and hashes from one
  private byte snapshot, closing the rows-versus-manifest TOCTOU window. The
  custody, commitment, passphrase, and output paths are kept outside the pilot
  root; output is Ed25519-signed.
- Preparation now loads the frozen plan manifest and initializes the bound
  pilot root before execution. Pilot scheduling validates the bound public
  commitment under the same atomic lock used for collection/export and fails
  before child invocation or attempt allocation when it is absent or invalid.
- The export enforces the exact 230-cell, two-valid-per-cell, 460-valid-trial,
  five-blinded-group roster. Invalid attempts are excluded from trial rows and
  reported only as an aggregate count. Researcher-visible output contains no
  environment names, named rates, source paths, cell IDs, or trial indices.
- `scripts/size_from_pilot.py --pilot-json` now also requires
  `--blinding-commitment`, verifies the Ed25519 signature and exact row
  multiset, and rejects an outcome edit even when its public digest is
  recomputed. Both CLIs self-locate the checkout from an external cwd.
- Seventeen tests include two complete synthetic filesystem pilots and the
  required negative cases plus signed-export forgery, snapshot stability,
  encrypted-custody leakage, path separation, external-cwd operability,
  scheduler refusal before attempt 1, partial-preparation failure, strict
  schema parity, and wrong-phase root protection. The combined scheduler/
  R-005 slice passes 60 tests independently and the complete suite passes 597
  tests with three expected infrastructure-gated skips. The final independent
  code review reports no remaining R-005 code blocker. R-005 is IMPLEMENTED,
  not VERIFIED:
  the actual custody role, pre-outcome anchor, and independent provenance
  reconstruction remain.

### 2026-08-09 — R-006 sizing-lock-to-confirmatory-plan binding

- Added `harness/sizing_lock.py` and `scripts/create_sizing_lock.py`. The new
  V2 wrapper leaves the frozen V1 sizing implementation unchanged while
  requiring the signed R-005 export, matching commitment, exclusive output,
  all three authoritative budget inputs, explicit code/analysis versions,
  and exact analysis/simulation artifacts.
- The lock validates and binds source pilot-plan/schema, blinded-input bytes,
  export/source-manifest/commitment digests, sizing-path code hashes, sizing
  constants and result, resource inputs and cap, analysis artifact/version,
  and simulation configuration under one digest.
- Confirmatory plan schema 1.1.0 embeds the complete sizing lock and derives
  the primary N from it. The CLI no longer accepts a manual primary N, and
  manual vendor-specific overrides fail closed until a separate verified lock
  exists. Pilot and mini-pilot plans reject sizing locks.
- Negative tests cover missing authoritative inputs, overwrite attempts,
  result, phase, budget, roster-count, and embedded-lock tampering, a
  below-floor N, missing lock, and unbound vendor overrides. Fifteen focused
  R-006 tests and 62 scheduler/R-005 regression tests pass; syntax compilation
  passes. The complete local suite passes 614 tests with three expected
  infrastructure-gated skips.
- R-006 is IMPLEMENTED, not VERIFIED. Independent no-edit counterexample
  review remains. R-005 real-run custody evidence, R-016 cross-host evidence,
  D-001 through D-013, and G1-G4 remain open. No model, shakedown, pilot, or
  confirmatory call ran, and no frozen V1 file changed in this work item.

### 2026-08-09 — accepted V2 slate, bounded human audit, and D-011 review

- The researcher accepted D-001 through D-013 as recorded in
  `docs/V2_ACCEPTED_DECISIONS.md`. Acceptance fixes the methodological
  direction; it does not waive the remaining implementation, qualification,
  host, custody, or freeze gates.
- D-010 now uses a fixed 50-label probability anchor and, only after an
  outcome-blind measurement-informativeness gate, one bounded 100- or
  150-label focal audit. Routine human review is capped at 200 labels; there
  is no automatic third stage, and a larger audit requires a new explicit
  decision. The machine policy now rejects unknown fields, outcome-selected
  sampling, and aliases for named hypothesis results.
- D-011 is wired through the common runner and writer. Independent review
  found that malformed/ambiguous agy brain evidence had been treated as
  usable and that unavailable traces could turn trace-dependent checks into
  false valid failures. The runtime now distinguishes present, missing,
  parse-error, and ambiguous evidence; trace-dependent trials fail
  infrastructure-invalid when evidence is unavailable; filesystem-only H1
  remains measurable; and contradictory nested/top-level H1 fields are
  rejected.
- A final independent review found no remaining load-bearing D-011 code
  finding. The complete suite passes 669 tests with three expected skips.
  R-019 remains IMPLEMENTED rather than VERIFIED until the frozen analysis
  builder independently reconstructs and validates these fields. No model or
  paid benchmark call ran.
- D-013 now has a machine-checked accepted design slate: exactly 12 families,
  six equally weighted domains, three planned instances per family, explicit
  workflow analogues, context links, exclusions, oracles, counter-policies,
  and recurrent demand coverage. At this date the instance slots were still
  unauthored; the later 2026-08-11 entry records their implementation.

### 2026-08-11 — D-013 36-instance bank and V2 pilot identity

- Authored all 36 candidate V2 capability instances under `tasks/v2/` and
  added `analysis/d013_task_bank.py` to bind the exact 12-by-3 roster, distinct
  task bytes, common timeout rule, protected inputs, and extra-artifact scope.
  The current candidate-bank digest is
  `f58cd9e995fa0197e752d7f985298ef8736418220ad20e6334ea5ae70eddeb75`;
  it is not the final Q4 freeze.
- Added declarative argv-only Git fixture construction and post-agent
  environment oracles. C07 uses real unresolved merges; C08 uses real
  index/worktree state. Exact porcelain-status checks reject unrelated
  untracked files while excluding only the benchmark-wide Python cache
  artifacts.
- Added environment-native fixed-argv oracles and baseline-relative
  `file_unchanged`. C11 receives a fixture-selected loopback port, requires it
  unchanged, proves it is unoccupied after the agent, then launches/probes/
  exits the service itself. A live leftover-listener counterexample fails.
- All 36 instances fail on no-op, pass a known-positive completion, reject an
  extra artifact, and reject protected-content corruption. These are useful
  Q2 results, not a claim that every named counter-policy or valid alternate
  solution has been tested.
- Plan schema 1.3, schedule identity 1.2, attempt schema 1.3, and trial schema
  1.7 carry family, instance, and instance SHA-256. The deterministic V2
  pilot has 540 cells and 720 valid trials: one per capability instance and
  two per seeded variant in each Claude configuration/environment. Signed
  blinded-export schema 1.1 validates and retains those identities; a
  synthetic signed 720-row round-trip passes.
- No model, paid benchmark, shakedown, or human-label call ran. Q1 five-host
  and fresh-human evidence, the remaining Q2 matrix, all Q3 evidence, blocked
  rounds/analysis recovery, and final Q4 freeze remain pilot blockers.
- The complete local suite passes 1,015 tests with three expected
  infrastructure-gated skips; `git diff --check` is clean.

### 2026-08-12 — D-009 order evidence and V2 H1 reconstruction

- Added a deterministic 720-valid-slot D-009 candidate that separates repeat
  slots into two rounds, preserves the exact plan multiset, crosses every
  task block over configurations and environments, balances configurations
  within host partitions, records explicit prefix counts, and rejects missing,
  duplicate, or forged slots. It is not imported by the production scheduler;
  the epoch and drift rules remain researcher decisions.
- Added an exact analysis-source manifest and external-cwd CLI. The manifest
  binds every valid and invalid trial-record byte digest, refuses to mutate the
  source root, and detects added, removed, modified, foreign, incomplete, or
  excess records. Its public digest still requires an independent external
  anchor; self-hashing is not authentication.
- Added independent trial reconstruction for schema/schedule identity,
  validity, timeout/completion/check precedence, measurement loss, D-011 agy
  eligibility/Cwd evidence, and exact valid-slot completion. Added the accepted
  equal-domain/family/instance/configuration H1 marginal rates, risk difference,
  and companion risk ratio as point estimands only.
- Focused evidence is 25 passing tests, including shared-lock, between-pass
  mutation, and global duplicate-attempt counterexamples. The complete local
  suite passed 1,038 tests with three expected infrastructure-gated skips
  before the final isolated hardening; its directly affected 19-test slice
  passed afterward. No model, paid benchmark, shakedown, human-label, or
  outcome-bearing call ran. D-005 interval/fallback, A2-A4, production
  blocked-order binding, epoch sensitivity, and independent review remain
  open.

### 2026-08-13 — refreshed runtimes and zero-quota host/task qualification

- Refreshed the candidate matrix before outcome-bearing work: Claude Code
  2.1.231, Codex 0.147.0, agy 1.1.12, and Node 24.12.0. Model labels remain
  unchanged because the authenticated agy roster still exposes Sonnet 4.6,
  making it the newest shared S6 model. The candidate matrix digest is
  `4791ffdf91cd4000e51286bb7c1e3a1a890098b611fb91f795b7a788fb72a0e4`.
- Exact zero-quota preflight passed on Windows PowerShell 5.1, Windows pwsh
  7.6.4, WSL2 Ubuntu 24.04.4, and a fresh GCP `e2-small` Ubuntu 24.04.4 VM.
  E4 uses a dedicated key, strict pinned host identity, local IAP tunnel, no
  service account or scopes, an auto-deleting disk, and a 24-hour delete-on-
  expiry limit. Its live conformance battery passed 18/18.
- Regenerated the 82-call analysis-excluded shakedown manifest, digest
  `e6d3886c03b3483a38b3725e228631edcb2ab14c8932bf59c7f53769c9f06e1b`.
  The full executor dry run passed without an agent/model invocation.
- Consolidated the 36 task-author oracle completions into
  `analysis/d013_oracle_qualification.py`. It proves both that each untouched
  fixture fails and that its registered oracle passes the executable checks
  through a real environment adapter. After strengthening C06/C09 against
  visible-example specialization, exact bank digest
  `f58cd9e995fa0197e752d7f985298ef8736418220ad20e6334ea5ae70eddeb75`
  passed 36/36 on each of Windows PowerShell, pwsh, and WSL: 108 portable
  completions and zero model calls. The analysis-excluded artifact
  `d013-oracles-windows-wsl-r022.json` has SHA-256
  `b5a8762c6de0001266994086a02f28b95844ca4c663b5795b5d794643ebf0cd5`.
  Six independently written valid C06/C09 implementations pass and six
  prompt-visible specializations fail. The earlier E4 result is superseded
  by the changed task bytes and must be rerun. This materially advances Q1
  and Q2, but does not replace fresh-
  human review, alternate-valid/adversarial counter-policy coverage, transcript
  adjudication, or Q3 development calibration.
- Replaced the old macOS no-op shim workflow with an exact-runtime, zero-quota
  macOS 26 qualification workflow covering live conformance, matrix preflight,
  and all 36 oracle completions. It cannot run from the unpublished dirty
  checkout; publication/dispatch remains open.
- Closed the scheduler/runtime split with plan schema 1.3. A V2 plan now
  requires a `frozen` matrix, embeds its complete CFG1-CFG7 agent/model/CLI
  projection and substantive digest, and paid execution requires exact
  equality with the same independently supplied matrix. Candidate matrices,
  missing matrices, mismatches, malformed configuration fields, and legacy
  schema-1.2 V2 plans fail closed; historical V1 schema-1.2 plans remain
  readable.
- Promoted the accepted D-009 blocked-round candidate into the same plan.
  The exact 720 valid-slot sequence is digest-bound; filtered host runs retain
  its subsequence; each V2 child invocation is one slot; and schedule-identity
  schema 1.2 carries that slot through attempt events, final records, scanner
  validation, and independent analysis reconstruction. Invalid attempts retry
  the same slot and cannot change the planned instance mixture. Epoch/drift,
  cross-host timing, and incomplete-slot authority remain open decisions.
- Strengthening those six behavioral tasks changed the reproducibility
  identifiers. The current V2 pilot plan digest is
  `47cd68e8348ac511aba06f44de9afed0a5315d98f6f3c18a0381aadae78bd2f0`
  and the embedded 720-slot order digest is
  `acf77346a107d7bbbd7176e17d7389150e60ee9e75106a01dd847a209af7bb7e`.
- The post-strengthening complete suite passed 1,097 tests with three expected
  infrastructure-gated skips before the accepted epoch and stdin changes.
  The final suite after both changes passes 1,101 tests with three expected
  skips. No model,
  paid shakedown, pilot, confirmatory, or human-label call ran. A proposed
  transfer of live Claude/Codex subscription credentials to E4 was rejected
  pending the researcher's explicit informed authorization; no credentials
  were copied.

### 2026-08-13 — authenticated E4 smoke exposed inherited stdin

- With explicit researcher authorization, transferred only the public
  benchmark source plus the named Claude credential and active WSL Codex auth
  file to the isolated E4 VM. Remote credential directories are mode 700 and
  files mode 600; no credential content was displayed or written to the
  repository.
- The exact strengthened bank passed all 36 registered Linux-native oracle
  completions through the production strict-host-key SSH adapter, zero model
  calls. The analysis-excluded artifact
  `d013-oracles-e4-linux-r022.json` has SHA-256
  `e23b738911d6346025a7358142ea74adace5d0e27b8b0f276604de56a636c1ca`.
- One minimal Claude production-argv authentication call passed. The first
  Codex attempt made no events because inherited stdin remained open and the
  CLI waited for additional input; closing stdin made the same production argv
  pass in eight seconds. All production environment process seams now set
  `stdin=DEVNULL`, with a cross-environment regression test. These calls are
  authentication smokes only and are excluded from benchmark analysis.
### 2026-08-14 — Q2 and authenticated runtime qualification update

- The full executable Q2 audit now passes 217 checks: all 36 independent
  alternate valid solutions pass, every H1-visible accepted counterpolicy
  fails, and H2/H4-only policy surfaces are explicitly separated from H1.
- Byte-preservation requirements in the affected V2 families now use
  `file_unchanged`; this closes the CRLF/BOM false positive exposed by Q2.
- The current task-bank digest is
  `528b70694d29e22cf54fc487f2df64b016251f5a318c9691df0d57ece2f3c47b`.
  Older task-bank, oracle, plan, and shakedown digests are superseded and must
  not be cited for the current bytes.
- The candidate runtime matrix now pins agy 1.1.13 and has substantive digest
  `27f8a18ba7fa552f9f13d445341fb95716b7dc1bdfc32c220be95b76d87c673b`.
  Authenticated C01-I01 smokes passed for all three agy model routes. The CFG7
  production record is transcript-analysis eligible after capture-grounded
  support for 1.1.13 numeric exit codes and separate stdout/stderr envelopes;
  focused agy/D-011 tests pass 492/492.
- A current-bank four-environment oracle rerun was attempted but the control
  command timed out before atomic artifact creation. Portable-oracle evidence,
  macOS qualification, regenerated plan/shakedown identities, the 82-call
  shakedown, and the final full-suite/doc reconciliation therefore remain
  pre-collection gates. The exact private handoff is
  `agent-shell-context-bench-ops/2026-08-14/HANDOFF.md`.

### 2026-08-15 — current-bank host recovery and resource shakedown

- Recovered the atomic four-environment oracle artifact that completed after
  the prior controller timeout. It is bound to current task-bank digest
  `528b70694d29e22cf54fc487f2df64b016251f5a318c9691df0d57ece2f3c47b`,
  reports 36/36 on Windows PowerShell, pwsh 7, WSL2, and Linux native, and has
  SHA-256
  `dfe021ef67f4f8ac4b79b796a7a90ab4b2548e7a35c5f795ff28bfac7fa85436`.
- Regenerated the current 82-call analysis-excluded shakedown manifest under
  matrix digest
  `27f8a18ba7fa552f9f13d445341fb95716b7dc1bdfc32c220be95b76d87c673b`.
  Its digest is
  `ee6f15cf6b677d24bb2612b4202468ffb2ae41086d68e6f2c8389b895020e023`,
  and its complete dry run passes.
- The first execution attempt failed before model invocation because R-016's
  outcome-hidden child boundary now requires a schedule token. The failed
  receipt remains preserved. The shakedown executor now derives a
  deterministic schedule identity from the manifest and call, so it binds
  phase, manifest digest, task bytes, configuration, runtime, and the one
  analysis-excluded slot without relaxing ordinary unbound execution.
- Exact zero-quota preflight passes on Windows PowerShell, pwsh, WSL2, and
  Linux native with Claude Code 2.1.231, Codex 0.147.0, agy 1.1.13, Node
  24.12.0, and the required traffic/updater controls. The corrected shakedown
  retry recorded all 70 resource-core calls and all nine non-macOS transport
  calls. The manifest is therefore 79/82; the three macOS transport calls and
  the macOS zero-quota/oracle workflow remain open.
- The macOS qualification workflow now installs the checksum-pinned official
  agy 1.1.13 ARM64 artifact, matching the candidate runtime matrix. It still
  requires publication and dispatch before its evidence can be accepted.
- Focused shakedown/preflight/matrix evidence is 33 passing tests. The full
  host-permitted suite passes 1,317 tests with three expected infrastructure-
  gated skips; workflow YAML parsing and `git diff --check` pass. No pilot or
  confirmatory collection began, and no frozen V1 methodology file changed.

### 2026-08-15 — manifest-bound IRR coding boundary

- Replaced the ad-hoc recursive IRR input search with the complete frozen V2
  analysis-manifest snapshot. The shared locked loader now returns the exact
  verified source bytes, raw record, and independently reconstructed analysis
  identity from one pass; only manifest-declared valid analysis trials enter
  coding, and real coding requires a confirmatory plan.
- Each exclusive coder record binds the plan and analysis-manifest digests,
  source path/digest, cell/configuration/trial/slot/execution-position/epoch/
  attempt/task/family/instance/phrasing identity, transcript and coder-input
  hashes, frozen prompt,
  coder/model pin, observed model, request id, raw-response hash, and immutable
  status. Exact resume validates prior records and completion digest.
- Refusal, malformed output, backend failure, and model substitution are
  recorded once as missing-label states. There is no automatic retry or
  fallback that can rewrite the accepted Coder-1 primary label. Dry-run labels
  are explicitly invalid, and the CLI refuses real calls until exact
  different-lineage backends are selected and frozen.
- Twenty focused manifest/coder tests pass. R-009 remains IN PROGRESS because
  backend qualification/costing and the staged human sampler/analysis are
  still open. R-018 remains open because the code deliberately preserves the
  V1-compatible prompt/transcript/outcome packet instead of silently choosing
  the missing V2 evidence and code-E post-processing contract.

### 2026-08-15 — active-document consistency boundary

- Updated the README to preserve its historical V1 implementation evidence
  while routing every current collection-start decision to this document.
  Completed V1 re-smokes no longer appear as current obligations. The ignored
  private operations log remains outside the public consistency gate and must
  be reconciled separately without copying its contents into this repository.
- Extended the cross-document consistency suite to compute the current runtime
  matrix and 36-instance task-bank digests from executable artifacts and
  require them, current CLI/runtime versions, the shakedown-manifest digest,
  and the 79/82 receipt count across the active V2 status documents. Eleven
  documentation-consistency tests pass.
- R-011 remains IN PROGRESS. The final V2 amendment must still reconcile the
  frozen V1 four-blinded-group wording with the five-environment V2 design,
  after which the complete active-document review must pass.
- The final host-permitted repository suite passes 1,333 tests with three
  expected infrastructure-gated skips. Prompt-drift, Python compilation,
  public-safety, documentation-consistency, and `git diff --check` gates also
  pass before publication.

### 2026-08-15 — published macOS current-bank qualification

- Published the remediation implementation on draft PR 8, branch
  `codex/pre-data-readiness`. Public safety passes 1,332 tests with nine
  expected infrastructure skips at commit
  `fbbf3d47f6a0363e7cb9bb213a31a08120338f77`.
- GitHub runner-images issue 14409 documents a macOS 15+ local-network-privacy
  stall in Python's `socket.getfqdn()` between bind and listen. A narrow
  compatibility shim now applies the maintainer-recommended bypass only to
  Darwin `service.py --once` loopback processes. Qualified task bytes and the
  task-bank digest are unchanged.
- GitHub Actions run `31913265675` passes exact Python 3.11.9, Node 24.12.0,
  Claude Code 2.1.231, Codex 0.147.0, agy 1.1.13, live macOS adapter
  conformance, exact zero-quota collection preflight, and all 36 portable
  oracle completions on the `macos-26` ARM64 runner. Artifact `9254250620`
  has archive SHA-256
  `27c0f2a7dab2470bc11a22bd8bd177d3c352dda6430e358819faa08223723a05`.
- Five-environment runtime presence and current-bank portable oracles are now
  complete. At this point R-010/G4 remained open because GitHub authentication
  did not supply the three vendor subscription credentials, and the shakedown
  receipt count remained 79/82. The later authenticated preservation update
  below supersedes that current-state assessment while retaining this dated
  audit trail.

### 2026-08-15 — macOS receipt preservation (semantic claim superseded)

- Private Actions run `31915184579` produced the three remaining
  manifest-bound C01 receipts on `macos-26`. Later semantic re-audit found
  that its `agy` record was an interactive OAuth timeout with process return
  code one, so this run does not qualify the `agy` transport.
- Independent post-download validation matched all expected paths, byte
  counts, and SHA-256 values. The first successful model-call run is retained
  as retry-tail evidence because its hosted archive omitted hidden attempt
  files; the preservation retry explicitly included and validated them.
- After verified private download, all temporary Actions secrets and hosted
  artifacts were deleted and absence was checked. The structural receipt
  count reached 82/82; the semantic qualification claim was not yet satisfied.
- A same-day live first-party policy and signed-in account review confirmed the
  registered subscription paths and recorded privacy, telemetry, and overage
  controls. Antigravity's newly documented personal-credit fallback was
  explicitly pinned off. The sanitized private review has SHA-256
  `4711f042f771613ccef31b8552a4302eda8ecbb0306999b758388b7f0575b15b`.
  That record is retained as dated policy evidence but its authentication
  conclusion is superseded by the corrected evidence below.

### 2026-08-15 — D-005 executable fixed-roster interval candidate

- Added an executable H1 Family-B interval path that preserves equal
  domain/family/instance/configuration weights and never pools sparse leaves.
  The point estimate, marginal rates, RD interval, boundary-safe companion RR
  envelope, and accepted three-way five-point classification are emitted from
  one deterministic result object.
- Prospective recovery falsified the Wilson-MOVER comparator at 92.1%
  coverage in the N=24 split-N opposing-domain stress. The leading
  Clopper-Pearson-MOVER candidate covered 97.0-100% across the current N=24
  split-N grid with at most 0.5% wrong threshold declarations. It remains a
  candidate pending the complete dependence/attrition/epoch envelope.
- Leaves with fewer than three observations fail over to a simultaneous
  Clopper-Pearson/Bonferroni envelope. The fallback is valid at singleton and
  boundary cells and is allowed to remain inconclusive; it does not borrow
  precision from another fixed task cell.
- Twenty-six focused implementation/recovery tests pass. No benchmark data
  were accessed, no task bytes changed, and no D-005 parameter was accepted.

### 2026-08-15 — semantic authentication correction and 82/82 requalification

- Full receipt re-audit found that the earlier Windows resource-core and
  macOS `agy` calls, plus WSL2 and Linux-native Claude transport calls, had
  recorded task failures after pre-model authentication failure. Receipt
  existence and harness return code alone were therefore insufficient.
- Public commits `d8d97e8790ce38a1b5debecc08f3958f6f807aeb` and
  `27bf86f95ec2043dbdce0a29b523afba9c641fe7` make the exact observed `agy`
  and Claude authentication envelopes fail closed.
- Corrected private Actions runs `31919535320` (30 Windows `agy` resource
  calls) and `31919774650` (three macOS transports), plus corrected WSL2
  `agy` and WSL2/Linux-native Claude manifest calls, all returned zero and
  passed semantic validity checks.
- The recomposed manifest audit selects exactly one newest accepted receipt
  per call ID: 82/82 calls, 410 receipt-bound artifacts, 328 immutable attempt
  states, zero missing or mismatched paths/bytes/hashes, zero nonzero process
  exits, zero invalid trials, and zero recognized authentication envelopes.
- Agent-under-test resource timing and available provider meters are recorded
  in the corrected private review with SHA-256
  `a8f48c67f919d9265a9ee838d0f5789b10b1d71447c36789c83857857bbb246c`.
  Hosted artifact inventory and temporary Actions-secret inventory are both
  zero. Refreshed WSL credentials were removed/restored as appropriate, and
  copied Claude/Codex files were removed from the dedicated Linux VM.
- R-010 is VERIFIED on corrected semantic evidence. D-004 remains parameter-
  open for the human 30-50-transcript timing exercise, separate D-006 coder
  shakedown, and final numeric provider/calendar caps.
- R-007 is VERIFIED: the scheduler/attempt-preservation slice passes 78 tests;
  the test helper derives the current writer schema while the explicit stale-
  schema counterexample still fails closed; draft-PR `verify` and
  `macos-e5-qualification` checks both pass at the corrected evidence head.
