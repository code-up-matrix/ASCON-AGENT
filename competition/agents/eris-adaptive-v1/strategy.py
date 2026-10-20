"""Bounded spot relative-value strategy for the official Eris Python runtime.

One inventory-funded action at a time. A lagged reference is an uncertain signal,
not a redeemable price; this is not atomic or risk-free cross-venue arbitrage.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import median

import constants as limits
from eris import Context, Observation, run
from eris.actions import balancer_swap, curve_swap, noop, swap
from eris.markets import AgentVenue, MarketView, market_views


@dataclass
class State:
    run_id: str = ""
    last_seen_block: int = -1
    last_action_block: int = -100
    high_water: Decimal = Decimal(0)


@dataclass(frozen=True)
class Candidate:
    market: MarketView
    venue: AgentVenue
    token_in: str
    amount: int
    notional: Decimal
    edge_bps: Decimal
    expected_net: Decimal


state = State()


def number(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non-finite market data")
    return result


def units(value: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ValueError("invalid unsigned token units")
    return int(value)


def regime(obs: Observation) -> tuple[str, Decimal, int]:
    """Infer recent WETH movement from past/current public observations only."""
    history = [number(row.fair_price_usdc_per_weth) for row in obs.history[-limits.HISTORY_WINDOW :]]
    history.append(number(obs.fair_price_usdc_per_weth))
    if any(price <= 0 for price in history):
        raise ValueError("invalid history price")
    if len(history) < limits.MIN_HISTORY:
        return "warming_up", limits.VOLATILE_MARGIN_BPS, limits.VOLATILE_SIZE_BPS
    moves = [abs(after / before - 1) * limits.BPS for before, after in zip(history, history[1:], strict=False)]
    if max(moves) >= limits.SHOCK_MOVE_BPS:
        return "shock", limits.SHOCK_MARGIN_BPS, limits.SHOCK_SIZE_BPS
    if median(moves) >= limits.VOLATILE_MOVE_BPS:
        return "volatile", limits.VOLATILE_MARGIN_BPS, limits.VOLATILE_SIZE_BPS
    return "calm", limits.CALM_MARGIN_BPS, limits.CALM_SIZE_BPS


def selected_markets(obs: Observation) -> list[MarketView]:
    result = []
    for market in market_views(obs):
        if market.base not in limits.ALLOWED_BASES:
            continue
        if market.base_decimals != (18 if market.base == "WETH" else 8):
            raise ValueError("unsupported token decimals")
        if number(market.fair) <= 0:
            raise ValueError("invalid reference price")
        units(market.base_balance_wei)
        result.append(market)
    return result[: limits.MAX_MARKETS]


def portfolio(obs: Observation) -> tuple[Decimal, Decimal]:
    """Value all supported spot inventory, even when a venue is unavailable."""
    cash = Decimal(units(obs.balances.usdc_units)) / limits.USDC_SCALE
    exposure = Decimal(units(obs.balances.weth_wei)) / limits.WEI_SCALE * number(obs.fair_price_usdc_per_weth)
    for base, balance in (obs.base_balances or {}).items():
        if base == "WETH" or units(balance) == 0:
            continue
        price = (obs.fair_prices_usd or {}).get(base)
        decimals = (obs.base_decimals or {}).get(base)
        if base not in limits.ALLOWED_BASES or price is None or decimals != 8:
            raise ValueError("cannot value existing base inventory")
        mark = number(price)
        if mark <= 0:
            raise ValueError("invalid inventory reference price")
        exposure += Decimal(units(balance)) / (10 ** int(decimals)) * mark
    if exposure < 0:
        raise ValueError("negative inventory valuation")
    return cash + exposure, exposure


def quote_prices(venue: AgentVenue) -> tuple[Decimal, Decimal]:
    """Two-sided quotes already include fees; never subtract those fees twice."""
    mid, fee = number(venue.price), number(venue.fee_bps)
    if mid <= 0 or not 0 <= fee <= limits.MAX_QUOTE_SPREAD_BPS:
        raise ValueError("invalid venue fee/price")
    if venue.buy_price is not None and venue.sell_price is not None:
        buy, sell = number(venue.buy_price), number(venue.sell_price)
    elif venue.protocol == "uniswap":
        buy, sell = mid / (1 - fee / limits.BPS), mid * (1 - fee / limits.BPS)
    else:
        # Legacy Balancer/Curve mids lack reliable execution costs under imbalance.
        raise ValueError("missing executable two-sided quote")
    if not 0 < sell <= buy or (buy / sell - 1) * limits.BPS > limits.MAX_QUOTE_SPREAD_BPS:
        raise ValueError("invalid or overly wide venue quote")
    return buy, sell


def depth_cap(obs: Observation, market: MarketView, venue: AgentVenue, token_in: str) -> int:
    """Bound input by visible depth or the pinned adapter's executable probe."""
    protocol = getattr(obs.protocols, venue.protocol)
    if protocol is None:
        return 0
    quote = (
        (protocol.pool if venue.protocol == "uniswap" else protocol)
        if market.base == "WETH"
        else (protocol.markets or {}).get(f"{market.base}/USDC")
    )
    if quote is None:
        return 0
    if venue.protocol == "uniswap":
        liquidity = getattr(quote, "liquidity", None)
        if liquidity is None:
            return 0
        raw_sqrt_price = (number(venue.price) * limits.USDC_SCALE / (10**market.base_decimals)).sqrt()
        reserve = (
            Decimal(units(liquidity)) * raw_sqrt_price
            if token_in == limits.QUOTE_ASSET
            else (Decimal(units(liquidity)) / raw_sqrt_price)
        )
    else:
        # Balancer/Curve observe() supplies executable quotes but no reserves.
        # Stay within the amount actually probed, even when reserves are supplied.
        # The quote->base probe spends the proceeds of the 0.1-base sell probe.
        if venue.sell_price is None or venue.buy_price is None:
            return 0
        probe_cap = (
            max(0, int(limits.AMM_QUOTE_PROBE_BASE * number(venue.sell_price) * limits.USDC_SCALE) - 1)
            if token_in == limits.QUOTE_ASSET
            else int(limits.AMM_QUOTE_PROBE_BASE * (10**market.base_decimals))
        )
        reserves = getattr(quote, "reserves", None)
        if reserves is None:
            return probe_cap
        reserve = Decimal(units(reserves.usdc if token_in == limits.QUOTE_ASSET else reserves.weth))
        return min(probe_cap, max(0, int(reserve * limits.MAX_POOL_INPUT_BPS / limits.BPS)))
    return max(0, int(reserve * limits.MAX_POOL_INPUT_BPS / limits.BPS))


