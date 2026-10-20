import json
import os
import subprocess
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from eris import Action, Observation
from eris.markets import AgentVenue
from pydantic import TypeAdapter


def decide(engine, observation, context):
    action = engine.decide(Observation.model_validate(observation), context)
    wire = action.model_dump(by_alias=True, exclude_none=True)
    TypeAdapter(Action).validate_python(wire)
    return wire


def add_balancer(observation, *, buy=2840, sell=2830):
    observation["protocols"]["balancer"] = {
        "priceUsdcPerWeth": (buy + sell) / 2,
        "buyPriceUsdcPerWeth": buy,
        "sellPriceUsdcPerWeth": sell,
        "effectiveHalfSpreadBps": 18,
    }


def test_buy_uses_official_wire_schema_and_bounded_cash(engine, observation, context):
    action = decide(engine, observation, context)
    assert action["type"] == "swap"
    assert action["tokenIn"] == "USDC"
    assert 0 < int(action["amountIn"]) <= 1_000_000_000
    assert int(observation["balances"]["usdcUnits"]) - int(action["amountIn"]) >= 7_500_000_000
    assert action["slippageBps"] == 35


def test_fee_band_means_no_trade(engine, observation, context):
    observation["protocols"]["uniswap"]["pool"]["priceUsdcPerWeth"] = 2995
    assert decide(engine, observation, context)["type"] == "noop"


def test_best_net_executable_venue_wins(engine, observation, context):
    add_balancer(observation, buy=2700, sell=2690)
    assert decide(engine, observation, context)["type"] == "balancerSwap"


@pytest.mark.parametrize("protocol,action_type", [("balancer", "balancerSwap"), ("curve", "curveSwap")])
@pytest.mark.parametrize("base,decimals,fair", [("WETH", 18, 3000), ("WBTC", 8, 60000)])
@pytest.mark.parametrize("buy_base", [True, False])
def test_real_amm_shape_without_reserves_trades_within_quote_probe(
    engine, observation, context, protocol, action_type, base, decimals, fair, buy_base
):
    sell = fair * (Decimal("0.9") if buy_base else Decimal("1.1"))
    quote = {
        "priceUsdcPerWeth": float(sell + 5),
        "buyPriceUsdcPerWeth": float(sell + 10),
        "sellPriceUsdcPerWeth": float(sell),
        "effectiveHalfSpreadBps": 20,
    }
    observation["fairPricesUsd"] = {"WETH": 3000, base: fair}
    observation["baseDecimals"] = {"WETH": 18, base: decimals}
    held = "0" if buy_base else str(10**decimals)
    if base == "WETH":
        observation["balances"]["wethWei"] = held
        observation["protocols"] = {protocol: quote}
    else:
        observation["baseBalances"] = {base: held}
        observation["protocols"] = {protocol: {"priceUsdcPerWeth": 3000, "markets": {f"{base}/USDC": quote}}}
    action = decide(engine, observation, context)
    assert action["type"] == action_type
    assert action["base"] == base
    assert action["tokenIn"] == ("USDC" if buy_base else base)
    probe_cap = Decimal("0.1") * (sell * 10**6 if buy_base else 10**decimals)
    assert 0 < int(action["amountIn"]) <= probe_cap


@pytest.mark.parametrize("protocol", ["balancer", "curve"])
def test_explicit_empty_reserves_still_prevent_trade(engine, observation, context, protocol):
    add_balancer(observation, buy=2700, sell=2690)
    quote = observation["protocols"]["balancer"]
    quote["reserves"] = {"weth": "0", "usdc": "0"}
    observation["protocols"] = {protocol: quote}
    assert decide(engine, observation, context)["type"] == "noop"


def test_two_sided_quote_does_not_pay_fee_twice(engine):
    venue = AgentVenue("balancer", "balancerSwap", 3000, 100, 2970, 3030)
    assert engine.quote_prices(venue) == (Decimal(3030), Decimal(2970))


def test_unpriced_legacy_amm_is_not_a_free_edge(engine, observation, context):
    observation["protocols"] = {"balancer": {"priceUsdcPerWeth": 2500}}
    assert decide(engine, observation, context)["type"] == "noop"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0, -1])
def test_invalid_reference_fails_closed(engine, observation, context, bad):
    observation["fairPriceUsdcPerWeth"] = bad
    assert decide(engine, observation, context)["type"] == "noop"


def test_invalid_venue_does_not_hide_valid_venue(engine, observation, context):
    add_balancer(observation)
    observation["protocols"]["balancer"]["buyPriceUsdcPerWeth"] = float("nan")
    assert decide(engine, observation, context)["type"] == "swap"


def test_tiny_depth_has_no_trade(engine, observation, context):
    observation["protocols"]["uniswap"]["pool"]["liquidity"] = "1"
    assert decide(engine, observation, context)["type"] == "noop"


@pytest.mark.parametrize("cash", ["0", "100000000", "1000000000"])
def test_cash_reserve_prevents_buy(engine, observation, context, cash):
    observation["balances"]["usdcUnits"] = cash
    assert decide(engine, observation, context)["type"] == "noop"


def test_gas_reserve_prevents_trade(engine, observation, context):
    observation["balances"]["ethWei"] = "9999999999999999"
    assert decide(engine, observation, context)["reason"] == "gas_reserve"


def test_exposure_cap_prevents_adding_to_large_position(engine, observation, context):
    observation["balances"]["wethWei"] = "10000000000000000000"
    assert decide(engine, observation, context)["type"] == "noop"


def test_no_borrowing_to_sell(engine, observation, context):
    observation["protocols"]["uniswap"]["pool"]["priceUsdcPerWeth"] = 3200
    assert decide(engine, observation, context)["type"] == "noop"


