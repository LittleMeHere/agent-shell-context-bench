# TOS / AUP Compliance - vendor access paths for this benchmark

This document records the vendor access paths the benchmark intends to use,
the methodology interpretation behind each path, and the compliance measures
applied. It is deliberately conservative: the access-path decisions are part
of the public pre-registration record, while final source captures and
archive links are a pre-tag checklist item.

The compliance posture for each vendor is locked at pre-registration tag time.
Any post-tag change to access path, account type, or compliance measure is
recorded as a deviation in [`../DEVIATIONS.md`](../DEVIATIONS.md).

## Evidence Status

The current public repo is ready for WIP review, but this file is not claiming
that the legal evidence pack is complete. Before the `pre-registration-v1` tag:

- Retrieve each cited vendor document in a browser.
- Record the retrieval date, vendor "last updated" date where available, and
  archive.org snapshot URL where available.
- Quote only the short operative clauses needed to anchor the methodology
  interpretation.
- Send or log disclosure emails where this document says they are required.

Until that pass is complete, this file is an access-path rationale and
checklist, not a finished legal appendix.

## Anthropic - configs #1 and #2

**Configs:** Claude Code x `claude-opus-4-8`; Claude Code x
`claude-sonnet-4-6`.

**Access path:** Consumer subscription tier (Claude Max) via the first-party
`claude` CLI in headless mode (`claude -p`).

**Operative sources:**

- Consumer Terms of Service: https://www.anthropic.com/legal/consumer-terms
- Acceptable Use Policy: https://www.anthropic.com/legal/aup
- Claude Code legal and compliance documentation:
  https://code.claude.com/docs/en/legal-and-compliance
- Claude Code headless mode documentation:
  https://code.claude.com/docs/en/headless
- Claude Code Agent SDK credit policy:
  https://support.claude.com/en/articles/15036540

**Methodology interpretation.** Anthropic documents headless Claude Code use
as a first-party feature. The benchmark therefore treats bounded `claude -p`
usage on a Claude Max subscription as permissible for ordinary individual
research use, provided the run stays within documented subscription limits,
does not share credentials, and does not use third-party credential bridges.

**Compliance measures:**

- Throttle to roughly 50% of documented per-tier rate caps for both Opus 4.8
  and Sonnet 4.6 cells.
