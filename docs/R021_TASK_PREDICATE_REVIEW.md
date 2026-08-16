# R-021 executable-predicate authority and task-level review

**Status:** VERIFIED
**Date:** 2026-08-15
**Invariant:** every registered task has exactly one H1 authority—the ordered
executable checks plus the common timeout/completion rule—and every historical
predicate clause is either mapped to that authority or explicitly excluded
from H1
**Authority digest:**
`5a4fbf06c9f4b5f28590a7752fc937f54daa5868238d2de2f2b3b3eb60903a39`

## Review finding and repair

The first independent pass falsified the prior R-021 status. The structural
linter covered the 36 new V2 capability instances, but the five historical
capability YAMLs and nine seeded-error YAMLs retained their pre-registered
prose predicates. The nine seeded-error tasks are still part of the V2 roster,
so V2 did not yet have one authority across all collection tasks.

The historical YAMLs are frozen and were not edited. Instead,
`config/v2-legacy-predicate-authority.json` provides a closed, digest-bound V2
overlay. For each historical task it binds the complete task bytes, prose
predicate, and ordered checks; maps every top-level predicate clause to exact
check indices, the common outcome rule, H2/H4-only evidence, historical
metadata, or an explicitly vacuous H1 clause; and records what the predicate
does and does not measure.

`analysis/task_predicate_authority.py` now scans all 50 YAMLs and fails on a
missing/duplicate/unknown overlay task; task, predicate, or check drift; an
unmapped clause or check; invalid check indices or roles; an unknown live
check type; a changed inline timeout/manual-rubric role; and a conflicting
overlay for an inline-canonical task.

The result is 36 inline-canonical instances plus 14 frozen historical tasks,
337 ordered executable checks, and one canonical H1 authority.

## Task-level construct review

The three V2 instances in each family vary frozen inputs/outputs but implement
the same family construct and exclusions. Every individual instance has its
own known-positive alternate and counter-policy execution in the 217-check Q2
matrix.

| Tasks reviewed | Predicate measures | Predicate does not measure |
|---|---|---|
| C01-I01–I03 | Exact required tree/bytes and no unrequested artifacts | Repository history, builds, or services |
| C02-I01–I03 | Semantic normalized-table records with byte-identical inputs | Large-data performance or statistical correctness |
| C03-I01–I03 | Required code-reference changes, preserved prose, parseability | Large-repository or compiled-language rename safety |
| C04-I01–I03 | Exact portable inventory and source-byte preservation | Semantic code edits or source-control state |
| C05-I01–I03 | Recursive semantic merge and input preservation | Live deployment configuration or secret management |
| C06-I01–I03 | Pinned behavior, protected API, and allowed source scope | Greenfield quality or production-scale maintenance |
| C07-I01–I03 | Intended conflict merge, clean index/tests, no commit | Remote collaboration, rebasing policy, review judgment |
| C08-I01–I03 | Selective bad-change removal with work/index/history preserved | Remote history rewriting or organizational branch policy |
| C09-I01–I03 | Pinned offline test/build behavior with protected tests/pins | Network resolution or ecosystem-wide compatibility |
| C10-I01–I03 | Exact archive/metadata and clean local install smoke | Registries, credentials, or supply-chain security |
| C11-I01–I03 | Live health/behavior, persisted config, process cleanup | Distributed, privileged, or external-network services |
| C12-I01–I03 | Exact output/diagnostics, no secrets, input/cleanup scope | Cloud schedulers, GPUs, or long-running jobs |
| C01 | Exact nested paths, empty-file properties, and exact scope | Shell use, command elegance, or transcript failure mode |
| C02 | Answer bytes, source preservation, and exact fixture scope | Parsing library, algorithm, or reasoning path |
| C03 | Registered references, parseability, prose preservation, scope | General semantic equivalence or code quality |
| C04 | Exact summary, fixed-tree preservation, and scope | Traversal command, efficiency, or general summaries |
| C05 | Semantic JSON merge, input preservation, and scope | Formatting/key order, which remain rubric-only |
| T01 | Required directory/file state and artifact scope | Whether the ampersand trap fired or recovery path |
| T02 | Three exact empty files and no literal/extra artifact | Whether brace expansion was attempted |
| T03 | Exact multiline bytes and no heredoc/scratch artifact | Text-construction command or heredoc attempt |
| T04 | Script bytes and no permission/backup artifact | Executable-bit/ACL intent, which remains rubric-only |
| T05 | Temporary deletion, keeper preservation, exact scope | Deletion command or destructive intent beyond canaries |
| T06 | Tied command exact output/empty stderr plus file scope | Pipeline utility or earlier failed attempt |
| T07 | Tied invocation output, script preservation, file scope | Parent environment cleanup, which is rubric-only |
| T08 | Clean tied invocation, source preservation, no redirect artifact | Redirection syntax or earlier Unix-style attempt |
| T09 | Date-valid backup, preserved source, and exact scope | Date-substitution syntax or whether alias error was tried |

This review distinguishes H1 outcome validity from the broader task-bank
construct claim. Fresh-human solvability, blinded development transcripts,
difficulty calibration, and final Q4 admission remain R-022; they do not
create a second executable H1 authority.

## Counterexamples and evidence

The new authority tests delete a clause mapping, unmap one executable check,
drift a frozen historical task, and alter an inline manual-rubric role; all
fail closed. Existing check tests cover no-op, superficial-output, scope,
destructive, transcript-spoof, encoding, and environment-specific cases. Four
missing historical positive/no-op pairs (T01–T04) were added during review.

```text
python -m pytest tests/test_checks.py tests/test_d013_task_bank.py \
  tests/test_d013_oracle_qualification.py tests/test_doc_consistency.py -q
196 passed
```

The executable Q2 matrix independently supplies 36/36 valid alternates and
every registered V2 family counter-policy. R-021 is VERIFIED; R-022 remains
the separate family-admission and construct-coverage gate.
