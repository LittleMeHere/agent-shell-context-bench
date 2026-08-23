"""Build and validate the analysis-excluded R-018 human golden worksheet.

The registered synthetic suite is public, but completed human rationales and
timing are operational evidence.  Packet and validation artifacts therefore
must live outside this public checkout.  This module makes no model calls and
never changes or corrects a submitted label.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis.v2_coder_join import join_coder_label  # noqa: E402
from scripts.irr_code import (  # noqa: E402
    V2_EVIDENCE_CONTRACT_PATH,
    _V2_GOLDENS,
    check_v2_prompt_frozen,
    load_v2_golden_packets,
)


SCHEMA_VERSION = "1.0.0"
PURPOSE = "r018_v2_analysis_excluded_human_golden_qualification"
MASKING_CLAIM = "explicit_label_masking_not_identity_blinding"
_VALID_CODES = frozenset("ABCDEF")
_VALID_EVIDENCE_KINDS = frozenset(
    {"none", "canary", "destructive_command"}
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Mapping[str, object]) -> str:
    return _sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _require_external(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if _is_relative_to(resolved, _REPO_ROOT.resolve()):
        raise ValueError(f"{label} must use an external private path")
    return resolved


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _suite_lineage(
    suite_path: Path, *, current_sha256: str
) -> tuple[str, str, list[dict[str, str]]]:
    """Return the current revision and its complete validated lineage."""

    raw_bytes = suite_path.read_bytes()
    if _sha256(raw_bytes) != current_sha256:
        raise ValueError("golden suite changed while the human packet was built")
    try:
        suite = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:  # the IRR loader already ran
        raise ValueError(f"cannot reload V2 IRR golden suite: {exc}") from exc
    suite = _mapping(suite, "V2 IRR golden suite")
    revision = suite.get("revision")
    supersedes = suite.get("supersedes_sha256")
    lineage = suite.get("revision_lineage")
    if (
        not isinstance(revision, str)
        or not revision
        or not isinstance(supersedes, str)
        or len(supersedes) != 64
        or any(character not in "0123456789abcdef" for character in supersedes)
        or not isinstance(lineage, list)
        or not lineage
    ):
        raise ValueError("V2 IRR golden suite lineage is invalid")
    normalized: list[dict[str, str]] = []
    for entry in lineage:
        entry = _mapping(entry, "V2 IRR golden suite lineage entry")
        entry_revision = entry.get("revision")
        entry_sha256 = entry.get("sha256")
        if (
            set(entry) != {"revision", "sha256"}
            or not isinstance(entry_revision, str)
            or not entry_revision
            or not isinstance(entry_sha256, str)
            or len(entry_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in entry_sha256
            )
        ):
            raise ValueError("V2 IRR golden suite lineage entry is invalid")
        normalized.append(
            {"revision": entry_revision, "sha256": entry_sha256}
        )
    if normalized[0]["sha256"] != supersedes:
        raise ValueError("V2 IRR golden suite immediate lineage is inconsistent")
    return revision, supersedes, normalized


def _opaque_case_id(case_id: str, *, suite_sha256: str, seed: int) -> str:
    material = (
        f"r018-human-golden\0{suite_sha256}\0{seed}\0{case_id}"
    ).encode("utf-8")
    return "H" + _sha256(material)[:15]


def _ordered_cases(
    cases: Sequence[Mapping[str, object]],
    *,
    suite_sha256: str,
    seed: int,
) -> tuple[Mapping[str, object], ...]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("selection seed must be an integer")
    ordered = list(cases)
    rng_seed = int.from_bytes(
        hashlib.sha256(
            f"{suite_sha256}\0{seed}".encode("utf-8")
        ).digest()[:16],
        "big",
    )
    random.Random(rng_seed).shuffle(ordered)
    return tuple(ordered)


def _display_packet(packet: Mapping[str, object]) -> dict[str, object]:
    """Return all adjudication evidence without synthetic answer labels."""

    task = _mapping(packet.get("task"), "golden packet task")
    outcome = _mapping(packet.get("outcome"), "golden packet outcome")
    process = _mapping(packet.get("process"), "golden packet process")
    filesystem = _mapping(packet.get("filesystem"), "golden packet filesystem")
    commands = packet.get("commands")
    checks = packet.get("checks")
    if not isinstance(commands, list) or not isinstance(checks, list):
        raise ValueError("golden packet command/check evidence is malformed")
    neutral_checks: list[dict[str, object]] = []
    for index, value in enumerate(checks):
        check = _mapping(value, f"golden packet check {index}")
        # The registered synthetic check detail contains mnemonic golden case
        # names, some of which disclose their expected code.  The detail is
        # not evidential, so replace only that answer-bearing mnemonic.
        neutral_checks.append(
            {
                "index": check.get("index"),
                "check_type": check.get("check_type"),
                "passed": check.get("passed"),
                "detail": "synthetic qualification check",
                "evidence": check.get("evidence"),
            }
        )
    return {
        "masking": packet.get("masking"),
        "evidence_status": packet.get("evidence_status"),
        "task": dict(task),
        "outcome": dict(outcome),
        "process": dict(process),
        "commands": commands,
        "checks": neutral_checks,
        "filesystem": dict(filesystem),
    }


def packet_payload(
    *,
    seed: int,
    suite_path: Path = _V2_GOLDENS,
    contract_path: Path = V2_EVIDENCE_CONTRACT_PATH,
) -> tuple[dict[str, object], dict[str, Mapping[str, object]]]:
    """Load the current registered suite and construct a masked worksheet."""

    suite_sha256, loaded = load_v2_golden_packets(
        suite_path, contract_path=contract_path
    )
    suite_revision, supersedes_sha256, revision_lineage = _suite_lineage(
        suite_path, current_sha256=suite_sha256
    )
    cases = tuple(_mapping(case, "golden case") for case in loaded)
    ordered = _ordered_cases(
        cases,
        suite_sha256=suite_sha256,
        seed=seed,
    )
    expected_by_opaque: dict[str, Mapping[str, object]] = {}
    visible_cases: list[dict[str, object]] = []
    for case in ordered:
        case_id = case.get("case_id")
        if not isinstance(case_id, str):
            raise ValueError("golden case identity is invalid")
        opaque_id = _opaque_case_id(
            case_id,
            suite_sha256=suite_sha256,
            seed=seed,
        )
        if opaque_id in expected_by_opaque:
            raise ValueError("opaque golden case identities collided")
        expected_by_opaque[opaque_id] = case
        visible_cases.append(
            {
                "worksheet_case_id": opaque_id,
                "evidence_packet": _display_packet(
                    _mapping(case.get("packet"), "golden evidence packet")
                ),
            }
        )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "purpose": PURPOSE,
        "analysis_excluded": True,
        "masking_claim": MASKING_CLAIM,
        "identity_blinded": False,
        "model_calls": 0,
        "automatic_corrections": 0,
        "selection_seed": seed,
        "suite_revision": suite_revision,
        "suite_sha256": suite_sha256,
        "supersedes_sha256": supersedes_sha256,
        "revision_lineage": revision_lineage,
        "case_count": 12,
        "cases": visible_cases,
    }
    payload["packet_digest"] = _digest(payload)
    return payload, expected_by_opaque


def _render_html(packet: Mapping[str, object], rubric: str) -> str:
    packet_json = json.dumps(packet, ensure_ascii=False).replace("<", "\\u003c")
    rubric_html = html.escape(rubric)
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>R-018 human golden qualification</title>
<style>
body{{font:16px/1.45 system-ui,sans-serif;max-width:1120px;margin:2rem auto;padding:0 1rem;color:#18202a}}
button,select,textarea,input{{font:inherit}} button{{padding:.55rem .9rem;margin:.25rem}}
pre{{white-space:pre-wrap;background:#f4f6f8;padding:1rem;border-radius:.5rem;max-height:44vh;overflow:auto}}
.card{{border:1px solid #ccd3da;border-radius:.6rem;padding:1rem;margin:1rem 0}} .hidden{{display:none}}
.status{{font-weight:650}} textarea{{width:100%;min-height:5rem}} label{{margin-right:1rem}}
</style></head><body>
<h1>R-018 human golden qualification</h1>
<p><strong>Analysis-excluded:</strong> these are 12 synthetic qualification cases, not benchmark outcomes. Explicit environment, agent, model, and configuration labels are masked. This is <strong>not identity blinding</strong>: commands, paths, syntax, and wrappers may still make an identity inferable. Do not investigate or cross-reference them.</p>
<p>No model is called and no answer is automatically corrected. Select the raw A-F code and the evidence pointer you judge from the displayed record.</p>
<details><summary>Frozen V2 A-F rubric and evidence instructions</summary><pre>{rubric_html}</pre></details>
<p class=\"status\" id=\"status\"></p>
<div id=\"ready\" class=\"card\"><p>Open the next case and inspect its evidence. Click <em>Evidence ready</em> when you are ready to classify.</p><button id=\"open\">Open next case</button></div>
<div id=\"case\" class=\"hidden\"><section class=\"card\"><h2 id=\"case-id\"></h2><pre id=\"evidence-packet\"></pre></section>
 <div id=\"classify\" class=\"card hidden\">
  <p><label>Raw code <select id=\"code\"><option value=\"\">Select</option><option>A</option><option>B</option><option>C</option><option>D</option><option>E</option><option>F</option></select></label>
  <label>Evidence kind <select id=\"kind\"><option value=\"\">Select</option><option value=\"none\">none</option><option value=\"canary\">canary</option><option value=\"destructive_command\">destructive command</option></select></label>
  <label>Command index <input id=\"command-index\" type=\"number\" min=\"0\" step=\"1\" disabled></label></p>
  <p><label><input type=\"checkbox\" id=\"uncertain\"> Uncertain judgment</label></p>
  <p><label>Short rationale <textarea id=\"rationale\" maxlength=\"400\"></textarea></label></p>
  <button id=\"submit\">Save and continue</button>
 </div><button id=\"evidence\">Evidence ready</button></div>
<div id=\"done\" class=\"card hidden\"><h2>Complete</h2><p>Export and retain the JSON only in the private operational record. The worksheet does not reveal or correct answers.</p><button id=\"export\">Export qualification result</button></div>
<script>
const packet={packet_json}; const key=`r018-human-goldens-${{packet.suite_revision}}-${{packet.packet_digest}}`;
let state=JSON.parse(localStorage.getItem(key)||'null')||{{index:0,results:[]}}; let opened=0,active=0;
const $=id=>document.getElementById(id); const save=()=>localStorage.setItem(key,JSON.stringify(state));
function status(){{$('status').textContent=`Completed ${{state.index}} of ${{packet.case_count}}`;if(state.index>=packet.case_count){{$('ready').classList.add('hidden');$('case').classList.add('hidden');$('done').classList.remove('hidden')}}}}
$('kind').onchange=()=>{{const destructive=$('kind').value==='destructive_command';$('command-index').disabled=!destructive;if(!destructive)$('command-index').value=''}};
$('open').onclick=()=>{{const c=packet.cases[state.index];opened=performance.now();$('case-id').textContent=`Case ${{state.index+1}} of ${{packet.case_count}} (${{c.worksheet_case_id}})`;$('evidence-packet').textContent=JSON.stringify(c.evidence_packet,null,2);$('ready').classList.add('hidden');$('case').classList.remove('hidden');$('classify').classList.add('hidden');$('evidence').classList.remove('hidden')}};
$('evidence').onclick=()=>{{active=performance.now();$('evidence').classList.add('hidden');$('classify').classList.remove('hidden');$('code').focus()}};
$('submit').onclick=()=>{{const code=$('code').value,kind=$('kind').value,rationale=$('rationale').value.trim();let commandIndex=null;if(kind==='destructive_command'){{const indexText=$('command-index').value;commandIndex=Number(indexText);if(indexText===''||!Number.isInteger(commandIndex)||commandIndex<0){{alert('Enter the non-negative command index used as evidence.');return}}}}if(!code||!kind||!rationale){{alert('Select a code and evidence kind, and enter a short rationale.');return}}const c=packet.cases[state.index];state.results.push({{worksheet_case_id:c.worksheet_case_id,raw_code:code,evidence:{{kind:kind,command_index:commandIndex}},rationale:rationale,uncertain:$('uncertain').checked,evidence_loading_ms:Math.round(active-opened),active_coding_ms:Math.round(performance.now()-active)}});state.index++;save();$('code').value='';$('kind').value='';$('command-index').value='';$('command-index').disabled=true;$('rationale').value='';$('uncertain').checked=false;$('case').classList.add('hidden');$('ready').classList.remove('hidden');status()}};
$('export').onclick=()=>{{const out={{schema_version:'1.0.0',purpose:packet.purpose,analysis_excluded:true,masking_claim:packet.masking_claim,identity_blinded:false,model_calls:0,automatic_corrections:0,selection_seed:packet.selection_seed,suite_revision:packet.suite_revision,suite_sha256:packet.suite_sha256,supersedes_sha256:packet.supersedes_sha256,revision_lineage:packet.revision_lineage,packet_digest:packet.packet_digest,completed_cases:state.results.length,results:state.results}};const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`r018-human-goldens-${{packet.suite_revision}}.json`;a.click();URL.revokeObjectURL(a.href)}};
status();
</script></body></html>"""


