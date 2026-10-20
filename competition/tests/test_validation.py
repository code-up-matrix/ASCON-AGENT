"""A zero backtester exit must not conceal missing execution or resource evidence."""

import json
from copy import deepcopy

import pytest

import validation


@pytest.fixture
def healthy_run():
    summary = {
        "blocksProcessed": 360,
        "blockTimeSec": 2,
        "valueSeries": {"failedReads": 0},
        "violations": [],
        "agents": [
            {"id": name, "pnlUsdc": 12.0, "netPnlUsdc": 12.0, "finalValueUsdc": 75012.0} for name in validation.AGENTS
        ],
    }
    resources = {
        name: {"memory": 4294967296, "memorySwap": 4294967296, "nanoCpus": 2000000000, "readOnlyRootfs": True}
        for name in validation.AGENTS
    }
    logs = {name: '{"round": 1, "kind": "decision"}\n' for name in validation.AGENTS}
    return summary, {"blocks": 360, "blockTimeSec": 2}, resources, logs


def test_complete_scenario_with_observed_caps_passes(healthy_run):
    assert validation.assess(*healthy_run) == []


@pytest.mark.parametrize("field,value", [("blocksProcessed", 359), ("blockTimeSec", 1)])
def test_shortened_or_accelerated_scenario_fails(healthy_run, field, value):
    healthy_run[0][field] = value
    assert validation.assess(*healthy_run)


@pytest.mark.parametrize("value", [None, 1])
def test_missing_or_failed_reads_fail(healthy_run, value):
    healthy_run[0]["valueSeries"]["failedReads"] = value
    assert validation.assess(*healthy_run)


def test_missing_and_duplicate_agents_fail(healthy_run):
    healthy_run[0]["agents"][2] = deepcopy(healthy_run[0]["agents"][1])
    assert "missing, duplicate or unexpected agents" in validation.assess(*healthy_run)


@pytest.mark.parametrize(
    "field,value",
    [
        ("processExitedEarly", "exit code 137"),
        ("pnlUsdc", None),
        ("pnlUsdc", float("nan")),
        ("pnlUsdc", True),
        ("unloggedTxCount", 1),
        ("finalValueUsdc", 0),
    ],
)
def test_invalid_agent_result_fails(healthy_run, field, value):
    healthy_run[0]["agents"][2][field] = value
    assert validation.assess(*healthy_run)


@pytest.mark.parametrize(
    "field,value",
    [
        ("memory", 0),
        ("memorySwap", -1),
        ("nanoCpus", 0),
        ("readOnlyRootfs", False),
    ],
)
def test_unenforced_resource_setting_fails(healthy_run, field, value):
    healthy_run[2]["eris-adaptive-v1"][field] = value
    assert validation.assess(*healthy_run)


def test_missing_container_observation_fails(healthy_run):
    healthy_run[2].clear()
    assert validation.assess(*healthy_run)


@pytest.mark.parametrize("line", ["decide error: bad action", "decide timeout: no answer", ""])
def test_decision_failure_or_empty_log_fails(healthy_run, line):
    healthy_run[3]["eris-adaptive-v1"] = line
    assert validation.assess(*healthy_run)


def test_incomplete_matrix_is_never_reported_as_passed(tmp_path, monkeypatch):
    monkeypatch.setattr(validation, "public_cases", lambda _: [{"regime": "calm", "seed": 101}])
    monkeypatch.setattr(validation, "source_hashes", lambda: {})
    output = tmp_path / "aggregate.json"
    with pytest.raises(ValueError, match="Incomplete"):
        validation.aggregate(tmp_path, tmp_path, output)
    assert validation.read_json(output)["public_matrix_passed"] is False


def test_extra_seed_requires_explicit_opt_in_and_cannot_change_regime():
    published = [{"regime": "calm", "seed": 101}]
    extra = {"regime": "calm", "seed": 606}
    with pytest.raises(ValueError, match="explicitly"):
        validation.validate_case(extra, published)
    validation.validate_case(extra, published, allow_extra_seed=True)
    for invalid in (
        {"regime": "../../custom", "seed": 606},
        {"regime": "calm", "seed": -1},
        {"regime": "calm", "seed": True},
        {"regime": "calm", "seed": 2**32},
    ):
        with pytest.raises(ValueError):
            validation.validate_case(invalid, published, allow_extra_seed=True)


def test_performance_comparison_keeps_losses_and_wins_separate():
    result = validation.summarize_metrics(
        [
            {"pnlUsdc": -10, "versusStarterUsdc": -100, "versusNoopUsdc": 2},
            {"pnlUsdc": 20, "versusStarterUsdc": 10, "versusNoopUsdc": -4},
            {"pnlUsdc": 50, "versusStarterUsdc": 30, "versusNoopUsdc": 8},
        ]
    )
    assert result["meanPnlUsdc"] == 20
    assert result["winsVersusStarter"] == 2
    assert result["meanVersusStarterUsdc"] == -20
    assert result["medianVersusStarterUsdc"] == 10
    assert result["winsVersusNoop"] == 2
    assert result["worstPnlUsdc"] == -10
    assert validation.summarize_metrics([]) == {"scenarios": 0}


def test_execution_report_distinguishes_pair_decisions_from_transactions():
    log = "\n".join(
        json.dumps(row)
        for row in [
            {"marker": "ASCON_DECISION", "reason": "cross_venue_pair"},
            {"event": "submitted"},
            {"event": "submitted"},
            {"event": "submit_failed"},
        ]
    )
    report = validation.execution_activity(log + "\nnot-json\n")
    assert report["pairedTrades"] == 1
    assert report["submitted"] == 2
    assert report["submitFailures"] == 1
    assert report["malformedLogLines"] == 1


def test_pair_outcomes_use_settled_receipts_instead_of_submission_count():
    records = [
        {"marker": "ASCON_DECISION", "reason": "cross_venue_pair", "block": b} for b in (10, 12, 14)
    ]
    records += [
        {"event": "submitted", "bundleId": str(b), "blockSeen": b, "hash": h}
        for b, h in ((10, "a"), (10, "b"), (12, "c"), (12, "d"), (14, "e"))
    ]
    report = validation.execution_activity(
        "\n".join(json.dumps(row) for row in records),
        {"a": "success", "b": "success", "c": "success", "d": "reverted"},
    )
    assert report["pairOutcomes"] == {"bothFilled": 1, "oneFilled": 1, "noneFilled": 1}
