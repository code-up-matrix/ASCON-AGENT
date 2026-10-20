"""A zero backtester exit must not conceal missing execution or resource evidence."""

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