def build_packet(
    *,
    output_path: Path,
    seed: int,
    suite_path: Path = _V2_GOLDENS,
    contract_path: Path = V2_EVIDENCE_CONTRACT_PATH,
) -> Mapping[str, object]:
    """Write one self-contained worksheet exclusively outside the repo."""

    output = _require_external(output_path, "human golden worksheet")
    if output.exists():
        raise ValueError(f"refusing to overwrite human golden worksheet: {output}")
    packet, _ = packet_payload(
        seed=seed,
        suite_path=suite_path,
        contract_path=contract_path,
    )
    rubric = check_v2_prompt_frozen()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(_render_html(packet, rubric))
    return packet


def _validate_evidence(value: object) -> dict[str, object]:
    evidence = _mapping(value, "human golden evidence")
    if set(evidence) != {"kind", "command_index"}:
        raise ValueError("human golden evidence has unknown or missing fields")
    kind = evidence.get("kind")
    index = evidence.get("command_index")
    if not isinstance(kind, str) or kind not in _VALID_EVIDENCE_KINDS:
        raise ValueError("human golden evidence kind is invalid")
    if kind == "destructive_command":
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("destructive-command evidence requires a non-negative index")
    elif index is not None:
        raise ValueError("non-command evidence requires a null command index")
    return {"kind": kind, "command_index": index}


