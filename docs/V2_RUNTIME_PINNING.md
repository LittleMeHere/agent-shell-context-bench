# V2 runtime-pinning and model-selection rule

**Status:** CANDIDATE — pre-data; not accepted or frozen
**Created:** 2026-08-06; candidate refreshed 2026-08-14
**Machine-readable candidate:** `config/v2-runtime-matrix.candidate.json`
**Decisions informed:** D-004, D-009, G1, G3, and G4

## Decision proposed

Refresh the executable and model pins together at the V2 freeze, before any
pilot or confirmatory outcome is observed. “Refresh” does not mean choosing
the largest version number automatically. A candidate is eligible only when:

1. it is available through the study's actual subscription surface in every
   environment assigned to it;
2. the required non-interactive, permission, model-selection, output, and
   working-directory controls remain usable;
3. the real transcript schema still passes adapter and parser conformance;
4. it retains the registered roster role (frontier, workhorse, or
   same-nominal-model harness control); and
5. its updater can be blocked, or an equally strong immutable-build procedure
   can be demonstrated for the whole collection epoch.

Benchmark-task success or failure must not be used to choose between eligible
models. Qualification calls may test availability, argument propagation,
schema, command capture, and resource behavior, but they are analysis-excluded
and cannot screen for a roster that produces a preferred effect.

## Current candidate snapshot

The JSON candidate records the exact labels observed or selected on
2026-08-14. It is an input to qualification, not a promise that these will be
the final V2 pins.

| Config | Role | Candidate model | Candidate CLI |
|---|---|---|---:|
| CFG1 | Anthropic frontier | `claude-opus-4-8` | Claude Code 2.1.231 |
| CFG2 | Anthropic workhorse / S6 pair | `claude-sonnet-4-6` | Claude Code 2.1.231 |
| CFG3 | OpenAI frontier | `gpt-5.6-sol` | Codex 0.147.0 |
| CFG4 | OpenAI workhorse | `gpt-5.6-terra` | Codex 0.147.0 |
| CFG5 | Google frontier | `gemini-3.1-pro-high` | agy 1.1.13 |
| CFG6 | Google workhorse | `gemini-3.6-flash-medium` | agy 1.1.13 |
| CFG7 | S6 harness control | `claude-sonnet-4-6` | agy 1.1.13 |

