"""Final per-trial records: the open-data substrate of the study.

Every fully measured trial writes one immutable JSON record.  The append-only
outer journal in :mod:`harness.attempts` also preserves pre/post-invocation
infrastructure failures and reconciles every started invocation to either a
record or an explicit terminal failure.  Analysis must consume that joined
on-disk evidence, never in-memory state.
"""

from .writer import SCHEMA_VERSION, build_trial_record, write_trial

__all__ = ["SCHEMA_VERSION", "build_trial_record", "write_trial"]
