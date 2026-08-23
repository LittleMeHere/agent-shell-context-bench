"""Create or verify the private prospective V2 N=36 capacity authorization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from harness.v2_design_lock import (  # noqa: E402
    EXPECTED_PROVIDER_IDS,
    V2DesignLockError,
    build_provider_cap_authorization,
    validate_provider_cap_authorization,
    write_provider_cap_authorization,
)


def _provider(value: str) -> tuple[str, dict[str, object]]:
    try:
        provider_id, raw = value.split("=", 1)
        window_unit, total, required = raw.split(",", 2)
        record = {
            "window_unit": window_unit,
            "total_window_units": float(total),
            "n36_required_units": float(required),
        }
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "provider must be ID=WINDOW_UNIT,TOTAL_UNITS,N36_REQUIRED_UNITS"
        ) from exc
    return provider_id, record


def _delay(value: str) -> tuple[str, float]:
    try:
        agent_id, raw = value.split("=", 1)
        return agent_id, float(raw)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("delay must be AGENT=SECONDS") from exc


def _unique(entries, *, label: str):
    result = {}
    for key, value in entries:
        if key in result:
            raise V2DesignLockError(f"duplicate {label} {key!r}")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("--as-of-date", required=True)
    create.add_argument("--calendar-days-cap", required=True, type=float)
    create.add_argument("--human-audit-hours-cap", required=True, type=float)
    create.add_argument("--provider", action="append", type=_provider, required=True)
    create.add_argument("--delay", action="append", type=_delay, required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "create":
            providers = _unique(args.provider, label="provider")
            if set(providers) != EXPECTED_PROVIDER_IDS:
                raise V2DesignLockError(
                    "provider roster must contain exactly "
                    f"{sorted(EXPECTED_PROVIDER_IDS)}"
                )
            artifact = build_provider_cap_authorization(
                as_of_date=args.as_of_date,
                calendar_days_cap=args.calendar_days_cap,
                human_audit_hours_cap=args.human_audit_hours_cap,
                providers=providers,
                inter_trial_delay_seconds=_unique(args.delay, label="delay"),
            )
            write_provider_cap_authorization(artifact, args.output)
            print(f"created provider-cap authorization: digest {artifact['artifact_digest']}")
            return 0
        raw = json.loads(args.artifact.read_text(encoding="utf-8"))
        digest = validate_provider_cap_authorization(raw)
        print(f"verified provider-cap authorization: digest {digest}")
        return 0
    except (OSError, json.JSONDecodeError, V2DesignLockError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