The OpenAI pair follows the current Codex role descriptions: Sol is the
flagship and Terra the balanced workhorse. Those roles, including the announced
retirement of older ChatGPT-auth Codex models, are documented on the
[official Codex model page](https://developers.openai.com/codex/models).
Anthropic has released Sonnet 5, but the authenticated agy 1.1.13 surface
inspected on 2026-08-14 exposed Sonnet 4.6 and not Sonnet 5. The candidate therefore retains
Sonnet 4.6 in both CFG2 and CFG7. The newer release is documented in the
[Sonnet 5 announcement](https://www.anthropic.com/news/claude-sonnet-5).

This is the load-bearing exception to a blanket “update every model” rule.
S6 compares the same nominal Sonnet model under Claude Code and agy. Advancing
CFG2 alone to Sonnet 5 would turn the contrast into model plus harness. If agy
exposes Sonnet 5 by the freeze and both paths qualify, advance both. Otherwise
retain the newest shared qualified Sonnet or explicitly remove/reframe S6 in
the V2 amendment; do not describe a mismatched pair as a harness control.

## Environment and dependency pins

The current candidate advances pwsh from 7.6.2 to 7.6.4, pins the locally
qualified Node 24.12.0 runtime (both candidate npm agent packages declare it
eligible), and retains Ubuntu
24.04 plus the `macos-26` runner. Re-query these at the freeze. Preserve
Windows PowerShell 5.1 as a measured construct rather than treating it as a
dependency to upgrade away: replacing it would change the research question.

Do not churn Python or statistical-library pins merely for currency. Upgrade
them only for a documented compatibility, correctness, security, or required
analysis reason, then rerun deterministic simulations and the full test suite.
OS image labels may advance only if the prior image is unavailable or the V2
amendment deliberately changes the target environment; record the exact image
and observed patch/build either way.

## Freeze procedure

1. Re-query first-party model availability and current stable CLI releases on
   the actual subscription accounts.
2. Apply the eligibility rule above and update the candidate JSON without
   looking at benchmark outcomes.
3. Run unit/conformance tests, then `scripts/collection_preflight.py --matrix`
   on all five real transport paths. The preflight performs only environment
   probes and `<agent> --version`; it consumes no model quota.
4. Run the analysis-excluded resource shakedown from a disposable qualified
   host using a manifest generated with the same matrix. Its manifest records
   the matrix SHA-256 digest.
5. Resolve every schema, routing, substitution, updater, and resource failure.
   If a replacement is needed, create a new candidate and repeat qualification.
6. Change `status` from `candidate` to `frozen` and record the final digest and
   verified-on evidence in the V2 amendment/version manifest. The scheduler
   accepts V2 collection plans only from that frozen artifact, embeds its
   complete configuration projection and digest, and requires the same
   independently supplied matrix again at execution. Status is recorded
   separately and excluded from the pin digest, so this administrative change
   does not invalidate qualification evidence when every substantive field is
   unchanged.
7. Any later change is a dated deviation and a new collection epoch; never
   silently edit the frozen matrix in place.

The frozen V1 scheduler constants remain untouched until the V2 methodology
decision is accepted. Legacy `--agy-cli-version` shakedown generation remains
available only for explicitly labeled V1 diagnostic work.

## 2026-08-15 qualification evidence

The refreshed substantive pin digest is
`27f8a18ba7fa552f9f13d445341fb95716b7dc1bdfc32c220be95b76d87c673b`.
Zero-quota preflight passed on native Windows PowerShell 5.1, Windows pwsh
7.6.4, WSL2 Ubuntu 24.04.4, and a fresh GCP `e2-small` Ubuntu 24.04.4 host.
The E4 path also passed all 18 live environment-conformance tests through a
dedicated strict-host-key IAP/SSH transport.

The analysis-excluded shakedown roster was regenerated against this matrix:
82 calls, manifest digest
`ee6f15cf6b677d24bb2612b4202468ffb2ae41086d68e6f2c8389b895020e023`.
All 82 coordinates and task hashes passed the executor dry run. Seventy
resource-core calls and nine non-macOS transport calls are now recorded; the
three macOS transport calls remain.

`analysis/d013_oracle_qualification.py` now provides one cross-environment
oracle path rather than relying on scattered local test helpers. The exact
36-instance bank digest
`528b70694d29e22cf54fc487f2df64b016251f5a318c9691df0d57ece2f3c47b`
passed 36/36 untouched-fixture failures and 36/36 oracle completions on each
of native Windows PowerShell, native pwsh, WSL2, and fresh E4 Linux (144 oracle
completions total, zero model calls). The combined current-bank artifact
SHA-256 is
`dfe021ef67f4f8ac4b79b796a7a90ab4b2548e7a35c5f795ff28bfac7fa85436`.
GitHub Actions run `31913265675` then passed the same protocol on the
`macos-26` ARM64 runner: exact runtimes, live conformance, zero-quota
collection preflight, and 36/36 oracle completions. The uploaded qualification
artifact has ID `9254250620` and archive SHA-256
`27c0f2a7dab2470bc11a22bd8bd177d3c352dda6430e358819faa08223723a05`.

Plan schema 1.3 now makes the runtime boundary fail closed: candidate matrices
cannot create V2 plans; the plan embeds all CFG1-CFG7 model/agent/CLI pins plus
the substantive matrix digest; and paid V2 execution requires exact equality
with an externally supplied frozen matrix. Historical V1 plan schema 1.2
remains readable, but a schema-1.2 V2 plan is rejected because it lacks this
binding.

These results qualify runtime presence and portable executable outcomes in
all five environments. Authenticated route smokes and 79/82
resource-shakedown calls are complete, but the three macOS authenticated
transport calls, fresh-human solvability, transcript adjudication, and Q3
difficulty remain. The matrix therefore remains `candidate`.
