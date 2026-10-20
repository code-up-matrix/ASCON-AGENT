"""Reviewed strategy limits; amounts below are human USDC unless named units/wei.

Limits follow the pinned SDK and are reviewed with frozen market comparisons.
The official runtime keeps this module on PYTHONPATH when replacing strategy.py.
"""

from decimal import Decimal

BPS = Decimal(10_000)
USDC_SCALE = 10**6
WEI_SCALE = 10**18
QUOTE_ASSET = "USDC"
ALLOWED_BASES = ("WETH", "WBTC")
ALLOWED_PROTOCOLS = ("uniswap", "balancer", "curve")
MAX_MARKETS = 2
HISTORY_WINDOW = 24
MIN_HISTORY = 4
VOLATILE_MOVE_BPS = Decimal(40)
SHOCK_MOVE_BPS = Decimal(150)
MAX_QUOTE_SPREAD_BPS = Decimal(500)
CALM_MARGIN_BPS = Decimal(25)
VOLATILE_MARGIN_BPS = Decimal(75)
SHOCK_MARGIN_BPS = Decimal(150)
CALM_SIZE_BPS = 500
VOLATILE_SIZE_BPS = 250
SHOCK_SIZE_BPS = 100
MAX_TRADE_USDC = Decimal(3000)
MIN_TRADE_USDC = Decimal(10)
MIN_EXPECTED_EDGE_USDC = Decimal(2)
CASH_RESERVE_BPS = 2000
MIN_CASH_RESERVE_USDC = Decimal(1000)
# The official 8 WETH / 0.4 WBTC / 25k USDC endowment starts around
# 33% per base and 66% total. Limits below that prevent buying either base.
MAX_BASE_EXPOSURE_BPS = 5000
MAX_TOTAL_EXPOSURE_BPS = 8000
MAX_POOL_INPUT_BPS = 10
# Pinned Eris Balancer/Curve adapters quote 0.1 base units, then quote the
# resulting USDC back into base. Their observations currently omit reserves.
AMM_QUOTE_PROBE_BASE = Decimal("0.1")
# Pinned deployer/src/protocols/balancer-v2.ts: 50/50 weights, 30 bps fee.
# The inverse quote model is specific to these official pools, not discovered pools.
BALANCER_FEE_BPS = Decimal(30)
BALANCER_DEPTH_DISCOUNT_BPS = 9000
BALANCER_MAX_PROBE_MULTIPLIER = 10
SLIPPAGE_BPS = 35
MAX_DRAWDOWN_BPS = Decimal(1000)
EXIT_BLOCKS = 8
DECISION_COOLDOWN_BLOCKS = 2
MIN_REVERT_SAMPLES = 5
REVERT_RATE_PAUSE = 0.5
EXECUTION_RECOVERY_BLOCKS = 12
RECOVERY_TRADE_USDC = Decimal(100)
MIN_GAS_WEI = 10**16
MAX_PRIORITY_FEE_WEI = 2 * 10**9
PRIORITY_MULTIPLIER = 3
# Observations do not expose base fee or a size-specific gas quote. Keep these
# explicit and report costs as estimates; calibrate against settled tx receipts.
ASSUMED_BASE_FEE_WEI = 10**9
ASSUMED_SWAP_GAS = 350_000

ENABLE_PAIRED_TRADES = True
ALLOW_DIRECTIONAL_TRADES = False