def trade_size(
    obs: Observation,
    market: MarketView,
    venue: AgentVenue,
    *,
    token_in: str,
    price: Decimal,
    size_bps: int,
    equity: Decimal,
    exposure: Decimal,
    reduce_only: bool,
) -> tuple[int, Decimal]:
    base_scale = 10**market.base_decimals
    held = Decimal(units(market.base_balance_wei)) / base_scale * number(market.fair)
    budget = min(limits.MAX_TRADE_USDC, equity * size_bps / limits.BPS)
    if token_in == limits.QUOTE_ASSET:
        reserve = max(limits.MIN_CASH_RESERVE_USDC, equity * limits.CASH_RESERVE_BPS / limits.BPS)
        cash = Decimal(units(obs.balances.usdc_units)) / limits.USDC_SCALE
        # Exposure caps use the conservative fair-value amount received, not cost.
        room = min(
            equity * limits.MAX_BASE_EXPOSURE_BPS / limits.BPS - held,
            equity * limits.MAX_TOTAL_EXPOSURE_BPS / limits.BPS - exposure,
        )
        budget = min(budget, cash - reserve, room * price / number(market.fair))
        amount = max(0, int(budget * limits.USDC_SCALE))
        scale = Decimal(limits.USDC_SCALE)
        unit_value = Decimal(1)
    else:
        # Exits can use the full per-trade cap, still constrained by depth and inventory.
        budget = limits.MAX_TRADE_USDC if reduce_only else budget
        amount = min(units(market.base_balance_wei), max(0, int(budget / price * base_scale)))
        scale = Decimal(base_scale)
        unit_value = price
    amount = min(amount, depth_cap(obs, market, venue, token_in))
    return amount, Decimal(amount) / scale * unit_value


def candidates(
    obs: Observation,
    markets: list[MarketView],
    *,
    equity: Decimal,
    exposure: Decimal,
    margin: Decimal,
    size_bps: int,
    gas_cost: Decimal,
    reduce_only: bool,
) -> list[Candidate]:
    result = []
    for market in markets:
        for venue in market.venues:
            if venue.protocol not in obs.enabled_protocols or venue.protocol not in limits.ALLOWED_PROTOCOLS:
                continue
            try:
                buy, sell = quote_prices(venue)
                fair = number(market.fair)
                token_in = market.base if reduce_only or sell > fair else limits.QUOTE_ASSET
                price = sell if token_in != limits.QUOTE_ASSET else buy
                edge = (1 - fair / sell if token_in != limits.QUOTE_ASSET else fair / buy - 1) * limits.BPS
                if not reduce_only and edge <= margin + limits.SLIPPAGE_BPS:
                    continue
                amount, notional = trade_size(
                    obs,
                    market,
                    venue,
                    token_in=token_in,
                    price=price,
                    size_bps=size_bps,
                    equity=equity,
                    exposure=exposure,
                    reduce_only=reduce_only,
                )
                net = notional * (edge - margin - limits.SLIPPAGE_BPS) / limits.BPS - gas_cost
                if amount == 0 or notional < limits.MIN_TRADE_USDC:
                    continue
                if not reduce_only and net < limits.MIN_EXPECTED_EDGE_USDC:
                    continue
                result.append(Candidate(market, venue, token_in, amount, notional, edge, net))
            except (ValueError, InvalidOperation, ZeroDivisionError):
                # A broken quote removes that venue, not all remaining usable venues.
                continue
    return result


