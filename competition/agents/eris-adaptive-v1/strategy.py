"""Bounded spot relative-value strategy for the official Eris Python runtime.

Inventory-funded spot actions and paired venue trades. A lagged reference is an
uncertain signal, not a redeemable price. Bundles are not atomic or risk-free.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import median

import constants as limits
from eris import Context, Observation, run
from eris.actions import balancer_swap, bundle, curve_swap, noop, swap
from eris.markets import AgentVenue, MarketView, market_views


@dataclass
class State:
    run_id: str = ""
    last_seen_block: int = -1
    last_action_block: int = -100
    high_water: Decimal = Decimal(0)
    recovery_until: int = -1


@dataclass(frozen=True)
class Candidate:
    market: MarketView
    venue: AgentVenue
    token_in: str
    amount: int
    notional: Decimal
    edge_bps: Decimal
    expected_net: Decimal


@dataclass(frozen=True)
class Pair:
    market: MarketView
    buy_venue: AgentVenue
    sell_venue: AgentVenue
    buy_amount: int
    sell_amount: int
    cash_in: Decimal
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


def balancer_depth(market: MarketView, venue: AgentVenue) -> tuple[Decimal, Decimal] | None:
    """Infer raw base/quote reserves from the pinned 50/50 pool's two probes.

    For fee multiplier f and a = probe*f/base_reserve, buy/sell =
    (1 + a*(1+f))/f**2. Quotes include fees already. Discount inferred
    depth and cap extrapolation; inconsistent quotes keep the probe-only path.
    """
    if venue.protocol != "balancer":
        return None
    buy, sell = quote_prices(venue)
    factor = 1 - limits.BALANCER_FEE_BPS / limits.BPS
    impact = (buy / sell * factor**2 - 1) / (1 + factor)
    if impact <= 0:
        return None
    base_reserve = limits.AMM_QUOTE_PROBE_BASE * factor / impact
    mid = sell * (1 + impact) / factor
    discount = Decimal(limits.BALANCER_DEPTH_DISCOUNT_BPS) / limits.BPS
    return (
        base_reserve * (10**market.base_decimals) * discount,
        base_reserve * mid * limits.USDC_SCALE * discount,
    )


def uniswap_reserve(obs: Observation, market: MarketView, venue: AgentVenue, token_in: str) -> Decimal:
    protocol = obs.protocols.uniswap
    quote = (
        protocol.pool
        if protocol and market.base == "WETH"
        else (protocol.markets or {}).get(f"{market.base}/USDC")
        if protocol
        else None
    )
    liquidity = getattr(quote, "liquidity", None)
    if liquidity is None:
        return Decimal(0)
    raw_sqrt_price = (number(venue.price) * limits.USDC_SCALE / (10**market.base_decimals)).sqrt()
    return (
        Decimal(units(liquidity)) * raw_sqrt_price
        if token_in == limits.QUOTE_ASSET
        else Decimal(units(liquidity)) / raw_sqrt_price
    )


def price_for_size(
    obs: Observation,
    market: MarketView,
    venue: AgentVenue,
    token_in: str,
    amount: int,
    price: Decimal,
) -> Decimal:
    """Charge estimated own-price impact in addition to fees in the quote."""
    extra = Decimal(0)
    if venue.protocol == "uniswap":
        reserve = uniswap_reserve(obs, market, venue, token_in)
        if reserve <= 0:
            raise ValueError("missing Uniswap liquidity")
        extra = Decimal(amount) * (1 - number(venue.fee_bps) / limits.BPS) / reserve
    elif venue.protocol == "balancer":
        depth = balancer_depth(market, venue)
        if depth is not None:
            reserve = depth[1] if token_in == limits.QUOTE_ASSET else depth[0]
            probe = limits.AMM_QUOTE_PROBE_BASE * (
                number(venue.sell_price) * limits.USDC_SCALE
                if token_in == limits.QUOTE_ASSET
                else 10**market.base_decimals
            )
            extra = max(Decimal(0), Decimal(amount) - probe) * (1 - limits.BALANCER_FEE_BPS / limits.BPS) / reserve
    return price * (1 + extra) if token_in == limits.QUOTE_ASSET else price / (1 + extra)


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
        reserve = uniswap_reserve(obs, market, venue, token_in)
    else:
        # Curve stays within its executable probe. For the pinned 50/50
        # Balancer pools, inverse quotes also bound a larger input by depth.
        # The quote->base probe spends the proceeds of the 0.1-base sell probe.
        if venue.sell_price is None or venue.buy_price is None:
            return 0
        probe_cap = (
            max(0, int(limits.AMM_QUOTE_PROBE_BASE * number(venue.sell_price) * limits.USDC_SCALE) - 1)
            if token_in == limits.QUOTE_ASSET
            else int(limits.AMM_QUOTE_PROBE_BASE * (10**market.base_decimals))
        )
        cap = probe_cap
        inferred = balancer_depth(market, venue)
        if inferred is not None:
            reserve = inferred[1] if token_in == limits.QUOTE_ASSET else inferred[0]
            cap = min(
                probe_cap * limits.BALANCER_MAX_PROBE_MULTIPLIER,
                max(0, int(reserve * limits.MAX_POOL_INPUT_BPS / limits.BPS)),
            )
        reserves = getattr(quote, "reserves", None)
        if reserves is None:
            return cap
        reserve = Decimal(units(reserves.usdc if token_in == limits.QUOTE_ASSET else reserves.weth))
        return min(cap, max(0, int(reserve * limits.MAX_POOL_INPUT_BPS / limits.BPS)))
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
    trade_cap: Decimal = limits.MAX_TRADE_USDC,
) -> tuple[int, Decimal]:
    base_scale = 10**market.base_decimals
    held = Decimal(units(market.base_balance_wei)) / base_scale * number(market.fair)
    budget = min(trade_cap, equity * size_bps / limits.BPS)
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
        budget = trade_cap if reduce_only else budget
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
    emergency_exit: bool = False,
    trade_cap: Decimal = limits.MAX_TRADE_USDC,
    rejected: dict[str, int] | None = None,
) -> list[Candidate]:
    result = []

    def reject(reason: str):
        if rejected is not None:
            rejected[reason] = rejected.get(reason, 0) + 1

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
                if not emergency_exit and edge <= margin + limits.SLIPPAGE_BPS:
                    reject("insufficient_price_edge")
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
                    trade_cap=trade_cap,
                )
                price = price_for_size(obs, market, venue, token_in, amount, price)
                if token_in != limits.QUOTE_ASSET:
                    notional = Decimal(amount) / (10**market.base_decimals) * price
                edge = (1 - fair / price if token_in != limits.QUOTE_ASSET else fair / price - 1) * limits.BPS
                net = notional * (edge - margin - limits.SLIPPAGE_BPS) / limits.BPS - gas_cost
                if amount == 0 or notional < limits.MIN_TRADE_USDC:
                    reject("inventory_cash_or_depth_limit")
                    continue
                if not emergency_exit and net < limits.MIN_EXPECTED_EDGE_USDC:
                    reject("insufficient_net_edge")
                    continue
                result.append(Candidate(market, venue, token_in, amount, notional, edge, net))
            except (ValueError, InvalidOperation, ZeroDivisionError):
                # A broken quote removes that venue, not all remaining usable venues.
                reject("invalid_venue_quote")
                continue
    return result


def paired_candidates(
    obs: Observation, markets: list[MarketView], *, equity: Decimal, exposure: Decimal,
    margin: Decimal, size_bps: int, gas_cost: Decimal,
) -> list[Pair]:
    """Find funded round trips without treating the reference as redeemable.

    A bundle is not atomic. Each leg must fit the current wallet, gas reserve
    and exposure limits on its own, including when the other leg fails.
    """
    result = []
    cushion = Decimal(limits.SLIPPAGE_BPS) / limits.BPS
    for market in markets:
        quoted = []
        for venue in market.venues:
            if venue.protocol not in obs.enabled_protocols or venue.protocol not in limits.ALLOWED_PROTOCOLS:
                continue
            try:
                buy, sell = quote_prices(venue)
                quoted.append((venue, buy, sell))
            except (ValueError, InvalidOperation, ZeroDivisionError):
                continue
        for buy_venue, buy, _ in quoted:
            for sell_venue, _, sell in quoted:
                if buy_venue.protocol == sell_venue.protocol or sell <= buy:
                    continue
                try:
                    buy_cap, _ = trade_size(
                        obs, market, buy_venue, token_in=limits.QUOTE_ASSET, price=buy,
                        size_bps=size_bps, equity=equity, exposure=exposure, reduce_only=False,
                    )
                    sell_cap, _ = trade_size(
                        obs, market, sell_venue, token_in=market.base, price=sell,
                        size_bps=size_bps, equity=equity, exposure=exposure, reduce_only=False,
                    )
                    if buy_cap <= 0 or sell_cap <= 0:
                        continue
                    # Use impact at the whole buy cap, a conservative estimate
                    # when the matched inventory forces a smaller purchase.
                    buy_price = price_for_size(obs, market, buy_venue, limits.QUOTE_ASSET, buy_cap, buy)
                    base_scale = 10**market.base_decimals
                    sell_amount = min(
                        sell_cap,
                        int(Decimal(buy_cap) / limits.USDC_SCALE / (buy_price * (1 + cushion)) * base_scale),
                    )
                    if sell_amount <= 0:
                        continue
                    base_quantity = Decimal(sell_amount) / base_scale
                    buy_amount = min(buy_cap, int(base_quantity * buy_price * (1 + cushion) * limits.USDC_SCALE) + 1)
                    cash_in = Decimal(buy_amount) / limits.USDC_SCALE
                    sell_price = price_for_size(obs, market, sell_venue, market.base, sell_amount, sell)
                    # Do not book the small leftover base as cash profit.
                    proceeds = base_quantity * sell_price * (1 - cushion)
                    net = proceeds - cash_in - 2 * gas_cost - cash_in * margin / limits.BPS
                    if cash_in < limits.MIN_TRADE_USDC or net < limits.MIN_EXPECTED_EDGE_USDC:
                        continue
                    result.append(Pair(market, buy_venue, sell_venue, buy_amount, sell_amount, cash_in, net))
                except (ValueError, InvalidOperation, ZeroDivisionError):
                    continue
    return result


def pair_action(pair: Pair, priority: int):
    constructors = {"uniswap": swap, "balancer": balancer_swap, "curve": curve_swap}
    actions = [
        constructors[pair.buy_venue.protocol](
            token_in=limits.QUOTE_ASSET, base=pair.market.base, amount_in=str(pair.buy_amount),
            slippage_bps=limits.SLIPPAGE_BPS, max_priority_fee_per_gas_wei=str(priority),
        ),
        constructors[pair.sell_venue.protocol](
            token_in=pair.market.base, base=pair.market.base, amount_in=str(pair.sell_amount),
            slippage_bps=limits.SLIPPAGE_BPS, max_priority_fee_per_gas_wei=str(priority),
        ),
    ]
    return bundle(actions=actions, max_priority_fee_per_gas_wei=str(priority))


def wait(ctx: Context, reason: str, **details):
    ctx.log({"marker": "ASCON_DECISION", "decision": "noop", "reason": reason, **details})
    return noop(reason=reason)


def priority_bid(obs: Observation) -> int:
    """Use the observed auction without chasing unbounded system/oracle bids."""
    default = units(obs.limits.default_priority_fee_per_gas_wei)
    observed = units(obs.competition.max_competitor_priority_fee_wei) if obs.competition else 0
    return min(
        max(default, observed + 1),
        default * limits.PRIORITY_MULTIPLIER,
        units(obs.limits.max_priority_fee_per_gas_wei),
        limits.MAX_PRIORITY_FEE_WEI,
    )


def decide_valid(obs: Observation, ctx: Context):
    block = units(obs.block_number)
    if state.run_id != obs.run_id:
        state.run_id = obs.run_id
        state.last_seen_block = -1
        state.last_action_block = -limits.DECISION_COOLDOWN_BLOCKS
        state.high_water = Decimal(0)
        state.recovery_until = -1
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
    emergency_exit = drawdown >= limits.MAX_DRAWDOWN_BPS
    reduce_only = ending or emergency_exit
    recovering = bool(
        obs.competition is not None
        and obs.competition.recent_sample_size >= limits.MIN_REVERT_SAMPLES
        and obs.competition.recent_revert_rate >= limits.REVERT_RATE_PAUSE
    )
    # The SDK's outcome ring does not age out while idle. An indefinite pause
    # therefore cannot recover. Wait, then permit one small funded probe.
    if recovering:
        if state.recovery_until < 0:
            state.recovery_until = block + limits.EXECUTION_RECOVERY_BLOCKS
        if block < state.recovery_until and not emergency_exit:
            return wait(ctx, "recent_execution_failures", resume_block=state.recovery_until)
    else:
        state.recovery_until = -1
    if block - state.last_action_block < limits.DECISION_COOLDOWN_BLOCKS:
        return wait(ctx, "settlement_cooldown")
    name, margin, size_bps = regime(obs)
    priority = priority_bid(obs)
    gas_wei = limits.ASSUMED_SWAP_GAS * (limits.ASSUMED_BASE_FEE_WEI + priority)
    if units(obs.balances.eth_wei) < limits.MIN_GAS_WEI + gas_wei:
        return wait(ctx, "gas_reserve_after_estimated_cost")
    gas_cost = Decimal(gas_wei) / limits.WEI_SCALE * fair
    markets = selected_markets(obs)
    if (
        limits.ENABLE_PAIRED_TRADES
        and not reduce_only
        and not recovering
        and units(obs.balances.eth_wei) >= limits.MIN_GAS_WEI + 2 * gas_wei
    ):
        pairs = paired_candidates(
            obs, markets, equity=equity, exposure=exposure,
            margin=margin, size_bps=size_bps, gas_cost=gas_cost,
        )
        if pairs:
            pair = max(pairs, key=lambda item: item.expected_net)
            ctx.log({
                "marker": "ASCON_DECISION", "decision": "bundle",
                "reason": "cross_venue_pair", "regime": name, "block": block,
                "base": pair.market.base, "buy_venue": pair.buy_venue.protocol,
                "sell_venue": pair.sell_venue.protocol,
                "buy_amount_in": str(pair.buy_amount), "sell_amount_in": str(pair.sell_amount),
                "notional_usdc": str(pair.cash_in), "estimated_net_edge_usdc": str(pair.expected_net),
                "estimated_gas_usdc": str(2 * gas_cost), "priority_fee_wei": str(priority),
                "both_legs_prefunded": True, "atomic": False,
            })
            state.last_action_block = block
            return pair_action(pair, priority)
    rejected: dict[str, int] = {}
    choices = candidates(
        obs,
        markets,
        equity=equity,
        exposure=exposure,
        margin=margin,
        size_bps=size_bps,
        gas_cost=gas_cost,
        reduce_only=reduce_only,
        emergency_exit=emergency_exit,
        trade_cap=limits.RECOVERY_TRADE_USDC if recovering else limits.MAX_TRADE_USDC,
        rejected=rejected,
    )
    if not choices:
        return wait(
            ctx,
            "no_fundable_exit" if reduce_only else "no_net_edge",
            regime=name,
            reduce_only=reduce_only,
            rejected=rejected,
        )
    # Forced risk reduction compares proceeds per unit of fair value, not
    # almost-equal rounded notionals that can select the worst-priced venue.
    best = max(choices, key=lambda item: item.edge_bps if emergency_exit else item.expected_net)
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
            "block": block,
            "fair_price": str(best.market.fair),
            "edge_bps": str(best.edge_bps),
            "spot_equity_usdc": str(equity),
            "exposure_usdc": str(exposure),
            "recovering": recovering,
            "priority_fee_wei": str(priority),
            "reduce_only": reduce_only,
            "reason": "epoch_exit" if ending else "drawdown_exit" if reduce_only else "relative_value",
        }
    )
    state.last_action_block = block
    if recovering:
        state.recovery_until = block + limits.EXECUTION_RECOVERY_BLOCKS
    return action


def decide(obs: Observation, ctx: Context):
    try:
        return decide_valid(obs, ctx)
    except (ValueError, InvalidOperation, ZeroDivisionError, OverflowError):
        return wait(ctx, "invalid_observation")


if __name__ == "__main__":
    run(decide)
