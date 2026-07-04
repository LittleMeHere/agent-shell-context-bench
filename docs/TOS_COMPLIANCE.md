# TOS / AUP Compliance - vendor access paths for this benchmark

This document records the vendor access paths the benchmark intends to use,
the methodology interpretation behind each path, and the compliance measures
applied. It is deliberately conservative: the access-path decisions are part
of the public pre-registration record, and the verbatim-clause evidence below
anchors each interpretation to retrievable source text.

The compliance posture for each vendor is locked at pre-registration tag time.
Any post-tag change to access path, account type, or compliance measure is
recorded as a deviation in [`../DEVIATIONS.md`](../DEVIATIONS.md).

## Evidence Status

The verbatim-clause evidence pass was executed on **2026-06-09** (see
`docs/DECISIONS.md` 2026-06-09). Method: each cited source was retrieved
live by direct HTTP GET (with content cross-checked against the raw page
HTML for every load-bearing clause), and archive.org snapshot URLs were
recorded from the Wayback Machine availability API the same day. Quotes
below preserve source wording exactly; typography (quote marks, dashes)
and whitespace are normalized, and bracketed ellipses mark elisions.

Pre-tag evidence checklist (last updated 2026-07-02; researcher
browser-capture sessions 2026-06-10 and 2026-06-11). Tag
`pre-registration-v1` was cut 2026-06-13T00:40:39Z; items 1, 2, and 4
closed before the tag, and items 3 and 5 remain standing (item 3 is a
snapshot-coverage / optional-hardening note, item 5 is a
data-collection-start obligation, partially re-confirmed 2026-07-02 with a
capture residual noted in the item):

1. **[DONE 2026-06-11] Disclosure to all three vendors.** Anthropic and
   OpenAI disclosure emails sent 2026-06-11; the Google disclosure was
   delivered 2026-06-11 as a reply inside the Google One support case
   filed 2026-06-10. Vendor responses are logged in the per-vendor
   disclosure logs as they arrive.
2. **[DONE 2026-06-11] Local PDF/page capture set complete.** Captured: OpenAI
   Sharing and Publication Policy, Services Agreement, Usage Policies,
   and consumer Terms of Use; Anthropic Consumer Terms, Claude Code
   legal-and-compliance, Claude Code headless docs, and the Agent SDK
   credit article; Google Prohibited Use Policy and the three Antigravity
   docs pages. The Anthropic Usage Policy page, the
   enforcement-evidence forum thread (full-page and print formats, plus
   two fresh content-verified archive.org snapshots), and the Antigravity
   SDK launch blog post were captured 2026-06-11, completing the set.
   The three Codex docs pages would not print from the browser
   and are preserved as first-party page-copy markdown in the off-repo
   archive instead. (Screenshots/PDFs are deliberately not committed to
   this public repo.)
3. **Snapshot coverage.** The OpenAI Sharing and Publication Policy has
   no archive.org snapshot (Save Page Now produced no capture on
   2026-06-09 or 2026-06-10); its retrieval is evidenced by a live
   capture and a PDF in the off-repo evidence archive. The Antigravity
   SDK repository's snapshot (2026-05-28) predates the README retrieval
   (2026-06-10); the retrieved README copy is preserved in the off-repo
   archive, and a fresh save is optional hardening. Every other cited
   web source has a snapshot. Optional hardening: also archive the
   first-party markdown variants of the two code.claude.com pages
   (append `.md` to each URL) because the archived HTML replays of those
   pages can error after initial render due to client-side hydration.
4. **[RESOLVED 2026-06-11] Verbatim text capture of the
   antigravity.google doc pages.** Rendered content for the CLI overview,
   CLI usage, and SDK overview pages was captured by researcher browser
   PDF on 2026-06-11 and is quoted in the Google section. The SDK launch
   blog post is covered by an archive.org snapshot; its PDF rides with
   item 2.
