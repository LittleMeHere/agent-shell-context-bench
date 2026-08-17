"""Build an explicit-label-masked, analysis-excluded human timing packet.

This utility is for D-004 resource costing only. It accepts completed resource-
shakedown trial records, selects one case from every configuration/workload
stratum crossing, and creates a private, self-contained browser worksheet.
It never reads pilot or confirmatory outcomes and refuses to write inside the
public repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.irr_code import check_prompt_frozen
from scripts.resource_shakedown_plan import CORE_VARIANTS


SCHEMA_VERSION = "1.0.0"
EXPECTED_CONFIGS = tuple(f"CFG{i}" for i in range(1, 8))
STRATUM_BY_TASK = {
    (task_id, phrasing): stratum
    for task_id, phrasing, stratum in CORE_VARIANTS
}


@dataclass(frozen=True)
class Candidate:
    source_path: Path
    source_sha256: str
    config_id: str
    stratum: str
    prompt: str
    outcome_success: bool
    transcript: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _load_candidate(path: Path) -> Candidate | None:
    raw_bytes = path.read_bytes()
    try:
        record = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid trial JSON {path}: {exc}") from exc
    if not isinstance(record, Mapping) or not {
        "schema_version",
        "trial",
        "schedule",
        "agent",
        "outcome",
        "validity",
    }.issubset(record):
        return None

    trial = _mapping(record.get("trial"), f"{path}: trial")
    schedule = _mapping(record.get("schedule"), f"{path}: schedule")
    agent = _mapping(record.get("agent"), f"{path}: agent")
    process = _mapping(agent.get("process"), f"{path}: agent.process")
    outcome = _mapping(record.get("outcome"), f"{path}: outcome")
    validity = _mapping(record.get("validity"), f"{path}: validity")

    config_id = schedule.get("config_id")
    task_id = trial.get("task_id")
    phrasing = trial.get("phrasing")
    stratum = STRATUM_BY_TASK.get((task_id, phrasing))
    if config_id not in EXPECTED_CONFIGS or stratum is None:
        return None
    if validity.get("valid") is not True:
        raise ValueError(f"timing source is not valid: {path}")
    if process.get("returncode") != 0 or process.get("timed_out") is not False:
        raise ValueError(f"timing source did not exit cleanly: {path}")

    prompt = record.get("prompt")
    transcript = agent.get("transcript")
    success = outcome.get("success")
    if not isinstance(prompt, str) or not isinstance(transcript, str):
        raise ValueError(f"timing source lacks string prompt/transcript: {path}")
    if type(success) is not bool:
        raise ValueError(f"timing source lacks boolean outcome.success: {path}")
    return Candidate(
        source_path=path.resolve(),
        source_sha256=_sha256(raw_bytes),
        config_id=str(config_id),
        stratum=stratum,
        prompt=prompt,
        outcome_success=success,
        transcript=transcript,
    )


def discover_candidates(source_roots: Sequence[Path]) -> tuple[Candidate, ...]:
    candidates: list[Candidate] = []
    seen_paths: set[Path] = set()
    for root in source_roots:
        resolved = root.resolve()
        if not resolved.is_dir():
            raise ValueError(f"timing source root is not a directory: {root}")
        for path in sorted(resolved.rglob("*.json")):
            path = path.resolve()
            if path in seen_paths or path.name == "receipt.json":
                continue
            seen_paths.add(path)
            candidate = _load_candidate(path)
            if candidate is not None:
                candidates.append(candidate)
    return tuple(candidates)


def select_balanced_cases(
    candidates: Sequence[Candidate], *, seed: int
) -> tuple[Candidate, ...]:
    by_cell: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_cell[(candidate.config_id, candidate.stratum)].append(candidate)

    expected_cells = {
        (config_id, stratum)
        for config_id in EXPECTED_CONFIGS
        for stratum in STRATUM_BY_TASK.values()
    }
    actual_cells = set(by_cell)
    if actual_cells != expected_cells:
        missing = sorted(expected_cells - actual_cells)
        extra = sorted(actual_cells - expected_cells)
        raise ValueError(f"timing roster is not exact; missing={missing}, extra={extra}")
    for cell, rows in by_cell.items():
        if len(rows) < 2:
            raise ValueError(f"timing cell {cell} has fewer than two replicates")
        if len({row.source_sha256 for row in rows}) != len(rows):
            raise ValueError(f"timing cell {cell} contains duplicate source bytes")

    rng = random.Random(seed)
    selected = [rng.choice(sorted(rows, key=lambda row: row.source_sha256)) for rows in by_cell.values()]
    rng.shuffle(selected)
    return tuple(selected)


def _case_id(source_sha256: str, seed: int) -> str:
    return _sha256(f"human-timing-v1\0{seed}\0{source_sha256}".encode())[:12]


def _packet_payload(cases: Sequence[Candidate], *, seed: int) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "purpose": "D-004 analysis-excluded human timing exercise",
        "analysis_excluded": True,
        "selection": "one deterministic replicate per 7-configuration x 5-workload-stratum cell",
        "selection_seed": seed,
        "case_count": len(cases),
        "cases": [
            {
                "case_id": _case_id(case.source_sha256, seed),
                "task_prompt": case.prompt,
                "programmatic_outcome": "success" if case.outcome_success else "failure",
                "transcript": case.transcript,
            }
            for case in cases
        ],
    }


def _render_html(packet: Mapping[str, object], frozen_prompt: str) -> str:
    packet_json = json.dumps(packet, ensure_ascii=False).replace("<", "\\u003c")
    rubric = html.escape(frozen_prompt)
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>D-004 label-masked human timing exercise</title>
<style>
body{{font:16px/1.45 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#18202a}}
button,select,textarea,input{{font:inherit}} button{{padding:.55rem .9rem;margin:.25rem}}
pre{{white-space:pre-wrap;background:#f4f6f8;padding:1rem;border-radius:.5rem;max-height:42vh;overflow:auto}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}} .card{{border:1px solid #ccd3da;border-radius:.6rem;padding:1rem}}
.hidden{{display:none}} .status{{font-weight:650}} textarea{{width:100%;min-height:5rem}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>D-004 label-masked human timing exercise</h1>
<p>This packet contains 35 non-analysis cases. Explicit environment, agent, model, and configuration fields are withheld. Commands, paths, and event wrappers may still make identities inferable; do not investigate or cross-reference them.</p>
<details><summary>Frozen A-F rubric</summary><pre>{rubric}</pre></details>
<p class=\"status\" id=\"status\"></p>
<div id=\"ready\" class=\"card\"><p>Open the case, inspect the evidence, then click <em>Evidence ready</em>. Active coding time starts only after that click.</p><button id=\"open\">Open next case</button></div>
<div id=\"case\" class=\"hidden\">
 <div class=\"grid\"><section class=\"card\"><h2>Task prompt</h2><pre id=\"prompt\"></pre><h2>Programmatic outcome</h2><p id=\"outcome\"></p></section><section class=\"card\"><h2>Transcript</h2><pre id=\"transcript\"></pre></section></div>
 <div id=\"classify\" class=\"card hidden\"><label>Code <select id=\"code\"><option value=\"\">Select</option><option>A</option><option>B</option><option>C</option><option>D</option><option>E</option><option>F</option></select></label> <label><input type=\"checkbox\" id=\"uncertain\"> Uncertain case</label><p><label>Short rationale <textarea id=\"rationale\" maxlength=\"400\"></textarea></label></p><button id=\"submit\">Save and continue</button></div>
 <button id=\"evidence\">Evidence ready</button>
</div>
<div id=\"done\" class=\"card hidden\"><h2>Complete</h2><p>Export the result JSON and retain it in the private operational record.</p><button id=\"export\">Export timing results</button></div>
<script>
const packet={packet_json}; const key='d004-human-timing-'+packet.selection_seed;
let state=JSON.parse(localStorage.getItem(key)||'null')||{{index:0,results:[]}}; let opened=0,active=0;
const $=id=>document.getElementById(id); const save=()=>localStorage.setItem(key,JSON.stringify(state));
function status(){{$('status').textContent=`Completed ${{state.index}} of ${{packet.case_count}}`; if(state.index>=packet.case_count){{$('ready').classList.add('hidden');$('case').classList.add('hidden');$('done').classList.remove('hidden')}}}}
$('open').onclick=()=>{{const c=packet.cases[state.index];opened=performance.now();$('prompt').textContent=c.task_prompt;$('outcome').textContent=c.programmatic_outcome;$('transcript').textContent=c.transcript;$('ready').classList.add('hidden');$('case').classList.remove('hidden');$('classify').classList.add('hidden');$('evidence').classList.remove('hidden')}};
$('evidence').onclick=()=>{{active=performance.now();$('evidence').classList.add('hidden');$('classify').classList.remove('hidden');$('code').focus()}};
$('submit').onclick=()=>{{const code=$('code').value,rationale=$('rationale').value.trim();if(!code||!rationale){{alert('Select a code and enter a short rationale.');return}}const c=packet.cases[state.index];state.results.push({{case_id:c.case_id,code,rationale,uncertain:$('uncertain').checked,evidence_loading_ms:Math.round(active-opened),active_coding_ms:Math.round(performance.now()-active)}});state.index++;save();$('code').value='';$('rationale').value='';$('uncertain').checked=false;$('case').classList.add('hidden');$('ready').classList.remove('hidden');status()}};
$('export').onclick=()=>{{const out={{schema_version:'1.0.0',purpose:packet.purpose,analysis_excluded:true,selection_seed:packet.selection_seed,packet_digest:packet.packet_digest,completed_cases:state.results.length,results:state.results}};const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='d004-human-timing-results.json';a.click();URL.revokeObjectURL(a.href)}};
status();
</script></body></html>"""


