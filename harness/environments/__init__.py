"""Environment adapters: one per (OS, shell) cell of the benchmark matrix.

The five pre-registered environments (RESEARCH_PLAN.md):
  windows_powershell  Windows 11 native, Windows PowerShell 5.1  -> powershell.py
                      (PS 5.1 pinned per D2 2026-05-23 — the default
                       Windows shell; the within-Windows pwsh-7 comparison
                       was restored as E2 per docs/DECISIONS.md
                       2026-05-25 (later))
  windows_pwsh7       Windows 11 native, pwsh 7.5.5              -> subclass of powershell.py
                      (E2 added 2026-05-25 (later); within-Windows
                       mechanism check vs E1)
  windows_wsl2        Windows 11 host, WSL2 Ubuntu 22.04         -> (V2 work)
  linux_native        Ubuntu 22.04 on GCP e2-small               -> (V2 work)
  macos_actions       macOS via GitHub Actions runner            -> (V2 work)

Only `powershell.py` is implemented so far — it is the reference example for
the base contract. The other three are written once this one validates
end-to-end against a real agent run.
"""
