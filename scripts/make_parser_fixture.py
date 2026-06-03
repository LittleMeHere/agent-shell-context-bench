"""Build a REDACTED parser fixture from a real trial log.

Real agent stdout embeds machine paths (e.g. C:\\Users\\<name>\\...), the
sandbox id, and a session UUID. None of that may enter a committed/public
fixture. This script applies a fixed, auditable redaction so the fixture is
reproducible and PII-free.

Usage:
  python scripts/make_parser_fixture.py <trial_log.json> <out.jsonl>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def redact(raw: str) -> str:
    """Strip machine PII. Handles every separator the username can appear
    behind: `\\` and `/` in real paths, and `-` in Claude Code's
    dash-flattened `.claude/projects/C--Users-<name>-...` directory name.
    """
    out = raw
    # Backslash form (JSON-escaped backslashes appear as `\\`).
    out = re.sub(r"Users\\+[^\\\"/]+", r"Users\\\\redacted-user", out)
    # Forward-slash form.
    out = re.sub(r"Users/[^/\"\\]+", "Users/redacted-user", out)
    # Dash-flattened form: Users-<username>-  (username = token until next -)
    out = re.sub(r"Users-[^-\"]+-", "Users-redacted-user-", out)
    # Sandbox dir id, underscore and dash flattened variants.
    out = re.sub(r"C0\d[_-]t\d+[_-]\d+", "TASK_t0_SANDBOX", out)
    # Session UUID -> zeros (not PII, but keep fixtures deterministic).
    out = re.sub(
        r'("session_id":\s*")[0-9a-fA-F-]+(")',
        r"\g<1>00000000-0000-0000-0000-000000000000\g<2>",
        out,
    )
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    log_path, out_path = Path(argv[1]), Path(argv[2])
    raw = json.loads(log_path.read_text(encoding="utf-8"))["agent"]["process"][
        "stdout"
    ]
    red = redact(raw)

    # General detector: any "Users" followed by separators then a token
    # that is not exactly 'redacted-user' is a redaction miss. This catches
    # ANY username generically — the username is never hardcoded here (that
    # would itself write PII into this committed script's git history).
    leftover = re.findall(
        r'Users[\\/_-]+(?!redacted-user)([^\\/_"-]+)', red
    )
    if leftover:
        raise SystemExit(f"redaction incomplete, found tokens: {set(leftover)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(red, encoding="utf-8")
    n = len([ln for ln in red.splitlines() if ln.strip()])
    print(f"wrote {out_path} ({n} json lines, redacted, PII-checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
