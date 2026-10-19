import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents" / "eris-adaptive-v1"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Competition unit tests must not use the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def observation():
    return {
        "kind": "observation",
        "runId": "test-epoch",
        "round": 10,
        "blockNumber": "100",
        "agentAddress": "0x" + "1" * 40,
        "fairPriceUsdcPerWeth": 3000,
        "oraclePrices": {"wethUsd": 3000, "usdcUsd": 1},
        "enabledProtocols": ["uniswap", "balancer", "curve"],
        "balances": {"ethWei": "1000000000000000000", "wethWei": "0", "usdcUnits": "25000000000"},
        "inventory": {"valueUsdc": 28000, "weth": 0, "usdc": 25000, "eth": 1},
        "history": [
            {"round": index, "poolPriceUsdcPerWeth": 3000, "fairPriceUsdcPerWeth": 3000} for index in range(4, 10)
        ],
        "limits": {
            "defaultPriorityFeePerGasWei": "100000000",
            "maxPriorityFeePerGasWei": "5000000000",
            "defaultSlippageBps": 50,
        },
        "protocols": {
            "uniswap": {
                "positions": [],
                "pool": {
                    "pair": "WETH/USDC",
                    "fee": 3000,
                    "priceUsdcPerWeth": 2900,
                    "tick": 0,
                    "tickSpacing": 60,
                    "liquidity": "100000000000000000",
                },
            },
        },
        "blocksRemaining": 200,
    }


@pytest.fixture
def engine():
    import strategy

    strategy.state = strategy.State()
    return strategy


@pytest.fixture
def context():
    from eris import Context

    messages = []
    ctx = Context({"id": 1, "agentId": "eris-adaptive-v1", "address": "0x" + "1" * 40}, messages.append)
    ctx.messages = messages
    return ctx