def build_packet(
    *, source_roots: Sequence[Path], output_dir: Path, seed: int
) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[1]
    output = output_dir.resolve()
    if _is_relative_to(output, repo_root):
        raise ValueError("human timing packet must use an external private output root")
    if output.exists():
        raise ValueError(f"refusing to overwrite timing output: {output}")

    candidates = discover_candidates(source_roots)
    cases = select_balanced_cases(candidates, seed=seed)
    packet = _packet_payload(cases, seed=seed)
    packet["packet_digest"] = _sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    frozen_prompt = check_prompt_frozen()

    output.mkdir(parents=True)
    (output / "timing-exercise.html").write_text(
        _render_html(packet, frozen_prompt), encoding="utf-8", newline="\n"
    )
    provenance = {
        "schema_version": SCHEMA_VERSION,
        "purpose": packet["purpose"],
        "analysis_excluded": True,
        "selection_seed": seed,
        "packet_digest": packet["packet_digest"],
        "cases": [
            {
                "case_id": _case_id(case.source_sha256, seed),
                "source_path": str(case.source_path),
                "source_sha256": case.source_sha256,
                "config_id": case.config_id,
                "stratum": case.stratum,
            }
            for case in cases
        ],
    }
    (output / "private-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output / "blank-timing-sheet.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["case_id", "code", "uncertain", "evidence_loading_ms", "active_coding_ms", "rationale"]
        )
        for case in cases:
            writer.writerow([_case_id(case.source_sha256, seed), "", "", "", "", ""])
    return packet


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="human_timing_packet")
    parser.add_argument("--source-root", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)
    packet = build_packet(source_roots=args.source_root, output_dir=args.out, seed=args.seed)
    print(
        f"wrote {packet['case_count']} label-masked cases; "
        f"digest={packet['packet_digest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