def test_sell_preserves_integer_precision_and_inventory(engine, observation, context):
    balance = "123456789012345678"
    observation["balances"]["wethWei"] = balance
    observation["protocols"]["uniswap"]["pool"]["priceUsdcPerWeth"] = 3200
    action = decide(engine, observation, context)
    assert action["tokenIn"] == "WETH"
    assert action["amountIn"] == balance


def test_shock_shrinks_position(engine, observation, context):
    calm = decide(engine, observation, context)
    engine.state = engine.State()
    observation["history"][-1]["fairPriceUsdcPerWeth"] = 2800
    shock = decide(engine, observation, context)
    assert shock["type"] == "swap"
    assert int(shock["amountIn"]) < int(calm["amountIn"])


def test_end_of_epoch_does_not_open_position(engine, observation, context):
    observation["blocksRemaining"] = 4
    assert decide(engine, observation, context)["type"] == "noop"


def test_end_of_epoch_exits_without_profitable_edge(engine, observation, context):
    observation["blocksRemaining"] = 4
    observation["balances"]["wethWei"] = "1000000000000000000"
    action = decide(engine, observation, context)
    assert action["tokenIn"] == "WETH"
    assert context.messages[-1]["log"]["reason"] == "epoch_exit"


def test_drawdown_only_reduces_exposure(engine, observation, context):
    engine.state.run_id = observation["runId"]
    engine.state.high_water = Decimal(40000)
    observation["balances"]["wethWei"] = "1000000000000000000"
    action = decide(engine, observation, context)
    assert action["tokenIn"] == "WETH"
    assert context.messages[-1]["log"]["reason"] == "drawdown_exit"


def test_duplicate_and_older_observations_are_rejected(engine, observation, context):
    assert decide(engine, observation, context)["type"] == "swap"
    assert decide(engine, observation, context)["reason"] == "duplicate_or_stale_observation"
    observation["blockNumber"] = "99"
    assert decide(engine, observation, context)["reason"] == "duplicate_or_stale_observation"


def test_new_epoch_resets_local_state(engine, observation, context):
    assert decide(engine, observation, context)["type"] == "swap"
    observation["runId"] = "next-epoch"
    observation["blockNumber"] = "1"
    assert decide(engine, observation, context)["type"] == "swap"


def test_settlement_cooldown(engine, observation, context):
    decide(engine, observation, context)
    observation["blockNumber"] = "101"
    assert decide(engine, observation, context)["reason"] == "settlement_cooldown"


def test_repeated_execution_failures_pause_entries(engine, observation, context):
    observation["competition"] = {
        "maxCompetitorPriorityFeeWei": "0",
        "maxBlockPriorityFeeWei": "0",
        "lastTxIndex": None,
        "recentRevertRate": 0.8,
        "recentSampleSize": 10,
    }
    assert decide(engine, observation, context)["reason"] == "recent_execution_failures"


def test_wbtc_uses_eight_decimals(engine, observation, context):
    observation["fairPricesUsd"] = {"WETH": 3000, "WBTC": 60000}
    observation["baseDecimals"] = {"WBTC": 8}
    observation["baseBalances"] = {"WBTC": "1234567"}
    observation["protocols"]["uniswap"]["pool"]["priceUsdcPerWeth"] = 3000
    observation["protocols"]["uniswap"]["markets"] = {
        "WBTC/USDC": {
            "pair": "WBTC/USDC",
            "fee": 3000,
            "priceUsdcPerWeth": 64000,
            "tick": 0,
            "tickSpacing": 60,
            "liquidity": "1000000000000000",
        },
    }
    action = decide(engine, observation, context)
    assert action["base"] == "WBTC"
    assert action["tokenIn"] == "WBTC"
    assert action["amountIn"] == "1234567"


def test_unavailable_wbtc_venue_still_counts_towards_total_exposure(engine, observation, context):
    observation["fairPricesUsd"] = {"WETH": 3000, "WBTC": 60000}
    observation["baseDecimals"] = {"WBTC": 8}
    observation["baseBalances"] = {"WBTC": "100000000"}
    assert decide(engine, observation, context)["type"] == "noop"


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_invalid_held_wbtc_mark_cannot_create_exposure_room(engine, observation, context, bad):
    observation["fairPricesUsd"] = {"WETH": 3000, "WBTC": bad}
    observation["baseDecimals"] = {"WBTC": 8}
    observation["baseBalances"] = {"WBTC": "100000000"}
    assert decide(engine, observation, context)["reason"] == "invalid_observation"


def test_decisions_repeat_for_identical_inputs(engine, observation, context):
    one = decide(engine, deepcopy(observation), context)
    engine.state = engine.State()
    assert decide(engine, deepcopy(observation), context) == one


def test_resident_jsonl_process_and_imports_survive_two_requests(observation):
    strategy = Path(__file__).resolve().parents[1] / "agents" / "eris-adaptive-v1" / "strategy.py"
    requests = [
        {
            "id": index,
            "obs": deepcopy(observation),
            "agentId": "eris-adaptive-v1",
            "address": observation["agentAddress"],
        }
        for index in (1, 2)
    ]
    requests[1]["obs"]["blockNumber"] = "102"
    clean_env = {
        key: value for key, value in os.environ.items() if not key.endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD"))
    }
    process = subprocess.run(
        [sys.executable, "-u", str(strategy)],
        input="".join(json.dumps(row) + "\n" for row in requests),
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
        env=clean_env,
    )
    frames = [json.loads(line) for line in process.stdout.splitlines()]
    responses = [frame for frame in frames if "action" in frame]
    assert [frame["id"] for frame in responses] == [1, 2]
    for response in responses:
        TypeAdapter(Action).validate_python(response["action"])
        assert response["action"]["type"] == "swap"