def wait(ctx: Context, reason: str, **details):
    ctx.log({"marker": "ASCON_DECISION", "decision": "noop", "reason": reason, **details})
    return noop(reason=reason)


def decide_valid(obs: Observation, ctx: Context):
    block = units(obs.block_number)
    if state.run_id != obs.run_id:
        state.run_id = obs.run_id
        state.last_seen_block = -1
        state.last_action_block = -limits.DECISION_COOLDOWN_BLOCKS
        state.high_water = Decimal(0)
    if block <= state.last_seen_block:
        return wait(ctx, "duplicate_or_stale_observation")
    state.last_seen_block = block
    fair = number(obs.fair_price_usdc_per_weth)
    if fair <= 0:
        return wait(ctx, "invalid_reference_price")
    if units(obs.balances.eth_wei) < limits.MIN_GAS_WEI:
        return wait(ctx, "gas_reserve")
    equity, exposure = portfolio(obs)
    if equity <= 0:
        return wait(ctx, "no_spot_capital")
    state.high_water = max(state.high_water, equity)
    drawdown = (1 - equity / state.high_water) * limits.BPS
    ending = obs.blocks_remaining is not None and number(obs.blocks_remaining) <= limits.EXIT_BLOCKS
    reduce_only = ending or drawdown >= limits.MAX_DRAWDOWN_BPS
    if obs.competition is not None and not reduce_only:
        if (
            obs.competition.recent_sample_size >= limits.MIN_REVERT_SAMPLES
            and obs.competition.recent_revert_rate >= limits.REVERT_RATE_PAUSE
        ):
            return wait(ctx, "recent_execution_failures")
    if block - state.last_action_block < limits.DECISION_COOLDOWN_BLOCKS:
        return wait(ctx, "settlement_cooldown")
    name, margin, size_bps = regime(obs)
    priority = min(
        units(obs.limits.default_priority_fee_per_gas_wei),
        units(obs.limits.max_priority_fee_per_gas_wei),
        limits.MAX_PRIORITY_FEE_WEI,
    )
    gas_wei = limits.ASSUMED_SWAP_GAS * (limits.ASSUMED_BASE_FEE_WEI + priority)
    if units(obs.balances.eth_wei) < limits.MIN_GAS_WEI + gas_wei:
        return wait(ctx, "gas_reserve_after_estimated_cost")
    gas_cost = Decimal(gas_wei) / limits.WEI_SCALE * fair
    choices = candidates(
        obs,
        selected_markets(obs),
        equity=equity,
        exposure=exposure,
        margin=margin,
        size_bps=size_bps,
        gas_cost=gas_cost,
        reduce_only=reduce_only,
    )
    if not choices:
        return wait(ctx, "no_fundable_exit" if reduce_only else "no_net_edge", regime=name, reduce_only=reduce_only)
    # For exits maximize value realized; otherwise compare estimated absolute net edge.
    best = max(choices, key=lambda item: item.notional if reduce_only else item.expected_net)
    constructor = {"uniswap": swap, "balancer": balancer_swap, "curve": curve_swap}[best.venue.protocol]
    action = constructor(
        token_in=best.token_in,
        base=best.market.base,
        amount_in=str(best.amount),
        slippage_bps=limits.SLIPPAGE_BPS,
        max_priority_fee_per_gas_wei=str(priority),
    )
    ctx.log(
        {
            "marker": "ASCON_DECISION",
            "decision": "swap",
            "regime": name,
            "venue": best.venue.protocol,
            "base": best.market.base,
            "token_in": best.token_in,
            "amount_in": str(best.amount),
            "notional_usdc": str(best.notional),
            "estimated_net_edge_usdc": str(best.expected_net),
            "estimated_gas_usdc": str(gas_cost),
            "drawdown_bps": str(drawdown),
            "reduce_only": reduce_only,
            "reason": "epoch_exit" if ending else "drawdown_exit" if reduce_only else "relative_value",
        }
    )
    state.last_action_block = block
    return action


def decide(obs: Observation, ctx: Context):
    try:
        return decide_valid(obs, ctx)
    except (ValueError, InvalidOperation, ZeroDivisionError, OverflowError):
        return wait(ctx, "invalid_observation")


if __name__ == "__main__":
    run(decide)