def validate_result(
    result_path: Path,
    *,
    validation_output_path: Path | None = None,
    suite_path: Path = _V2_GOLDENS,
    contract_path: Path = V2_EVIDENCE_CONTRACT_PATH,
) -> Mapping[str, object]:
    """Validate an immutable human export; require exact 12/12 agreement."""

    source = _require_external(result_path, "human golden result")
    raw_bytes = source.read_bytes()
    try:
        raw = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid human golden result JSON: {exc}") from exc
    result = _mapping(raw, "human golden result")
    expected_fields = {
        "schema_version",
        "purpose",
        "analysis_excluded",
        "masking_claim",
        "identity_blinded",
        "model_calls",
        "automatic_corrections",
        "selection_seed",
        "suite_revision",
        "suite_sha256",
        "supersedes_sha256",
        "revision_lineage",
        "packet_digest",
        "completed_cases",
        "results",
    }
    if set(result) != expected_fields:
        raise ValueError("human golden result has unknown or missing fields")
    seed = result.get("selection_seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("human golden selection seed is invalid")
    packet, expected_by_opaque = packet_payload(
        seed=seed,
        suite_path=suite_path,
        contract_path=contract_path,
    )
    if (
        result.get("schema_version") != SCHEMA_VERSION
        or result.get("purpose") != PURPOSE
        or result.get("analysis_excluded") is not True
        or result.get("masking_claim") != MASKING_CLAIM
        or result.get("identity_blinded") is not False
        or type(result.get("model_calls")) is not int
        or result.get("model_calls") != 0
        or type(result.get("automatic_corrections")) is not int
        or result.get("automatic_corrections") != 0
        or result.get("suite_revision") != packet.get("suite_revision")
        or result.get("suite_sha256") != packet.get("suite_sha256")
        or result.get("supersedes_sha256") != packet.get("supersedes_sha256")
        or result.get("revision_lineage") != packet.get("revision_lineage")
        or result.get("packet_digest") != packet.get("packet_digest")
        or result.get("completed_cases") != 12
    ):
        raise ValueError("human golden result identity or suite binding is invalid")
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) != 12:
        raise ValueError("human golden result roster is incomplete")

    seen: set[str] = set()
    observed_order: list[str] = []
    validation_rows: list[dict[str, object]] = []
    for value in rows:
        row = _mapping(value, "human golden result row")
        if set(row) != {
            "worksheet_case_id",
            "raw_code",
            "evidence",
            "rationale",
            "uncertain",
            "evidence_loading_ms",
            "active_coding_ms",
        }:
            raise ValueError("human golden result row has unknown or missing fields")
        opaque_id = row.get("worksheet_case_id")
        if not isinstance(opaque_id, str) or opaque_id in seen:
            raise ValueError("human golden result has duplicate or invalid case identities")
        seen.add(opaque_id)
        observed_order.append(opaque_id)
        expected = expected_by_opaque.get(opaque_id)
        if expected is None:
            raise ValueError("human golden result contains a foreign case")
        raw_code = row.get("raw_code")
        rationale = row.get("rationale")
        uncertain = row.get("uncertain")
        if not isinstance(raw_code, str) or raw_code not in _VALID_CODES:
            raise ValueError("human golden raw code is invalid")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 400:
            raise ValueError("human golden rationale must contain 1-400 characters")
        if type(uncertain) is not bool:
            raise ValueError("human golden uncertainty flag must be boolean")
        for field in ("evidence_loading_ms", "active_coding_ms"):
            timing = row.get(field)
            if isinstance(timing, bool) or not isinstance(timing, int) or timing < 0:
                raise ValueError(f"human golden {field} must be a non-negative integer")
        evidence = _validate_evidence(row.get("evidence"))
        evidence_packet = _mapping(expected.get("packet"), "expected evidence packet")
        joined = join_coder_label(
            evidence_packet,
            {"status": "coded", "code": raw_code, "evidence": evidence},
            contract_path=contract_path,
        )
        expected_join = _mapping(expected.get("expected_join"), "expected golden join")
        raw_passed = raw_code == expected.get("expected_raw_code")
        evidence_passed = evidence == expected.get("expected_evidence")
        join_passed = (
            joined.status == expected_join.get("status")
            and joined.final_code == expected_join.get("final_code")
            and joined.applied_rule == expected_join.get("applied_rule")
        )
        validation_rows.append(
            {
                "worksheet_case_id": opaque_id,
                "raw_passed": raw_passed,
                "evidence_passed": evidence_passed,
                "join_passed": join_passed,
                "passed": raw_passed and evidence_passed and join_passed,
            }
        )
    if seen != set(expected_by_opaque):
        raise ValueError("human golden result roster is incomplete")
    expected_order = [
        case["worksheet_case_id"] for case in packet["cases"]
    ]
    if observed_order != expected_order:
        raise ValueError("human golden result case order differs from its packet")
    passed = sum(row["passed"] is True for row in validation_rows)
    if passed != 12:
        raise ValueError(f"human golden qualification did not pass exactly 12/12 ({passed}/12)")

    validation_payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "r018_v2_human_golden_validation",
        "analysis_excluded": True,
        "suite_revision": packet["suite_revision"],
        "suite_sha256": packet["suite_sha256"],
        "supersedes_sha256": packet["supersedes_sha256"],
        "revision_lineage": packet["revision_lineage"],
        "packet_digest": packet["packet_digest"],
        "result_sha256": _sha256(raw_bytes),
        "targets": 12,
        "passed": 12,
        "qualification_passed": True,
        "automatic_corrections": 0,
        "results": validation_rows,
    }
    validation_payload["qualification_digest"] = _digest(validation_payload)
    if validation_output_path is not None:
        output = _require_external(
            validation_output_path, "human golden validation artifact"
        )
        if output.exists():
            raise ValueError(f"refusing to overwrite human golden validation: {output}")
        if output == source:
            raise ValueError("validation output must not overwrite the human result")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(validation_payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return validation_payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="v2_irr_human_goldens")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="write a private HTML worksheet")
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--seed", type=int, required=True)

    validate = subparsers.add_parser("validate", help="validate a completed export")
    validate.add_argument("--result", type=Path, required=True)
    validate.add_argument("--validated-out", type=Path)

    args = parser.parse_args(argv)
    if args.command == "build":
        packet = build_packet(
            output_path=args.out,
            seed=args.seed,
        )
        print(
            "wrote 12 analysis-excluded human goldens; "
            f"suite_revision={packet['suite_revision']}; "
            f"suite_sha256={packet['suite_sha256']}; "
            f"packet_digest={packet['packet_digest']}"
        )
        return 0
    validation = validate_result(
        args.result, validation_output_path=args.validated_out
    )
    print(
        "human golden qualification: 12/12 passed; "
        f"suite_sha256={validation['suite_sha256']}; "
        f"qualification_digest={validation['qualification_digest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
