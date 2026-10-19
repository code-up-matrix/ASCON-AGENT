"""Reviewed strategy limits; amounts below are human USDC unless named units/wei.

These are conservative starting assumptions, not parameters fitted to an Eris run.
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
MAX_TRADE_USDC = Decimal(1000)
MIN_TRADE_USDC = Decimal(10)
MIN_EXPECTED_EDGE_USDC = Decimal(2)
CASH_RESERVE_BPS = 3000
MIN_CASH_RESERVE_USDC = Decimal(1000)
MAX_BASE_EXPOSURE_BPS = 3000
MAX_TOTAL_EXPOSURE_BPS = 5000
MAX_POOL_INPUT_BPS = 10
SLIPPAGE_BPS = 35
MAX_DRAWDOWN_BPS = Decimal(1000)
EXIT_BLOCKS = 8
DECISION_COOLDOWN_BLOCKS = 2
MIN_REVERT_SAMPLES = 5
REVERT_RATE_PAUSE = 0.5
MIN_GAS_WEI = 10**16
MAX_PRIORITY_FEE_WEI = 2 * 10**9
# Observations do not expose base fee or a size-specific gas quote. Keep these
# explicit and report costs as estimates; calibrate against settled tx receipts.
ASSUMED_BASE_FEE_WEI = 10**9
ASSUMED_SWAP_GAS = 350_000