- Set Claude Code environment hygiene variables before trials:
  `DISABLE_TELEMETRY=1`, `DISABLE_ERROR_REPORTING=1`,
  `DISABLE_FEEDBACK_COMMAND=1`, and
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`.
- Do not invoke `/feedback` on any trial.
- Enable account-level training opt-out before data collection.
- Run destructive seeded-error trials only inside sandboxed VMs with canary
  sentinels.
- Track usage and report budget-limited cells under the SAP stopping rule
  rather than switching accounts or bypassing vendor limits.

**Disclosure log:** An Anthropic disclosure email is sent as part of the
pre-tag workflow. Date, recipient, and response summary appear in the
tagged version of this document.

## OpenAI - configs #3 and #4

**Configs:** Codex x `gpt-5.5`; Codex x `gpt-5.4-mini`.

**Access path:** ChatGPT Business subscription via the first-party Codex CLI
in non-interactive mode (`codex exec --json`).

**Operative sources:**

- ChatGPT Business Services Agreement:
  https://openai.com/policies/services-agreement
- Usage Policies: https://openai.com/policies/usage-policies
- Consumer Terms of Use for cross-reference:
  https://openai.com/policies/row-terms-of-use
- Codex CLI documentation: https://developers.openai.com/codex/cli
- Codex CLI authentication documentation:
  https://developers.openai.com/codex/auth
- Codex CLI pricing and rate caps:
  https://developers.openai.com/codex/pricing
- Sharing and Publication Policy:
  https://openai.com/policies/sharing-publication-policy

**Resolved gate as of 2026-05-27.** The working decision is KEEP: ChatGPT
Business is governed by the Services Agreement, and the relevant restriction
uses "permitted through the Services" framing rather than the Consumer Terms'
API-only framing. The benchmark treats `codex exec --json` as OpenAI's
documented automation interface for the Codex service, not as direct HTTP API
use.

**Methodology interpretation.** The OpenAI arm uses a supported first-party
Codex CLI path, with no third-party client, no output distillation, no
fine-tuning, and no competing-model training. Outputs are used only for
benchmark scoring, qualitative analysis, replication data, and research
publication.

**Compliance measures:**

- Throttle to roughly 50% of documented per-5-hour ChatGPT Business caps.
- Use one ChatGPT Business workspace seat for the study.
- Do not share logins, multiplex sessions, or run parallel browser sessions on
  the same account during data collection.
- Use `codex exec --json` only; do not use third-party Codex clients.
- Run seeded-error trials in disposable VMs; never use dangerous bypass flags
  on the researcher's workstation.

**Disclosure log:** An OpenAI disclosure email is sent as part of the
pre-tag workflow. Date, recipient, and response summary appear in the
tagged version of this document.

## Google - configs #5, #6, and #7

**Configs:** `agy x Gemini 3.1 Pro (High)`;
`agy x Gemini 3.5 Flash (Medium)`;
`agy x Claude Sonnet 4.6 (Thinking)`.

**Access path:** Google AI Ultra subscription via official first-party
Antigravity CLI (`agy --print`) and/or Antigravity SDK. This supersedes the
2026-05-26 Vertex-on-alt-GCP plan for V1 data collection.

**Operative sources:**

- Antigravity CLI overview: https://antigravity.google/docs/cli-overview
- Antigravity CLI usage: https://antigravity.google/docs/cli-using
- Antigravity SDK overview: https://antigravity.google/docs/sdk-overview
- Antigravity SDK launch post:
  https://antigravity.google/blog/introducing-google-antigravity-sdk
- Local installed `agy --help` output, observed 2026-05-27; replicators should
  verify against their installed `agy` version before running Google-arm
  trials.
- Google Cloud Generative AI Prohibited Use Policy:
  https://policies.google.com/terms/generative-ai/use-policy
- Google AI Developer Forum OpenClaw enforcement report:
  https://discuss.ai.google.dev/t/account-restricted-without-warning-google-ai-ultra-oauth-via-openclaw/122778

**Methodology interpretation.** Official `agy --print` and the Antigravity
SDK are documented first-party scripted/programmatic surfaces for Antigravity.
This benchmark stays inside those surfaces: no extracted OAuth tokens, no
third-party bridge tools, no resale, no shared credentials, and no private API
clients. Public enforcement evidence reviewed so far clusters around
third-party OAuth/private-API bridge tools, not official `agy` or the
Antigravity SDK.

**Compliance measures:**

- Use only official Google tooling for the Google arm.
- Do not use third-party OAuth bridges such as OpenClaw, opencode, or
  cockpit-tools-style wrappers.
- Throttle to roughly 50% of documented or observed plan limits.
- Pin agy model labels exactly as recorded in `docs/VERSIONS.md`.
- Verify model routing at trial start.
- Use sandboxed VMs and canary sentinels for destructive seeded-error trials,
  including the agy-specific scratch-path canary documented in the SAP.
- Report budget- or access-limited cells via the pre-registered stopping rule
  rather than changing accounts or bypassing vendor controls.

**Disclosure log:** No pre-tag disclosure email currently required for Google
because the V1 access path uses documented first-party subscription CLI / SDK
surfaces. Any vendor contact or enforcement response during the study is
recorded in the operations log and, if methodology-relevant, in
[`../DEVIATIONS.md`](../DEVIATIONS.md).

## Cross-Cutting Measures

These apply across all three arms:

1. No account sharing.
2. No third-party CLI or OAuth-bridge tools.
3. No backup accounts.
4. Sandbox isolation for destructive trials.
5. Redaction review before publishing transcripts or trial logs.
6. Daily operations logging for trial counts, rates observed, anti-abuse or
   rate-limit messages, model-routing observations, and any served-model
   mismatch.
7. Access-limited cells are reported as such; the study proceeds with partial
   arm truncation if a vendor-side limit prevents the SAP-derived N.

## Replicator Note

A team reproducing this benchmark on different subscription or API access
should substitute its own access path here, re-verify current vendor terms,
and log any divergence before running trials. Vendor terms can change; the
pre-registration tag records the decision-state used for this study, not a
permanent interpretation of any vendor policy.