5. **[PARTIALLY RE-CONFIRMED 2026-07-02] Re-confirm the Anthropic Agent SDK
   credit policy at data-collection start** - the documented billing basis
   for headless usage was slated to change on 2026-06-15, but Anthropic
   paused that change on its effective day: Agent SDK / `claude -p` usage
   continues to draw from subscription usage limits, the same basis that was
   in force at tag time (see the dated update in the Anthropic section).
   Residual before collection: a live raw-HTML-cross-checked capture and a
   fresh archive.org snapshot of the credit article (the 2026-07-02 check
   ran in an environment whose network policy blocked direct HTTPS to
   support.claude.com and archive.org), and a repeat of this re-confirmation
   if collection starts materially later than 2026-07-02.

## Anthropic - configs #1 and #2

**Configs:** Claude Code x `claude-opus-4-8`; Claude Code x
`claude-sonnet-4-6`.

**Access path:** Consumer subscription tier (Claude Max) via the first-party
`claude` CLI in headless mode (`claude -p`).

**Operative sources:**

- Consumer Terms of Service: https://www.anthropic.com/legal/consumer-terms
- Usage Policy (the page self-identifies as "also referred to as our
  'Acceptable Use Policy' or 'AUP'"): https://www.anthropic.com/legal/aup
- Claude Code legal and compliance documentation:
  https://code.claude.com/docs/en/legal-and-compliance
- Claude Code headless mode documentation:
  https://code.claude.com/docs/en/headless
- Claude Code Agent SDK credit policy:
  https://support.claude.com/en/articles/15036540

**Verbatim operative clauses (retrieved 2026-06-09):**

- Consumer Terms of Service, "Effective October 8, 2025". The prohibited-use
  list restricts automated access *with an explicit-permission carve-out*:
  > "Except when you are accessing our Services via an Anthropic API Key or
  > where we otherwise explicitly permit it, to access the Services through
  > automated or non-human means, whether through a bot, script, or
  > otherwise."
- Consumer Terms of Service, account integrity:
  > "You may not share your Account login information, Anthropic API key, or
  > Account credentials with anyone else. You also may not make your Account
  > available to anyone else."
- Claude Code legal-and-compliance page - the explicit first-party permission
  the carve-out above points at, plus the governing-terms routing:
  > "Your use of Claude Code is subject to: [...] Consumer Terms of Service -
  > for Free, Pro, and Max users."
  > "OAuth authentication is intended exclusively for purchasers of Claude
  > Free, Pro, Max, Team, and Enterprise subscription plans and is designed
  > to support ordinary use of Claude Code and other native Anthropic
  > applications."
  > "Anthropic does not permit third-party developers to offer Claude.ai
  > login or to route requests through Free, Pro, or Max plan credentials on
  > behalf of their users."
  > "Claude Code usage is subject to the Anthropic Usage Policy. Advertised
  > usage limits for Pro and Max plans assume ordinary, individual usage of
  > Claude Code and the Agent SDK."
- Claude Code headless documentation - headless mode is a documented
  first-party feature:
  > "Add the `-p` (or `--print`) flag to any `claude` command to run it
  > non-interactively."
- Usage Policy, "Effective September 15, 2025", restriction relevant to the
  no-bypass compliance measures:
  > "Intentionally bypass capabilities, restrictions, or guardrails
  > established within our products for the purposes of instructing the model
  > to produce harmful outputs (e.g., jailbreaking or prompt injection)
  > without prior authorization from Anthropic"
- Agent SDK credit policy article ("Use the Claude Agent SDK with your
  Claude plan") - **billing basis for headless usage changes on
  2026-06-15**:
  > "Starting June 15, 2026, Agent SDK and `claude -p` usage on subscription
  > plans will draw from a new monthly Agent SDK credit, separate from your
  > interactive usage limits."
  (quoted from the notice on the Claude Code documentation pages, retrieved
  2026-06-09)
  > "Claude Agent SDK and `claude -p` usage no longer counts toward your
  > Claude plan's usage limits."
  > "Your subscription usage limits stay the same and stay reserved for
  > interactive use of Claude Code, Claude Cowork, and Claude."

  **Update 2026-07-02 (item 5 re-confirmation, partial):** Anthropic paused
  the credit change on its effective day. The Help Center article now opens
  with a pause notice - "We're pausing the changes to Claude Agent SDK usage
  described below." - and Agent SDK / `claude -p` usage continues to draw
  from the subscription's usage limits, i.e. the pre-change basis that was
  in force at the pre-registration tag. Evidence: (i) first-party `.md`
  variants of the Claude Code legal-and-compliance, headless, costs,
  Agent-SDK-overview, and setup pages retrieved live 2026-07-02 - every
  operative clause quoted above is unchanged verbatim, and the "Starting
  June 15, 2026" credit notice no longer appears on any of those pages;
  (ii) the article's pause wording as surfaced by search-indexed content
  and multiple independent same-day reports (e.g. The New Stack, "Anthropic
  pauses Claude Agent SDK subscription change on day it was due to take
  effect",
  https://thenewstack.io/anthropic-pauses-claude-agent-sdk-subscription-change/;
  Hacker News item 48546618). Limitation: the retrieval environment's
  network egress policy blocked direct HTTPS to support.claude.com and
  archive.org, so no live raw-HTML cross-check or fresh snapshot of the
  article itself was possible from that environment; that capture remains
  owed (checklist item 5 residual). Because the pause leaves the tag-time
  access path, billing basis, and compliance measures in force, this is an
  evidence update, not a `DEVIATIONS.md` entry. Incidental observation from
  the live 2026-07-02 costs page: Pro/Max plans now document a user-side
  monthly spend cap on usage credits ("you can set a monthly spend limit on
  usage credits with the `/usage-credits` command") - a user-configurable
  cap, not a change to the plan-limits billing basis.

**Source capture register (Anthropic):**

| Source | Retrieved | Vendor date | archive.org snapshot |
|---|---|---|---|
| Consumer Terms of Service | 2026-06-09 (live; raw-HTML cross-checked) | Effective October 8, 2025 | http://web.archive.org/web/20260609181517/https://www.anthropic.com/legal/consumer-terms |
| Usage Policy (AUP) | 2026-06-09 (live; raw-HTML cross-checked) | Effective September 15, 2025 | http://web.archive.org/web/20260609180317/https://www.anthropic.com/legal/aup |
| Claude Code legal-and-compliance | 2026-06-09 (live; first-party `.md` variant also captured) | n/a (docs page) | http://web.archive.org/web/20260610022333/https://code.claude.com/docs/en/legal-and-compliance (replay may render then error - client-side hydration; capture verified present) |
| Claude Code headless docs | 2026-06-09 (live; first-party `.md` variant also captured) | n/a (docs page) | http://web.archive.org/web/20260610035144/https://code.claude.com/docs/en/headless (same replay caveat; capture verified present) |
| Agent SDK credit policy article | 2026-06-09 (live) | policy change effective June 15, 2026 | https://web.archive.org/web/20260610022536/https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan (content-bearing capture verified 2026-06-10) |
| Agent SDK credit policy article - re-check | 2026-07-02 (indirect: direct HTTPS blocked by retrieval-env egress policy; pause corroborated via search-indexed article content, independent same-day reports, and the live docs-page sweep below) | change paused on 2026-06-15, its effective day | fresh snapshot owed at collection start (archive.org unreachable from retrieval env; item 5 residual) |
| Claude Code docs `.md` variants: legal-and-compliance, headless, costs, agent-sdk/overview, setup | 2026-07-02 (live) | n/a (docs pages) | not snapshotted this pass (archive.org unreachable from retrieval env) |

**Methodology interpretation.** Anthropic documents headless Claude Code use
as a first-party feature, and the Consumer Terms' automated-access
restriction carries an express carve-out for access Anthropic "otherwise
explicitly permit[s]". The Claude Code documentation states OAuth
authentication is *intended for* subscription purchasers using Claude Code
and native Anthropic applications, and that advertised limits assume
"ordinary, individual usage of Claude Code and the Agent SDK". The benchmark
therefore treats bounded `claude -p` usage on a Claude Max subscription,
within documented limits, as inside the documented first-party surface:
ordinary individual research use, no credential sharing, no third-party
credential bridges.

**Compliance measures:**

- Throttle to roughly 50% of the documented limits that govern headless
  usage at run time. The documented basis was slated to change on 2026-06-15
  to a monthly Agent SDK credit, but Anthropic paused that change on its
  effective day (see the 2026-07-02 update above): as of 2026-07-02 the
  documented basis remains the per-tier subscription usage limits that were
  in force at tag time. Re-confirm the documented allocation at
  data-collection start and record it in the operations log.
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
pre-tag workflow. Date, recipient role, and response summary appear in the
tagged version of this document. Status: sent 2026-06-11 to Anthropic's
published support contact, with the Usage Policy safety-notification
contact copied; response pending at the time of this entry.

## OpenAI - configs #3 and #4

**Configs:** Codex x `gpt-5.5`; Codex x `gpt-5.4-mini`.

**Access path:** ChatGPT Business subscription via the first-party Codex CLI
in non-interactive mode (`codex exec --json`).

**Operative sources:**

- OpenAI Services Agreement: https://openai.com/policies/services-agreement
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

**Resolved gate, re-verified with verbatim text 2026-06-09.** The decision is
KEEP. The Services Agreement ("Updated: December 1, 2025", "Effective:
January 1, 2026") states its own scope:

> "This OpenAI Services Agreement only applies to use of OpenAI's APIs,
> ChatGPT Enterprise, ChatGPT Business, ChatGPT for Clinicians, and other
> services for customers who are businesses and developers, and does not
> apply to OpenAI services used by consumers or individuals unless specified
> above."

so ChatGPT Business is governed by the Services Agreement. Its section 3.3
("Restrictions. Customer will not, and will not permit End Users to: [...]")
contains the operative items:

> "(f) extract data from the Services other than as permitted through the
> Services;"
> "(h) interfere with or disrupt the Services, including circumvent any rate
> limits or restrictions or bypass any protective measures or safety
> mitigations for the Services;"
> "(i) violate or circumvent Usage Limits or otherwise configure the
> Services to avoid Usage Limits."

Clause 3.3(f) is the "permitted through the Services" framing the KEEP
decision turns on: collecting the structured output that the documented
first-party Codex CLI itself emits (`codex exec --json`) is extraction *as
permitted through the Services*. Clauses 3.3(h) and 3.3(i) anchor the
throttling and no-bypass measures below.

**Cross-reference update (supersedes the 2026-05-27 description).** The
consumer Terms of Use were republished "Effective: January 1, 2026". The
earlier analysis cited a consumer clause lettered c(iv) with "except as
permitted through the API" framing; the current consumer text instead
prohibits, without lettering and without a carve-out:

> "Automatically or programmatically extract data or Output (defined
> below)."

The contrast with the Services Agreement is therefore sharper than at the
2026-05-27 review: the consumer terms now contain a flat programmatic-
extraction prohibition, while the Services Agreement governing ChatGPT
Business permits extraction "as permitted through the Services". This
strengthens the rationale for running the OpenAI arm on a Business
subscription rather than a consumer plan.

**Further verbatim support (retrieved 2026-06-09):**

- Codex CLI documentation - scripted use is a documented first-party
  feature, and Business plans include Codex:
  > "Automate repeatable workflows by scripting Codex with the `exec`
  > command."
  > "ChatGPT Plus, Pro, Business, Edu, and Enterprise plans include Codex."
- Codex authentication documentation:
  > "Codex cloud requires signing in with ChatGPT. The Codex CLI and IDE
  > extension support both sign-in methods."
- Codex pricing documentation - the documented Business-plan caps the
  benchmark throttles against (Business usage-limit table, researcher page
  capture 2026-06-11): local messages per 5-hour window "15-80" (GPT-5.5)
  and "60-350" (GPT-5.4-mini); and:
  > "Business, Edu, and Enterprise plans with flexible pricing can purchase
  > additional workspace credits to continue using Codex."
  The same page's feature-availability matrix lists "Codex SDK, `codex
  exec`, and scriptable workflows" as available on ChatGPT Business -
  first-party confirmation that scripted `exec` use is an included
  Business-plan feature under ChatGPT sign-in.
- Codex authentication documentation (researcher page capture 2026-06-11)
  also states:
  > "We recommend API key authentication for programmatic Codex CLI
  > workflows, such as CI/CD jobs."
  Disclosed for completeness: this is a recommendation, not a restriction,
  and the API-key option is framed by the pricing page as "Great for
  automation in shared environments like CI." This study's scripted trials
  run locally on a single Business seat, not in a shared or public CI
  environment, and the feature matrix above lists scripted `exec`
  workflows as included on the Business plan.
- Usage Policies, "Effective: October 29, 2025":
  > "We hold people accountable for inappropriate use of our services, and
  > breaking or circumventing our rules and safeguards may mean you lose
  > access to our systems or experience other penalties."
- Sharing and Publication Policy, "Updated: November 14, 2022":
  > "Accordingly, we welcome research publications related to the OpenAI
  > API."
  (The policy's research section predates Codex; it is retained as the
  closest published OpenAI statement on research publication.)

**Source capture register (OpenAI):**

| Source | Retrieved | Vendor date | archive.org snapshot |
|---|---|---|---|
| Services Agreement | 2026-06-09 (live; raw-HTML cross-checked; page blocks some automated fetchers) | Updated December 1, 2025; Effective January 1, 2026 | http://web.archive.org/web/20260609222032/https://openai.com/policies/services-agreement/ |
| Usage Policies | 2026-06-09 (live; raw-HTML cross-checked) | Effective October 29, 2025 | http://web.archive.org/web/20260607080512/https://openai.com/policies/usage-policies/ |
| Consumer Terms of Use (cross-ref) | 2026-06-09 (live; raw-HTML cross-checked) | Published January 1, 2026; Effective January 1, 2026 | http://web.archive.org/web/20260607080512/https://openai.com/policies/row-terms-of-use/ (shares a crawl-batch timestamp with the Usage Policies snapshot; both URLs verified 2026-06-12 to resolve to their own distinct documents) |
| Sharing and Publication Policy | 2026-06-09 (live; raw-HTML cross-checked) | Updated November 14, 2022 | none - Save Page Now produced no capture on 2026-06-09 or 2026-06-10; retrieval evidenced by live capture + PDF in the off-repo evidence archive |
| Codex CLI docs | 2026-06-09 (live) | n/a (docs page) | http://web.archive.org/web/20260602180528/https://developers.openai.com/codex/cli |
| Codex auth docs | 2026-06-09 (live) | n/a (docs page) | https://web.archive.org/web/20260610022703/https://developers.openai.com/codex/auth (content-bearing capture verified 2026-06-10) |
| Codex pricing docs | 2026-06-09 (live) | n/a (docs page) | http://web.archive.org/web/20260607123022/https://developers.openai.com/codex/pricing |

**Methodology interpretation.** The OpenAI arm uses a supported first-party
Codex CLI path, with no third-party client, no output distillation, no
fine-tuning, and no competing-model training (Services Agreement 3.3(e)
restricts using Output to "develop artificial intelligence models that
compete with OpenAI's products and services"; this benchmark trains
nothing). Outputs are used only for benchmark scoring, qualitative
analysis, replication data, and research publication.

**Compliance measures:**

- Throttle to roughly 50% of the documented Business-plan local-message
  caps per 5-hour window (documented ranges: "15-80" / 5h for the frontier
  tier `gpt-5.5`, "60-350" / 5h for the workhorse tier `gpt-5.4-mini`; use
  the observed account-specific cap from the operations log as the
  denominator).
- Use one ChatGPT Business workspace seat for the study.
- Do not share logins, multiplex sessions, or run parallel browser sessions on
  the same account during data collection.
- Use `codex exec --json` only; do not use third-party Codex clients.
- Run seeded-error trials in disposable VMs; never use dangerous bypass flags
  on the researcher's workstation.

**Disclosure log:** An OpenAI disclosure email is sent as part of the
pre-tag workflow. Date, recipient role, and response summary appear in the
tagged version of this document. Status: sent 2026-06-11 to the
legal-notices contact designated by Services Agreement section 16.5, with
the Business workspace identifiers included per OpenAI's support guidance;
response pending at the time of this entry.

## Google - configs #5, #6, and #7

**Configs:** `agy x Gemini 3.1 Pro (High)`;
`agy x Gemini 3.5 Flash (Medium)`;
`agy x Claude Sonnet 4.6 (Thinking)`.

**Access path:** Google AI Ultra subscription via the official
first-party Antigravity CLI (`agy --print`) - the sole V1 invocation
surface (the first-party Antigravity SDK was ruled out for V1 on
2026-06-10; see the invocation-surface note below). This supersedes the
2026-05-26 Vertex-on-alt-GCP plan for V1 data collection.

**Operative sources:**

- Antigravity CLI overview: https://antigravity.google/docs/cli-overview
- Antigravity CLI usage: https://antigravity.google/docs/cli-using
- Antigravity SDK overview: https://antigravity.google/docs/sdk-overview
- Antigravity SDK launch post:
  https://antigravity.google/blog/introducing-google-antigravity-sdk
- Local installed `agy --help` output (primary source for the CLI-surface
  claim; see below). Replicators should verify against their installed `agy`
  version before running Google-arm trials.
- Antigravity SDK public repository (API documentation; Apache License
  2.0; installs as the `google-antigravity` package from PyPI):
  https://github.com/google-antigravity/antigravity-sdk-python
- Google Cloud Generative AI Prohibited Use Policy:
  https://policies.google.com/terms/generative-ai/use-policy
- Google AI Developer Forum OpenClaw enforcement report:
  https://discuss.ai.google.dev/t/account-restricted-without-warning-google-ai-ultra-oauth-via-openclaw/122778

**Verbatim operative clauses (retrieved 2026-06-09):**

- Local `agy --help` (captured on agy 1.0.4, 2026-06-09; the same flag
  lines re-confirmed verbatim on agy 1.0.7 after the 2026-06-12 update;
  whitespace
  collapsed) - non-interactive mode is a documented first-party CLI surface:
  > "-p  Short alias for --print"
  > "--print  Run a single prompt non-interactively and print the response"
- Antigravity CLI overview docs page (rendered content captured by
  researcher browser PDF, retrieved 2026-06-11; PDF in the off-repo
  evidence archive):
  > "The Antigravity CLI is the lightweight Terminal User Interface (TUI)
  > surface of Antigravity."
  Its platform-comparison table lists the CLI's "Workflow focus" as "Fast
  local iterations, SSH, headless", and its integration section states:
  > "Shared agent harness: Both environments run on the exact same agent
  > core."
  (The latter also supports the pre-registered S6 same-model
  harness-control framing.)
- Antigravity CLI usage docs page (researcher browser capture 2026-06-11)
  documents the settings file and launch-flag overrides the harness relies
  on:
  > "Configuration File: Stored in a plain JSON file
  > ~/.gemini/antigravity-cli/settings.json"
  > "Overrides: Certain settings can be overridden at launch via CLI flags
  > (e.g., --sandbox or --dangerously-skip-permissions)."
- Antigravity SDK overview docs page (researcher browser capture
  2026-06-11):
  > "The Antigravity SDK is a programmatic Python framework designed to
  > build, test, and run autonomous AI agents. It extends the same core
  > agent harness that powers the Antigravity CLI and Antigravity 2.0 [...]"
  No authentication or plan statement appears on the page, so the SDK auth
  caveat in the invocation-surface note below stands.
- Generative AI Prohibited Use Policy, "Last Modified: December 17, 2024"
  (raw-HTML cross-checked):
  > "Circumvention of abuse protections or safety filters -- for example,
  > manipulating the model to contravene our policies."
- Antigravity SDK README (GitHub `main`, raw file retrieved 2026-06-10):
  > "The Google Antigravity SDK is a Python SDK for building AI agents
  > powered by Antigravity and Gemini. It provides a secure, scalable, and
  > stateful infrastructure layer that abstracts the agentic loop [...]"
  Note: the README's quickstart authenticates via a `GEMINI_API_KEY`
  environment variable; no statement about subscription (AI Ultra)
  authentication for the SDK was found in the README.
- Enforcement-evidence forum thread (title verbatim: "Account Restricted
  Without WARNING- Google AI Ultra / OAuth via OpenClaw"), quoting the
  Google staff response reproduced in-thread:
  > "the use of your credentials within the third-party tool 'open claw'
  > for testing purposes constitutes a violation of the Google Terms of
  > Service. This is due to the use of Antigravity servers to power a
  > non-Antigravity product."
  This confirms the enforcement cluster is third-party OAuth/private-API
  bridge tooling ("a non-Antigravity product"), not official first-party
  `agy` / Antigravity SDK surfaces - the access path this benchmark uses.

**Source capture register (Google):**

| Source | Retrieved | Vendor date | archive.org snapshot |
|---|---|---|---|
| Generative AI Prohibited Use Policy | 2026-06-09 (live; raw-HTML cross-checked) | Last Modified December 17, 2024 | http://web.archive.org/web/20260608063432/https://policies.google.com/terms/generative-ai/use-policy |
| Local `agy --help` output | 2026-06-09 (agy 1.0.4); flag lines re-confirmed on agy 1.0.7, 2026-06-12 | n/a | n/a (local primary source; transcript in researcher's off-repo evidence archive) |
| Antigravity SDK repository (GitHub) | 2026-06-10 (raw README from branch `main`; copy preserved in the off-repo archive) | n/a (repository) | http://web.archive.org/web/20260528073045/https://github.com/google-antigravity/antigravity-sdk-python (predates the README retrieval by ~2 weeks; fresh save is optional hardening) |
| Antigravity CLI overview docs | 2026-06-09 (automated: app shell); 2026-06-11 researcher browser PDF (rendered content captured; quoted above) | unknown | https://web.archive.org/web/20260610022757/https://antigravity.google/docs/cli-overview (replays fully in a browser - sub-resources captured; raw HTML is an application shell, so text is not machine-extractable) |
| Antigravity CLI usage docs | 2026-06-09 (automated: app shell); 2026-06-11 researcher browser PDF (rendered content captured; quoted above) | unknown | https://web.archive.org/web/20260610022857/https://antigravity.google/docs/cli-using (same: full browser replay verified by the researcher; not machine-extractable) |
| Antigravity SDK overview docs | 2026-06-09 (automated: app shell); 2026-06-11 researcher browser PDF (rendered content captured; quoted above) | unknown | http://web.archive.org/web/20260607145444/https://antigravity.google/docs/sdk-overview |
| Antigravity SDK launch post | 2026-06-09 (HTTP 200; client-side-rendered shell - no extractable text) | unknown | http://web.archive.org/web/20260520213301/https://antigravity.google/blog/introducing-google-antigravity-sdk |
| Forum enforcement thread | 2026-06-09 (live); full-thread + staff-post PDFs captured 2026-06-11 | thread ongoing | full thread: https://web.archive.org/web/20260612024424/https://discuss.ai.google.dev/t/account-restricted-without-warning-google-ai-ultra-oauth-via-openclaw/122778 ; staff reply (post 9): https://web.archive.org/web/20260612022826/https://discuss.ai.google.dev/t/account-restricted-without-warning-google-ai-ultra-oauth-via-openclaw/122778/9 (both verified content-bearing, incl. the quoted staff response; an earlier pre-study-state snapshot was attempted but did not resolve on archive.org — the operative captures are the two 2026-06-12 snapshots above) |

**Capture caveat (flagged 2026-06-09; content resolved 2026-06-11):** the
four antigravity.google doc pages are client-side-rendered, so automated
retrieval returns an application shell. Rendered content for three of the
four (CLI overview, CLI usage, SDK overview) was captured by researcher
browser PDF on 2026-06-11 and is quoted above; archive.org snapshots
exist for all four and replay fully in a browser, but are not
machine-extractable. All four pages now have researcher PDF captures
(the launch post's PDF, added 2026-06-11, is a capture-only artifact -
no quote from it is load-bearing). Notably, none of the captured pages
documents the
`--print` flag itself - the pages document a "headless" workflow focus,
the settings file, and launch-flag overrides - so the in-tool `agy
--help` output quoted above remains the documentation of record for the
non-interactive flag.

**Invocation-surface note (added 2026-06-10, see `docs/DECISIONS.md`
2026-06-10; capture status updated 2026-06-11):** the public docs pages
document a "headless" workflow focus, the settings file, and launch-flag
overrides (rendered content captured 2026-06-11, quoted above) but do not
document the `--print` flag itself; the in-tool `agy --help` output
quoted above is the documented interface description for the CLI
surface. The Antigravity SDK
is publicly documented (GitHub/PyPI), but its README quickstart
authenticates via `GEMINI_API_KEY`, and subscription (AI Ultra)
authentication for the SDK is unverified. V1 therefore treats
subscription `agy --print` as the **primary** Google-arm invocation
surface; a move to SDK-with-API-key would change the access path
(governing terms and billing model) and requires a logged pre-tag
decision or, after the tag, a `DEVIATIONS.md` entry. Update 2026-06-10
(later): the researcher ruled the SDK out for V1 on budget grounds (its
documented authentication path is API-key-based and the study has no API
budget), making subscription `agy --print` the sole planned Google-arm
invocation surface for V1.

**Methodology interpretation.** Official `agy --print` is the documented
first-party scripted surface this benchmark uses; the Antigravity SDK,
while also a documented first-party programmatic surface, is out of V1
scope per the invocation-surface note above. The benchmark stays inside
the first-party CLI surface: no extracted OAuth tokens, no
third-party bridge tools, no resale, no shared credentials, and no private API
clients. Public enforcement evidence reviewed (including the verbatim staff
response quoted above) clusters around third-party OAuth/private-API bridge
tools, not official `agy` or the Antigravity SDK.

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

**Disclosure log:** Per researcher decision 2026-06-09 (recorded in
`docs/DECISIONS.md`), a Google disclosure email is sent as part of the
pre-tag workflow, mirroring the Anthropic and OpenAI arms. This supersedes
the earlier posture that no Google pre-tag disclosure was required. Date,
recipient role, and response summary appear in the tagged version of this
document. Status: a support case was filed 2026-06-10 via the Google One membership
support flow, signed in to the study account (case reference held in the
researcher's private records); a human support response was received
2026-06-10; the full disclosure was delivered 2026-06-11 as a reply inside
that case thread (superseding the earlier plan to email a separate
published support address); further response pending at the time of this
entry. Any vendor contact or enforcement response during the study is
additionally recorded in the operations log and, if methodology-relevant, in
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
8. Pre-tag disclosures are sent to all three vendors — email for Anthropic
   and OpenAI, a Google One support-case reply for Google (per researcher
   decision 2026-06-09); send dates and response summaries are logged in the
   per-vendor disclosure logs above.

## Replicator Note

A team reproducing this benchmark on different subscription or API access
should substitute its own access path here, re-verify current vendor terms,
and log any divergence before running trials. Vendor terms can change; the
pre-registration tag records the decision-state used for this study, not a
permanent interpretation of any vendor policy. Two dated examples from this
study's own evidence pass: the OpenAI consumer Terms of Use were republished
effective 2026-01-01 with materially different automated-access wording than
the version analyzed six weeks earlier, and Anthropic's headless-usage
billing basis changes on 2026-06-15.
