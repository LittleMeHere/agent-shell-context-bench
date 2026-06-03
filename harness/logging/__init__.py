"""Per-trial log: the open-data substrate of the whole study.

Every trial — valid or invalid — writes exactly one immutable JSON file.
The analysis (SAP) reads only these files; nothing is computed from
in-memory state. If a number in the paper cannot be re-derived from this
directory by a stranger, it does not go in the paper.
"""

from .writer import SCHEMA_VERSION, build_trial_record, write_trial

__all__ = ["SCHEMA_VERSION", "build_trial_record", "write_trial"]
