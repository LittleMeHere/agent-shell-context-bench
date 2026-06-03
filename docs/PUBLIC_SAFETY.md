# Public safety hardening

This repository is public. The safety posture is layered:

- Tracked files in this repository (this document, `CLAUDE.md`,
  `AGENTS.md`, `.claude/settings.json`) define the working rules for
  AI coding agents operating inside this checkout.
- A CI workflow runs structural hygiene checks on every push and pull
  request.
- Untracked local hooks scan staged and to-be-pushed content for
  identity tokens before content reaches the local index or the public
  remote.
- GitHub branch protection on `main` is the maintainer-enforced last
  line of defense.

## CI checks

`.github/workflows/public-safety.yml` runs on pushes to `main` and on
pull requests. It verifies:

- the frozen IRR prompt at `scripts/irr_prompt.frozen.md` still matches
  the rubric render (the `--check-prompt` drift gate in
  `scripts/irr_code.py`);
- the full pytest suite passes, including the structural hygiene tests
  in `tests/test_public_safety.py` (no common secret filenames tracked,
  no raw smoke-trial JSONs tracked, no generated Python artifacts
  tracked, line-ending policy present in `.gitattributes`).

## Local hygiene hooks

Pre-commit and pre-push hooks at `.git/hooks/pre-commit` and
`.git/hooks/pre-push` scan staged and to-be-pushed content for identity
tokens that should not appear in public history. The hook scripts
contain the literal token list, so they are intentionally not tracked —
the patterns stay out of public commits.

A fresh clone does not include these hooks. The maintainer reinstalls
them locally on each clone; outside contributors are not expected to
maintain them.

## Agent safety

`AGENTS.md`, `CLAUDE.md`, and `.claude/settings.json` define the working
rules for AI coding agents operating inside this checkout. The rules
reduce the surface area for accidental destructive operations, hook
tampering, and silent methodology drift. They constrain agents that
respect the relevant configuration system; they are not a universal
sandbox for every tool or GUI client.

## Branch protection contract

The `main` branch on the public remote operates under a branch
protection contract:

- the `verify` CI check must pass before merge;
- force pushes to `main` are disallowed;
- deletion of `main` is disallowed.

Maintainer-side enforcement is via the GitHub branch protection rules
attached to `main`.
