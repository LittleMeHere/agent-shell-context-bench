import json

import pytest

from analysis.d004_resource_feasibility import (
    candidate_roster_cost,
    main,
    provider_agent_calls,
    resource_rows,
    review_hours,
)


@pytest.mark.parametrize(
    ("base_n", "n_cap", "capability", "seeded", "full"),
    (
        (6, 3, 1_260, 3_780, 5_040),
        (12, 5, 2_100, 7_560, 9_660),
        (24, 10, 4_200, 15_120, 19_320),
    ),
)
def test_candidate_roster_exact_counts(
    base_n: int,
    n_cap: int,
    capability: int,
    seeded: int,
    full: int,
) -> None:
    cost = candidate_roster_cost(base_n)
    assert cost.capability_n == n_cap
    assert cost.capability_trials_full_matrix == capability
    assert cost.seeded_trials_full_matrix == seeded
    assert cost.full_trials == full
    assert capability + seeded == full


def test_provider_partition_and_agy_bottleneck() -> None:
    cost = candidate_roster_cost(6)
    full = provider_agent_calls(cost, scope="full_four_hypothesis_matrix")
    core = provider_agent_calls(cost, scope="capability_core_h1_h3")
    assert full == {
        "anthropic_subscription": 1_440,
        "openai_subscription": 1_440,
        "agy_google_subscription": 2_160,
    }
    assert core == {
        "anthropic_subscription": 360,
        "openai_subscription": 360,
        "agy_google_subscription": 540,
    }
    assert sum(full.values()) == cost.full_trials
    with pytest.raises(ValueError, match="unknown collection scope"):
        provider_agent_calls(cost, scope="invented")


def test_literal_coder_and_hypothesis_specific_counts() -> None:
    row = next(
        row
        for row in resource_rows(
            base_common_ns=(6,),
            audit_budgets=(200,),
            minutes_per_label=(5.0,),
        )
        if row["record_type"] == "d004_candidate_roster_cost"
    )
    assert row["current_two_ai_full_sample_grading_calls"] == 10_080
    assert row["h4_seeded_two_ai_grading_calls"] == 7_560
    assert row[
        "literal_current_total_subscription_invocations_before_pilot_or_retries"
    ] == 15_120
    assert row["raw_calls_are_quota_estimates"] is False
    assert row["judge_provider_assignment"] == "open_D006_not_charged_to_provider"


def test_review_hours_are_explicit_and_include_overhead() -> None:
    assert review_hours(
        labels=650,
        minutes_per_label=5,
        overhead_fraction=0.10,
    ) == pytest.approx(59.583333333333336)
    with pytest.raises(ValueError):
        review_hours(labels=-1, minutes_per_label=5)
    with pytest.raises(ValueError):
        review_hours(labels=1, minutes_per_label=0)


def test_requested_audit_caps_at_scenario_mean_failure_population() -> None:
    rows = resource_rows(
        base_common_ns=(6,),
        audit_budgets=(200, 1_000),
        minutes_per_label=(3.0,),
    )
    human = [
        row for row in rows if row["record_type"] == "d004_human_review_reference"
    ]
    assert len(human) == 2
    small, census = human
    assert small["scenario_mean_actual_audit_labels"] == 200
    assert census["scenario_mean_actual_audit_labels"] == pytest.approx(
        census["scenario_mean_focal_failure_population"]
    )
    assert census["scenario_mean_total_human_labels"] == pytest.approx(
        census["scenario_mean_actual_audit_labels"] + 50
    )


def test_cli_emits_strict_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(
        [
            "--base-common-ns",
            "6",
            "--audit-budgets",
            "200",
            "--minutes-per-label",
            "5",
        ]
    ) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert {record["record_type"] for record in records} == {
        "d004_candidate_roster_cost",
        "d004_human_review_reference",
    }


@pytest.mark.parametrize("value", (True, 5, 6.5))
def test_invalid_base_n_fails_closed(value: object) -> None:
    with pytest.raises(ValueError):
        candidate_roster_cost(value)  # type: ignore[arg-type]
