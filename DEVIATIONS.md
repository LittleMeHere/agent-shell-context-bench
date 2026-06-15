# Deviations log — agent-shell-context-bench

This file records every meaningful deviation from the pre-registered
methodology (`HYPOTHESIS.md` + `docs/SAP.md` + task YAMLs + harness
contracts + `docs/VERSIONS.md`) after the `pre-registration-v1` tag.

The deviation-vs-clarification policy is defined in `docs/SAP.md`
section "Deviation vs. clarification policy". Briefly: changes to
methodology go here as dated entries; implementation bug fixes go
in commit messages with a `Clarification:` prefix in the subject
line and do NOT require an entry here.

When a deviation occurs:
1. Add a new dated entry below this header section (newest at the
   top, above existing entries).
2. State concretely what was pre-registered, what was changed, and
   the reason for the change.
3. State whether the change affects already-collected data and how
   that data is handled (re-analyzed under the new rule; excluded;
   re-run).
4. Reference the commit hash that implemented the deviation.

Entry format (per the existing `docs/DECISIONS.md` convention):

```
## YYYY-MM-DD — <deviation title>

**Pre-registered rule:** <quote or cite the original methodology>
**Deviation:** <what was changed>
**Reason:** <why>
**Effect on collected data:** <re-analyzed / excluded / re-run / no effect yet>
**Implementing commit:** <hash>
```

---

## 2026-06-13 — Initial deviations log, established at the `pre-registration-v1` tag (commit `34104be`; log first scaffolded during 2026-05-25 drafting)

**No deviations from the pre-registered methodology as of this commit.**

This entry exists so the absence of deviations is legible: an empty
file would be ambiguous. This entry says explicitly that nothing has
happened.

The pre-registered methodology as of this commit is defined by:
- `HYPOTHESIS.md` (H1a, H1b, H2, H3, H4, reporting rules, IRR
  conditionality, code-E evidence requirement)
- `docs/SAP.md` (Configuration eligibility, Outcome construction,
  A1 / A1b / A1c, A2, A3a / A3b / A3c, A4, S1–S6 including the S3
  evidence requirement and the S4 hard IRR Interpretation rule,
  Stopping rules including the pilot-sizing formula and the
  variance-generalization disclosure, Deviation vs. clarification
  policy)
- `docs/VERSIONS.md` (V1 confirmatory matrix, pinned tool versions,
  IRR coders + same-vendor substitution rule, pre-tag gate status)
- The 14 task YAMLs in `tasks/capability/` (C01–C05) and
  `tasks/trap/` (seeded-error tasks T01–T09; folder path retained as
  internal legacy identifier per 2026-05-30 DECISIONS), each with its
  `binary_success_predicate`
  (split into `h1_binary_checks` vs `h2_rubric_signals` where the
  pre-registered intent exceeds what `success_checks` can verify
  from the snapshot alone)
- The harness contracts in `harness/` (`EnvironmentAdapter`,
  `AgentAdapter`, `checks.py`, `classifier/rubric.py`, the
  canary-sentinel system in `EnvironmentAdapter.canary_paths()` /
  `set_canaries()` / `check_canaries()`)
- The frozen IRR prompt at `scripts/irr_prompt.frozen.md` with its
  sha256 drift gate enforced by `scripts/irr_code.py`
  `check_prompt_frozen()`

Any change to the above after this tag is a candidate deviation per
the SAP "Deviation vs. clarification policy". Implementation bug
fixes that do not alter the methodology (e.g., adding a tool name to
the parser's `_SHELL_TOOLS` set) are clarifications, not deviations,
and are logged via commit message rather than here.
