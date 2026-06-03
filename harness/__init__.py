"""agent-shell-context-bench harness.

Three moving parts, kept deliberately separate so a critic can audit each
in isolation:

  environments/  How and where a process runs (local Windows pwsh, WSL2,
                 Linux over SSH, macOS on a GitHub Actions runner) plus
                 sandbox lifecycle and filesystem diffing.
  adapters/      How a specific coding-agent CLI is invoked and how its
                 output is parsed into a transcript + structured commands.
  classifier/    The spiral rubric (A-F) applied post hoc to transcripts.

`types.py` holds the contract every part agrees on. Importing the contract
from one place (rather than across adapters <-> environments) keeps the
dependency graph acyclic and gives the eventual logging schema a single
source of truth.
"""
